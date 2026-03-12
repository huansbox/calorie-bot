"""週報功能：營養攝取 / 消耗收支 / 體重趨勢。"""

import logging
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from services.db import (
    get_meals_by_week,
    get_tdee_by_week,
    get_weight_range,
)

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]


def _fmt(n: int) -> str:
    return f"{n:,}"


def _date_str(d: date) -> str:
    if os.name == "nt":
        return f"{d.month}/{d.day}"
    return d.strftime("%-m/%-d")


def _get_last_week_range() -> tuple[date, date]:
    """取得上週一～上週日的日期範圍。"""
    today = datetime.now(TW_TZ).date()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def _get_current_week_range() -> tuple[date, date]:
    """取得本週一～今天的日期範圍。"""
    today = datetime.now(TW_TZ).date()
    this_monday = today - timedelta(days=today.weekday())
    return this_monday, today


def _build_daily_table(
    start: date,
    end: date,
    meals: list[dict],
    tdee_rows: list[dict],
) -> list[str]:
    """產生每日收支表格。"""
    daily_cal: dict[date, int] = defaultdict(int)
    for m in meals:
        rec = datetime.fromisoformat(m["recorded_at"])
        tw_date = (rec + timedelta(hours=8)).date()
        daily_cal[tw_date] += m["calories"] or 0

    tdee_map: dict[str, int] = {r["date"]: r["tdee_kcal"] for r in tdee_rows}

    lines = ["── 每日收支 ──"]
    d = start
    while d <= end:
        wd = WEEKDAY_NAMES[d.weekday()]
        ds = _date_str(d)
        intake = daily_cal.get(d, 0)
        tdee = tdee_map.get(d.isoformat())

        if tdee is not None:
            gap = intake - tdee
            mark = " ✅" if gap <= 0 else ""
            lines.append(f"{ds} {wd}　{_fmt(intake)}　{_fmt(tdee)}　{gap:+,}{mark}")
        else:
            lines.append(f"{ds} {wd}　{_fmt(intake)}　--　--")

        d += timedelta(days=1)

    return lines


def _build_macro_section(meals: list[dict]) -> list[str]:
    """營養素平均佔比。"""
    total_p = sum(float(m["protein_g"] or 0) for m in meals)
    total_c = sum(float(m["carbs_g"] or 0) for m in meals)
    total_f = sum(float(m["fat_g"] or 0) for m in meals)
    total_cal = total_p * 4 + total_c * 4 + total_f * 9

    if total_cal == 0:
        return ["── 營養素結構 ──", "本週無記錄"]

    p_pct = round(total_p * 4 / total_cal * 100)
    c_pct = round(total_c * 4 / total_cal * 100)
    f_pct = round(total_f * 9 / total_cal * 100)

    return [
        "── 營養素結構 ──",
        f"🍗 蛋白質 {p_pct}%　🍚 碳水 {c_pct}%　🧈 脂肪 {f_pct}%",
    ]


def _build_meal_type_section(meals: list[dict]) -> list[str]:
    """正餐 vs 非正餐熱量佔比。"""
    regular = 0
    other = 0
    for m in meals:
        cal = m["calories"] or 0
        if m["meal_type"] in ("早餐", "午餐", "晚餐"):
            regular += cal
        else:
            other += cal

    total = regular + other
    if total == 0:
        return ["── 正餐 vs 非正餐 ──", "本週無記錄"]

    r_pct = round(regular / total * 100)
    o_pct = 100 - r_pct

    return [
        "── 正餐 vs 非正餐 ──",
        f"正餐（早午晚）：{r_pct}%　其他：{o_pct}%",
    ]


def _build_balance_section(meals: list[dict], tdee_rows: list[dict]) -> list[str]:
    """週累積收支。"""
    total_intake = sum(m["calories"] or 0 for m in meals)
    total_tdee = sum(r["tdee_kcal"] for r in tdee_rows)
    tdee_days = len(tdee_rows)

    lines = [
        "── 週累積收支 ──",
        f"總攝取：{_fmt(total_intake)} kcal",
    ]

    if tdee_days > 0:
        gap = total_intake - total_tdee
        lines.append(f"總消耗：{_fmt(total_tdee)} kcal（{tdee_days} 天有記錄）")
        lines.append(f"累積{'缺口' if gap <= 0 else '盈餘'}：{gap:+,} kcal")
    else:
        lines.append("本週未記錄 TDEE")

    return lines


def _build_weight_section(
    weights: list[dict],
    total_intake: int,
    total_tdee: int,
    tdee_days: int,
) -> list[str]:
    """體重預估 vs 實際。"""
    lines = ["── 體重預估 vs 實際 ──"]

    if tdee_days > 0:
        gap = total_intake - total_tdee
        estimated = gap / 7700
        lines.append(f"預估變化：{estimated:+.2f} kg（依缺口 ÷ 7700）")
    else:
        lines.append("預估變化：無法計算（無 TDEE 記錄）")

    if len(weights) >= 2:
        first = float(weights[0]["weight_kg"])
        last = float(weights[-1]["weight_kg"])
        diff = last - first
        lines.append(f"實際變化：{diff:+.1f} kg（{first:.1f} → {last:.1f}）")
    elif len(weights) == 1:
        lines.append(f"實際變化：僅一筆記錄（{float(weights[0]['weight_kg']):.1f} kg）")
    else:
        lines.append("實際變化：本週無體重記錄")

    return lines


def _build_wow_section(
    meals: list[dict],
    tdee_rows: list[dict],
    num_days: int,
    prev_meals: list[dict],
    prev_tdee_rows: list[dict],
) -> list[str]:
    """週對週比較。"""
    lines = ["── 週對週 ──"]

    if not prev_meals and not prev_tdee_rows:
        lines.append("上週無記錄")
        return lines

    def _avg(m: list[dict], t: list[dict], days: int) -> tuple[int, int | None, int | None]:
        avg_intake = round(sum(r["calories"] or 0 for r in m) / days) if days > 0 else 0
        if t:
            avg_tdee = round(sum(r["tdee_kcal"] for r in t) / days)
            avg_gap = avg_intake - avg_tdee
        else:
            avg_tdee = None
            avg_gap = None
        return avg_intake, avg_tdee, avg_gap

    this_avg = _avg(meals, tdee_rows, num_days)
    prev_avg = _avg(prev_meals, prev_tdee_rows, num_days)

    lines.append("　　　　　本週　　上週")
    lines.append(f"日均攝取　{_fmt(this_avg[0])}　{_fmt(prev_avg[0])}")

    if this_avg[1] is not None and prev_avg[1] is not None:
        lines.append(f"日均消耗　{_fmt(this_avg[1])}　{_fmt(prev_avg[1])}")
        lines.append(f"日均缺口　{this_avg[2]:+,}　{prev_avg[2]:+,}")
    elif this_avg[1] is not None:
        lines.append(f"日均消耗　{_fmt(this_avg[1])}　--")
    else:
        lines.append("日均消耗　--　--")

    return lines


def generate_report(start: date, end: date, label: str) -> str:
    """產生完整週報文字。"""
    meals = get_meals_by_week(start, end)
    tdee_rows = get_tdee_by_week(start, end)
    weights = get_weight_range(start, end)

    num_days = (end - start).days + 1

    # 上週同期
    prev_start = start - timedelta(days=7)
    prev_end = end - timedelta(days=7)
    prev_meals = get_meals_by_week(prev_start, prev_end)
    prev_tdee_rows = get_tdee_by_week(prev_start, prev_end)

    # 累積數值
    total_intake = sum(m["calories"] or 0 for m in meals)
    total_tdee = sum(r["tdee_kcal"] for r in tdee_rows)
    tdee_days = len(tdee_rows)

    sections = [
        [f"📊 {label}（{_date_str(start)} - {_date_str(end)}）"],
        _build_daily_table(start, end, meals, tdee_rows),
        _build_macro_section(meals),
        _build_meal_type_section(meals),
        _build_balance_section(meals, tdee_rows),
        _build_weight_section(weights, total_intake, total_tdee, tdee_days),
        _build_wow_section(meals, tdee_rows, num_days, prev_meals, prev_tdee_rows),
    ]

    return "\n\n".join("\n".join(s) for s in sections)


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /r 指令。/r = 上週週報，/r now = 本週至今。"""
    text = update.message.text
    parts = text.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""

    if arg == "now":
        start, end = _get_current_week_range()
        label = "本週至今"
    else:
        start, end = _get_last_week_range()
        label = "週報"

    report = generate_report(start, end, label)
    await update.message.reply_text(report)
