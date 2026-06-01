## Parent PRD

`issues/prd.md`

## What to build

第一顆 tracer bullet：打通「COROS 抓取 → 決策 → 寫入 DB」最小端到端路徑。對應 PRD「排程」「寫入規則」「Token 處理」節的核心寫入路徑。

- `services/db.py`：新增 upsert on `log_date`（比照 `upsert_tdee` 的 `on_conflict`）、取最近一筆（值 + log_date）、判斷「今天台灣日期是否已有筆」。
- `scheduler.py`：新增 `sync_coros_weight` job，**先只掛 10:29 單一時點**；組裝 `load_token → fetch_user_info → parse_user_weight → 取最近筆 → decide_weight_sync`。本 issue **只消費 WRITE_SILENT / SKIP**（寫入或跳過）；ALERT 與 WRITE+ALERT 的 Telegram 通知留 `issues/006`。
- **實作陷阱（US 22）**：token 沿用既有 03:05 `sync_coros_tdee` refresh 過的 access_token，本 job 自身**不 refresh**。

驗收：手動觸發（本機對測試庫或部署後），`weight_logs` 出現一筆 `source='coros'` 的今日記錄；當天已有筆時不重複寫。

## Acceptance criteria

- [ ] `db.py` 有 upsert on `log_date`、取最近筆、今日是否有筆三個能力
- [ ] `sync_coros_weight` 串起抓取→parse→決策→寫入，掛 10:29
- [ ] WRITE_SILENT 路徑：當天無筆 → 寫入一筆 `source='coros'`
- [ ] SKIP 路徑：當天已有筆 → 不寫、不報錯
- [ ] token 沿用既有 access_token，函式內**不呼叫 refresh**
- [ ] 手動觸發可驗證端到端寫入（log 或 DB 查得到今日 coros 筆）

## Blocked by

- Blocked by `issues/001-migration-script.md`
- Blocked by `issues/003-coros-fetch-parse.md`
- Blocked by `issues/004-decide-weight-sync.md`

## User stories addressed

- User story 1
- User story 2（整條管線自動跑）
- User story 3
- User story 7
- User story 11
