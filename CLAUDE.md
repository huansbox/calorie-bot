# Calorie Bot

## 專案概述

個人用 Telegram 體重管理 Bot。使用者透過 Telegram 傳食物照片或文字，AI Vision 自動分析三大營養素並記錄至 Supabase。

## 進行中的設計

- **AI provider 品質評估（已定案並部署 2026-07-18，觀察期）**：Sonnet 台灣品牌品項知識缺口（奧利多案例，判定為 model 非 prompt 問題）→ VPS 裝 agy CLI smoke 4/4 全過（留作搜尋能力選項）→ GCP 抵免額回歸後**接回 gemini-api，模型對照後選定 `gemini-3.1-pro-preview`**（note 誠實度最佳；2.5-pro 與 Flash 系因假冒官方值失格）。全鏈 smoke 過、gemini 路徑補記 `ai_model`。觀察項：note 權威捏造率（已知 1/8，維他露張冠李戴案）、preview 模型異動（看 ai_model 漂移）、抵免額消耗。全程記錄見 [docs/agy-cli-exploration.md](docs/agy-cli-exploration.md)
- **Prompt v2（Sonnet 適配）+ 品牌數值策略**（**已上線 2026-07-06，觀察期**）：R4 三視角設計 review → R5 使用者逐段審定 → 4-4-9 回填機制實驗（錨點精度 0.2%）→ R6 錨點 15 條 TFDA／官方查證 → 實作三視角 review（R7）→ 兩段式部署 smoke 全過（四種 note 情境 4/4 命中；「50嵐奶茶半糖」歷史原句命中 700cc 預設鎖 435）→ /f 快取盤點 17 項對齊新錨點（更新 4：芝麻麻糬、8冰綠、Subway、星巴克採台灣官方最高值口徑）。隨案新增 `meals.note` 落庫（校正係數 basis 分類用）。**後續觀察清單（note 遵守率、7/13 週報台階屬預期、天仁錨點適配、快取備忘、校正係數前置）見 [docs/prompt-v2-design.md](docs/prompt-v2-design.md)「運行觀察交接」段**。註：2026-07-18 起主要讀者由 Sonnet 5 改為 gemini-3.1-pro-preview（prompt 不動，觀察清單中 Sonnet 專屬項目適用性下降；note 關鍵字制度實測跨模型通用且成為模型評選指標）
- **claude -p 轉正 + 每月更新提醒**（已上線 2026-07-01，全案完結；**2026-07-18 起預設 provider 切回 gemini，claude -p 降為 fallback**）：`--model sonnet`（現解析 Sonnet 5）、`DISABLE_AUTOUPDATER=1` + 每月 1 號 10:30 提醒手動 update（fallback 仍依賴 CLI，提醒照常）、每餐回覆印實際模型。詳見 [docs/claude-cli-primary-design.md](docs/claude-cli-primary-design.md)

## 技術架構

- **語言**: Python 3.12
- **套件管理**: uv
- **Bot 框架**: python-telegram-bot v22 (polling 模式，HTTPXRequest 自訂 timeout: read/write 20s, connect 10s)
- **AI**: Gemini API 為現行路徑（2026-07-18 切換），失敗時 fallback claude -p CLI；可切換（`AI_PROVIDER`）
  - Gemini 3.1 Pro Preview (現行預設，`AI_PROVIDER=gemini`，JSON mode 強制合法輸出，失敗時 fallback claude -p，費用由 GCP 抵免額覆蓋至 2027-07)
  - claude -p CLI (`AI_PROVIDER=claude-cli`，走 Max 訂閱零費用，透過 subprocess 呼叫，`--model` 由 `CLAUDE_CLI_MODEL` 控制，預設 `sonnet`)
  - Claude Sonnet 4.6 API (`AI_PROVIDER=claude`，無 fallback)
- **資料庫**: Supabase (PostgreSQL) — meals（含 ai_provider / ai_model / note 欄位）, weight_logs（log_date UNIQUE + source，一天一筆）, daily_tdee, food_cache 四張表，全部啟用 RLS，使用 Secret Key 繞過
- **排程**: APScheduler (AsyncIOScheduler) — 每日 08:00 昨日摘要 + 週一 08:05 API 週報 + 週一 08:10 營養週報 + 03:00 照片清理 + 03:05 COROS TDEE 同步 + 10:29/22:29 COROS 體重同步 + 每月 1 號 10:30 claude 更新提醒
- **COROS 整合**: 每日活動消耗（TDEE）走 MCP `queryDailyHealthData`（teamapi 無此資料，2026-07-30 掃過端點確認）；體重走 teamapi 帳密登入（`/account/login` 回應直接帶 weight），MCP `queryUserInfo` 降為 fallback。MCP token 近到期時用帳密自動重新授權（免瀏覽器）
- **密鑰管理**: 1Password — 本機 `op run` + VPS Service Account，`.env` 只存 `op://` 參照。`Developer / Calorie Bot` item 含 `TELEGRAM_TOKEN` / `SUPABASE_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN` / `COROS_EMAIL` / `COROS_PASSWORD`
- **部署**: RackNerd VPS (Ubuntu 24.04, systemd + `op run`)

## 檔案結構

```
main.py              # 進入點，註冊 handlers + 排程，auth_check decorator
config.py            # 環境變數讀取 (dotenv)，含 BMR、COROS_TOKEN_PATH 設定
scheduler.py         # 每日 08:00 昨日摘要 + 週一 08:05 API 週報 + 週一 08:10 營養週報 + 03:00 照片清理 + 03:05 COROS TDEE 同步 + 10:29/22:29 COROS 體重同步 + 每月 1 號 10:30 claude 更新提醒
handlers/
  meal.py            # 食物記錄核心 (文字/照片 → AI 分析 → DB → 回覆)，含 token 追蹤
  weight.py          # /w 體重記錄（upsert on log_date，一天一筆覆蓋；含 7 日移動平均）
  tdee.py            # /t 每日消耗記錄（預設昨天，加 n 記今天，自動加 BMR）
  query.py           # /s 今日摘要
  correction.py      # 餐別覆蓋 (1-4) + /u 撤銷 + 「修正」按鈕手動修正營養素
  manual_meal.py     # 手動記錄 (Bot 回覆貼上 / @前綴 / /m 指令)，免 AI 分析
  food_cache.py      # 食物快取：Inline Button 加入、/f 管理、數字 11-99 快速記錄
  report.py          # /r 週報 + /r now 本週至今，週一自動推播
  backfill.py        # /b 補記過去日期的食物（預設昨天，支援 MMDD 日期 + 1-4 餐別）
services/
  ai.py              # AI 引擎 (Gemini/Claude CLI/Claude API)，SYSTEM_PROMPT，parse_ai_response (有單元測試)
  db.py              # Supabase CRUD (meals, weight_logs, daily_tdee, food_cache)，含體重 upsert on log_date + 移動平均
  nutrition.py       # 營養素計算 (三大營養素→熱量) + 格式化 (含百分比)
  dates.py           # MMDD 日期解析 (有單元測試)
  format.py          # 訊息格式化 helper：餐別分組清單 (有單元測試)
  coros_mcp.py       # COROS MCP client（calobot 端）：queryDailyHealthData + queryUserInfo + 文字解析 + token 續命編排（有單元測試）
  coros_mcp_core.py  # COROS 共用核心：token 持久化 + OAuth refresh（含 fallback）+ MCP 傳輸——與 strava-sync 逐字節相同的複本，修改規範見檔頭
  coros_web.py       # COROS teamapi 直撈（帳密登入）：體重主路徑，零 OAuth（有單元測試）
  coros_oauth.py     # MCP token 帳密自動重新授權（跑完整 OAuth flow，免瀏覽器），token 近到期時由 coros_mcp.ensure_token 觸發
  weight_sync.py     # decide_weight_sync 純函式：體重同步決策真值表（無 I/O，有單元測試）
scripts/
  coros_backfill.py       # 手動補登 daily_tdee（MCP 文字檔 or coros-api fallback）
  coros_mcp_bootstrap.py  # 一次性 OAuth PKCE flow，產生 token 檔
  check_weight_logs.py    # 一次性：檢查 weight_logs 同日多筆（migration 前的盤點）
  migrate_weight_logs_log_date.sql  # forward-only：weight_logs 加 log_date+source、壓一天一筆、建 UNIQUE（已對 prod 執行）
tests/
  test_ai.py         # AI 單元測試 (31 cases，含 parse、note soft-check、claude -p cmd 結構)
  test_manual_meal.py # 手動記錄解析函式測試 (28 cases)
  test_backfill.py   # 補記解析 + UTC 換算測試 (24 cases)
  test_nutrition.py  # 營養素計算與格式化測試 (5 cases)
  test_cost.py       # API 費用計算測試 (3 cases，Gemini/Claude/claude-cli 費率)
  test_food_cache.py # parse_cache_number / is_cache_number 測試 (13 cases)
  test_correction.py # is_meal_type_correction 測試 (5 cases)
  test_report.py     # 週報 helper 測試 (24 cases，每日 map + 4 section)
  test_coros_mcp.py  # MCP parse (daily health + user weight) + token rotation + refresh fallback + 效期判讀/自動重新授權 (38 cases)
  test_coros_web.py  # teamapi 體重解析 + OAuth 登入表單解析 (11 cases)
  test_meal_media_group.py # Telegram 相簿聚合（多張照片合併成一次判讀）(4 cases)
  test_weight_sync.py # decide_weight_sync 真值表 + 閾值邊界測試 (14 cases)
  test_dates.py      # parse_mmdd 測試 (8 cases，含退一年邏輯)
  test_scheduler.py  # sweep_orphan_media 兜底掃描測試 (12 cases，含年齡邊界、dotfile 保留、刪除失敗)
  test_format.py     # format_meal_groups 測試 (8 cases，強制餐別與空 placeholder)
docs/                # 設計探索文件（如 cli-model-tracking-design.md）
wiki/                # GitHub wiki 頁面（唯一編輯處，CI 自動發佈到 .wiki.git）
```

## 開發慣例

- 所有變更開 feature branch，合併回 main
- Commit 遵循 Conventional Commits
- 單元測試涵蓋 services/ai.py、services/nutrition.py、services/dates.py (MMDD 解析)、services/format.py (餐別分組)、handlers/manual_meal.py、handlers/backfill.py、handlers/food_cache.py (快取編號)、handlers/correction.py (餐別覆蓋)、handlers/report.py (週報 helper) 與 API 費用計算
- Windows 開發環境需設 PYTHONIOENCODING=utf-8
- 本機啟動: `op run --env-file .env -- python main.py`（需 1Password 桌面 App 解鎖）
- DB 查詢凡有 ORDER BY，必須包含唯一欄位（如 `id`）作為 tie-breaker，避免同 timestamp 排序不確定
- `wiki/` + `.github/workflows/publish-wiki.yml` = GitHub wiki 唯一編輯處，CI 自動發佈到 `.wiki.git`，不要在網頁上編輯。穩定頁（Home/Maintenance）跟機制變更的 PR 順手改；快照頁（Plan/Roadmap/Tech-Debt）標快照日期，milestone 或每月用 /repo-wiki refresh 刷新

## 關鍵設計決策

- **polling 模式** (非 webhook)：簡單、不需公開 URL
- **auth_check decorator**：單人 Bot，所有 handler 統一用 chat_id 驗證
- **餐別**：早餐(05:00-10:30)/午餐(11:00-14:30)/晚餐(16:30-21:00)/其他，依台灣時間分鐘級推斷，使用者可用 1-4 覆蓋
- **TDEE = BMR + 活動消耗**：BMR 固定值存 .env，活動消耗來自 COROS（自動）或 /t（手動覆寫）
- **/t 預設記昨天**：符合早上看手錶輸入昨日消耗的使用情境
- **COROS 自動同步**：每日 03:05 排程拉過去 7 天 daily health → BMR + Calories 寫 daily_tdee。fill-missing-only 不覆寫手動 /t；昨天沒拉到資料會推 Telegram 告警。`Calories` 欄位含 NEAT，與手錶錶面「活動消耗」widget 一致（實測 27 天誤差 ≤ 1 kcal）
- **COROS token rotation + refresh fallback**：refresh_token 每次 refresh 都換新，舊的失效。atomic write (tmp file + rename) 寫回避免半成品，`save → fetch` 順序確保 refresh 成功就先持久化。**refresh 失敗不中止**：退用既存 access_token（30 天效期）續撈（2026-07-18 起 COROS refresh endpoint 對有效 token 回 500 的實案，7/18-7/19 TDEE 斷兩天）；撈取也失敗才發「請手動 /t」告警（訊息合併兩層脈絡）
- **COROS token 帳密自動重新授權**（2026-07-30）：refresh 既然救不回來，就讓 token 到期前自己換新的一份。`services/coros_mcp.ensure_token` 從 access_token（JWT）的 `exp` 判斷效期，剩 < 3 天就呼叫 `coros_oauth.bootstrap_token`——用 `COROS_EMAIL`/`COROS_PASSWORD` 跑完整 OAuth authorize flow（DCR 註冊 → authorize → openus 表單登入 → 攔 localhost callback 取 code → PKCE 換 token），**不需要瀏覽器**。token 檔存 `redirect_uri`，之後續期重用同一個 client。效期充足時照常試 refresh，失敗只記 log 不推播（有自動續期兜底，天天推 500 是噪音）；撈取失敗但 token 未到期 → 重新授權後重試一次。**實測坑**：登入表單預設 `country=CN` 會回 `result 1001`，要改 `TW`；POST 缺 `Origin` 或瀏覽器型 UA 同樣 1001。沒設帳密時退回舊行為（refresh 失敗發警示、近到期提醒人工跑 `scripts/coros_mcp_bootstrap.py`）。**維護唯一要記的事：改 COROS 密碼時同步更新 1Password `Developer / Calorie Bot` 的 `COROS_PASSWORD` 欄位**，否則下次續期會失敗（會發 Telegram 告警，且 token 還有 3 天緩衝）。COROS 帳號若開啟兩階段驗證或登入頁加 captcha，自動化會失效 → 退回人工 bootstrap，再不行 TDEE 回到手動 `/t`（體重不受影響，走 teamapi）
- **COROS 共用核心（與 strava-sync 逐字節同步）**：token 持久化／OAuth refresh（含 fallback）／MCP 傳輸抽在 `services/coros_mcp_core.py`，與 strava-sync `lt2_auto/coros_mcp_core.py` 為必須逐字節相同的複本（COROS 端故障歷來同時打壞兩邊）。修改任一份後跑 strava-sync `tools/sync_coros_core.py` 同步；strava-sync sync.bat 每小時 drift check，不一致會 ntfy 告警。此檔嚴禁 repo 專屬內容（規範見檔頭）
- **COROS 體重自動同步**：每日 10:29（主）+ 22:29（fallback）抓 profile 當前體重 → `decide_weight_sync` 純函式決策 → upsert `weight_logs`。**撈取走 teamapi 帳密登入為主路徑**（比照 strava-sync GitHub #31：零 OAuth、沒有會壞掉的 token 狀態；`/account/login` 回應直接帶 `weight`，不必第二個請求），失敗才退 MCP `queryUserInfo`。**走「日期路線」**：profile 體重無時間戳，無法區分「同重」與「沒量」，故只要當天沒筆就寫（接受偶爾寫沿用舊值的假點，換零紀律），`/w` 是假點修正出口。fill-missing-only（當天已有筆→SKIP，故 fallback 自動成立、晨重優先）。決策真值表：當天有筆→SKIP；抓不到→告警不寫；無基準→寫；跳變 >3kg（含離譜壞值）→告警不寫；值同上次→寫+輕提醒；正常→靜默寫。**token 不自己 refresh**，沿用 03:05 `sync_coros_tdee` rotate 過的 access_token（US22，rotation 風險集中單一時點）
- **體重一天一筆**：`weight_logs.log_date`(date) UNIQUE，所有寫入 upsert on log_date（比照 daily_tdee）。手動 /w（`source='manual'`）永遠覆蓋當天，自動同步（`source='coros'`）只在沒筆時寫，故手動永遠優先、無需特判。`source` 純內部驅動覆蓋邏輯，不出現在任何訊息
- **AI 路由（現行 gemini）**：現行 `AI_PROVIDER=gemini`（2026-07-18 切換，model 寫死 `gemini-3.1-pro-preview`）走 Gemini API，失敗時 fallback claude -p CLI。切換動機：Sonnet 台灣品牌品項知識缺口；模型對照中 2.5-pro 與 Flash 系會假冒「官方值／標示轉錄」＋confidence high，3.1-pro 校準最佳（詳見 [docs/agy-cli-exploration.md](docs/agy-cli-exploration.md)）。preview 後綴的下架風險由 fallback 鏈緩解。`AI_PROVIDER=claude-cli` 只走 claude -p、無 fallback；`AI_PROVIDER=claude` 直接走 Claude API（無 fallback）
- **主路徑失敗告警**（2026-09-06）：`AI_PROVIDER=gemini` 的 fallback 是靜默的——判讀照常成功，只留一行 `logger.warning`。2026-09-04 Gemini 對 VPS IP 回 400（`User location is not supported for the API use.`）連兩天、15 次呼叫全滅都沒被發現，是從 Telegram 回覆的模型名才看出來的。`services/ai.py` 改為只記狀態**轉換**：主路徑由通轉不通推一則 Telegram、由不通轉通再推一則，中間持續失敗不重複推（每餐都推是噪音）。狀態是 module-level，process 重啟歸零（重啟後第一次失敗會再推一次，可接受）。services 不碰 Telegram：`push_primary_alert(send)` 收一個可 await 的送訊息函式，由 `handlers/meal.py`、`handlers/backfill.py` 傳 `update.message.reply_text`；推播失敗只記 log，不影響判讀結果回覆。無 fallback 的 `claude` / `claude-cli` 路徑失敗時使用者本來就會看到「分析失敗」，不另外告警
- **claude -p CLI**：透過 subprocess 呼叫 VPS 上的 Claude Code CLI，走 Max 訂閱零費用。`--model` 由 `CLAUDE_CLI_MODEL`（預設 `sonnet` 別名）帶入，有圖片時加 `--allowedTools Read`，timeout 60s。SYSTEM_PROMPT 走 `--append-system-prompt`、`-p` 只放使用者輸入（指令/資料分離；文字帶「使用者輸入：」前綴防 leading-dash 被當 option）
- **claude -p 認證＝長效 OAuth token**（2026-09-01 起）：`CLAUDE_CODE_OAUTH_TOKEN`（`claude setup-token` 產生，1 年期，**2027-09-01 到期**）由 `.env` 的 `op://` 參照注入 bot 環境，subprocess 繼承。**不再依賴 `~/.claude/.credentials.json`**——那份短期 token 靠 refresh 續命，而 refresh 只在 `claude -p` 被呼叫時發生；fallback 平時不被呼叫（2026-07-18 切 gemini 後整整 6 週零呼叫），refresh token 就這樣靜靜過期，直到 9/01 月更新 smoke 才被抓到（credentials 檔的 token 被 CLI 清成空字串）。長效 token 沒有這個「不用就壞」的性質。**維護要記的事：2027-09 前換發**——`sudo -u botuser -H claude setup-token`（互動式，無法自動化）→ 新 token 寫回 1Password 同名欄位 → restart bot（`.env` 不用動）。`ANTHROPIC_API_KEY` 在 VPS `.env` 是註解掉的（避免被 subprocess 繼承走 API 計費），所以 OAuth token 是 claude -p 的唯一認證來源，它失效＝完全沒有 fallback（主路徑 gemini 不受影響）
- **prompt v2 錨點三層**：定值錨（高頻手搖/豆漿釘死 kcal，TFDA 查證值）、品類校準區間（泛用品項檢核）、單位基準（TFDA per-100g macro 三元組）。note 必以「官方值：/標示轉錄：/推估：」開頭（parse soft-check 只警告不擋），原文落庫 `meals.note` 供未來校正係數分類 basis
- **ai_provider 追蹤**：meals 表 `ai_provider` 欄位記錄判讀來源（gemini/claude-cli/claude-api/null），週報依 provider 分組計費
- **ai_model 追蹤**：meals 表 `ai_model` 欄位記錄實際判讀模型名（如 `gemini-3.1-pro-preview`、`claude-sonnet-5`），claude-cli 與 gemini 路徑皆寫入（即時記錄 + `/b` 補記皆寫），Telegram 回覆印同款標示。gemini 從 API 回應 `model_version` 帶入（2026-07-18 起，preview 模型被 Google 改版重導向時可現形）；claude-cli 從 stdout JSON envelope 的 `modelUsage` 解析——**新版 CLI（≥2.1.197）會混入內部小模型（haiku），故取 token 用量最大的主判讀模型，不能取第一個 key**（舊版單 key 時 `next(iter())` 剛好對，升級後會誤記成 haiku）。**用量必須含 `cacheReadInputTokens` + `cacheCreationInputTokens`**：CLI 2.1.222 把整份 system prompt 走 prompt cache，主判讀模型的 `inputTokens` 只剩個位數，只算 input+output 會被無 cache 的內部 haiku（~911）壓過去——實際判讀仍是 sonnet，只有記錄欄位挑錯，臨界值是主模型 output ≈ 926 tokens（2026-09-04～09-05 誤記 9/15 筆，2026-09-06 修）。稽核用途，2026-04-09 API key 洩漏事件衍生
- **Gemini JSON mode**：response_mime_type + response_json_schema 強制合法 JSON 輸出
- **Claude JSON 容錯**：parse_ai_response 處理 code fence、畸形 JSON (如 `>` 替代 `:`)、confidence 數字→字串轉換
- **相簿合併判讀**：Telegram 一次傳多張照片會拆成 N 個獨立 message（只有第一張帶 caption），靠 `media_group_id` 串起來。收到第一張先回「分析中」並起收集任務，等 2 秒內沒有新的同組照片就視為到齊，**N 張圖 + caption 合併送一次 AI、寫一筆**。修此問題前是逐張各判讀一次（2026-07-30 實案：3 張同餐照片 → 3 筆，說明涵蓋的菜色被重複計算 642 kcal）
- **圖片 24 小時過期**：暫存 data/media/，排程清理。相簿記錄的 `image_path` 是逗號串接的多個路徑，清理排程會拆開逐一刪。**孤兒檔兜底**：`cleanup_expired_images` 是 DB 驅動的，只認得 `meals.image_path` 還指得到的檔案；`/u` 撤銷會 `delete_meal` 刪整個 row、AI 分析失敗時照片已存檔但沒 insert，這兩條路徑都會讓檔案永久掃不到（2026-09-06 實案：15 個檔案有 13 個是孤兒）。故排程末尾再用 `sweep_orphan_media` 掃一次 `MEDIA_DIR`，刪掉 mtime > 48h 的**非 dotfile** 檔案（DB 引用的最長活 24h + 一輪排程，48h 有邊際；跳過 dotfile 是因為 `data/media/.gitkeep` 永遠是最舊的那個，實作當天就被掃掉一次）。用 mtime 兜底而不是在每條斷關聯的路徑補刪除，是為了不依賴「日後新增路徑時記得補」
- **API 費用追蹤**：每筆 meal 記錄 input/output tokens + ai_provider，週一推播週報（依 provider 分組，claude-cli 費用為 $0）
- **ai_confidence 觀察中**：v1 時代 Gemini 2.5 Pro 幾乎不回 low/medium；prompt v2 + gemini-3.1-pro-preview 已見合理分佈（high 有依據、推估給 medium、不確定給 low），欄位續留觀察。已知失效模式：權威捏造時會連帶標 high。區分 AI vs 手動用 input_tokens=0 即可
- **手動記錄**：三種免 AI 輸入方式 — 貼上 Bot 回覆、@前綴快速輸入、/m 指令，末尾可加 x 倍數（如 x2, x0.5）
- **手動修正**：AI 分析回覆附「修正」按鈕，點擊後輸入正確值直接更新該筆記錄
- **熱量計算**：AI 只回傳三大營養素重量，程式端用 4-4-9 公式算熱量，回覆含百分比
- **食物快取**：常吃食物存 food_cache 表，記錄完成後 Inline Button 一鍵加入，/f 列出清單，輸入編號 11-99 直接記錄（可加 x 倍數如 `11 x2`）
- **數字路由**：1-4 餐別覆蓋、11-99 快取記錄，不衝突
- **週報**：/r 上週、/r now 本週至今，六區塊（每日收支、營養素結構、正餐比例、累積收支、體重預估vs實際+7日均線、週對週），未記錄 TDEE 的天數用 BMR 補位（標 *）
- **體重 7 日移動平均**：/w 記錄後顯示均線，週報體重區段與 08:00 昨日摘要也顯示。一天一筆後「最近 7 筆」即「最近 7 天」。取最近 7 筆，不足 3 筆不顯示。用於壓平量測時機造成的 1-2 kg 日間波動
- **補記 /b**：預設昨天（比照 /t），MMDD 4位數指定日期（今天或未來自動退回上一年），可選 1-4 餐別（預設其他）。recorded_at 設為台灣正午 12:00 轉 UTC，確保落在 get_meals_by_date 查詢區間內。照片 caption 支援純餐別/日期（allow_empty_food）。食物描述若為快取編號（11-99，可加 x 倍數）則走 cache 路徑免 AI。已知限制：修正補記餐點後累計顯示今天而非補記日（已加註記提示）

## COROS 體重同步驗收（2026-06-01 上線，2026-06-02 全數驗證）

issues 001–008 的 acceptance criteria **已全數打勾**，PRD 22 條 User Story 全覆蓋。排程時點皆**台灣時間**（scheduler `timezone="Asia/Taipei"`；VPS 系統時鐘是 UTC，差 8 小時）。

**已驗證（2026-06-02）**：
- 排程決策：6/01 22:29 台北 `SKIP`（當天已有筆）、6/02 10:29 台北 `WRITE_SILENT`（跳變 0.8kg < 3kg 閾值）（issues/005、006）
- DB 落地：weight_logs 有 `log_date=2026-06-02 weight_kg=72.20 source=coros`，upsert `on_conflict=log_date` 回 201（issues/006）
- 昨日摘要：6/02 08:00 job 查 weight_logs（limit=1 取最新 + limit=7 算均線）並成功送出（issues/008）
- `/w` 覆蓋 + NOT NULL 修復：隔離表整合測試（`CREATE TABLE weight_logs_verify (LIKE weight_logs INCLUDING ALL)`，驗完 DROP，prod 真表零變動）— 先 coros 後 manual upsert on `log_date` → 1 筆、`source=manual`、weight 更新、`recorded_at` 保留（payload 缺 `recorded_at` 由 `DEFAULT now()` 補＝NOT NULL 修復成立）（issues/007）
- 時序註記：08:00 摘要（00:00 UTC）跑在體重同步（02:29 UTC）之前，故早上摘要的「最新體重」是前一天的筆，非當天晨重。符合「昨日摘要」語意，不需改

**剩運行時觀察（非 acceptance criteria，純錦上添花、非阻塞）**：
- 值同上次的輕提醒 / 跳變 >3kg 告警的 **Telegram 實際推送**：決策邏輯已由 `test_weight_sync.py` 14 cases 覆蓋，但這兩個分支至今未在 prod 觸發（6/01、6/02 同步都走 WRITE_SILENT），等真實事件出現時瞄一眼 log
- 今晚 6/02 22:29「coros 自動晨筆 → SKIP」為晨重優先同機制再現（issues/006 已憑 6/01 manual 早筆驗過，此為再確認）
- 從 Telegram 實打一次 `/w` 的 UI 全鏈 smoke（DB 行為層已由隔離表測試驗證，風險低）

## 未來想做

- 月報統計（等資料滿 2 個月）
- AI 校正係數：用體重趨勢反推系統性偏差，套用在非 cache 的 AI 估值上（等資料滿 6-8 週）
- Web Dashboard
- 食物資料庫：衛福部 TFDA API、自訂食物別名
- COROS MCP 增加 sport records / training load 整合，週報加入訓練量視角

## 部署

VPS 已設定 SSH key 免密碼登入，Claude Code 可直接執行部署：

```bash
ssh root@107.175.30.172 "cd /home/botuser/calorie-bot && sudo -u botuser git pull origin main && sudo systemctl restart calorie-bot"
```

### 已知無害現象：op zombie process（決定不修）

`calorie-bot.service` 穩定掛 1 個 zombie：`[op] <defunct>`，parent 是 systemd 啟的常駐 `op run`。根因是 op 啟動背景 `op daemon` 時的 double-fork，中間程序沒被 `wait()` 回收；因常駐 `op run` 永久 block 在等 python（bot），這顆 zombie 一輩子收不掉，每次重啟重生但不累積。**無害**（1 個 PID entry，零 CPU/RAM）。

評估後**決定不修**：
- 升級 op（2.33.1→2.34.x）無效：changelog 無 reaping/daemon 修正，2.34.0 那條是「Ctrl+C 終止 subprocess」，與此無關。
- 唯一根治（`op run` 改 `op inject` + tmpfs EnvironmentFile）要犧牲「secret 不落地」這個既有安全屬性、外加改寫 `.env`→`.env.tpl` 與 `RuntimeDirectory`，純為消一顆無害 zombie，不划算。
- tini/dumb-init 包在 python 外無效：zombie 的 parent 是 op，不是 python。

### COROS MCP token 部署（首次）

```bash
# 1. 本機跑 bootstrap，瀏覽器登入授權
uv run python scripts/coros_mcp_bootstrap.py

# 2. 把 token 透過 root 傳到 VPS，再交給 botuser
scp data/coros-token.json root@107.175.30.172:/tmp/coros-token.json
ssh root@107.175.30.172 "mv /tmp/coros-token.json /home/botuser/calorie-bot/data/coros-token.json \
  && chown botuser:botuser /home/botuser/calorie-bot/data/coros-token.json \
  && chmod 600 /home/botuser/calorie-bot/data/coros-token.json"

# 3. .env 預設 COROS_TOKEN_PATH 相對於 cwd，systemd unit 的 WorkingDirectory
#    若不是 /home/botuser/calorie-bot，需在 .env 加絕對路徑
#    COROS_TOKEN_PATH=/home/botuser/calorie-bot/data/coros-token.json

# 4. restart service，等隔天 03:05 排程觸發
sudo systemctl restart calorie-bot
```

token 之後會被 rotation 寫回原檔（atomic rename），botuser 需有該檔與所在目錄的寫權限。

## VPS 資訊

- IP: 107.175.30.172
- SSH: root@107.175.30.172（本機已設定 SSH key）
- Bot 執行帳號: botuser
- 專案路徑: /home/botuser/calorie-bot
- 服務名稱: calorie-bot.service（`op run` 透過 EnvironmentFile 載入 Service Account token）
- Service Account token: `/etc/calorie-bot/op-token.env`（權限 600，root only）
- GitHub remote: https://github.com/huansbox/calorie-bot.git (public)

### SSH 加固與 log 噪音（2026-09-06）

VPS 原本 `PasswordAuthentication yes` + `PermitRootLogin yes`，24 小時內實測 **9,612 次 Failed password、5,241 次 Invalid user、174 個不重複來源 IP** 的持續暴力破解（過去 30 天 `Accepted password` = 0，未被攻破）。這些 sshd 訊息佔 journal 的 **78.7%**，`httpx` 的 getUpdates INFO 再佔 **17.6%**——真正有診斷價值的每天只剩約 1,700 行。

三項處置：

1. **`/etc/ssh/sshd_config.d/10-hardening.conf`**：`PasswordAuthentication no` + `PermitRootLogin prohibit-password` + `KbdInteractiveAuthentication no`。**檔名前綴必須小於 `50-cloud-init.conf`**——sshd_config 取「第一個出現」的值不是最後一個，而 `50-cloud-init.conf` 正是 `PasswordAuthentication yes` 的來源；用 `99-` 會靜默失效且 `sshd -t` 不報錯。改完用 `sshd -T` 確認解析後的有效值，再開新連線驗證。登入一律走 publickey，root 的 `authorized_keys` 有 `calobot-vps` 與 `macbook-calorie-bot` 兩把。
2. **`main.py` 把 `httpx` logger 設 WARNING**：polling 每 10 秒一筆 getUpdates 200 OK＝8,640 行/天，無診斷價值；失敗仍以 WARNING 以上留下。
3. **`/etc/systemd/journald.conf.d/10-retention.conf`**：`MaxRetentionSec=180d`，`SystemMaxUse` 維持預設（檔案系統 10% = 2.4G）當容量上限。原本 2.3G 剛好收斂在預設上限＝93 天；兩項降噪後**實測** 5.9 MB/day（加固前 25.3），180 天約 1.06G，仍在 2.4G 上限內，時間為第一約束。**注意 `PasswordAuthentication no` 不會讓 sshd log 歸零**：認證必定失敗，但 sshd 仍為每次密碼嘗試記一行 `Failed password`，實測只降約 76%，加固後 sshd 仍佔 journal 的八成左右。餘裕約 2 倍，夠用就不加 fail2ban（密碼登入已關，它只降 log 不增安全）。
