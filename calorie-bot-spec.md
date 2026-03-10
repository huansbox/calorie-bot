# Calorie Bot — Claude Code 實作 Spec

## 專案概述

個人使用的 Telegram 體重管理 Bot。使用者透過 Telegram 傳送食物照片或文字，AI 自動分析三大營養素並記錄。每日睡前記錄 TDEE，計算熱量缺口。

**核心設計原則：使用者操作越少越好。**

---

## 技術選型

| 項目 | 選擇 |
|---|---|
| 語言 | Python 3.12+ |
| 套件管理 | `uv` |
| Bot 框架 | `python-telegram-bot` v21 |
| AI | Anthropic Claude API（claude-sonnet-4-5，Vision） |
| 資料庫 | Supabase（PostgreSQL） |
| 排程 | APScheduler |
| 部署 | VPS 常駐或本機常駐 |

---

## 資料庫 Schema

```sql
-- 飲食記錄
CREATE TABLE meals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  meal_type TEXT CHECK (meal_type IN ('早餐','午餐','下午茶','晚餐','宵夜')),
  description TEXT,
  calories INTEGER,
  protein_g NUMERIC(6,1),
  carbs_g NUMERIC(6,1),
  fat_g NUMERIC(6,1),
  raw_input TEXT,
  has_image BOOLEAN DEFAULT false,
  ai_confidence TEXT CHECK (ai_confidence IN ('high','medium','low')),
  image_path TEXT,
  image_expires_at TIMESTAMPTZ
);

-- 體重記錄
CREATE TABLE weight_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  weight_kg NUMERIC(5,2)
);

-- 每日消耗記錄
CREATE TABLE daily_tdee (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  date DATE NOT NULL UNIQUE,
  tdee_kcal INTEGER
);
```

---

## 指令與輸入設計

### 食物記錄（主要功能）

任何非指令的輸入都視為食物記錄：

| 輸入方式 | 範例 |
|---|---|
| 純文字 | `滷肉飯中碗加一顆蛋` |
| 純照片 | （直接傳照片） |
| 照片＋文字 | 照片 ＋ `大碗` |

Bot 自動呼叫 Claude Vision 分析，回覆：

```
✅ 記錄完成
🍱 滷肉飯（中碗）＋滷蛋
熱量：680 kcal
蛋白質：28g　碳水：88g　脂肪：20g
餐別：午餐

今日累計：1,240 / 2,000 kcal
```

若 AI 信心度為 low，回覆末尾附註：
```
⚠️ 份量不確定，以一人份估算
```

### 餐別自動判斷

依訊息送出時間自動推斷，不需使用者輸入：

| 時間 | 餐別 |
|---|---|
| 05:00–10:59 | 早餐 |
| 11:00–14:59 | 午餐 |
| 15:00–17:59 | 下午茶 |
| 18:00–21:59 | 晚餐 |
| 22:00–04:59 | 宵夜 |

若判斷錯誤，使用者可輸入數字覆蓋：

```
1 → 早餐
2 → 午餐
3 → 下午茶
4 → 晚餐
5 → 宵夜
```

覆蓋方式：回覆該筆記錄訊息並輸入數字，Bot 更新餐別。

### 指令清單

| 指令 | 功能 | 範例 |
|---|---|---|
| `/w <數字>` | 記錄體重（kg） | `/w 74.2` |
| `/tdee <數字>` | 記錄今日總消耗（kcal） | `/tdee 2340` |
| `/today` | 查詢今日完整記錄 | `/today` |
| `/undo` | 覆蓋最後一筆食物記錄 | `/undo`（再傳新內容） |

#### `/w` 回覆格式
```
⚖️ 體重記錄：74.2 kg
上次：74.8 kg（3 天前）
變化：-0.6 kg
```

#### `/tdee` 回覆格式
```
🔥 今日總消耗記錄：2,340 kcal
攝取：1,840 kcal
熱量缺口：-500 kcal ✅
```

#### `/today` 回覆格式
```
📋 今日記錄（3/10）

早餐　燕麥粥　350 kcal
午餐　滷肉飯＋滷蛋　680 kcal
下午茶　拿鐵（中）　210 kcal

攝取合計：1,240 kcal
蛋白質：62g　碳水：168g　脂肪：38g

總消耗（TDEE）：2,340 kcal
熱量缺口：-1,100 kcal

目標攝取參考：2,000 kcal
```

#### `/undo` 流程
1. 使用者輸入 `/undo`
2. Bot 回覆：「請重新傳送正確的食物資訊（文字或照片），將覆蓋上一筆記錄。」
3. 使用者傳送新內容 → 整筆覆蓋，重新分析

---

## AI Prompt 設計

```
你是一個營養分析助理，專門分析台灣常見食物。

分析使用者提供的食物（照片和/或文字描述），回傳 JSON。

規則：
- 以台灣常見餐廳的一人份份量為預設基準
- 文字有補充份量資訊時（如「大碗」、「兩份」）優先採用
- 無法確定份量時，以一人份估算並標記 confidence 為 low
- 永遠給出估算值，不拒絕分析

只回傳以下 JSON，不要任何其他文字或 markdown：
{
  "description": "食物的簡短中文描述（15字以內）",
  "calories": 620,
  "protein_g": 22.0,
  "carbs_g": 85.0,
  "fat_g": 18.0,
  "confidence": "high|medium|low",
  "note": "不確定之處說明，無則空字串"
}
```

---

## 照片處理

- 收到照片後，下載暫存至本機 `data/media/`
- 傳給 Claude API 分析後，在 DB 記錄 `image_expires_at = now() + 24 hours`
- 每日排程清理：刪除 `image_expires_at < now()` 的檔案，並將 DB 的 `image_path` 設為 null

---

## 每日推播

- 時間：每日 21:00（台灣時間，UTC+8）
- 條件：當天有至少一筆食物記錄才推播，否則跳過
- 格式：

```
📊 今日摘要（3/10）

攝取：1,840 kcal　目標參考：2,000 kcal
蛋白質：88g　碳水：210g　脂肪：62g
記錄筆數：4 餐

總消耗（TDEE）：2,340 kcal
熱量缺口：-500 kcal ✅
```

若未記錄 TDEE，消耗那行改為：
```
今日尚未記錄 TDEE（/tdee <數字>）
```

---

## 環境變數（.env）

```
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=        # 只接受這個 chat id（單人使用）
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
DAILY_CALORIE_GOAL=2000  # 攝取參考目標
PUSH_HOUR=21             # 每日推播小時（台灣時間）
DATA_DIR=./data
```

---

## 檔案結構

```
calorie-bot/
├── main.py                  # 進入點，啟動 bot 與排程
├── config.py                # 讀取環境變數
├── scheduler.py             # APScheduler，每日推播 + 照片清理
├── handlers/
│   ├── meal.py              # 處理食物輸入（照片/文字）
│   ├── correction.py        # 處理餐別覆蓋、/undo
│   ├── weight.py            # 處理 /w 指令
│   ├── tdee.py              # 處理 /tdee 指令
│   └── query.py             # 處理 /today 指令
├── services/
│   ├── ai.py                # Claude API 呼叫與 prompt
│   └── db.py                # Supabase 讀寫（meals, weight_logs, daily_tdee）
├── data/
│   └── media/               # 照片暫存（24小時後清除）
├── pyproject.toml
└── .env
```

---

## 實作順序建議

1. 環境建置（uv init、安裝套件、.env 設定）
2. Supabase 建立三張資料表
3. Bot 基礎接線（接收訊息、回覆）
4. `services/ai.py`：Claude Vision 呼叫與 JSON 解析
5. `services/db.py`：三張表的 CRUD
6. `handlers/meal.py`：核心功能，食物記錄完整流程
7. `handlers/weight.py` + `handlers/tdee.py`
8. `handlers/query.py`：`/today`
9. `handlers/correction.py`：餐別覆蓋 + `/undo`
10. `scheduler.py`：每日推播 + 照片清理
11. `main.py`：整合所有 handlers 與排程

---

## MVP 不包含（未來再加）

- 週報 / 月報
- 條碼掃描（包裝食品）
- 運動單次消耗記錄（目前用手錶 TDEE 總值）
- 語音輸入
- 多用戶支援
- Web Dashboard
