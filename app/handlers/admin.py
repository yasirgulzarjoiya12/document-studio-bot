from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Config
from ..database import Database
from ..keyboards.admin import admin_keyboard


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config: Config = context.application.bot_data["config"]
    user = update.effective_user
    return bool(user and user.id in config.admin_ids)


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        await update.effective_message.reply_text("Admin only.")
        return
    await update.effective_message.reply_text(
        "\U0001f6e0 Admin panel", reply_markup=admin_keyboard()
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.effective_message.reply_text("Usage: /broadcast <message>")
        return
    db: Database = context.application.bot_data["db"]
    users = await db.list_users(500)
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(u["chat_id"], text)
            sent += 1
        except Exception:
            pass
    await update.effective_message.reply_text(f"Broadcast sent to {sent} users.")


async def users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_users(30)
    lines = [f"{r['user_id']} @{r.get('username') or '-'} {r.get('first_name') or ''}" for r in rows]
    await update.effective_message.reply_text("Users:\n" + ("\n".join(lines) or "none"))


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_jobs(20)
    lines = [f"{r['job_id'][:8]} {r['status']} {r['operation']} u={r['user_id']}" for r in rows]
    await update.effective_message.reply_text("Jobs:\n" + ("\n".join(lines) or "none"))


async def queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        return
    manager = context.application.bot_data.get("job_manager")
    active = len(manager.runtime) if manager else 0
    counts = await context.application.bot_data["db"].count_by_status()
    await update.effective_message.reply_text(f"Active runtime: {active}\nDB status: {counts}")


async def maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context):
        return
    await update.effective_message.reply_text("Maintenance mode toggle is not enabled in this build.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Personal stats is also available non-admin via /stats in misc; keep admin alias.
    from .misc import stats as personal_stats
    await personal_stats(update, context)
