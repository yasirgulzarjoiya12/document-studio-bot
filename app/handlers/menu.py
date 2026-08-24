from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..keyboards.main import main_menu, cancel_keyboard


OPERATIONS = {
    "pdfimg": "PDF \u2192 Images",
    "imgpdf": "Images \u2192 PDF",
    "merge": "Merge PDFs",
    "split": "Split PDF",
    "text": "Extract text",
    "ocr": "OCR",
    "compress": "Compress PDF",
    "rotate": "Rotate PDF",
}


async def choose_operation(update: Update, context: ContextTypes.DEFAULT_TYPE, op: str) -> None:
    q = update.callback_query
    if op not in OPERATIONS:
        await q.answer("Unknown operation", show_alert=True)
        return
    context.user_data.clear()
    context.user_data["operation"] = op
    context.user_data["inputs"] = []
    await q.answer()
    prompts = {
        "pdfimg": "Send a PDF. Pages will be rendered to images.",
        "imgpdf": "Send one or more images, then tap Finish.",
        "merge": "Send two or more PDFs, then tap Finish.",
        "split": "Send a PDF, then send page ranges like 1-3,5,8-10.",
        "text": "Send a PDF to extract text.",
        "ocr": "Send a PDF or image for OCR (Tesseract required).",
        "compress": "Send a PDF to compress (raster rebuild).",
        "rotate": "Send a PDF, then send 90, 180, or 270.",
    }
    await q.edit_message_text(
        f"\U0001f4c4 <b>{OPERATIONS[op]}</b>\n\n{prompts[op]}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
