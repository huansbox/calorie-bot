## Parent PRD

`issues/prd.md`

## What to build

新增同步決策核心純函式 `decide_weight_sync(fetched, last_weight, today_has_row) -> Decision`，封裝所有「該不該寫 / 寫什麼 / 要不要告警」的判斷，**無 I/O**。對應 PRD「同步決策核心」節真值表。end-to-end 整合驗收發生在 `issues/005`，本 issue 以單元測試為驗收。

真值表：

| 條件 | action |
|---|---|
| today_has_row=True | SKIP |
| fetched is None | ALERT_NO_WRITE（抓取失敗）|
| last_weight is None | WRITE_SILENT（無基準，第一筆不擋）|
| \|fetched − last_weight\| > 3 | ALERT_NO_WRITE（跳變過大）|
| fetched == last_weight | WRITE + ALERT（假點提醒）|
| 其他 | WRITE_SILENT |

## Acceptance criteria

- [ ] 純函式無 I/O，回傳含 action 與（若有）告警/提醒訊息的決策結構
- [ ] 真值表六條分支全部實作
- [ ] 「值相同」採嚴格相等（一位小數）
- [ ] ±3kg 為閾值，同時涵蓋離譜壞值與真實大跳變
- [ ] 單元測試覆蓋每條分支 + 邊界（差=3.0 不觸發、=3.01 觸發、負向跳變 −3.01 觸發）
- [ ] 測試風格比照 `tests/test_dates.py` / `tests/test_backfill.py` 純函式真值表

## Blocked by

None - can start immediately

## User stories addressed

- User story 7（邏輯）
- User story 11（邏輯）
- User story 12（邏輯）
- User story 13（邏輯）
