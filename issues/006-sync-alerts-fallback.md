## Parent PRD

`issues/prd.md`

## What to build

補齊決策的通知分支與 fallback 時點，對應 PRD「可見性兩層—即時層」與「排程—22:29」。

- 接上 `decide_weight_sync` 的 ALERT_NO_WRITE（抓取失敗 / 跳變過大 → 推告警請 `/w` 確認）與 WRITE+ALERT（值同上次 → 寫入並推「若還沒量請 `/w`」輕提醒）的 Telegram 發送，比照 `sync_coros_tdee` 既有告警寫法。
- `scheduler.py` 加掛 22:29 fallback 時點（與 10:29 同一 job 邏輯；fallback 透過「當天已有筆 → SKIP」自動成立）。
- 驗證「晨重優先」：10:29 先寫，22:29 因當天已有筆而 SKIP（US 6）。
- 驗證 token 沿用不 refresh（US 22）。

## Acceptance criteria

- [ ] ALERT_NO_WRITE → 推 Telegram 告警，內容提示 `/w` 確認；不寫入
- [ ] WRITE+ALERT → 寫入 + 推輕提醒「與上次相同，若還沒量請 `/w`」
- [ ] 抓取 / 解析失敗 → 走告警路徑（US 14）
- [ ] 22:29 fallback 時點掛上，與 10:29 共用邏輯
- [ ] 驗證：早上已寫，22:29 SKIP（不重複、不覆蓋）→ 晨重優先成立
- [ ] 確認整條同步未呼叫 refresh（token 沿用 03:05）

## Blocked by

- Blocked by `issues/005-auto-sync-tracer.md`

## User stories addressed

- User story 4
- User story 6
- User story 12
- User story 13
- User story 14
- User story 22
