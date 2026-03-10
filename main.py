import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

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
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """暫時回覆收到的文字，確認接線正常。"""
    await update.message.reply_text(f"收到文字：{update.message.text}")


@auth_check
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """暫時回覆收到照片，確認接線正常。"""
    caption = update.message.caption or ""
    await update.message.reply_text(f"收到照片（caption: {caption}）")


@auth_check
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Calorie Bot 啟動完成，直接傳食物照片或文字即可記錄。")


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot started. Listening for chat_id=%s", TELEGRAM_CHAT_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
