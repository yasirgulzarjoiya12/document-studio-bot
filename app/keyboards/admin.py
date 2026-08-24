from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Users", callback_data="admin:users"),
                InlineKeyboardButton("Jobs", callback_data="admin:jobs"),
            ],
            [
                InlineKeyboardButton("Queue", callback_data="admin:queue"),
                InlineKeyboardButton("Maintenance", callback_data="admin:maintenance"),
            ],
            [InlineKeyboardButton("Home", callback_data="nav:home")],
        ]
    )
