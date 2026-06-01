import logging
from datetime import date, datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from services.db import get_latest_weight_before, get_weight_moving_avg, upsert_weight

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


async def cmd_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /w <數字> 指令，記錄體重（upsert：當天一筆，覆蓋既有含自動 coros 筆）。"""
    if not context.args:
        await update.message.reply_text("用法：/w 74.2")
        return

    try:
        weight = float(context.args[0])
    except ValueError:
        await update.message.reply_text("請輸入數字，例如：/w 74.2")
        return

    today = datetime.now(TW_TZ).date()
    # 「上次」取當天之前最近一筆 → 同日重複 /w 時 prev 指向前一天，不是剛被覆蓋的自己
    prev = get_latest_weight_before(today)

    upsert_weight(weight, log_date=today, source="manual")

    avg = get_weight_moving_avg(7)
    if avg:
        lines = [f"⚖️ 體重記錄：{weight} kg（7日均線 {avg:.1f}）"]
    else:
        lines = [f"⚖️ 體重記錄：{weight} kg"]

    if prev:
        prev_kg = float(prev["weight_kg"])
        prev_date = date.fromisoformat(prev["log_date"])
        days_ago = (today - prev_date).days
        diff = weight - prev_kg
        sign = "+" if diff > 0 else ""
        lines.append(f"上次：{prev_kg} kg（{days_ago} 天前）")
        lines.append(f"變化：{sign}{diff:.1f} kg")

    await update.message.reply_text("\n".join(lines))
