import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from handlers.correction import (
    cmd_undo,
    handle_correct_callback,
    handle_correction_input,
    handle_meal_type_correction,
    is_meal_type_correction,
)
from handlers.manual_meal import (
    handle_at_input,
    handle_bot_reply_paste,
    handle_manual_command,
    is_at_manual_input,
    is_bot_reply_format,
)
from handlers.food_cache import cmd_food_cache, handle_cache_callback, handle_cache_number, handle_mtype_callback, is_cache_number
from handlers.goal import cmd_goal
from handlers.meal import handle_photo, handle_text
from handlers.report import cmd_report
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

    # 修正模式：優先處理
    pending = context.user_data.get("pending_correction")
    if pending:
        context.user_data.pop("pending_correction")
        try:
            await handle_correction_input(update, context, pending)
            return
        except ValueError:
            pass  # 解析失敗，繼續正常路由

    if is_meal_type_correction(text):
        await handle_meal_type_correction(update, context)
        return
    if is_cache_number(text):
        await handle_cache_number(update, context)
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
    context.user_data.pop("pending_correction", None)
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
async def _cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_report(update, context)


@auth_check
async def _cmd_food_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_food_cache(update, context)


@auth_check
async def _handle_cache_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_cache_callback(update, context)


@auth_check
async def _handle_mtype_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_mtype_callback(update, context)


@auth_check
async def _handle_correct_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_correct_callback(update, context)


@auth_check
async def _cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [
        "操作說明",
        "",
        "【記錄食物】",
        "傳文字或照片 → AI 自動分析",
        "@品名 熱量 [蛋白質 碳水 脂肪] → 手動",
        "/m 品名 熱量 [蛋白質 碳水 脂肪] → 手動",
        "11-99 → 快取編號直接記錄",
        "貼上 Bot 回覆 → 自動解析重新記錄",
        "末尾加 x2, x0.5 → 倍數記錄",
        "",
        "【指令】",
        "/s — 今日摘要",
        "/w 體重 — 記錄體重",
        "/t 消耗 [n] — TDEE（預設昨天，加 n 今天）",
        "/f — 食物快取清單",
        "/r — 上週週報 | /r now 本週至今",
        "/g 熱量 — 調整每日目標",
        "/u — 撤銷上一筆",
        "/h — 本說明",
        "",
        "【快捷操作】",
        "1-4 — 改上一筆餐別（1早 2午 3晚 4其他）",
        "「修正」按鈕 → 修改營養素",
        "「加入快取」按鈕 → 存為常用食物",
    ]
    await update.message.reply_text("\n".join(lines))


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
    app.add_handler(CommandHandler("r", _cmd_report))
    app.add_handler(CommandHandler("f", _cmd_food_cache))
    app.add_handler(CommandHandler("h", _cmd_help))
    app.add_handler(CallbackQueryHandler(_handle_cache_callback, pattern="^cache:"))
    app.add_handler(CallbackQueryHandler(_handle_mtype_callback, pattern="^mtype:"))
    app.add_handler(CallbackQueryHandler(_handle_correct_callback, pattern="^correct:"))
    app.add_handler(MessageHandler(filters.PHOTO, _handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))

    logger.info("Bot started. Listening for chat_id=%s", TELEGRAM_CHAT_ID)
    app.run_polling()


if __name__ == "__main__":
    main()
