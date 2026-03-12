import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import get_calorie_goal, set_calorie_goal

logger = logging.getLogger(__name__)


async def cmd_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /g 指令，查看或修改每日攝取目標。"""
    args = update.message.text.split()

    if len(args) < 2:
        await update.message.reply_text(f"目前每日攝取目標：{get_calorie_goal():,} kcal")
        return

    try:
        value = int(args[1])
    except ValueError:
        await update.message.reply_text("請輸入數字，例如 /g 1800")
        return

    if value < 500 or value > 10000:
        await update.message.reply_text("目標範圍：500 ~ 10,000 kcal")
        return

    set_calorie_goal(value)
    await update.message.reply_text(f"每日攝取目標已更新為 {value:,} kcal")
    logger.info("Calorie goal updated to %d", value)
