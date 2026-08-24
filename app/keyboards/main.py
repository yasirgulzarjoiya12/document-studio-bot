from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📄 PDF → Images", callback_data="menu:pdfimg"),
         InlineKeyboardButton("🖼 Images → PDF", callback_data="menu:imgpdf")],
        [InlineKeyboardButton("🧩 Merge PDFs", callback_data="menu:merge"),
         InlineKeyboardButton("✂️ Split PDF", callback_data="menu:split")],
        [InlineKeyboardButton("📝 Extract Text", callback_data="menu:text"),
         InlineKeyboardButton("🔎 OCR", callback_data="menu:ocr")],
        [InlineKeyboardButton("🗜 Compress PDF", callback_data="menu:compress"),
         InlineKeyboardButton("🔄 Rotate PDF", callback_data="menu:rotate")],
        [InlineKeyboardButton("📚 History", callback_data="nav:history:0"),
         InlineKeyboardButton("⚙️ Settings", callback_data="nav:settings")],
        [InlineKeyboardButton("📊 My Stats", callback_data="nav:stats"),
         InlineKeyboardButton("ℹ️ Help", callback_data="nav:help")],
    ]
    return InlineKeyboardMarkup(rows)


def cancel_keyboard(job_id: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⛔ Cancel", callback_data=f"job:cancel:{job_id}:{user_id}")]
    ])


def retry_keyboard(job_id: str, user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Retry", callback_data=f"job:retry:{job_id}:{user_id}")],
        [InlineKeyboardButton("🏠 Home", callback_data="nav:home")],
    ])


def upload_done_keyboard(operation: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Finish", callback_data=f"input:finish:{operation}")],
        [InlineKeyboardButton("🏠 Cancel", callback_data="nav:home")],
    ])


def result_keyboard(
    job_id: str,
    user_id: int,
    page: int,
    pages: int,
    result_ids: list[int] | None = None,
    has_zip: bool = True,
) -> InlineKeyboardMarkup:
    rows = []
    if result_ids:
        for i in range(0, len(result_ids), 2):
            row = [
                InlineKeyboardButton(
                    f"⬇️ File {page * len(result_ids) + i + 1}",
                    callback_data=f"result:item:{result_ids[i]}:{user_id}",
                )
            ]
            if i + 1 < len(result_ids):
                row.append(
                    InlineKeyboardButton(
                        f"⬇️ File {page * len(result_ids) + i + 2}",
                        callback_data=f"result:item:{result_ids[i+1]}:{user_id}",
                    )
                )
            rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Previous", callback_data=f"gallery:{job_id}:{user_id}:{page-1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"gallery:{job_id}:{user_id}:{page+1}"))
    if nav:
        rows.append(nav)
    if has_zip:
        rows.append([InlineKeyboardButton("📦 Download All", callback_data=f"result:zip:{job_id}:{user_id}")])
    rows.append([InlineKeyboardButton("🏠 Home", callback_data="nav:home")])
    return InlineKeyboardMarkup(rows)


def navigation() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="nav:home")]])
