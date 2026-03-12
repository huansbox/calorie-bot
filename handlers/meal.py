import logging
import os
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import MEDIA_DIR, get_calorie_goal
from handlers.food_cache import make_cache_button
from services.ai import analyze_food
from services.db import get_today_meals, insert_meal
from services.nutrition import format_macros

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

MEAL_TIME_RANGES = [
    (5, 11, "早餐"),
    (11, 15, "午餐"),
    (15, 22, "晚餐"),
    # 22-5 → 其他（default）
]


def _infer_meal_type() -> str:
    """依台灣時間推斷餐別。"""
    hour = datetime.now(TW_TZ).hour
    for start, end, name in MEAL_TIME_RANGES:
        if start <= hour < end:
            return name
    return "其他"


def _format_number(n: int | float) -> str:
    """數字加千分位逗號。"""
    return f"{int(n):,}"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理純文字食物記錄。"""
    text = update.message.text
    await _process_food(update, context, text=text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理照片（可附 caption）食物記錄。"""
    photo = update.message.photo[-1]  # 最高解析度
    file = await photo.get_file()

    # 下載到 data/media/
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ext = "jpg"
    local_path = MEDIA_DIR / f"{photo.file_unique_id}.{ext}"
    await file.download_to_drive(str(local_path))
    logger.info("Photo saved to %s", local_path)

    caption = update.message.caption or None
    await _process_food(update, context, text=caption, image_path=str(local_path))


async def _process_food(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str | None = None,
    image_path: str | None = None,
):
    """共用的食物分析 → 儲存 → 回覆流程。"""
    # 先回覆提示，讓使用者知道在處理中
    processing_msg = await update.message.reply_text("分析中...")

    try:
        result = await analyze_food(text=text, image_path=image_path)
    except Exception:
        logger.exception("AI analysis failed")
        await processing_msg.edit_text("分析失敗，請重試。")
        return

    meal_type = _infer_meal_type()

    # 計算圖片過期時間
    image_expires = None
    if image_path:
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        image_expires = expires.isoformat()

    # 寫入 DB
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
    )

    # 計算今日累計
    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    # 組合回覆
    lines = [
        "記錄完成",
        f"🍱 {result.description}",
        f"熱量：{_format_number(result.calories)} kcal",
        *format_macros(result.protein_g, result.carbs_g, result.fat_g),
        f"餐別：{meal_type}",
        "",
        f"今日累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
    ]

    if result.confidence == "low":
        lines.append("")
        lines.append("⚠️ 份量不確定，以一人份估算")

    if result.note:
        lines.append(f"📝 {result.note}")

    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=make_cache_button(row["id"]),
    )

    # 儲存 meal_id 到 context，供 correction handler 使用
    context.user_data["last_meal_id"] = row["id"]
    context.user_data["last_meal_message_id"] = processing_msg.message_id
