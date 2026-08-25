from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..config import Config
from ..database import Database
from ..keyboards.admin import admin_keyboard
from ..keyboards.main import cancel_keyboard, main_menu, navigation, result_keyboard, retry_keyboard
from ..keyboards.settings import settings_keyboard
from ..services.job_manager import RuntimeJob
from ..services.validation import ValidationError, validate_file
from ..utils.formatting import safe_text
from ..utils.security import safe_filename

log = logging.getLogger(__name__)


async def _edit(q, text: str, **kwargs) -> None:
    await q.edit_message_text(safe_text(text), **kwargs)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user = update.effective_user
    limiter = context.application.bot_data.get("rate_limiter")
    if limiter and not await limiter.allow(user.id):
        await q.answer("Too many actions. Please wait.", show_alert=True)
        return
    data = q.data or ""
    if data.startswith("menu:"):
        from .menu import choose_operation
        await choose_operation(update, context, data.split(":", 1)[1])
        return
    if data == "nav:home":
        context.user_data.clear()
        await q.answer()
        await _edit(
            q,
            "<b>Document Studio</b>\n\nChoose an operation:",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return
    if data.startswith("nav:help"):
        await q.answer()
        await _edit(
            q,
            "<b>Help</b>\n\nChoose a tool, upload valid files, wait for processing.\n"
            "Every result is checked before delivery.",
            parse_mode="HTML",
            reply_markup=navigation(),
        )
        return
    if data.startswith("nav:stats"):
        await q.answer()
        stats = await context.application.bot_data["db"].personal_stats(user.id)
        await _edit(
            q,
            f"<b>Your statistics</b>\n\n"
            f"Total: {stats.get('total', 0)}\nCompleted: {stats.get('completed', 0)}\n"
            f"Failed: {stats.get('failed', 0)}\nCancelled: {stats.get('cancelled', 0)}",
            parse_mode="HTML",
            reply_markup=navigation(),
        )
        return
    if data.startswith("nav:settings"):
        await q.answer()
        s = await context.application.bot_data["db"].get_settings(user.id)
        await _edit(q, "<b>Settings</b>", parse_mode="HTML", reply_markup=settings_keyboard(s))
        return
    if data.startswith("nav:history"):
        await q.answer()
        await show_history(q, context, user.id, 0)
        return
    if data.startswith("settings:"):
        await handle_setting(q, context, data)
        return
    if data.startswith("input:finish:"):
        await q.answer()
        await start_job_from_context(update, context)
        return
    if data.startswith("job:cancel:"):
        await q.answer()
        parts = data.split(":")
        job_id, owner = parts[2], int(parts[3])
        if owner != user.id:
            return
        manager = context.application.bot_data["job_manager"]
        ok = await manager.cancel(job_id, user.id)
        await _edit(q, "Cancelled." if ok else "Nothing to cancel.")
        return
    if data.startswith("job:retry:"):
        await q.answer()
        parts = data.split(":")
        owner = int(parts[3])
        if owner != user.id:
            return
        await _edit(q, "Use /menu and upload again to retry.")
        return
    if data.startswith("gallery:"):
        await q.answer()
        parts = data.split(":")
        job_id, owner, page = parts[1], int(parts[2]), int(parts[3])
        if owner != user.id:
            return
        await show_gallery(q, context, job_id, user.id, page)
        return
    if data.startswith("result:zip:"):
        await q.answer("Preparing archive...")
        parts = data.split(":")
        job_id, owner = parts[2], int(parts[3])
        if owner != user.id:
            return
        await send_zip(update, context, job_id, user.id)
        return
    if data.startswith("result:item:"):
        await q.answer()
        parts = data.split(":")
        result_id, owner = int(parts[2]), int(parts[3])
        if owner != user.id:
            return
        await send_result_by_id(update, context, result_id, user.id)
        return
    if data.startswith("admin:"):
        await q.answer()
        await _edit(q, "Admin", reply_markup=admin_keyboard())
        return
    await q.answer("Unknown action.", show_alert=True)


async def handle_setting(q, context, data: str) -> None:
    db: Database = context.application.bot_data["db"]
    uid = q.from_user.id
    kind = data.split(":")[1]
    if kind == "page_size":
        current = (await db.get_settings(uid))["page_size"]
        value = {4: 6, 6: 8, 8: 10, 10: 4}.get(int(current), 6)
        await db.update_setting(uid, "page_size", value)
    elif kind == "auto_cleanup":
        settings = await db.get_settings(uid)
        await db.update_setting(uid, "auto_cleanup", 0 if settings["auto_cleanup"] else 1)
    elif kind == "notify_progress":
        settings = await db.get_settings(uid)
        await db.update_setting(uid, "notify_progress", 0 if settings["notify_progress"] else 1)
    await q.answer("Saved")
    await q.edit_message_reply_markup(reply_markup=settings_keyboard(await db.get_settings(uid)))


async def show_history(q, context, user_id: int, page: int) -> None:
    db: Database = context.application.bot_data["db"]
    rows = await db.recent_jobs(user_id, 10)
    if not rows:
        await _edit(q, "No history yet.", reply_markup=navigation())
        return
    text = "\n".join(f"{r['job_id'][:8]} | {r['operation']} | {r['status']}" for r in rows)
    await _edit(q, f"<b>History</b>\n\n{text}", parse_mode="HTML", reply_markup=navigation())


async def show_gallery(q, context, job_id: str, user_id: int, page: int) -> None:
    db: Database = context.application.bot_data["db"]
    config: Config = context.application.bot_data["config"]
    page_size = config.gallery_page_size
    results = await db.get_results(job_id, page_size, page * page_size)
    total_rows = await db.get_results(job_id, 1000, 0)
    pages = max(1, (len(total_rows) + page_size - 1) // page_size)
    if not results:
        await _edit(q, "No results.", reply_markup=navigation())
        return
    await _edit(
        q,
        f"<b>Results</b>\nPage {page + 1}/{pages} | {len(total_rows)} file(s)",
        parse_mode="HTML",
        reply_markup=result_keyboard(
            job_id, user_id, page, pages, [int(r["id"]) for r in results], True
        ),
    )


async def send_result_by_id(update: Update, context, result_id: int, user_id: int) -> None:
    db: Database = context.application.bot_data["db"]
    item = await db.get_result(result_id)
    msg = update.effective_message
    if not item:
        await msg.reply_text("Result no longer exists.")
        return
    job = await db.get_job(item["job_id"])
    if not job or int(job["user_id"]) != user_id:
        await msg.reply_text("That result is not available.")
        return
    path = Path(item["path"])
    try:
        validate_file(path, context.application.bot_data["config"])
    except ValidationError as exc:
        await msg.reply_text(f"Result validation failed: {exc}")
        return
    with path.open("rb") as fh:
        await msg.reply_document(document=fh, filename=item["original_name"])


async def send_zip(update: Update, context, job_id: str, user_id: int) -> None:
    db: Database = context.application.bot_data["db"]
    results = await db.get_results(job_id, 100, 0)
    msg = update.effective_message
    if not results:
        await msg.reply_text("No results are available to archive.")
        return
    job = await db.get_job(job_id)
    if not job or int(job["user_id"]) != user_id:
        await msg.reply_text("Not available.")
        return
    config: Config = context.application.bot_data["config"]
    job_dir = config.job_data_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    archive = job_dir / f"{job_id[:8]}_results.zip"
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in results:
                path = Path(item["path"])
                validate_file(path, config)
                zf.write(path, arcname=safe_filename(item["original_name"]))
        validate_file(archive, config)
        with archive.open("rb") as fh:
            await msg.reply_document(document=fh, filename=archive.name)
    except Exception as exc:
        await msg.reply_text(f"Could not build ZIP: {exc}")


async def start_job_from_context(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        chat.id, "<b>Queued</b>\nWaiting for a worker...", parse_mode="HTML"
    )

    async def runner(job: RuntimeJob, progress):
        return await operations.run(job, progress, config)

    try:
        job = await manager.create(
            user.id, chat.id, op, inputs, params, status.message_id, runner
        )
    except RuntimeError as exc:
        await status.edit_text(str(exc))
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
            text=safe_text(f"<b>Processing</b>\n\n{stage}\nProgress: {value}%"),
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
            text=safe_text(f"<b>Completed</b>\n\n{len(results)} result(s) ready."),
            parse_mode="HTML",
        )
    except TelegramError:
        pass
    await app.bot.send_message(
        job.chat_id,
        "<b>Results ready.</b>\nOpen the gallery to browse files.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Open Gallery", callback_data=f"gallery:{job.job_id}:{job.user_id}:0")],
                [InlineKeyboardButton("Download All", callback_data=f"result:zip:{job.job_id}:{job.user_id}")],
            ]
        ),
    )


async def on_failed(job: RuntimeJob, error: str, retryable: bool = False) -> None:
    app = getattr(on_failed, "app", None)
    if not app:
        return
    text = safe_text(f"<b>Failed</b>\n\n{error[:500]}")
    try:
        await app.bot.edit_message_text(
            chat_id=job.chat_id,
            message_id=job.message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=retry_keyboard(job.job_id, job.user_id) if retryable else navigation(),
        )
    except TelegramError:
        pass
