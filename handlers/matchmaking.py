from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def find_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = InlineKeyboardMarkup([
        [{"text": "1v1", "callback_data": "mode_1v1"}],
        [{"text": "2v2", "callback_data": "mode_2v2"}],
        [{"text": "3v3", "callback_data": "mode_3v3"}]
    ])
    await context.bot.send_message(
        chat_id=user.id,
        text="Choisissez un mode :",
        reply_markup=keyboard
    )