# Calorie Bot

Telegram 體重管理 Bot，傳食物照片或文字自動分析營養素並記錄。支援 Gemini / Claude 雙 AI 引擎切換。

## 功能

| 操作 | 說明 |
|---|---|
| 傳文字 | `滷肉飯加蛋` → AI 分析並記錄 |
| 傳照片 | 直接傳食物照片，可附 caption 補充 |
| `@品名 熱量` | 手動記錄，免 AI 分析（如 `@御飯糰 280`） |
| `@品名 熱量 蛋白質 碳水 脂肪` | 手動記錄含三大營養素 |
| 末尾加 `x2`, `x0.5` | 倍數記錄（如 `@養樂多 100 1 20 2 x2`、`11 x2`） |
| `/m 品名 熱量 ...` | 同 `@` 的指令版 |
| `/w 74.2` | 記錄體重 |
| `/t 290` | 記錄昨日活動消耗（自動加 BMR 算 TDEE） |
| `/t 290 n` | 記錄今日活動消耗 |
| `/s` | 查看今日所有記錄與摘要 |
| `/r` | 上週營養週報 |
| `/r now` | 本週至今累積 |
| `/g 1800` | 調整每日熱量目標（重啟回預設） |
| `/f` | 列出食物快取清單 |
| `/f 品名 熱量 ...` | 新增食物快取 |
| `/f 品名 delete` | 刪除食物快取 |
| 輸入 `11`-`99` | 以快取編號直接記錄 |
| `/u` | 刪除最後一筆食物記錄 |
| `/h` | 操作說明 |
| 回覆 `1`-`4` | 修改最後一筆的餐別（1早餐 2午餐 3晚餐 4其他） |
| 「修正」按鈕 | 修改 AI 分析結果的營養素數值 |

### 多道菜記錄技巧

迴轉壽司、鐵板燒等多道菜場景，不需要逐一拍照或列出每道菜。用簡短文字描述即可，AI 能從模糊描述估算：

```
迴轉壽司 大概12盤 主要鮭魚鮪魚
鐵板燒套餐 牛排雞腿海鮮 吃很飽
```

## 自動排程

| 時間 | 內容 |
|---|---|
| 每日 08:00 | 推播昨日攝取摘要 |
| 每週一 08:05 | 推播 API 用量與費用 |
| 每週一 08:10 | 推播上週營養週報 |
| 每日 03:00 | 清理過期照片 |

## 環境設置

### 1. 安裝依賴

```bash
uv sync
```

### 2. 設定環境變數

```bash
cp .env.example .env
```

填入：

| 變數 | 說明 | 必填 |
|---|---|---|
| `TELEGRAM_TOKEN` | BotFather 取得 | 是 |
| `TELEGRAM_CHAT_ID` | 你的 Telegram chat ID | 是 |
| `SUPABASE_URL` | Supabase Project URL | 是 |
| `SUPABASE_KEY` | Supabase Secret Key（Settings → API Keys） | 是 |
| `AI_PROVIDER` | `gemini` 或 `claude` (預設 gemini) | 否 |
| `GEMINI_API_KEY` | Google AI Studio 取得 | AI_PROVIDER=gemini 時必填 |
| `ANTHROPIC_API_KEY` | Anthropic Console 取得 | AI_PROVIDER=claude 時必填 |
| `DAILY_CALORIE_GOAL` | 每日攝取目標 kcal (預設 2000) | 否 |
| `BMR` | 基礎代謝率 kcal (預設 1577) | 否 |
| `PUSH_HOUR` | 每日推播時間 (預設 8) | 否 |
| `DATA_DIR` | 照片暫存目錄 (預設 ./data) | 否 |

### 3. Supabase 建表

到 Supabase SQL Editor 執行 `calorie-bot-spec.md` 中的 CREATE TABLE SQL，再加上：

```sql
ALTER TABLE meals ADD COLUMN input_tokens INTEGER DEFAULT 0;
ALTER TABLE meals ADD COLUMN output_tokens INTEGER DEFAULT 0;
```

### 4. 本機啟動

```bash
.venv/Scripts/python.exe main.py   # Windows
.venv/bin/python main.py           # Linux
```

## 測試

```bash
uv run pytest tests/ -v
```

## VPS 部署 (RackNerd / Ubuntu)

### 首次部署

```bash
# VPS 上
su - botuser
cd ~/calorie-bot
git clone https://github.com/huansbox/calorie-bot.git .
cp /path/to/.env .env   # 手動放入環境變數檔
mkdir -p data/media
uv sync
```

### systemd 服務

```bash
# /etc/systemd/system/calorie-bot.service
[Unit]
Description=Calorie Telegram Bot
After=network.target

[Service]
User=botuser
WorkingDirectory=/home/botuser/calorie-bot
ExecStart=/home/botuser/calorie-bot/.venv/bin/python main.py
Restart=always
RestartSec=10
Environment=PYTHONIOENCODING=utf-8

[Install]
WantedBy=multi-user.target
```

### 管理指令

```bash
systemctl status calorie-bot     # 查看狀態
journalctl -u calorie-bot -f     # 即時 log
systemctl restart calorie-bot    # 重啟
systemctl stop calorie-bot       # 停止
```

### 更新部署

```bash
ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"
```
