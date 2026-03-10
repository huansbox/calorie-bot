# Calorie Bot

## 專案概述

個人用 Telegram 體重管理 Bot。使用者透過 Telegram 傳食物照片或文字，Claude Vision 自動分析三大營養素並記錄至 Supabase。

## 技術架構

- **語言**: Python 3.12
- **套件管理**: uv
- **Bot 框架**: python-telegram-bot v22 (polling 模式)
- **AI**: Anthropic Claude API (claude-sonnet-4-6, Vision)
- **資料庫**: Supabase (PostgreSQL) — meals, weight_logs, daily_tdee 三張表
- **排程**: APScheduler (AsyncIOScheduler)
- **部署**: RackNerd VPS (Ubuntu 24.04, systemd 管理)

## 檔案結構

```
main.py              # 進入點，註冊 handlers + 排程，auth_check decorator
config.py            # 環境變數讀取 (dotenv)
scheduler.py         # 每日 21:00 推播 + 03:00 照片清理
handlers/
  meal.py            # 食物記錄核心 (文字/照片 → AI 分析 → DB → 回覆)
  weight.py          # /w 體重記錄
  tdee.py            # /tdee 每日消耗記錄
  query.py           # /today 今日摘要
  correction.py      # 餐別覆蓋 (1-5) + /undo
services/
  ai.py              # Claude API 呼叫, parse_ai_response (有單元測試)
  db.py              # Supabase CRUD (meals, weight_logs, daily_tdee)
tests/
  test_ai.py         # parse_ai_response 單元測試 (7 cases)
```

## 開發慣例

- 所有變更開 feature branch，合併回 main
- Commit 遵循 Conventional Commits
- 僅 services/ai.py 的 JSON 解析有單元測試
- Windows 開發環境需設 PYTHONIOENCODING=utf-8

## 關鍵設計決策

- **polling 模式** (非 webhook)：簡單、不需公開 URL
- **auth_check decorator**：單人 Bot，所有 handler 統一用 chat_id 驗證
- **餐別自動推斷**：依台灣時間 (UTC+8) 判斷，使用者可用 1-5 覆蓋
- **AI JSON 容錯**：parse_ai_response 處理 code fence、畸形 JSON (如 `>` 替代 `:`)
- **圖片 24 小時過期**：暫存 data/media/，排程清理

## VPS 資訊

- IP: 107.175.30.172
- User: botuser
- 專案路徑: /home/botuser/calorie-bot
- 服務名稱: calorie-bot.service
