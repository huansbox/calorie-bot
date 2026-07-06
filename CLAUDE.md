# Calorie Bot

## 專案概述

個人用 Telegram 體重管理 Bot。使用者透過 Telegram 傳食物照片或文字，AI Vision 自動分析三大營養素並記錄至 Supabase。

## 進行中的設計

- **claude -p 轉正 + 每月更新提醒**（**已上線 2026-07-01**）：Gemini 停用（code 保留），`claude -p` 為唯一預設路徑、`--model sonnet`（現解析為 Sonnet 5）走 `CLAUDE_CLI_MODEL` env、切 botuser 自己的 binary（2.1.96→2.1.197）、`DISABLE_AUTOUPDATER=1` + 每月 1 號 10:30 提醒手動 update、每餐回覆印實際模型。部署 smoke 抓到並修掉「2.1.197 modelUsage 混入內部 haiku」bug（取 token 最大主模型）。`chmod 700 /root` 已於 2026-07-06 收（botuser 實跑 claude -p smoke 通過 + 反向驗證進不去 /root），**全案完結**。詳見 [docs/claude-cli-primary-design.md](docs/claude-cli-primary-design.md)

## 技術架構

- **語言**: Python 3.12
- **套件管理**: uv
- **Bot 框架**: python-telegram-bot v22 (polling 模式，HTTPXRequest 自訂 timeout: read/write 20s, connect 10s)
- **AI**: claude -p CLI 為預設唯一路徑；Gemini / Claude API 保留可切換（`AI_PROVIDER`）
  - claude -p CLI (預設，`AI_PROVIDER=claude-cli`，走 Max 訂閱零費用，透過 subprocess 呼叫，`--model` 由 `CLAUDE_CLI_MODEL` 控制，預設 `sonnet`)
  - Gemini 2.5 Pro (`AI_PROVIDER=gemini`，JSON mode 強制合法輸出，失敗時仍 fallback claude -p)
  - Claude Sonnet 4.6 API (`AI_PROVIDER=claude`，無 fallback)
- **資料庫**: Supabase (PostgreSQL) — meals（含 ai_provider 欄位）, weight_logs（log_date UNIQUE + source，一天一筆）, daily_tdee, food_cache 四張表，全部啟用 RLS，使用 Secret Key 繞過
- **排程**: APScheduler (AsyncIOScheduler) — 每日 08:00 昨日摘要 + 週一 08:05 API 週報 + 週一 08:10 營養週報 + 03:00 照片清理 + 03:05 COROS TDEE 同步 + 10:29/22:29 COROS 體重同步 + 每月 1 號 10:30 claude 更新提醒
- **COROS 整合**: queryDailyHealthData → 每日自動補 daily_tdee（免手動 /t）；queryUserInfo → 每日自動補體重（免手動 /w）。同一條 MCP 管線（OAuth + refresh_token rotation）
- **密鑰管理**: 1Password — 本機 `op run` + VPS Service Account，`.env` 只存 `op://` 參照
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
  coros_mcp.py       # COROS MCP client：OAuth refresh + queryDailyHealthData + queryUserInfo + 文字解析（有單元測試）
  weight_sync.py     # decide_weight_sync 純函式：體重同步決策真值表（無 I/O，有單元測試）
scripts/
  coros_backfill.py       # 手動補登 daily_tdee（MCP 文字檔 or coros-api fallback）
  coros_mcp_bootstrap.py  # 一次性 OAuth PKCE flow，產生 token 檔
  check_weight_logs.py    # 一次性：檢查 weight_logs 同日多筆（migration 前的盤點）
  migrate_weight_logs_log_date.sql  # forward-only：weight_logs 加 log_date+source、壓一天一筆、建 UNIQUE（已對 prod 執行）
tests/
  test_ai.py         # parse_ai_response 單元測試 (12 cases，含 confidence 數字轉換)
  test_manual_meal.py # 手動記錄解析函式測試 (28 cases)
  test_backfill.py   # 補記解析 + UTC 換算測試 (24 cases)
  test_nutrition.py  # 營養素計算與格式化測試 (5 cases)
  test_cost.py       # API 費用計算測試 (3 cases，Gemini/Claude/claude-cli 費率)
  test_food_cache.py # parse_cache_number / is_cache_number 測試 (13 cases)
  test_correction.py # is_meal_type_correction 測試 (5 cases)
  test_report.py     # 週報 helper 測試 (24 cases，每日 map + 4 section)
  test_coros_mcp.py  # MCP parse (daily health + user weight) + token rotation + refresh 流程 (26 cases)
  test_weight_sync.py # decide_weight_sync 真值表 + 閾值邊界測試 (14 cases)
  test_dates.py      # parse_mmdd 測試 (8 cases，含退一年邏輯)
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
- **COROS token rotation**：refresh_token 每次 refresh 都換新，舊的失效。`services/coros_mcp.py` 用 atomic write (tmp file + rename) 寫回避免半成品。`save → fetch` 順序確保 refresh 成功就先持久化，即使 MCP call 失敗下次仍能用
- **COROS 體重自動同步**：每日 10:29（主）+ 22:29（fallback）`queryUserInfo` 抓 profile 當前體重 → `decide_weight_sync` 純函式決策 → upsert `weight_logs`。**走「日期路線」**：profile 體重無時間戳，無法區分「同重」與「沒量」，故只要當天沒筆就寫（接受偶爾寫沿用舊值的假點，換零紀律），`/w` 是假點修正出口。fill-missing-only（當天已有筆→SKIP，故 fallback 自動成立、晨重優先）。決策真值表：當天有筆→SKIP；抓不到→告警不寫；無基準→寫；跳變 >3kg（含離譜壞值）→告警不寫；值同上次→寫+輕提醒；正常→靜默寫。**token 不自己 refresh**，沿用 03:05 `sync_coros_tdee` rotate 過的 access_token（US22，rotation 風險集中單一時點）
- **體重一天一筆**：`weight_logs.log_date`(date) UNIQUE，所有寫入 upsert on log_date（比照 daily_tdee）。手動 /w（`source='manual'`）永遠覆蓋當天，自動同步（`source='coros'`）只在沒筆時寫，故手動永遠優先、無需特判。`source` 純內部驅動覆蓋邏輯，不出現在任何訊息
- **AI 路由（預設 claude-cli-only）**：預設 `AI_PROVIDER=claude-cli` 只走 claude -p CLI、**無 fallback**（掛掉該餐直接「分析失敗」，靠手動記錄逃生）。`AI_PROVIDER=gemini` 才有 fallback 鏈（Gemini API → claude -p CLI）；`AI_PROVIDER=claude` 直接走 Claude API（無 fallback）
- **claude -p CLI**：透過 subprocess 呼叫 VPS 上的 Claude Code CLI，走 Max 訂閱零費用。`--model` 由 `CLAUDE_CLI_MODEL`（預設 `sonnet` 別名）帶入，有圖片時加 `--allowedTools Read`，timeout 60s
- **ai_provider 追蹤**：meals 表 `ai_provider` 欄位記錄判讀來源（gemini/claude-cli/claude-api/null），週報依 provider 分組計費
- **ai_model 追蹤**：meals 表 `ai_model` 欄位記錄實際判讀模型名（如 `claude-sonnet-5`），claude-cli 路徑寫入（即時記錄 + `/b` 補記皆寫）。從 stdout JSON envelope 的 `modelUsage` 解析——**新版 CLI（≥2.1.197）會混入內部小模型（haiku），故取 token 用量最大的主判讀模型，不能取第一個 key**（舊版單 key 時 `next(iter())` 剛好對，升級後會誤記成 haiku）。稽核用途，2026-04-09 API key 洩漏事件衍生
- **Gemini JSON mode**：response_mime_type + response_json_schema 強制合法 JSON 輸出
- **Claude JSON 容錯**：parse_ai_response 處理 code fence、畸形 JSON (如 `>` 替代 `:`)、confidence 數字→字串轉換
- **圖片 24 小時過期**：暫存 data/media/，排程清理
- **API 費用追蹤**：每筆 meal 記錄 input/output tokens + ai_provider，週一推播週報（依 provider 分組，claude-cli 費用為 $0）
- **ai_confidence 觀察中**：Gemini 幾乎不回 low/medium（Prompt 指示未被嚴格遵守），目前保留欄位觀察，未來可能移除。區分 AI vs 手動用 input_tokens=0 即可
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
