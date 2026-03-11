import logging

from telegram import Update
from telegram.ext import ContextTypes

from services.db import delete_meal, get_last_meal, update_meal

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
