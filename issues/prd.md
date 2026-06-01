# PRD：COROS 體重自動同步

## Problem Statement

我每天量體重這件事，目前要在兩個地方各記一次：COROS app（因為手錶健康生態系需要）和 calobot（因為趨勢分析、7 日均線、週報需要）。同一筆數字記兩遍是重複勞動，而且我**常常忘記其中一邊**——有時 Telegram 打了 `/w` 卻忘了在 COROS 更新，有時反過來在 COROS 記了卻忘了 `/w`。結果兩邊資料不同步，calobot 的趨勢線出現缺口。

我要的不是「少打幾個字」，而是**徹底消除「記兩邊」這個動作**：在 COROS 量一次（這個動作本來就因為手錶而免不了），calobot 自動拿到。

## Solution

calobot 每天定時用程式自動從 COROS 抓當前體重，寫進 `weight_logs`，我完全不用碰 Telegram。

關鍵前提已驗證：COROS 的 MCP server 是標準 HTTP + OAuth 服務，純 Python 就能呼叫（不需要 Claude session）。專案現有的 `services/coros_mcp.py` + `scheduler.py` 已經天天在 VPS 上無人值守地這樣抓 daily health 資料（daily_tdee 自動同步），體重同步只是在同一條已驗證的管線上多呼叫一個 tool（`queryUserInfo`）。

實測 COROS profile 體重在 app 記錄後 **2 分鐘內**就能透過 MCP 讀到，延遲不是瓶頸。

核心限制與取捨：COROS profile 體重**不帶量測時間戳**，只有一個「當前值」。因此程式無法區分「今天量了剛好同重」和「今天根本沒量、沿用舊值」——這兩種情況在 profile 上長得一模一樣。面對這個死結，我選擇「日期路線」：每天只要還沒記錄就寫一筆（接受「沒量的日子會寫進沿用舊值的假點」），換取「完全零紀律、不用手動處理同重」。假點對按日聚合的趨勢線傷害很小（不製造跳動，只是少一個新資訊），而真正需要修正時我隨時能用 `/w` 覆蓋。

## User Stories

1. 作為使用者，我希望在 COROS app 量完體重後 calobot 自動拿到，這樣我就不用再到 Telegram 打 `/w`。
2. 作為使用者，我希望體重同步是程式自動跑的（不依賴任何 Claude session），這樣它能在 VPS 上無人值守地天天執行。
3. 作為使用者，我希望系統每天早上 10:29 自動抓一次體重，這樣涵蓋我大多數量晨重的時段。
4. 作為使用者，我希望系統晚上 22:29 再嘗試一次作為補位，這樣即使早上沒抓到（我早上沒量、或早班同步失敗）也有第二次機會。
5. 作為使用者，我希望一天最多只保留一筆體重，這樣 7 日均線「最近 7 筆」自動等於「最近 7 天」，趨勢不被一天多筆壓縮。
6. 作為使用者，我希望系統優先保留晨重而非晚重，因為晚重被一天的進食和水分灌高，會污染趨勢線。
7. 作為使用者，我希望自動同步「只在當天還沒有任何記錄時才寫」，這樣它不會覆蓋我已經記好的資料。
8. 作為使用者，我希望保留手動 `/w` 指令，這樣 COROS 沒量或抓到怪值時我能手動補記或修正。
9. 作為使用者，我希望手動 `/w` 永遠能覆蓋當天的自動筆，這樣我的人工判斷永遠優先於自動估計。
10. 作為使用者，我希望同一天重複打 `/w` 以最後一次為準（覆蓋，不留歷史），這樣當天體重永遠是我最新確認的值。
11. 作為使用者，我希望自動同步平時保持安靜（不推訊息），這樣我不會被每天一則「已同步」洗版。
12. 作為使用者，我希望當自動抓到的值跟上次完全相同時收到一則輕提醒（「若今天還沒量請 /w」），這樣我能及時發現並修正可能的假點。
13. 作為使用者，我希望當自動抓到的值跟上次差超過 3 kg 時系統不要自動寫入、改推告警請我確認，這樣離譜的壞值或大跳變不會污染趨勢線。
14. 作為使用者，我希望當 COROS 抓取或解析失敗時收到告警，這樣我知道同步壞了、可以手動 `/w` 補上。
15. 作為使用者，我希望每天 08:00 的昨日摘要裡附上「最新體重 + 該筆日期 + 7 日均線」，這樣我每天能看到體重趨勢。
16. 作為使用者，我希望 08:00 摘要的體重帶日期，這樣我一眼看出那是不是今天的（08:00 時今天的同步還沒跑），也能看出最新一筆是否已是好幾天前（久沒量）。
17. 作為使用者，我希望既有的 `/w` 回覆（上次 N 天前、變化 ±X、7 日均線）在新模型下繼續正常運作。
18. 作為使用者，我希望週報的體重區段在一天一筆下更整齊。
19. 作為使用者，我希望我過去手動記的 42 筆歷史體重在升級後完整保留（除了同日重複的那一筆按規則清掉）。
20. 作為使用者，我希望升級時 3/13 那天同日兩筆（72.3 午夜筆 / 71.2 晨重）只保留 71.2 晨重，這樣歷史資料符合「一天一筆、晨重優先」的新規則。
21. 作為使用者，我希望體重的來源（自動/手動）被記錄下來但不顯示在任何訊息裡，因為它只用於驅動覆蓋邏輯，對我日常判讀沒有意義。
22. 作為維運者，我希望體重同步不自己 refresh token、而是沿用既有 03:05 同步續命的 access_token，這樣避免一天多次 token rotation 增加風險。

## Implementation Decisions

### Schema 變更
- `weight_logs` 新增兩欄：
  - `log_date`（date，UNIQUE）：用於保證「一天一筆」並作為 upsert 衝突鍵。
  - `source`（text，'coros' / 'manual'）：記錄來源，純內部用途。
- 所有體重寫入改為 **upsert on `log_date`**（比照現有 `daily_tdee` 的 `upsert on date` 模式）。

### 同步決策核心（deep module）
- 抽出純函式 `decide_weight_sync(fetched, last_weight, today_has_row) -> Decision`，封裝所有「該不該寫 / 寫什麼 / 要不要告警」的判斷，無 I/O。
- 決策真值表：
  - `today_has_row` 為真 → SKIP（不寫、不通知）。
  - `fetched` 為 None（parse 失敗）→ ALERT_NO_WRITE（抓取失敗告警）。
  - `last_weight` 為 None（DB 冷啟動、無基準）→ WRITE_SILENT（第一筆不擋）。
  - `|fetched - last_weight| > 3` → ALERT_NO_WRITE（跳變過大，請 /w 確認）。
  - `fetched == last_weight` → WRITE + ALERT（寫入，並推「與上次相同，若還沒量請 /w」輕提醒）。
  - 其他（正常新值）→ WRITE_SILENT。
- 「值相同」採嚴格相等判斷（profile 體重為一位小數）。
- `±3 kg` 為固定閾值，同時涵蓋「離譜壞值（如 0、200）」與「真實大跳變」——離譜值本質就是極端跳變，不需要額外的數值範圍檢查。

### COROS 抓取與解析
- `services/coros_mcp.py` 新增 `fetch_user_info(token) -> str`，呼叫 MCP `queryUserInfo` tool（無參數），比照現有 `fetch_daily_health`。
- 新增純函式 `parse_user_weight(text) -> float | None`，從 `queryUserInfo` 文字輸出（格式如 `Weight: 71.0 kg`）解出體重，解析不到回 None，比照現有 `parse_daily_health`。

### Token 處理
- 體重同步只做 `load → fetch`，**不自己 refresh**。既有 03:05 `sync_coros_tdee` 每天已 refresh 並 rotate token（access_token 約 30 天有效），10:29/22:29 直接沿用當天有效的 access_token。
- 若 03:05 那次 refresh 失敗導致 token 過期，體重同步抓取會失敗並走「抓取失敗告警」路徑。

### 排程
- `scheduler.py` 新增 `sync_coros_weight` job，掛兩個 cron 時點：10:29（主抓）與 22:29（fallback）。
- 兩個時點執行相同邏輯：抓 → 取最近一筆 → `decide_weight_sync` → 依決策寫入 upsert / 發 Telegram 訊息。fallback 透過「當天已有筆 → SKIP」自動成立，不需特殊分支。

### 寫入規則
- **自動**：當天 `log_date` 沒筆才寫，`source='coros'`（fill-missing-only，比照 `sync_coros_tdee`）。
- **手動 `/w`**：一律 upsert 覆蓋當天那筆，`source='manual'`。手動永遠優先、自動絕不覆蓋手動（因自動只在「沒筆」時動手，無需特判）。手動 `/w` 不受 ±3 kg 閾值限制。

### 可見性兩層
- **即時層**（同步當下）：依 `decide_weight_sync` 的決策——正常新值靜默；值同上次推輕提醒；失敗或跳變過大推告警。
- **每日層**：08:00 昨日摘要新增一行「⚖️ 最新體重 X kg（日期，7 日均線 Y）」，取最近一筆及其 `log_date`。

### Migration
- 現況：42 筆 / 41 個台灣日期，範圍 2026-03-11 ~ 2026-06-01。
- 回填：所有現有筆 `source='manual'`、`log_date` = `recorded_at` 換算台灣日期。
- 衝突處理：唯一同日多筆是 2026-03-13（72.3 午夜筆 / 71.2 晨重）。刪除 72.3 那筆（hardcode 該 id），保留 71.2 晨重。不寫通用去重邏輯（只有一個 case 不值得該複雜度）。
- 清理後建立 `log_date` UNIQUE 約束。

### 既有功能（不改）
- `get_previous_weight`（/w 顯示上次與變化）、`get_weight_range`（週報體重區段）、7 日均線（`get_recent_weights` / `get_weight_moving_avg`）在「一天一筆」下自動變整齊，沿用不改。

## Testing Decisions

好的測試只驗證**外部可觀察的行為**，不綁定實作細節——對純函式而言，就是「給定輸入、斷言輸出」，不去窺探內部如何計算。

要寫測試的模組（兩個純函式深模組）：

1. **`parse_user_weight`**：
   - 正常格式（`Weight: 71.0 kg`）、整數值、不同小數、欄位前後有雜訊、缺 Weight 欄位、空字串、格式變異 → 確認回傳正確 float 或 None。
   - Prior art：`tests/test_coros_mcp.py`（`parse_daily_health` 測試）、`tests/test_ai.py`（`parse_ai_response` 容錯測試）。

2. **`decide_weight_sync`**：
   - 覆蓋真值表每一條分支：當天有筆→SKIP；parse 失敗→告警不寫；無基準→寫入；差 >3→告警不寫；值相同→寫入+提醒；正常新值→靜默寫入。
   - 邊界：差剛好 = 3 kg（不觸發）、= 3.01 kg（觸發）；負向跳變（瘦 3 kg 以上）同樣觸發。
   - Prior art：`tests/test_backfill.py`、`tests/test_dates.py` 這類「純函式 + 多 case 真值表」風格。

不寫單元測試的部分（比照現有慣例，皆為薄 I/O 層）：
- `fetch_user_info`（MCP HTTP 呼叫，比照 `fetch_daily_health` 不測）。
- `db.py` 的 upsert / 查詢（Supabase I/O，現有 db.py 無單元測）。
- `scheduler.py` 的 `sync_coros_weight` job（I/O 編排）。
- migration 與一次性清理腳本（手動驗證，部署後看 log 確認）。

## Out of Scope

- **早晚雙序列追蹤**：不分開維護「晨重趨勢線」與「晚重趨勢線」。一天一筆、晨重優先。
- **連續多天假點的累積告警**：「profile 值連續 N 天沒變就提醒你該量了」是未來可加的防護，本期不做。當下僅有「值同上次的輕提醒」。
- **`/ws` 半自動指令**：評估後否決（沒解決「記兩邊」痛點，還多一個前置動作）。
- **體脂 / 身體組成同步**：COROS MCP 無相關 endpoint。
- **體重歷史 backfill**：COROS profile 只有當前值，無歷史序列可補。
- **來源顯示**：`source` 不出現在任何使用者可見訊息。

## Further Notes

- **COROS profile 更新延遲**：實測 ≤ 2 分鐘（app 記錄 71.0 後，第二次查詢約 2 分鐘內讀到），遠小於排程間隔，延遲非瓶頸。
- **核心死結**：profile 體重無時間戳，「同重」與「沒量」無法區分。本 PRD 選「日期路線」（寧可偶爾寫假點、零紀律），而非「值變化去重」（需手動 ±0.1 騙過去重、體重穩定期易漏記）。`/w` 覆蓋權是假點的修正出口。
- **基礎設施複用**：本功能不是從零接 COROS，而是在每天都在跑的 Python 管線（`coros_mcp.py` + `sync_coros_tdee`）上多掛一個 tool 呼叫，風險低。部署後第一天看 VPS log 確認 `queryUserInfo` 回傳正常即可。
- **token rotation 集中於 03:05**：體重同步刻意不 refresh，把 rotation 風險集中在單一每日時點。
