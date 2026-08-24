from telegram import Update
from telegram.ext import ContextTypes

from ..keyboards.main import navigation


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .callbacks import show_history

    class Q:
        def __init__(self, message):
            self.message = message

        async def edit_message_text(self, *args, **kwargs):
            await self.message.reply_text(*args, **kwargs)

        async def answer(self, *args, **kwargs):
            return None

    await show_history(Q(update.effective_message), context, update.effective_user.id, 0)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    jobs = await context.application.bot_data["db"].active_jobs(update.effective_user.id)
    if not jobs:
        await update.effective_message.reply_text("No active jobs.")
        return
    text = "\n".join(
        f"{j['job_id'][:8]} • {j['operation']} • {j['status']} • {j['progress']}%" for j in jobs
    )
    await update.effective_message.reply_text(f"⚙️ Active jobs:\n\n{text}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    manager = context.application.bot_data["job_manager"]
    count = await manager.cancel_all(update.effective_user.id)
    await update.effective_message.reply_text(
        f"Cancellation requested for {count} active job(s)."
    )


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📚 Document Studio\n\nAn original asynchronous Telegram document workspace."
    )


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🔒 Privacy\n\nFiles are stored temporarily for processing and cleanup. "
        "Persistent data is limited to account settings, job metadata, and result metadata."
    )


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "📜 Terms\n\nUse the bot only for files you are authorized to process. "
        "Do not upload unlawful or harmful material. You are responsible for your files."
    )


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "🛑 Report\n\nDescribe the problem and include the job ID if one was created. "
        "Do not send secrets or credentials."
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    s = await context.application.bot_data["db"].get_settings(update.effective_user.id)
    from ..keyboards.settings import settings_keyboard

    await update.effective_message.reply_text(
        "⚙️ Settings", reply_markup=settings_keyboard(s)
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    stats_data = await context.application.bot_data["db"].personal_stats(
        update.effective_user.id
    )
    await update.effective_message.reply_text(
        f"📊 Your statistics\n\n"
        f"Total: {stats_data.get('total', 0)}\n"
        f"Completed: {stats_data.get('completed', 0)}\n"
        f"Failed: {stats_data.get('failed', 0)}\n"
        f"Cancelled: {stats_data.get('cancelled', 0)}",
        reply_markup=navigation(),
    )
