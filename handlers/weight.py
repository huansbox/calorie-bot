import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from services.db import get_previous_weight, get_weight_moving_avg, insert_weight

logger = logging.getLogger(__name__)


async def cmd_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /w <數字> 指令，記錄體重。"""
    if not context.args:
        await update.message.reply_text("用法：/w 74.2")
        return

    try:
        weight = float(context.args[0])
    except ValueError:
        await update.message.reply_text("請輸入數字，例如：/w 74.2")
        return

    # 先取上一筆（插入前的最新一筆就是「上次」）
    prev = get_previous_weight()
    # 這裡邏輯：insert 前的 last 就是 previous
    from services.db import get_last_weight

    prev = get_last_weight()

    insert_weight(weight)

    avg = get_weight_moving_avg(7)
    if avg:
        lines = [f"⚖️ 體重記錄：{weight} kg（7日均線 {avg:.1f}）"]
    else:
        lines = [f"⚖️ 體重記錄：{weight} kg"]

    if prev:
        prev_kg = float(prev["weight_kg"])
        prev_date = datetime.fromisoformat(prev["recorded_at"])
        days_ago = (datetime.now(prev_date.tzinfo) - prev_date).days
        diff = weight - prev_kg
        sign = "+" if diff > 0 else ""
        lines.append(f"上次：{prev_kg} kg（{days_ago} 天前）")
        lines.append(f"變化：{sign}{diff:.1f} kg")

    await update.message.reply_text("\n".join(lines))
