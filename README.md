# Calorie Bot

Telegram 體重管理 Bot，傳食物照片或文字自動分析營養素並記錄。支援 Gemini / Claude 雙 AI 引擎切換。

## 功能

| 操作 | 說明 |
|---|---|
| 傳文字 | `滷肉飯加蛋` → AI 分析並記錄 |
| 傳照片 | 直接傳食物照片，可附 caption 補充 |
| `/w 74.2` | 記錄體重 |
| `/t 290` | 記錄昨日活動消耗（自動加 BMR 算 TDEE） |
| `/t 290 n` | 記錄今日活動消耗 |
| `/s` | 查看今日所有記錄與摘要 |
| `/u` | 刪除最後一筆食物記錄 |
| 回覆 `1`-`4` | 修改最後一筆的餐別（1早餐 2午餐 3晚餐 4其他） |

## 自動排程

| 時間 | 內容 |
|---|---|
| 每日 08:00 | 推播昨日攝取摘要 |
| 每週日 08:05 | 推播 API 用量與費用 |
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
| `SUPABASE_KEY` | Supabase Publishable Key | 是 |
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
# 本機上傳
scp -r *.py pyproject.toml uv.lock .env handlers services root@<VPS_IP>:/home/botuser/calorie-bot/

# VPS 上
su - botuser
cd ~/calorie-bot
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
# 本機
scp -r *.py handlers services root@<VPS_IP>:/home/botuser/calorie-bot/

# VPS
chown -R botuser:botuser /home/botuser/calorie-bot
systemctl restart calorie-bot
```
