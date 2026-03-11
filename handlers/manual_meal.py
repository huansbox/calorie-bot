"""手動輸入食物記錄（不經 AI 分析）。

支援兩種格式：
1. 貼上 Bot 回覆：偵測 🍱 + 熱量： 自動解析
2. @ 前綴：@品名 熱量 [蛋白質 碳水 脂肪]
"""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def is_bot_reply_format(text: str) -> bool:
    """判斷是否為 Bot 回覆格式（含 🍱 和 熱量：）。"""
    return "🍱" in text and "熱量：" in text


def is_at_manual_input(text: str) -> bool:
    """判斷是否為 @ 手動輸入格式。"""
    return text.strip().startswith("@") and len(text.strip()) > 1


def parse_bot_reply(text: str) -> dict:
    """解析 Bot 回覆格式，擷取品名與營養素。

    預期格式：
        🍱 {description}
        熱量：{calories} kcal
        蛋白質：{protein}g　碳水：{carbs}g　脂肪：{fat}g
    """
    desc_match = re.search(r"🍱\s*(.+)", text)
    cal_match = re.search(r"熱量：([\d,]+)\s*kcal", text)
    macro_match = re.search(
        r"蛋白質：([\d.]+)g\s*碳水：([\d.]+)g\s*脂肪：([\d.]+)g", text
    )

    if not desc_match or not cal_match:
        raise ValueError("無法解析 Bot 回覆格式")

    calories = int(cal_match.group(1).replace(",", ""))
    protein_g = float(macro_match.group(1)) if macro_match else 0.0
    carbs_g = float(macro_match.group(2)) if macro_match else 0.0
    fat_g = float(macro_match.group(3)) if macro_match else 0.0

    return {
        "description": desc_match.group(1).strip(),
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }


def parse_at_input(text: str) -> dict:
    """解析 @ 手動輸入格式。

    支援：
        @品名 熱量
        @品名 熱量 蛋白質 碳水 脂肪
    """
    content = text.strip()[1:].strip()  # 去掉 @

    # 從後面找數字，品名是前面的部分
    # 支援：@起司蛋餅 350 15 30 18 或 @御飯糰 280
    parts = content.rsplit(maxsplit=4)

    if len(parts) >= 5:
        # 嘗試：品名 熱量 蛋白質 碳水 脂肪
        name_parts, nums = parts[:-4], parts[-4:]
        try:
            calories = int(nums[0])
            protein_g = float(nums[1])
            carbs_g = float(nums[2])
            fat_g = float(nums[3])
            description = " ".join(name_parts) if name_parts else nums[0]
            return {
                "description": description,
                "calories": calories,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
            }
        except ValueError:
            pass

    if len(parts) >= 2:
        # 嘗試：品名 熱量
        name_parts, num = parts[:-1], parts[-1]
        try:
            calories = int(num)
            return {
                "description": " ".join(name_parts),
                "calories": calories,
                "protein_g": 0.0,
                "carbs_g": 0.0,
                "fat_g": 0.0,
            }
        except ValueError:
            pass

    raise ValueError(
        "格式錯誤，請使用：\n"
        "@品名 熱量\n"
        "@品名 熱量 蛋白質 碳水 脂肪"
    )


async def handle_manual_meal(update: Update, context: ContextTypes.DEFAULT_TYPE, data: dict):
    """共用的手動記錄流程：儲存 → 回覆。"""
    from config import DAILY_CALORIE_GOAL
    from handlers.meal import _infer_meal_type, _format_number
    from services.db import get_today_meals, insert_meal

    meal_type = _infer_meal_type()

    row = insert_meal(
        meal_type=meal_type,
        description=data["description"],
        calories=data["calories"],
        protein_g=data["protein_g"],
        carbs_g=data["carbs_g"],
        fat_g=data["fat_g"],
        raw_input=update.message.text,
        ai_confidence="manual",
        input_tokens=0,
        output_tokens=0,
    )

    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    lines = [
        "記錄完成（手動）",
        f"🍱 {data['description']}",
        f"熱量：{_format_number(data['calories'])} kcal",
        f"蛋白質：{data['protein_g']:.0f}g　碳水：{data['carbs_g']:.0f}g　脂肪：{data['fat_g']:.0f}g",
        f"餐別：{meal_type}",
        "",
        f"今日累計：{_format_number(total_cal)} / {_format_number(DAILY_CALORIE_GOAL)} kcal",
    ]

    msg = await update.message.reply_text("\n".join(lines))

    context.user_data["last_meal_id"] = row["id"]
    context.user_data["last_meal_message_id"] = msg.message_id


async def handle_bot_reply_paste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理貼上 Bot 回覆格式的手動記錄。"""
    try:
        data = parse_bot_reply(update.message.text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    await handle_manual_meal(update, context, data)


async def handle_at_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 @ 前綴的手動輸入。"""
    try:
        data = parse_at_input(update.message.text)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    await handle_manual_meal(update, context, data)


async def handle_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /m 指令的手動輸入。"""
    text = update.message.text
    # 把 /m 轉成 @ 格式，複用同一個解析器
    content = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
    if not content:
        await update.message.reply_text(
            "用法：\n"
            "/m 品名 熱量\n"
            "/m 品名 熱量 蛋白質 碳水 脂肪"
        )
        return

    try:
        data = parse_at_input("@" + content)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    await handle_manual_meal(update, context, data)
