import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from handlers.correction import cmd_undo, handle_meal_type_correction, is_meal_type_correction
from handlers.manual_meal import (
    handle_at_input,
    handle_bot_reply_paste,
    handle_manual_command,
    is_at_manual_input,
    is_bot_reply_format,
)
from handlers.goal import cmd_goal
from handlers.meal import handle_photo, handle_text
from handlers.tdee import cmd_tdee
from handlers.query import cmd_today
from handlers.weight import cmd_weight
from scheduler import setup_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def auth_check(func):
    """只允許指定 chat_id 的使用者操作。"""

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != TELEGRAM_CHAT_ID:
            logger.warning("Unauthorized access from chat_id=%s", update.effective_chat.id)
            return
        return await func(update, context)

    return wrapper


@auth_check
async def _handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if is_meal_type_correction(text):
        await handle_meal_type_correction(update, context)
        return
    if is_bot_reply_format(text):
        await handle_bot_reply_paste(update, context)
        return
    if is_at_manual_input(text):
        await handle_at_input(update, context)
        return
    await handle_text(update, context)


@auth_check
async def _handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_photo(update, context)


@auth_check
async def _cmd_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_weight(update, context)


@auth_check
async def _cmd_tdee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_tdee(update, context)


@auth_check
async def _cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_today(update, context)


@auth_check
async def _cmd_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_manual_command(update, context)


@auth_check
async def _cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_undo(update, context)


@auth_check
async def _cmd_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_goal(update, context)


@auth_check
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Calorie Bot 啟動完成，直接傳食物照片或文字即可記錄。")


async def post_init(application: Application):
    setup_scheduler(application)


def main():
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("m", _cmd_manual))
    app.add_handler(CommandHandler("w", _cmd_weight))
    app.add_handler(CommandHandler("t", _cmd_tdee))
    app.add_handler(CommandHandler("s", _cmd_today))
    app.add_handler(CommandHandler("u", _cmd_undo))
    app.add_handler(CommandHandler("g", _cmd_goal))
    app.add_handler(MessageHandler(filters.PHOTO, _handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    logger.info("Bot started. Listening for chat_id=%s", TELEGRAM_CHAT_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
