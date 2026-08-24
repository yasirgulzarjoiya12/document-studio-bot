from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    auto = "ON" if settings.get("auto_cleanup") else "OFF"
    notify = "ON" if settings.get("notify_progress") else "OFF"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"Page size: {settings.get('page_size', 6)}",
                    callback_data="settings:page_size",
                )
            ],
            [
                InlineKeyboardButton(
                    f"Auto cleanup: {auto}",
                    callback_data="settings:auto_cleanup",
                )
            ],
            [
                InlineKeyboardButton(
                    f"Progress notify: {notify}",
                    callback_data="settings:notify_progress",
                )
            ],
            [InlineKeyboardButton("Home", callback_data="nav:home")],
        ]
    )
