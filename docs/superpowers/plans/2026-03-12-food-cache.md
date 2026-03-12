# 食物快取 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓常吃的食物可以快速記錄，跳過 AI 分析，透過 Inline Button 加入快取或 `/f` 指令管理，數字 11-99 快速選取

**Architecture:** Supabase 新增 `food_cache` 表儲存常用食物。`handlers/food_cache.py` 統一處理 `/f` 指令、callback button、數字選取。現有 meal/manual_meal 回覆加上 Inline Button。

**Tech Stack:** Python 3.12, python-telegram-bot v22 (InlineKeyboardButton, CallbackQueryHandler), Supabase

**DB schema:** 需在 Supabase SQL Editor 手動建立 `food_cache` 表（見 Task 1）

---

## Chunk 1: DB 層 + 核心 handler

### Task 1: 建立 food_cache 表（手動）

**提醒使用者**在 Supabase SQL Editor 執行：

```sql
CREATE TABLE food_cache (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    description TEXT NOT NULL UNIQUE,
    calories INTEGER NOT NULL,
    protein_g REAL NOT NULL,
    carbs_g REAL NOT NULL,
    fat_g REAL NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

- [ ] **Step 1: 請使用者在 Supabase 建表**
- [ ] **Step 2: 確認表已建立**

---

### Task 2: DB CRUD 函式

**Files:**
- Modify: `services/db.py`

- [ ] **Step 1: 在 `services/db.py` 末尾新增 food_cache CRUD**

```python
# ── Food Cache ────────────────────────────────────────

MAX_CACHE_ITEMS = 89  # 編號 11-99


def get_all_cache() -> list[dict]:
    """取得所有快取食物，依建立時間排序。"""
    result = (
        supabase.table("food_cache")
        .select("*")
        .order("created_at")
        .execute()
    )
    return result.data


def get_cache_by_index(index: int) -> dict | None:
    """依編號取得快取（11 = 第一筆）。"""
    offset = index - 11
    if offset < 0:
        return None
    result = (
        supabase.table("food_cache")
        .select("*")
        .order("created_at")
        .limit(1)
        .offset(offset)
        .execute()
    )
    return result.data[0] if result.data else None


def insert_cache(description: str, calories: int, protein_g: float, carbs_g: float, fat_g: float) -> dict:
    """新增快取食物。"""
    row = {
        "description": description,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
    }
    result = supabase.table("food_cache").insert(row).execute()
    logger.info("Inserted cache: %s", description)
    return result.data[0]


def delete_cache_by_name(description: str) -> bool:
    """依品名刪除快取，回傳是否有刪除。"""
    result = supabase.table("food_cache").delete().eq("description", description).execute()
    return len(result.data) > 0


def cache_exists(description: str) -> bool:
    """檢查品名是否已在快取中。"""
    result = (
        supabase.table("food_cache")
        .select("id")
        .eq("description", description)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


def get_meal_by_id(meal_id: str) -> dict | None:
    """依 ID 取得單筆 meal 記錄。"""
    result = (
        supabase.table("meals")
        .select("*")
        .eq("id", meal_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None
```

- [ ] **Step 2: Commit**

```bash
git add services/db.py
git commit -m "feat: add food_cache CRUD functions"
```

---

### Task 3: food_cache handler — `/f` 指令 + callback + 數字選取

**Files:**
- Create: `handlers/food_cache.py`

- [ ] **Step 1: 建立 `handlers/food_cache.py`**

```python
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import get_calorie_goal
from handlers.manual_meal import parse_at_input
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


def make_cache_button(meal_id: str) -> InlineKeyboardMarkup:
    """建立「加入快取」Inline Button。"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("加入快取", callback_data=f"cache:{meal_id}")]
    ])


def is_cache_number(text: str) -> bool:
    """判斷是否為快取編號（11-99 純數字）。"""
    s = text.strip()
    if not s.isdigit():
        return False
    n = int(s)
    return 11 <= n <= 99


async def handle_cache_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理數字 11-99 的快取記錄。"""
    index = int(update.message.text.strip())
    item = get_cache_by_index(index)

    if not item:
        await update.message.reply_text("查無快取項目，請先 /f 查看清單")
        return

    meal_type = _infer_meal_type()

    row = insert_meal(
        meal_type=meal_type,
        description=item["description"],
        calories=item["calories"],
        protein_g=item["protein_g"],
        carbs_g=item["carbs_g"],
        fat_g=item["fat_g"],
        raw_input=update.message.text,
        ai_confidence="high",
        input_tokens=0,
        output_tokens=0,
    )

    today_meals = get_today_meals()
    total_cal = sum(m["calories"] for m in today_meals)

    lines = [
        "記錄完成（快取）",
        f"🍱 {item['description']}",
        f"熱量：{_format_number(item['calories'])} kcal",
        *format_macros(item["protein_g"], item["carbs_g"], item["fat_g"]),
        f"餐別：{meal_type}",
        "",
        f"今日累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
    ]

    msg = await update.message.reply_text("\n".join(lines))
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
            await update.message.reply_text("📋 食物快取\n\n尚無快取，按記錄下方「加入快取」按鈕或用 /f 品名 熱量 蛋白質 碳水 脂肪 新增")
            return
        lines = ["📋 食物快取", ""]
        for i, item in enumerate(items):
            lines.append(f"{i + 11}. {item['description']} {_format_number(item['calories'])}kcal")
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
    except ValueError as e:
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
        await query.answer("已在快取中")
        await query.edit_message_reply_markup(reply_markup=None)
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

    await query.answer(f"已加入快取：{meal['description']}")
    await query.edit_message_reply_markup(reply_markup=None)
```

- [ ] **Step 2: Commit**

```bash
git add handlers/food_cache.py
git commit -m "feat: add food_cache handler (list/add/delete/callback/number select)"
```

---

## Chunk 2: 整合到現有系統

### Task 4: 修改 meal.py 和 manual_meal.py — 加 Inline Button

**Files:**
- Modify: `handlers/meal.py:106-124`
- Modify: `handlers/manual_meal.py:136-149`

- [ ] **Step 1: 修改 `handlers/meal.py` — `_process_food` 回覆加按鈕**

在 import 區加上：
```python
from handlers.food_cache import make_cache_button
```

修改 `await processing_msg.edit_text(...)` 加上 `reply_markup`：
```python
    await processing_msg.edit_text(
        "\n".join(lines),
        reply_markup=make_cache_button(row["id"]),
    )
```

- [ ] **Step 2: 修改 `handlers/manual_meal.py` — `handle_manual_meal` 回覆加按鈕**

在 `handle_manual_meal` 函式內的 import 區加上：
```python
    from handlers.food_cache import make_cache_button
```

修改 `await update.message.reply_text(...)` 加上 `reply_markup`：
```python
    msg = await update.message.reply_text(
        "\n".join(lines),
        reply_markup=make_cache_button(row["id"]),
    )
```

- [ ] **Step 3: Commit**

```bash
git add handlers/meal.py handlers/manual_meal.py
git commit -m "feat: add inline cache button to meal and manual_meal replies"
```

---

### Task 5: 修改 main.py — 註冊 handler + 文字判斷

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 新增 import**

```python
from telegram.ext import CallbackQueryHandler
from handlers.food_cache import cmd_food_cache, handle_cache_callback, handle_cache_number, is_cache_number
```

- [ ] **Step 2: 新增 auth_check wrapper**

```python
@auth_check
async def _cmd_food_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_food_cache(update, context)


@auth_check
async def _handle_cache_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_cache_callback(update, context)
```

- [ ] **Step 3: 在 `_handle_text` 中插入快取數字判斷**

在 `is_meal_type_correction` 判斷之後、`is_bot_reply_format` 之前插入：

```python
    if is_cache_number(text):
        await handle_cache_number(update, context)
        return
```

- [ ] **Step 4: 註冊 handler**

在 `app.add_handler(CommandHandler("g", _cmd_goal))` 之後加上：
```python
    app.add_handler(CommandHandler("f", _cmd_food_cache))
    app.add_handler(CallbackQueryHandler(_handle_cache_callback))
```

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: register food_cache handlers in main.py"
```

---

### Task 6: 全量測試 + 部署

- [ ] **Step 1: 跑全部測試**

Run: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 如有失敗，修復後重跑**

- [ ] **Step 3: 合併到 main，push，部署 VPS**

```bash
git checkout main
git merge feat/food-cache --no-ff
git push origin main
ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"
```

- [ ] **Step 4: 在 Telegram 測試**

驗證項目：
1. `/f` → 顯示空清單
2. 傳食物文字 → AI 分析回覆下方出現「加入快取」按鈕
3. 按「加入快取」→ 成功加入
4. `/f` → 顯示快取清單
5. 傳 `11` → 從快取記錄
6. `/f 品名 delete` → 刪除
7. 再按同一個按鈕 → 「已在快取中」
