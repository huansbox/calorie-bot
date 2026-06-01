## Parent PRD

`issues/prd.md`

## What to build

撰寫 forward-only 的 `weight_logs` schema migration SQL 與驗證查詢腳本。**本 issue 不對 production 執行**（執行見 `issues/002-execute-migration.md`）。對應 PRD「Schema 變更」與「Migration」兩節。

- 加 `log_date`(date) 與 `source`(text) 兩欄。
- 回填既有 42 筆：`source='manual'`、`log_date` = `recorded_at` 換算台灣時區(UTC+8)日期。
- 處理 3/13 同日兩筆衝突：**先 SELECT 出該日兩筆供人工確認**，再刪除午夜偏高那筆（72.3，台灣 00:29），保留晨重 71.2。**不盲刪寫死 id**（PRD 記錄的 id 僅供對照）。
- 資料壓成一天一筆後，建立 `log_date` UNIQUE 約束。
- 提供驗證查詢：確認總筆數 42→41、每個台灣日期恰一筆、UNIQUE 建立成功。

採 forward-only（不寫 rollback），符合單人專案慣例。現有 `scripts/check_weight_logs.py` 可作為驗證查詢基礎。

## Acceptance criteria

- [x] 加上 `log_date`(date)、`source`(text) 兩欄
- [x] 回填 `source='manual'`，`log_date` 由 `recorded_at` 以 UTC+8 換算
- [x] 3/13 衝突處理寫成「先 SELECT 兩筆、再 DELETE 午夜筆」，不盲刪寫死 id；結果保留 71.2、刪 72.3
- [x] 建立 `log_date` UNIQUE 約束的語句在「壓成一天一筆」之後
- [x] 附驗證查詢：可確認 41 筆、每台灣日期恰一筆、UNIQUE 生效
- [x] 腳本含註解說明 3/13 id 來源，可供審查，但不在本 issue 對 production 執行

## Blocked by

None - can start immediately

## User stories addressed

- User story 19
- User story 20
- User story 21（schema 部分）
