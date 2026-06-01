## Parent PRD

`issues/prd.md`

## What to build

對 production Supabase 執行 `issues/001-migration-script.md` 產出的 migration，並完成執行後驗證。此為**不可逆操作**（刪資料 + 加 UNIQUE 約束），需人工在執行前確認、執行後核對。對應 PRD「Migration」節。

此 issue 標記為 HITL：執行前須人工確認 3/13 兩筆資料與 PRD 描述一致、確認回填無誤，再按下執行。

## Acceptance criteria

- [ ] 執行前：人工跑 SELECT 確認 3/13 兩筆的 id 與數值與 PRD 描述一致（72.3 台灣午夜 / 71.2 晨重）
- [ ] 執行 migration script
- [ ] 執行後驗證：`weight_logs` 由 42 筆變 41 筆
- [ ] 執行後驗證：每個台灣日期恰一筆（重跑驗證查詢無同日多筆）
- [ ] 執行後驗證：`log_date` UNIQUE 約束已生效（嘗試插入同日兩筆會被擋）
- [ ] 抽查：既有週報體重區段（`get_weight_range`）每日至多一筆、無重複日期（US 18 驗證）

## Blocked by

- Blocked by `issues/001-migration-script.md`

## User stories addressed

- User story 5（schema / UNIQUE 部分）
- User story 18（一天一筆後週報自動整齊，此處為執行後驗證項）
