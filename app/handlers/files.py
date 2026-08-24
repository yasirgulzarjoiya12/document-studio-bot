from __future__ import annotations

import logging
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Config
from ..keyboards.main import upload_done_keyboard
from ..services.validation import ValidationError, validate_input
from ..utils.security import safe_filename

log = logging.getLogger(__name__)


async def _save_telegram_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_id: str, name: str) -> Path:
    config: Config = context.application.bot_data["config"]
    tg_file = await context.bot.get_file(file_id)
    dest_dir = config.download_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_filename(name)
    await tg_file.download_to_drive(custom_path=str(dest))
    return dest


async def receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    op = context.user_data.get("operation")
    if not op:
        await update.effective_message.reply_text("Choose an operation from /menu first.")
        return
    doc = update.effective_message.document
    if not doc:
        return
    config: Config = context.application.bot_data["config"]
    path = await _save_telegram_file(update, context, doc.file_id, doc.file_name or "file.bin")
    try:
        allowed = {".pdf"} if op in {"pdfimg", "merge", "split", "text", "compress", "rotate"} else {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
        if op == "ocr":
            allowed = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
        if op == "imgpdf":
            allowed = {".jpg", ".jpeg", ".png", ".webp"}
        validate_input(path, config, allowed)
    except ValidationError as exc:
        path.unlink(missing_ok=True)
        await update.effective_message.reply_text(f"⚠️ {exc}")
        return
    inputs = context.user_data.setdefault("inputs", [])
    inputs.append(path)
    if op in {"imgpdf", "merge"}:
        await update.effective_message.reply_text(
            f"Added file ({len(inputs)}). Send more or Finish.",
            reply_markup=upload_done_keyboard(op),
        )
        return
    # Single-file ops: queue immediately or wait for params
    if op in {"split", "rotate"}:
        context.user_data["awaiting_param"] = True
        prompt = "Send page ranges like 1-3,5" if op == "split" else "Send 90, 180, or 270"
        await update.effective_message.reply_text(prompt)
        return
    from .callbacks import start_job_from_context
    await start_job_from_context(update, context)


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    op = context.user_data.get("operation")
    if op not in {"imgpdf", "ocr"}:
        await update.effective_message.reply_text("Photos are used for Images→PDF or OCR. Use /menu.")
        return
    photo = update.effective_message.photo[-1]
    path = await _save_telegram_file(update, context, photo.file_id, f"photo_{photo.file_unique_id}.jpg")
    inputs = context.user_data.setdefault("inputs", [])
    inputs.append(path)
    if op == "imgpdf":
        await update.effective_message.reply_text(
            f"Added image ({len(inputs)}). Send more or Finish.",
            reply_markup=upload_done_keyboard(op),
        )
        return
    from .callbacks import start_job_from_context
    await start_job_from_context(update, context)


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("awaiting_param"):
        return
    text = (update.effective_message.text or "").strip()
    op = context.user_data.get("operation")
    if op == "split":
        context.user_data.setdefault("params", {})["pages"] = text
    elif op == "rotate":
        if text not in {"90", "180", "270"}:
            await update.effective_message.reply_text("Send 90, 180, or 270.")
            return
        context.user_data.setdefault("params", {})["degrees"] = int(text)
    else:
        return
    context.user_data["awaiting_param"] = False
    from .callbacks import start_job_from_context
    await start_job_from_context(update, context)
