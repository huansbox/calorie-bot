import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import MEDIA_DIR
from services.ai import analyze_food, push_primary_alert
from services.db import get_today_meals, insert_meal
from services.nutrition import format_macros

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

# 相簿（media group）聚合：Telegram 把一次傳的 N 張照片拆成 N 個獨立 message，
# 只有第一個帶 caption，靠 media_group_id 串起來。收到第一張後等這麼久（秒）
# 沒有新的同組照片進來，才視為整組到齊、合併成一次判讀。
MEDIA_GROUP_WAIT = 2.0

MEAL_TIME_RANGES = [
    (5 * 60, 10 * 60 + 30, "早餐"),       # 05:00-10:30
    (11 * 60, 14 * 60 + 30, "午餐"),       # 11:00-14:30
    (16 * 60 + 30, 21 * 60, "晚餐"),       # 16:30-21:00
]


def _infer_meal_type() -> str:
    """依台灣時間推斷餐別。"""
    now = datetime.now(TW_TZ)
    minutes = now.hour * 60 + now.minute
    for start, end, name in MEAL_TIME_RANGES:
        if start <= minutes < end:
            return name
    return "其他"


def _format_number(n: int | float) -> str:
    """數字加千分位逗號。"""
    return f"{int(n):,}"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理純文字食物記錄。"""
    text = update.message.text
    await _process_food(update, context, text=text)


async def _download_photo(update: Update) -> str:
    """下載訊息中最高解析度的照片到 data/media/，回傳本機路徑。"""
    photo = update.message.photo[-1]
    file = await photo.get_file()

    os.makedirs(MEDIA_DIR, exist_ok=True)
    local_path = MEDIA_DIR / f"{photo.file_unique_id}.jpg"
    await file.download_to_drive(str(local_path))
    logger.info("Photo saved to %s", local_path)
    return str(local_path)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理照片（可附 caption）食物記錄；同一相簿的多張照片合併成一筆。"""
    local_path = await _download_photo(update)
    caption = update.message.caption or None
    group_id = update.message.media_group_id

    if group_id is None:
        await _process_food(update, context, text=caption, image_paths=[local_path])
        return

    groups = context.chat_data.setdefault("media_groups", {})
    entry = groups.get(group_id)
    if entry is None:
        # 這組的第一張：先回「分析中」給即時回饋，再起一個收集任務等其餘照片
        processing_msg = await update.message.reply_text("分析中...")
        groups[group_id] = entry = {
            "paths": [],
            "caption": None,
            "processing_msg": processing_msg,
        }
        asyncio.create_task(_flush_media_group(update, context, group_id))

    entry["paths"].append(local_path)
    if caption and not entry["caption"]:
        entry["caption"] = caption


async def _flush_media_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE, group_id: str
):
    """等同組照片到齊（連續兩次檢查張數不變）後，合併成一次判讀。"""
    groups = context.chat_data["media_groups"]
    last_count = -1
    while True:
        entry = groups.get(group_id)
        if entry is None:  # 理論上不會發生（只有本任務會 pop）
            return
        count = len(entry["paths"])
        if count == last_count:
            break
        last_count = count
        await asyncio.sleep(MEDIA_GROUP_WAIT)

    entry = groups.pop(group_id)
    logger.info("Media group %s: %d 張照片合併分析", group_id, len(entry["paths"]))
    await _process_food(
        update,
        context,
        text=entry["caption"],
        image_paths=entry["paths"],
        processing_msg=entry["processing_msg"],
    )


async def _process_food(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str | None = None,
    image_paths: list[str] | None = None,
    processing_msg=None,
):
    """共用的食物分析 → 儲存 → 回覆流程。"""
    # 先回覆提示，讓使用者知道在處理中（相簿路徑已在收到第一張時先回過）
    if processing_msg is None:
        processing_msg = await update.message.reply_text("分析中...")

    try:
        result = await analyze_food(text=text, image_paths=image_paths)
    except Exception:
        logger.exception("AI analysis failed")
        await push_primary_alert(update.message.reply_text)
        await processing_msg.edit_text("分析失敗，請重試。")
        return

    await push_primary_alert(update.message.reply_text)

    meal_type = _infer_meal_type()

    # 計算圖片過期時間
    paths = image_paths or []
    image_expires = None
    if paths:
        expires = datetime.now(timezone.utc) + timedelta(hours=24)
        image_expires = expires.isoformat()

    # 寫入 DB（相簿多張路徑以逗號串接存同一欄，清理排程會拆開逐一刪）
    row = insert_meal(
        meal_type=meal_type,
        description=result.description,
        calories=result.calories,
        protein_g=result.protein_g,
        carbs_g=result.carbs_g,
        fat_g=result.fat_g,
        raw_input=text or ("(照片)" if len(paths) <= 1 else f"(照片 x{len(paths)})"),
        ai_confidence=result.confidence,
        has_image=bool(paths),
        image_path=",".join(paths) or None,
        image_expires_at=image_expires,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        thinking_tokens=result.thinking_tokens,
        ai_provider=result.provider,
        ai_model=result.ai_model,
        note=result.note,
    )

    # 計算今日累計
    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    # 組合回覆
    model_tag = f" · {result.ai_model}" if result.ai_model else ""
    lines = [
        f"記錄完成{model_tag}",
        f"🍱 {result.description}",
        f"熱量：{_format_number(result.calories)} kcal",
        *format_macros(result.protein_g, result.carbs_g, result.fat_g),
        f"餐別：{meal_type}",
        "",
        f"今日累計：{_format_number(total_cal)} kcal",
    ]

    if result.confidence == "low":
        lines.append("")
        lines.append("⚠️ 低信心估算，誤差可能較大")

    if result.note:
        lines.append(f"📝 {result.note}")

    from handlers.food_cache import make_meal_buttons

    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=make_meal_buttons(row["id"]),
    )

    # 儲存 meal_id 到 context，供 correction handler 使用
    context.user_data["last_meal_id"] = row["id"]
    context.user_data["last_meal_message_id"] = processing_msg.message_id
