from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..database import Database
from ..keyboards.main import main_menu, navigation, result_keyboard
from ..services.job_manager import RuntimeJob

log = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    data = q.data or ""
    user = update.effective_user
    await q.answer()
    if data.startswith("menu:"):
        from .menu import choose_operation
        await choose_operation(update, context, data.split(":", 1)[1])
        return
    if data == "nav:home":
        context.user_data.clear()
        await q.edit_message_text(
            "🏠 <b>Document Studio</b>\n\nChoose an operation:",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return
    if data.startswith("nav:help"):
        await q.edit_message_text(
            "ℹ️ Help: choose a tool, upload files, wait for processing.",
            reply_markup=navigation(),
        )
        return
    if data.startswith("nav:stats"):
        stats = await context.application.bot_data["db"].personal_stats(user.id)
        await q.edit_message_text(
            f"📊 Total {stats.get('total',0)} / Completed {stats.get('completed',0)}",
            reply_markup=navigation(),
        )
        return
    if data.startswith("nav:settings"):
        from ..keyboards.settings import settings_keyboard
        s = await context.application.bot_data["db"].get_settings(user.id)
        await q.edit_message_text("⚙️ Settings", reply_markup=settings_keyboard(s))
        return
    if data.startswith("nav:history"):
        await show_history(q, context, user.id, 0)
        return
    if data.startswith("input:finish:"):
        await start_job_from_context(update, context)
        return
    if data.startswith("gallery:"):
        parts = data.split(":")
        job_id, owner, page = parts[1], int(parts[2]), int(parts[3])
        if owner != user.id:
            return
        await show_gallery(q, context, job_id, user.id, page)
        return
    if data.startswith("job:cancel:"):
        parts = data.split(":")
        job_id, owner = parts[2], int(parts[3])
        if owner != user.id:
            return
        manager = context.application.bot_data["job_manager"]
        ok = await manager.cancel(job_id, user.id)
        await q.edit_message_text("Cancelled." if ok else "Nothing to cancel.")
        return


async def show_history(q, context, user_id: int, page: int) -> None:
    rows = await context.application.bot_data["db"].recent_jobs(user_id, 10)
    if not rows:
        await q.edit_message_text("No history yet.", reply_markup=navigation())
        return
    text = "\n".join(
        f"{r['job_id'][:8]} • {r['operation']} • {r['status']}" for r in rows
    )
    await q.edit_message_text(f"📚 History\n\n{text}", reply_markup=navigation())


async def show_gallery(q, context, job_id: str, user_id: int, page: int) -> None:
    db: Database = context.application.bot_data["db"]
    config = context.application.bot_data["config"]
    results = await db.get_results(job_id, config.gallery_page_size, page * config.gallery_page_size)
    total_rows = await db.get_results(job_id, 1000, 0)
    pages = max(1, (len(total_rows) + config.gallery_page_size - 1) // config.gallery_page_size)
    if not results:
        await q.edit_message_text("No results.", reply_markup=navigation())
        return
    await q.edit_message_text(
        f"🖼 Results page {page+1}/{pages}",
        reply_markup=result_keyboard(
            job_id, user_id, page, pages, [int(r["id"]) for r in results], True
        ),
    )


async def start_job_from_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from ..keyboards.main import cancel_keyboard
    from ..services import operations

    op = context.user_data.get("operation")
    inputs = list(context.user_data.get("inputs") or [])
    params = dict(context.user_data.get("params") or {})
    if not op or not inputs:
        msg = update.effective_message or (
            update.callback_query.message if update.callback_query else None
        )
        if msg:
            await msg.reply_text("No files queued. Use /menu and upload again.")
        return

    config = context.application.bot_data["config"]
    manager = context.application.bot_data["job_manager"]
    chat = update.effective_chat
    user = update.effective_user
    status = await context.bot.send_message(
        chat.id, "⏳ <b>Queued</b>\nWaiting for a worker...", parse_mode="HTML"
    )

    async def runner(job: RuntimeJob, progress):
        return await operations.run(job, progress, config)

    try:
        job = await manager.create(
            user.id, chat.id, op, inputs, params, status.message_id, runner
        )
    except RuntimeError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    context.user_data.clear()
    await status.edit_reply_markup(reply_markup=cancel_keyboard(job.job_id, job.user_id))


async def on_progress(job: RuntimeJob, value: int, stage: str) -> None:
    app = getattr(on_progress, "app", None)
    if not app or not job.message_id:
        return
    try:
        await app.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.message_id,
            text=f"⚙️ <b>Processing</b>\n\n{stage}\nProgress: {value}%",
            parse_mode="HTML",
        )
    except TelegramError:
        pass


async def on_complete(job: RuntimeJob, results: list) -> None:
    app = getattr(on_complete, "app", None)
    if not app:
        return
    try:
        await app.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.message_id,
            text=f"✅ <b>Completed</b>\n\n{len(results)} result(s) ready.",
            parse_mode="HTML",
        )
    except TelegramError:
        pass
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    await app.bot.send_message(
        job.chat_id,
        "📦 Results ready.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Open Gallery", callback_data=f"gallery:{job.job_id}:{job.user_id}:0")]]
        ),
    )


async def on_failed(job: RuntimeJob, error: str, retryable: bool = False) -> None:
    app = getattr(on_failed, "app", None)
    if not app:
        return
    try:
        await app.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.message_id,
            text=f"❌ Failed\n\n{error[:500]}",
        )
    except TelegramError:
        pass
