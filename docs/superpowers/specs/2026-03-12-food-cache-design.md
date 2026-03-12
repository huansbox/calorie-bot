# 食物快取功能設計

## 目標

讓常吃的食物可以快速記錄，跳過 AI 分析，省 API 費用並確保一致性。

## 功能概覽

### 1. 加入快取

兩種方式：

**A) Inline Button（主要）**
- 每則食物記錄回覆（AI 分析 / 手動記錄）下方帶一個「加入快取」按鈕
- 按下後，將該筆記錄的 description、protein_g、carbs_g、fat_g 存入 `food_cache` 表
- calories 由 `calc_calories()` 計算，不另外傳入
- 回覆「已加入快取：{品名}」
- 若 description 已存在 food_cache，回覆「已在快取中」
- 按鈕**不出現在**快取記錄回覆（避免重複加入）

**B) `/f` 指令手動建立**
- `/f 公司便當 800 30 90 25` — 新增快取
- 解析邏輯直接複用 `parse_at_input`（把 `/f` 替換為 `@`，與 `/m` 做法相同）
- 適用於 AI 沒分析過但你想預設的食物

### 2. 列出快取

- `/f` — 列出所有快取食物，編號從 11 開始
- 顯示格式：
  ```
  📋 食物快取

  11. 公司便當 800kcal
  12. 7-11 御飯糰 280kcal
  13. 早餐店蛋餅 350kcal
  ```
- 上限 89 筆（編號 11-99），超過時拒絕新增並提示「快取已滿」

### 3. 快取記錄

- 傳送 `11`-`99` 的純數字，Bot 查 food_cache 對應項目
- 有匹配 → 直接記錄，回覆格式同一般記錄，標註「快取」
- **無匹配 → 回覆「查無快取項目，請先 /f 查看清單」，不 fallback 到 AI**

### 4. 刪除快取

- `/f 公司便當 delete` — 刪除指定品名的快取

## DB Schema

新增 `food_cache` 表：

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

- `description` 設 UNIQUE，避免重複加入
- `calories` 存 `calc_calories()` 計算後的值，方便列表顯示
- 編號不存 DB，由查詢順序動態產生（ORDER BY created_at，11 = 第一筆）

## 文字 handler 判斷順序

```
1. 餐別覆蓋（1-4）
2. 快取選擇（11-99 純數字 → 查 food_cache，無匹配則回覆錯誤）
3. Bot 回覆貼上
4. @ 手動輸入
5. AI 分析
```

判斷條件：`text.strip()` 為純數字且 11 ≤ int(text) ≤ 99 時進入步驟 2。

## Inline Button 實作

- 使用 python-telegram-bot 的 `InlineKeyboardButton` + `CallbackQueryHandler`
- callback_data 格式：`cache:{meal_id}`（UUID 36 字元 + 前綴 6 字元 = 42 bytes，未超 64-byte 限制）
- 按下按鈕時，從 meals 表讀取該筆的 description、protein_g、carbs_g、fat_g，寫入 food_cache
- `_process_food` 的 `processing_msg.edit_text()` 需同時帶 `reply_markup=InlineKeyboardMarkup(...)` 參數，否則按鈕不會顯示
- `handle_manual_meal` 的 `reply_text()` 同樣帶 `reply_markup`

## 影響範圍

### 新增
- `handlers/food_cache.py` — `/f` 指令 handler + callback handler + 快取記錄
- `food_cache` 表（Supabase）

### 修改
- `main.py` — 註冊 `/f` CommandHandler + CallbackQueryHandler
- `main.py` 的 `_handle_text` — 在餐別覆蓋後、Bot 回覆前插入快取數字判斷
- `handlers/meal.py` — `_process_food` 的 `edit_text` 加上 `reply_markup`（Inline Button）
- `handlers/manual_meal.py` — `handle_manual_meal` 的 `reply_text` 加上 `reply_markup`
- `services/db.py` — 新增 food_cache CRUD 函式

## 不做的事

- 不做自動比對（模糊匹配容易誤判）
- 不做照片快取（只快取文字 description 與營養素）
- 不做快取更新（要改就先刪再建）
- 不做 description 正規化（大小寫、全半形視為不同品名）
