import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import DAILY_CALORIE_GOAL
from services.db import get_today_meals, get_today_tdee

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


def _fmt(n: int) -> str:
    return f"{n:,}"


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /today 指令，顯示今日完整記錄。"""
    meals = get_today_meals()
    now_tw = datetime.now(TW_TZ)
    date_str = now_tw.strftime("%-m/%-d") if not _is_windows() else now_tw.strftime("%#m/%#d")

    if not meals:
        await update.message.reply_text(f"📋 今日記錄（{date_str}）\n\n尚無記錄")
        return

    lines = [f"📋 今日記錄（{date_str}）", ""]

    total_cal = 0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    for m in meals:
        meal_type = m["meal_type"] or "其他"
        desc = m["description"] or ""
        cal = m["calories"] or 0
        lines.append(f"{meal_type}　{desc}　{_fmt(cal)} kcal")
        total_cal += cal
        total_protein += float(m["protein_g"] or 0)
        total_carbs += float(m["carbs_g"] or 0)
        total_fat += float(m["fat_g"] or 0)

    lines.append("")
    lines.append(f"攝取合計：{_fmt(total_cal)} kcal")
    lines.append(f"蛋白質：{total_protein:.0f}g　碳水：{total_carbs:.0f}g　脂肪：{total_fat:.0f}g")

    # TDEE
    tdee_row = get_today_tdee()
    lines.append("")
    if tdee_row:
        tdee = tdee_row["tdee_kcal"]
        deficit = total_cal - tdee
        lines.append(f"總消耗（TDEE）：{_fmt(tdee)} kcal")
        if deficit <= 0:
            lines.append(f"熱量缺口：{_fmt(deficit)} kcal")
        else:
            lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")
    else:
        lines.append("今日尚未記錄 TDEE（/tdee <數字>）")

    lines.append("")
    lines.append(f"目標攝取參考：{_fmt(DAILY_CALORIE_GOAL)} kcal")

    await update.message.reply_text("\n".join(lines))


def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"
