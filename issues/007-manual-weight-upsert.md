## Parent PRD

`issues/prd.md`

## What to build

把手動 `/w` 改成 upsert + 寫 source，對應 PRD「寫入規則—手動」。

- `handlers/weight.py`：`/w` 改為 upsert on 今天台灣 `log_date`、`source='manual'`，覆蓋當天既有筆（含自動 coros 筆）。
- **清掉現有冗餘的 prev 計算**：weight.py 目前把 prev 算了兩遍（先 `get_previous_weight`、又被 `get_last_weight` 覆蓋），順手清理。
- **驗證陷阱（US 17）**：upsert 後「上次 N 天前、變化 ±X」仍正確；特別是同一天改兩次時，第二次的 prev 不該是第一次的自己（因 upsert 蓋掉、不新增 row，prev 應指向前一天）。

> 註：「當天已有 coros 自動筆 → `/w` 覆蓋」這條的端到端抽驗待 `issues/005-auto-sync-tracer.md` 上線後補做；007 本身的 upsert 覆蓋邏輯用兩次手動 `/w` 即可驗。

## Acceptance criteria

- [x] `/w` 改 upsert on `log_date`，寫 `source='manual'`
- [ ] 當天已有 coros 自動筆 → `/w` 覆蓋成 manual 值（手動優先）⏳ 待 6/02 有 coros 自動筆後驗（見 CLAUDE.md 待辦）
- [x] 同一天重複 `/w` → 以最後一次為準（覆蓋，不新增 row）
- [x] 移除 weight.py 冗餘的 prev 雙重計算
- [x] 驗證「上次 / 變化」顯示在 upsert 模型下正確（同日改兩次時 prev 指向前一天而非自己）
- [x] source 不出現在 `/w` 回覆訊息

## Blocked by

- Blocked by `issues/001-migration-script.md`

## User stories addressed

- User story 8
- User story 9
- User story 10
- User story 17
- User story 21（不顯示部分）
