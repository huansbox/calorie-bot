# Calorie Bot

## 專案概述

個人用 Telegram 體重管理 Bot。使用者透過 Telegram 傳食物照片或文字，AI Vision 自動分析三大營養素並記錄至 Supabase。

## 技術架構

- **語言**: Python 3.12
- **套件管理**: uv
- **Bot 框架**: python-telegram-bot v22 (polling 模式，HTTPXRequest 自訂 timeout: read/write 20s, connect 10s)
- **AI**: Gemini 優先 + claude -p CLI 自動 fallback
  - Gemini 2.5 Pro (預設，JSON mode 強制合法輸出)
  - claude -p CLI (fallback，走 Max 訂閱零費用，透過 subprocess 呼叫)
  - Claude Sonnet 4.6 API (備選，AI_PROVIDER=claude 時使用)
- **資料庫**: Supabase (PostgreSQL) — meals（含 ai_provider 欄位）, weight_logs, daily_tdee, food_cache 四張表，全部啟用 RLS，使用 Secret Key 繞過
- **排程**: APScheduler (AsyncIOScheduler) — 每日 08:00 昨日摘要 + 週一 08:05 API 週報 + 週一 08:10 營養週報 + 03:00 照片清理
- **密鑰管理**: 1Password — 本機 `op run` + VPS Service Account，`.env` 只存 `op://` 參照
- **部署**: RackNerd VPS (Ubuntu 24.04, systemd + `op run`)

## 檔案結構

```
main.py              # 進入點，註冊 handlers + 排程，auth_check decorator
config.py            # 環境變數讀取 (dotenv)，含 BMR 設定
scheduler.py         # 每日 08:00 昨日摘要 + 週一 08:05 API 週報 + 週一 08:10 營養週報 + 03:00 照片清理
handlers/
  meal.py            # 食物記錄核心 (文字/照片 → AI 分析 → DB → 回覆)，含 token 追蹤
  weight.py          # /w 體重記錄（含 7 日移動平均）
  tdee.py            # /t 每日消耗記錄（預設昨天，加 n 記今天，自動加 BMR）
  query.py           # /s 今日摘要
  correction.py      # 餐別覆蓋 (1-4) + /u 撤銷 + 「修正」按鈕手動修正營養素
  manual_meal.py     # 手動記錄 (Bot 回覆貼上 / @前綴 / /m 指令)，免 AI 分析
  goal.py            # /g 動態調整每日熱量目標
  food_cache.py      # 食物快取：Inline Button 加入、/f 管理、數字 11-99 快速記錄
  report.py          # /r 週報 + /r now 本週至今，週一自動推播
  backfill.py        # /b 補記過去日期的食物（預設昨天，支援 MMDD 日期 + 1-4 餐別）
services/
  ai.py              # AI 引擎 (Gemini/Claude CLI/Claude API)，SYSTEM_PROMPT，parse_ai_response (有單元測試)
  db.py              # Supabase CRUD (meals, weight_logs, daily_tdee, food_cache)，含體重移動平均
  nutrition.py       # 營養素計算 (三大營養素→熱量) + 格式化 (含百分比)
tests/
  test_ai.py         # parse_ai_response 單元測試 (12 cases，含 confidence 數字轉換)
  test_manual_meal.py # 手動記錄解析函式測試 (28 cases)
  test_backfill.py   # 補記解析 + UTC 換算測試 (24 cases)
  test_nutrition.py  # 營養素計算與格式化測試 (5 cases)
  test_cost.py       # API 費用計算測試 (3 cases，Gemini/Claude/claude-cli 費率)
  test_food_cache.py # parse_cache_number / is_cache_number 測試 (13 cases)
  test_correction.py # is_meal_type_correction 測試 (5 cases)
  test_report.py     # 週報 helper 測試 (24 cases，每日 map + 4 section)
```

## 開發慣例

- 所有變更開 feature branch，合併回 main
- Commit 遵循 Conventional Commits
- 單元測試涵蓋 services/ai.py、services/nutrition.py、handlers/manual_meal.py、handlers/backfill.py、handlers/food_cache.py (快取編號)、handlers/correction.py (餐別覆蓋)、handlers/report.py (週報 helper) 與 API 費用計算
- Windows 開發環境需設 PYTHONIOENCODING=utf-8
- 本機啟動: `op run --env-file .env -- python main.py`（需 1Password 桌面 App 解鎖）
- DB 查詢凡有 ORDER BY，必須包含唯一欄位（如 `id`）作為 tie-breaker，避免同 timestamp 排序不確定

## 關鍵設計決策

- **polling 模式** (非 webhook)：簡單、不需公開 URL
- **auth_check decorator**：單人 Bot，所有 handler 統一用 chat_id 驗證
- **餐別**：早餐(05:00-10:30)/午餐(11:00-14:30)/晚餐(16:30-21:00)/其他，依台灣時間分鐘級推斷，使用者可用 1-4 覆蓋
- **TDEE = BMR + 活動消耗**：BMR 固定值存 .env，/t 只需輸入手錶活動消耗
- **/t 預設記昨天**：符合早上看手錶輸入昨日消耗的使用情境
- **AI fallback 鏈**：Gemini API → claude -p CLI → 錯誤訊息。AI_PROVIDER=claude 時直接走 Claude API（無 fallback）
- **claude -p CLI**：透過 subprocess 呼叫 VPS 上的 Claude Code CLI，走 Max 訂閱零費用。有圖片時加 `--allowedTools Read`，timeout 60s
- **ai_provider 追蹤**：meals 表 `ai_provider` 欄位記錄判讀來源（gemini/claude-cli/claude-api/null），週報依 provider 分組計費
- **Gemini JSON mode**：response_mime_type + response_json_schema 強制合法 JSON 輸出
- **Claude JSON 容錯**：parse_ai_response 處理 code fence、畸形 JSON (如 `>` 替代 `:`)、confidence 數字→字串轉換
- **圖片 24 小時過期**：暫存 data/media/，排程清理
- **API 費用追蹤**：每筆 meal 記錄 input/output tokens + ai_provider，週一推播週報（依 provider 分組，claude-cli 費用為 $0）
- **ai_confidence 觀察中**：Gemini 幾乎不回 low/medium（Prompt 指示未被嚴格遵守），目前保留欄位觀察，未來可能移除。區分 AI vs 手動用 input_tokens=0 即可
- **手動記錄**：三種免 AI 輸入方式 — 貼上 Bot 回覆、@前綴快速輸入、/m 指令，末尾可加 x 倍數（如 x2, x0.5）
- **手動修正**：AI 分析回覆附「修正」按鈕，點擊後輸入正確值直接更新該筆記錄
- **熱量計算**：AI 只回傳三大營養素重量，程式端用 4-4-9 公式算熱量，回覆含百分比
- **每日目標**：/g 動態調整（記憶體內，重啟回 .env 預設值）
- **食物快取**：常吃食物存 food_cache 表，記錄完成後 Inline Button 一鍵加入，/f 列出清單，輸入編號 11-99 直接記錄（可加 x 倍數如 `11 x2`）
- **數字路由**：1-4 餐別覆蓋、11-99 快取記錄，不衝突
- **週報**：/r 上週、/r now 本週至今，六區塊（每日收支、營養素結構、正餐比例、累積收支、體重預估vs實際+7日均線、週對週），未記錄 TDEE 的天數用 BMR 補位（標 *）
- **體重 7 日移動平均**：/w 記錄後顯示均線，週報體重區段也顯示。取最近 7 筆，不足 3 筆不顯示。用於壓平量測時機造成的 1-2 kg 日間波動
- **補記 /b**：預設昨天（比照 /t），MMDD 4位數指定日期（今天或未來自動退回上一年），可選 1-4 餐別（預設其他）。recorded_at 設為台灣正午 12:00 轉 UTC，確保落在 get_meals_by_date 查詢區間內。照片 caption 支援純餐別/日期（allow_empty_food）。食物描述若為快取編號（11-99，可加 x 倍數）則走 cache 路徑免 AI。已知限制：修正補記餐點後累計顯示今天而非補記日（已加註記提示）

## 未來想做

- 月報統計（等資料滿 2 個月）
- AI 校正係數：用體重趨勢反推系統性偏差，套用在非 cache 的 AI 估值上（等資料滿 6-8 週）
- Web Dashboard
- 食物資料庫：衛福部 TFDA API、自訂食物別名

## 部署

VPS 已設定 SSH key 免密碼登入，Claude Code 可直接執行部署：

```bash
ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"
```

## VPS 資訊

- IP: 107.175.30.172
- SSH: root@107.175.30.172（本機已設定 SSH key）
- Bot 執行帳號: botuser
- 專案路徑: /home/botuser/calorie-bot
- 服務名稱: calorie-bot.service（`op run` 透過 EnvironmentFile 載入 Service Account token）
- Service Account token: `/etc/calorie-bot/op-token.env`（權限 600，root only）
- GitHub remote: https://github.com/huansbox/calorie-bot.git (public)
