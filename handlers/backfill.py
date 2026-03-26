from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

MEAL_TYPE_MAP = {
    "1": "早餐",
    "2": "午餐",
    "3": "晚餐",
    "4": "其他",
}


def _format_number(n: int | float) -> str:
    return f"{int(n):,}"


def _format_date(d: date) -> str:
    return f"{d.month}/{d.day}"


def parse_backfill_args(text: str, *, allow_empty_food: bool = False) -> tuple[str, date, str]:
    """解析補記指令參數。

    Args:
        text: /b 後面的文字。
        allow_empty_food: 若為 True（照片場景），允許 food_text 為空。

    Returns:
        (meal_type, target_date, food_text)

    Raises:
        ValueError: 輸入無法解析或缺少食物描述（當 allow_empty_food=False）。
    """
    text = text.strip()
    if not text:
        raise ValueError("請輸入食物描述")

    tokens = text.split()

    # 1) 餐別：第一個 token 若為 1-4
    meal_type = "其他"
    if tokens and tokens[0] in MEAL_TYPE_MAP:
        meal_type = MEAL_TYPE_MAP[tokens.pop(0)]

    # 2) 日期：最後一個 token 若為合法 MMDD
    now_tw = datetime.now(TW_TZ)
    target_date = (now_tw - timedelta(days=1)).date()

    if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
        mmdd = tokens.pop()
        try:
            parsed = datetime.strptime(f"2000{mmdd}", "%Y%m%d")
            candidate = date(now_tw.year, parsed.month, parsed.day)
        except ValueError:
            raise ValueError(f"日期格式錯誤：{mmdd}")
        if candidate >= now_tw.date():
            try:
                candidate = date(now_tw.year - 1, parsed.month, parsed.day)
            except ValueError:
                raise ValueError(f"日期格式錯誤：{mmdd}")
        target_date = candidate

    # 3) 食物描述
    food_text = " ".join(tokens)
    if not food_text and not allow_empty_food:
        raise ValueError("請輸入食物描述")

    return meal_type, target_date, food_text


def date_to_recorded_at(target_date: date) -> str:
    """將目標日期轉為 UTC ISO 字串（台灣正午 12:00 → UTC 04:00）。"""
    tw_noon = datetime(
        target_date.year, target_date.month, target_date.day,
        12, 0, 0, tzinfo=TW_TZ,
    )
    return tw_noon.astimezone(timezone.utc).isoformat()


async def cmd_backfill(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """處理 /b 文字補記指令。"""
    raw = update.message.text
    after_cmd = raw.split(None, 1)[1] if len(raw.split(None, 1)) > 1 else ""

    try:
        meal_type, target_date, food_text = parse_backfill_args(after_cmd)
    except ValueError as e:
        await update.message.reply_text(
            f"{e}\n\n用法：/b [1-4] 食物描述 [MMDD]\n"
            f"例：/b 雞排便當\n"
            f"例：/b 2 雞排便當 0325"
        )
        return

    await _process_backfill(update, context, meal_type, target_date, text=food_text)


async def handle_backfill_photo(update: "Update", context: "ContextTypes.DEFAULT_TYPE"):
    """處理 /b 照片補記（caption 以 /b 開頭）。"""
    caption = update.message.caption or ""
    after_cmd = caption.split(None, 1)[1] if len(caption.split(None, 1)) > 1 else ""

    if after_cmd:
        try:
            meal_type, target_date, food_text = parse_backfill_args(
                after_cmd, allow_empty_food=True,
            )
        except ValueError as e:
            await update.message.reply_text(
                f"{e}\n\n照片補記用法：caption 輸入 /b [1-4] [MMDD]"
            )
            return
    else:
        meal_type = "其他"
        target_date = (datetime.now(TW_TZ) - timedelta(days=1)).date()
        food_text = ""

    # 下載照片
    from config import MEDIA_DIR

    photo = update.message.photo[-1]
    file = await photo.get_file()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    local_path = MEDIA_DIR / f"{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(local_path))
    logger.info("Backfill photo saved to %s", local_path)

    await _process_backfill(
        update, context, meal_type, target_date,
        text=food_text or None, image_path=str(local_path),
    )


async def _process_backfill(
    update: "Update",
    context: "ContextTypes.DEFAULT_TYPE",
    meal_type: str,
    target_date: date,
    text: str | None = None,
    image_path: str | None = None,
):
    """補記的共用流程：AI 分析 → DB → 回覆。"""
    from config import MEDIA_DIR, get_calorie_goal
    from services.ai import analyze_food
    from services.db import get_meals_by_date, insert_meal
    from services.nutrition import format_macros

    processing_msg = await update.message.reply_text("分析中...")

    try:
        result = await analyze_food(text=text, image_path=image_path)
    except Exception:
        logger.exception("AI analysis failed (backfill)")
        await processing_msg.edit_text("分析失敗，請重試。")
        return

    recorded_at = date_to_recorded_at(target_date)

    image_expires = None
    if image_path:
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        image_expires = expires.isoformat()

    row = insert_meal(
        meal_type=meal_type,
        description=result.description,
        calories=result.calories,
        protein_g=result.protein_g,
        carbs_g=result.carbs_g,
        fat_g=result.fat_g,
        raw_input=text or "(照片)",
        ai_confidence=result.confidence,
        has_image=image_path is not None,
        image_path=image_path,
        image_expires_at=image_expires,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        thinking_tokens=result.thinking_tokens,
        recorded_at=recorded_at,
    )

    # 該日累計（非 get_today_meals）
    day_meals = get_meals_by_date(target_date)
    total_cal = sum(m["calories"] for m in day_meals)
    date_str = _format_date(target_date)

    lines = [
        f"補記完成（{date_str}）",
        f"🍱 {result.description}",
        f"熱量：{_format_number(result.calories)} kcal",
        *format_macros(result.protein_g, result.carbs_g, result.fat_g),
        f"餐別：{meal_type}",
        "",
        f"{date_str} 累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
    ]

    if result.confidence == "low":
        lines.append("")
        lines.append("⚠️ 份量不確定，以一人份估算")

    if result.note:
        lines.append(f"📝 {result.note}")

    from handlers.food_cache import make_meal_buttons

    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=make_meal_buttons(row["id"]),
    )

    context.user_data["last_meal_id"] = row["id"]
    context.user_data["last_meal_message_id"] = processing_msg.message_id
