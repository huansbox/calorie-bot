import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.db import delete_meal, get_last_meal, get_meal_by_id, get_today_meals, update_meal

logger = logging.getLogger(__name__)

MEAL_TYPE_MAP = {
    "1": "早餐",
    "2": "午餐",
    "3": "晚餐",
    "4": "其他",
}


def is_meal_type_correction(text: str) -> bool:
    """判斷是否為餐別覆蓋指令（數字 1-4）。"""
    return text.strip() in MEAL_TYPE_MAP


async def handle_meal_type_correction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理餐別覆蓋：使用者回覆記錄訊息並輸入 1-5。"""
    text = update.message.text.strip()
    new_type = MEAL_TYPE_MAP[text]

    meal_id = context.user_data.get("last_meal_id")
    if not meal_id:
        await update.message.reply_text("找不到可修改的記錄")
        return

    update_meal(meal_id, {"meal_type": new_type})
    await update.message.reply_text(f"已將餐別更新為：{new_type}")


async def handle_correct_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理「修正」Inline Button：進入修正模式。"""
    query = update.callback_query
    data = query.data
    if not data.startswith("correct:"):
        await query.answer()
        return

    meal_id = data[8:]
    meal = get_meal_by_id(meal_id)
    if not meal:
        await query.answer("找不到記錄")
        return

    context.user_data["pending_correction"] = meal_id
    await query.answer()
    await query.message.reply_text(
        "請輸入修正值：\n"
        "品名 熱量 蛋白質 碳水 脂肪\n"
        "或 品名 熱量"
    )


async def handle_correction_input(update: Update, context: ContextTypes.DEFAULT_TYPE, meal_id: str):
    """處理修正模式的文字輸入：解析並更新記錄。"""
    from config import get_calorie_goal
    from handlers.manual_meal import parse_at_input
    from handlers.meal import _format_number
    from services.nutrition import format_macros

    text = update.message.text.strip()
    data = parse_at_input("@" + text)  # ValueError 由呼叫端捕捉

    meal = get_meal_by_id(meal_id)
    if not meal:
        await update.message.reply_text("找不到記錄，可能已被刪除")
        return

    updates = {
        "description": data["description"],
        "calories": data["calories"],
        "protein_g": data["protein_g"],
        "carbs_g": data["carbs_g"],
        "fat_g": data["fat_g"],
    }
    update_meal(meal_id, updates)

    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    lines = [
        "已修正",
        f"🍱 {data['description']}",
        f"熱量：{_format_number(data['calories'])} kcal",
        *format_macros(data["protein_g"], data["carbs_g"], data["fat_g"]),
        "",
        f"今日累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
    ]

    from handlers.food_cache import make_meal_buttons

    msg = await update.message.reply_text(
        "\n".join(lines),
        reply_markup=make_meal_buttons(meal_id),
    )
    context.user_data["last_meal_id"] = meal_id
    context.user_data["last_meal_message_id"] = msg.message_id


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /undo 指令，刪除最後一筆並等待重新輸入。"""
    last = get_last_meal()
    if not last:
        await update.message.reply_text("沒有可撤銷的記錄")
        return

    desc = last["description"] or "未知"
    meal_id = last["id"]

    delete_meal(meal_id)
    context.user_data.pop("last_meal_id", None)

    await update.message.reply_text(
        f"已刪除：{desc}\n請重新傳送正確的食物資訊（文字或照片），將作為新記錄。"
    )
