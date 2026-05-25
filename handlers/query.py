import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from services.dates import parse_mmdd
from services.db import (
    get_meals_by_date,
    get_tdee_by_date,
    get_today_meals,
    get_today_tdee,
)
from services.format import format_meal_groups
from services.nutrition import format_macros

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))


def _fmt(n: int) -> str:
    return f"{n:,}"


async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /s 指令，顯示今日或指定日期完整記錄。

    用法：
        /s         → 今日
        /s MMDD    → 指定日期（今天/未來自動退回上一年）
    """
    args = context.args
    now_tw = datetime.now(TW_TZ)

    if args:
        try:
            target_date = parse_mmdd(args[0], now_tw=now_tw)
        except ValueError as e:
            await update.message.reply_text(f"{e}\n\n用法：/s [MMDD]")
            return
        meals = get_meals_by_date(target_date)
        tdee_row = get_tdee_by_date(target_date)
        is_today = False
    else:
        target_date = now_tw.date()
        meals = get_today_meals()
        tdee_row = get_today_tdee()
        is_today = True

    date_str = target_date.strftime("%-m/%-d") if not _is_windows() else target_date.strftime("%#m/%#d")

    if not meals:
        await update.message.reply_text(f"📋 記錄（{date_str}）\n\n尚無記錄")
        return

    lines = [f"📋 記錄（{date_str}）"]

    total_cal = 0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0
    for m in meals:
        total_cal += m["calories"] or 0
        total_protein += float(m["protein_g"] or 0)
        total_carbs += float(m["carbs_g"] or 0)
        total_fat += float(m["fat_g"] or 0)

    lines.extend(format_meal_groups(meals))

    lines.append("")
    lines.append(f"攝取合計：{_fmt(total_cal)} kcal")
    lines.extend(format_macros(total_protein, total_carbs, total_fat))

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
        if is_today:
            lines.append("今日尚未記錄 TDEE（/t <活動消耗> n）")
        else:
            lines.append(f"{date_str} 未記錄 TDEE")

    await update.message.reply_text("\n".join(lines))


def _is_windows() -> bool:
    import sys
    return sys.platform == "win32"
