from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..database import Database
from ..keyboards.main import main_menu, navigation


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db: Database = context.application.bot_data["db"]
    await db.register_user(user.id, update.effective_chat.id, user.username, user.first_name)
    config = context.application.bot_data["config"]
    text = (
        f"📄 <b>{config.bot_name}</b>\n\n"
        f"{config.bot_description}\n\n"
        "Choose an operation below. Every file is validated before and after processing."
    )
    await update.effective_message.reply_text(text, parse_mode="HTML", reply_markup=main_menu())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.clear()
    await update.effective_message.reply_text(
        "🏠 <b>Main menu</b>\n\nChoose an operation:",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "ℹ️ <b>Help</b>\n\n"
        "1. Choose a tool from the menu\n"
        "2. Upload the requested file(s)\n"
        "3. Wait for real processing\n"
        "4. Download validated results\n\n"
        "Commands: /menu /settings /history /status /cancel /stats",
        parse_mode="HTML",
        reply_markup=navigation(),
    )
