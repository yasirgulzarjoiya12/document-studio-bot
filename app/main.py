from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from .config import Config
from .database import Database
from .health import HealthServer
from .utils.logging import setup_logging

log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    from .handlers.callbacks import on_complete, on_failed, on_progress
    from .services.cleanup import CleanupService
    from .services.job_manager import JobManager
    from .services.rate_limit import RateLimiter

    config: Config = application.bot_data["config"]
    db: Database = application.bot_data["db"]
    await db.connect()

    health: HealthServer | None = application.bot_data.get("health")
    if health is not None:
        health.attach_db(db)

    cleanup = CleanupService(config, db)
    cleanup.start()
    application.bot_data["cleanup"] = cleanup

    manager = JobManager(config, db)
    application.bot_data["job_manager"] = manager
    application.bot_data["rate_limiter"] = RateLimiter(
        config.rate_limit, config.rate_window_seconds
    )

    on_progress.app = application
    on_complete.app = application
    on_failed.app = application
    manager.on_progress = on_progress
    manager.on_complete = on_complete
    manager.on_failed = on_failed

    log.info("Application initialized")


async def post_shutdown(application: Application) -> None:
    manager = application.bot_data.get("job_manager")
    if manager:
        await manager.shutdown()
    cleanup = application.bot_data.get("cleanup")
    if cleanup:
        await cleanup.stop()
    health = application.bot_data.get("health")
    if health:
        await health.stop()
    db: Database | None = application.bot_data.get("db")
    if db:
        await db.close()
    log.info("Application shutdown complete")


def build_application(config: Config) -> Application:
    from .handlers.admin import admin, broadcast, jobs, maintenance, queue, stats, users
    from .handlers.callbacks import callback_router
    from .handlers.errors import error_handler
    from .handlers.files import receive_document, receive_photo, receive_text
    from .handlers.misc import about, cancel, history, privacy, report, settings, status, terms
    from .handlers.start import help_command, menu, start

    db = Database(config.database_path)
    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["config"] = config
    application.bot_data["db"] = db

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CommandHandler("privacy", privacy))
    application.add_handler(CommandHandler("terms", terms))
    application.add_handler(CommandHandler("report", report))

    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("users", users))
    application.add_handler(CommandHandler("jobs", jobs))
    application.add_handler(CommandHandler("queue", queue))
    application.add_handler(CommandHandler("maintenance", maintenance))

    application.add_handler(CallbackQueryHandler(callback_router))
    application.add_handler(MessageHandler(filters.Document.ALL, receive_document))
    application.add_handler(MessageHandler(filters.PHOTO, receive_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

    application.add_error_handler(error_handler)
    return application


def _start_health_early() -> HealthServer | None:
    """Bind /health before Config so platform probes pass even if BOT_TOKEN is missing."""
    port = int(os.getenv("PORT", "8080") or "8080")
    enable = os.getenv("ENABLE_HEALTH", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enable:
        return None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        health = HealthServer(port, time.time())
        loop.run_until_complete(health.start())
        logging.getLogger(__name__).info("Early health server on 0.0.0.0:%s/health", port)
        return health
    except Exception:
        logging.getLogger(__name__).exception("Could not start early health server")
        return None


def run() -> None:
    from telegram.error import Conflict, NetworkError, RetryAfter, TimedOut

    # Basic console logging until Config/log dir is ready
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # 1) Health first — Back4App probes :8080 immediately
    health = _start_health_early()

    # 2) Wait for BOT_TOKEN in container environment (not a committed .env file)
    backoff = 5
    max_backoff = 60
    config: Config | None = None
    while config is None:
        token = (os.getenv("BOT_TOKEN") or "").strip()
        if not token:
            log.error(
                "BOT_TOKEN is missing from the container environment. "
                "In Back4App: App Settings → Environment Variables → add BOT_TOKEN "
                "(and optionally ADMIN_IDS). Do not rely on a .env file in the image. "
                "Retrying in %s s...",
                backoff,
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue
        try:
            config = Config.from_env()
        except Exception as exc:
            log.error("Config error: %s — retrying in %s s...", exc, backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    setup_logging(config.log_dir, config.log_level)
    log.info(
        "Starting Document Studio bot (health=%s, port=%s)",
        config.enable_health,
        config.port,
    )

    backoff = 5
    while True:
        try:
            application = build_application(config)
        except Exception:
            log.exception(
                "Failed to build application. Health still up. Retrying in %s s...",
                backoff,
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
            continue

        if health is not None:
            application.bot_data["health"] = health
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=(signal.SIGINT, signal.SIGTERM),
            )
            log.info("Polling stopped cleanly.")
            break
        except Conflict:
            log.error(
                "Telegram Conflict: another instance is polling this BOT_TOKEN. Retrying in %s s...",
                backoff,
            )
        except (NetworkError, TimedOut) as exc:
            log.warning("Network error (%s). Retrying in %s s...", exc, backoff)
        except RetryAfter as exc:
            wait = max(int(exc.retry_after) + 1, backoff)
            log.warning("Flood control. Sleeping %s s...", wait)
            time.sleep(wait)
            backoff = min(backoff * 2, max_backoff)
            continue
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
            break
        except Exception:
            log.exception("Fatal polling error. Retrying in %s s...", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)

    if health is not None:
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                loop.run_until_complete(health.stop())
        except Exception:
            pass
