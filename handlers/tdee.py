import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.db import get_today_meals, upsert_tdee

logger = logging.getLogger(__name__)


def _format_number(n: int) -> str:
    return f"{n:,}"


async def cmd_tdee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /tdee <數字> 指令，記錄今日總消耗。"""
    if not context.args:
        await update.message.reply_text("用法：/tdee 2340")
        return

    try:
        tdee = int(context.args[0])
    except ValueError:
        await update.message.reply_text("請輸入整數，例如：/tdee 2340")
        return

    upsert_tdee(tdee)

    # 計算今日攝取
    today_meals = get_today_meals()
    total_intake = sum(m["calories"] for m in today_meals)
    deficit = total_intake - tdee

    lines = [
        f"🔥 今日總消耗記錄：{_format_number(tdee)} kcal",
        f"攝取：{_format_number(total_intake)} kcal",
    ]

    if deficit <= 0:
        lines.append(f"熱量缺口：{_format_number(deficit)} kcal ✅")
    else:
        lines.append(f"熱量盈餘：+{_format_number(deficit)} kcal")

    await update.message.reply_text("\n".join(lines))
