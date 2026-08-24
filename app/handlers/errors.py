from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import ContextTypes


log = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    if isinstance(error, RetryAfter):
        log.warning("Telegram flood wait: %s seconds", error.retry_after)
        return
    log.exception("Unhandled bot error", exc_info=error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong while handling that request. "
                "No success was reported. Please retry or use /report."
            )
        except TelegramError:
            pass
