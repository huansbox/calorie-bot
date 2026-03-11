import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import BMR
from services.db import get_meals_by_date, upsert_tdee

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


def _fmt(n: int) -> str:
    return f"{n:,}"


async def cmd_tdee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /t <活動消耗> [n] 指令。預設記昨天，加 n 記今天。自動加上 BMR。"""
    if not context.args:
        await update.message.reply_text("用法：/t 290（記昨天）或 /t 290 n（記今天）")
        return

    try:
        active_cal = int(context.args[0])
    except ValueError:
        await update.message.reply_text("請輸入整數，例如：/t 290")
        return

    # 判斷記錄日期
    now_tw = datetime.now(TW_TZ)
    is_today = len(context.args) >= 2 and context.args[1].lower() == "n"
    target_date = now_tw.date() if is_today else (now_tw - timedelta(days=1)).date()

    tdee = BMR + active_cal
    upsert_tdee(tdee, target_date)

    # 計算該日攝取
    meals = get_meals_by_date(target_date)
    total_intake = sum(m["calories"] for m in meals)
    deficit = total_intake - tdee

    date_label = "今日" if is_today else "昨日"
    date_str = target_date.strftime("%#m/%#d") if __import__("os").name == "nt" else target_date.strftime("%-m/%-d")

    lines = [
        f"🔥 {date_label}總消耗（{date_str}）：{_fmt(tdee)} kcal",
        f"　 BMR {_fmt(BMR)} + 活動 {_fmt(active_cal)}",
        f"攝取：{_fmt(total_intake)} kcal",
    ]

    if deficit <= 0:
        lines.append(f"熱量缺口：{_fmt(deficit)} kcal ✅")
    else:
        lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")

    await update.message.reply_text("\n".join(lines))
