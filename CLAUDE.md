# Calorie Bot

## 專案概述

個人用 Telegram 體重管理 Bot。使用者透過 Telegram 傳食物照片或文字，AI Vision 自動分析三大營養素並記錄至 Supabase。

## 技術架構

- **語言**: Python 3.12
- **套件管理**: uv
- **Bot 框架**: python-telegram-bot v22 (polling 模式)
- **AI**: 雙引擎架構，透過 AI_PROVIDER 切換
  - Gemini 2.5 Pro (預設，JSON mode 強制合法輸出)
  - Claude Sonnet 4.6 (備選，parse_ai_response 容錯解析)
- **資料庫**: Supabase (PostgreSQL) — meals, weight_logs, daily_tdee 三張表
- **排程**: APScheduler (AsyncIOScheduler)
- **部署**: RackNerd VPS (Ubuntu 24.04, systemd 管理)

## 檔案結構

```
main.py              # 進入點，註冊 handlers + 排程，auth_check decorator
config.py            # 環境變數讀取 (dotenv)，含 BMR 設定
scheduler.py         # 每日 08:00 昨日摘要 + 週日 08:05 API 週報 + 03:00 照片清理
handlers/
  meal.py            # 食物記錄核心 (文字/照片 → AI 分析 → DB → 回覆)，含 token 追蹤
  weight.py          # /w 體重記錄
  tdee.py            # /t 每日消耗記錄（預設昨天，加 n 記今天，自動加 BMR）
  query.py           # /s 今日摘要
  correction.py      # 餐別覆蓋 (1-4) + /u 撤銷
  manual_meal.py     # 手動記錄 (Bot 回覆貼上 / @前綴 / /m 指令)，免 AI 分析
services/
  ai.py              # AI 雙引擎 (Gemini/Claude)，SYSTEM_PROMPT，parse_ai_response (有單元測試)
  db.py              # Supabase CRUD (meals, weight_logs, daily_tdee)
tests/
  test_ai.py         # parse_ai_response 單元測試 (7 cases)
  test_manual_meal.py # 手動記錄解析函式測試
```

## 開發慣例

- 所有變更開 feature branch，合併回 main
- Commit 遵循 Conventional Commits
- 單元測試涵蓋 services/ai.py (JSON 解析) 與 handlers/manual_meal.py (輸入解析)
- Windows 開發環境需設 PYTHONIOENCODING=utf-8

## 關鍵設計決策

- **polling 模式** (非 webhook)：簡單、不需公開 URL
- **auth_check decorator**：單人 Bot，所有 handler 統一用 chat_id 驗證
- **餐別**：早餐/午餐/晚餐/其他，依台灣時間自動推斷，使用者可用 1-4 覆蓋
- **TDEE = BMR + 活動消耗**：BMR 固定值存 .env，/t 只需輸入手錶活動消耗
- **/t 預設記昨天**：符合早上看手錶輸入昨日消耗的使用情境
- **AI 雙引擎**：AI_PROVIDER 環境變數切換 gemini/claude，共用同一份 SYSTEM_PROMPT
- **Gemini JSON mode**：response_mime_type + response_json_schema 強制合法 JSON 輸出
- **Claude JSON 容錯**：parse_ai_response 處理 code fence、畸形 JSON (如 `>` 替代 `:`)
- **圖片 24 小時過期**：暫存 data/media/，排程清理
- **API 費用追蹤**：每筆 meal 記錄 input/output tokens，週日推播週報
- **手動記錄**：三種免 AI 輸入方式 — 貼上 Bot 回覆、@前綴快速輸入、/m 指令

## 未來想做

- 週報 / 月報統計
- 條碼掃描（拍條碼照片 → pyzbar 解碼 → 查食品資料庫）
- 運動單次消耗記錄
- 語音輸入
- Web Dashboard
- 食物資料庫：個人常吃快取、衛福部 TFDA API、自訂食物別名
- Bot 指令修改每日攝取目標（/g），免改 .env 重啟

## 待辦：設定本機 SSH key 連 VPS

目標：讓 Claude Code 能直接 SSH 進 VPS 執行部署（git pull + restart service）。

步驟：
1. 本機產生 SSH key：`ssh-keygen -t ed25519 -C "calobot-vps"`
2. 把公鑰加到 VPS：`ssh-copy-id root@107.175.30.172`（需使用者輸入一次 VPS 密碼）
3. 驗證連線：`ssh root@107.175.30.172 "echo connected"`
4. 部署指令：`ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"`

注意：步驟 2 需要使用者互動輸入密碼，Claude Code 無法代勞。

## VPS 資訊

- IP: 107.175.30.172
- SSH: root@107.175.30.172
- Bot 執行帳號: botuser
- 專案路徑: /home/botuser/calorie-bot
- 服務名稱: calorie-bot.service
