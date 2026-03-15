import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import get_calorie_goal
from handlers.manual_meal import _apply_multiplier, parse_at_input
from handlers.meal import _infer_meal_type, _format_number
from services.db import (
    MAX_CACHE_ITEMS,
    cache_exists,
    delete_cache_by_name,
    get_all_cache,
    get_cache_by_index,
    get_meal_by_id,
    get_today_meals,
    insert_cache,
    insert_meal,
)
from services.nutrition import calc_calories, format_macros

logger = logging.getLogger(__name__)


def make_meal_buttons(meal_id: str) -> InlineKeyboardMarkup:
    """建立記錄完成後的 Inline Buttons：加入快取 + 改為其他 + 修正。"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("加入快取", callback_data=f"cache:{meal_id}"),
            InlineKeyboardButton("改為其他", callback_data=f"mtype:{meal_id}"),
            InlineKeyboardButton("修正", callback_data=f"correct:{meal_id}"),
        ]
    ])


_CACHE_RE = re.compile(r'^(\d+)(?:\s*[xX](\d+(?:\.\d+)?))?\s*$')


def is_cache_number(text: str) -> bool:
    """判斷是否為快取編號（11-99，可帶乘數如 11 x2）。"""
    match = _CACHE_RE.match(text.strip())
    if not match:
        return False
    n = int(match.group(1))
    return 11 <= n <= 99


async def handle_cache_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理數字 11-99 的快取記錄（可帶乘數）。"""
    match = _CACHE_RE.match(update.message.text.strip())
    index = int(match.group(1))
    multiplier = float(match.group(2) or 1)
    item = get_cache_by_index(index)

    if not item:
        await update.message.reply_text("查無快取項目，請先 /f 查看清單")
        return

    meal_type = _infer_meal_type()

    # 套用乘數
    values = _apply_multiplier({
        "description": item["description"],
        "calories": item["calories"],
        "protein_g": item["protein_g"],
        "carbs_g": item["carbs_g"],
        "fat_g": item["fat_g"],
    }, multiplier)

    row = insert_meal(
        meal_type=meal_type,
        description=values["description"],
        calories=values["calories"],
        protein_g=values["protein_g"],
        carbs_g=values["carbs_g"],
        fat_g=values["fat_g"],
        raw_input=update.message.text,
        ai_confidence="high",
        input_tokens=0,
        output_tokens=0,
    )

    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    lines = [
        "記錄完成（快取）",
        f"🍱 {values['description']}",
        f"熱量：{_format_number(values['calories'])} kcal",
        *format_macros(values["protein_g"], values["carbs_g"], values["fat_g"]),
        f"餐別：{meal_type}",
        "",
        f"今日累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
    ]

    cache_buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("改為其他", callback_data=f"mtype:{row['id']}"),
            InlineKeyboardButton("修正", callback_data=f"correct:{row['id']}"),
        ]
    ])
    msg = await update.message.reply_text("\n".join(lines), reply_markup=cache_buttons)
    context.user_data["last_meal_id"] = row["id"]
    context.user_data["last_meal_message_id"] = msg.message_id


async def cmd_food_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /f 指令：列出、新增、刪除快取。"""
    text = update.message.text
    parts = text.split(maxsplit=1)
    content = parts[1] if len(parts) > 1 else ""

    # /f → 列出
    if not content:
        items = get_all_cache()
        if not items:
            await update.message.reply_text(
                "📋 食物快取\n\n"
                "尚無快取，按記錄下方「加入快取」按鈕\n"
                "或用 /f 品名 熱量 蛋白質 碳水 脂肪 新增"
            )
            return
        lines = ["📋 食物快取", ""]
        for i, item in enumerate(items):
            p = round(item["protein_g"] or 0)
            c = round(item["carbs_g"] or 0)
            f = round(item["fat_g"] or 0)
            macro = f" P{p}/C{c}/F{f}" if (p or c or f) else ""
            lines.append(f"{i + 11}. {item['description']} {_format_number(item['calories'])}kcal{macro}")
        await update.message.reply_text("\n".join(lines))
        return

    # /f 品名 delete → 刪除
    if content.endswith(" delete"):
        name = content[:-7].strip()
        if delete_cache_by_name(name):
            await update.message.reply_text(f"已刪除快取：{name}")
        else:
            await update.message.reply_text(f"找不到快取：{name}")
        return

    # /f 品名 熱量 [蛋白質 碳水 脂肪] → 新增
    items = get_all_cache()
    if len(items) >= MAX_CACHE_ITEMS:
        await update.message.reply_text(f"快取已滿（上限 {MAX_CACHE_ITEMS} 筆），請先刪除不需要的項目")
        return

    try:
        data = parse_at_input("@" + content)
    except ValueError:
        await update.message.reply_text(
            "用法：\n"
            "/f 品名 熱量 蛋白質 碳水 脂肪\n"
            "/f 品名 delete"
        )
        return

    if cache_exists(data["description"]):
        await update.message.reply_text(f"已在快取中：{data['description']}")
        return

    if data["protein_g"] == 0 and data["carbs_g"] == 0 and data["fat_g"] == 0:
        calories = data["calories"]
    else:
        calories = calc_calories(data["protein_g"], data["carbs_g"], data["fat_g"])

    insert_cache(
        description=data["description"],
        calories=calories,
        protein_g=data["protein_g"],
        carbs_g=data["carbs_g"],
        fat_g=data["fat_g"],
    )
    await update.message.reply_text(f"已加入快取：{data['description']} {_format_number(calories)}kcal")


async def handle_cache_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 Inline Button callback：加入快取。"""
    query = update.callback_query

    data = query.data
    if not data.startswith("cache:"):
        await query.answer()
        return

    meal_id = data[6:]  # 去掉 "cache:" 前綴
    meal = get_meal_by_id(meal_id)
    if not meal:
        await query.answer("找不到記錄")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if cache_exists(meal["description"]):
        mtype_only = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("改為其他", callback_data=f"mtype:{meal_id}"),
                InlineKeyboardButton("修正", callback_data=f"correct:{meal_id}"),
            ]
        ])
        await query.answer("已在快取中")
        await query.edit_message_reply_markup(reply_markup=mtype_only)
        return

    items = get_all_cache()
    if len(items) >= MAX_CACHE_ITEMS:
        await query.answer("快取已滿", show_alert=True)
        return

    calories = calc_calories(meal["protein_g"], meal["carbs_g"], meal["fat_g"])
    insert_cache(
        description=meal["description"],
        calories=calories,
        protein_g=meal["protein_g"],
        carbs_g=meal["carbs_g"],
        fat_g=meal["fat_g"],
    )

    mtype_only = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("改為其他", callback_data=f"mtype:{meal_id}"),
            InlineKeyboardButton("修正", callback_data=f"correct:{meal_id}"),
        ]
    ])

    await query.answer(f"已加入快取：{meal['description']}")
    await query.edit_message_reply_markup(reply_markup=mtype_only)


async def handle_mtype_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 Inline Button callback：改為其他餐別。"""
    query = update.callback_query

    data = query.data
    if not data.startswith("mtype:"):
        await query.answer()
        return

    meal_id = data[6:]
    meal = get_meal_by_id(meal_id)
    if not meal:
        await query.answer("找不到記錄")
        await query.edit_message_reply_markup(reply_markup=None)
        return

    if meal["meal_type"] == "其他":
        await query.answer("已經是「其他」")
        return

    from services.db import update_meal

    update_meal(meal_id, {"meal_type": "其他"})

    # 更新訊息中的餐別文字
    old_text = query.message.text
    old_type = meal["meal_type"]
    new_text = old_text.replace(f"餐別：{old_type}", "餐別：其他")

    # 只保留「加入快取」按鈕
    cache_only = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("加入快取", callback_data=f"cache:{meal_id}"),
            InlineKeyboardButton("修正", callback_data=f"correct:{meal_id}"),
        ]
    ])

    await query.answer(f"已改為「其他」（原：{old_type}）")
    await query.edit_message_text(text=new_text, reply_markup=cache_only)
