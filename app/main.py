from __future__ import annotations

import asyncio
import logging
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
from .handlers.admin import admin, broadcast, jobs, maintenance, queue, stats, users
from .handlers.callbacks import callback_router, on_complete, on_failed, on_progress
from .handlers.errors import error_handler
from .handlers.files import receive_document, receive_photo, receive_text
from .handlers.misc import about, cancel, history, privacy, report, settings, status, terms
from .handlers.start import help_command, menu, start
from .health import HealthServer
from .services.cleanup import CleanupService
from .services.job_manager import JobManager
from .services.rate_limit import RateLimiter
from .utils.logging import setup_logging


log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    config: Config = application.bot_data["config"]
    db: Database = application.bot_data["db"]
    await db.connect()
    cleanup = CleanupService(config, db)
    cleanup.start()
    application.bot_data["cleanup"] = cleanup

    manager = JobManager(config, db)
    application.bot_data["job_manager"] = manager
    application.bot_data["rate_limiter"] = RateLimiter(config.rate_limit, config.rate_window_seconds)

    on_progress.app = application
    on_complete.app = application
    on_failed.app = application
    manager.on_progress = on_progress
    manager.on_complete = on_complete
    manager.on_failed = on_failed

    if config.enable_health:
        try:
            health = HealthServer(db, config.port, time.time())
            await health.start()
            application.bot_data["health"] = health
            log.info("Health server listening on 0.0.0.0:%s/health", config.port)
        except OSError as exc:
            # Port already in use or bind failure must not kill the bot.
            log.error(
                "Health server failed to start on port %s (%s). Bot continues without /health.",
                config.port,
                exc,
            )
        except Exception:
            log.exception("Unexpected error starting health server; bot continues without /health.")

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


def run() -> None:
    """Start the bot with resilient polling.

    Common failure modes that used to take the process down after ~1 minute:
    - Telegram Conflict (another instance polling the same token)
    - Transient network / TimedOut errors from getUpdates
    - Health server bind errors (now non-fatal in post_init)
    """
    from telegram.error import Conflict, NetworkError, RetryAfter, TimedOut

    config = Config.from_env()
    setup_logging(config.log_dir, config.log_level)
    log.info("Starting Document Studio bot (health=%s, port=%s)", config.enable_health, config.port)

    backoff = 5
    max_backoff = 60
    while True:
        application = build_application(config)
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=True,
                stop_signals=(signal.SIGINT, signal.SIGTERM),
            )
            # Clean shutdown (signal) — exit the restart loop.
            log.info("Polling stopped cleanly.")
            break
        except Conflict:
            log.error(
                "Telegram Conflict: another instance is already polling with this BOT_TOKEN. "
                "Stop the other process (or wait for it to die) then restart. "
                "Retrying in %s seconds...",
                backoff,
            )
        except (NetworkError, TimedOut) as exc:
            log.warning("Network error during polling (%s). Retrying in %s seconds...", exc, backoff)
        except RetryAfter as exc:
            wait = max(int(exc.retry_after) + 1, backoff)
            log.warning("Telegram flood control. Sleeping %s seconds...", wait)
            time.sleep(wait)
            backoff = min(backoff * 2, max_backoff)
            continue
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
            break
        except Exception:
            log.exception("Unexpected fatal error in run_polling. Retrying in %s seconds...", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)
