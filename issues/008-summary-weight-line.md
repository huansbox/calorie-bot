## Parent PRD

`issues/prd.md`

## What to build

在每日 08:00 昨日摘要加一行最新體重，對應 PRD「可見性兩層—每日層」。

- `scheduler.py` 的 `daily_summary` 加「⚖️ 最新體重 X kg（日期，7 日均線 Y）」，取最近一筆體重及其 `log_date`，均線沿用 `get_weight_moving_avg`。
- 帶日期讓使用者看出是否為今日（08:00 時當日同步尚未跑，顯示的必然是昨日或更早）或久未量測。

## Acceptance criteria

- [ ] 08:00 摘要含一行最新體重 + 該筆 log_date + 7 日均線
- [ ] 體重取最近一筆（含其 log_date）
- [ ] 均線沿用既有 `get_weight_moving_avg`（不足 3 筆時的處理比照現有）
- [ ] 無體重資料時不出錯（優雅省略該行）
- [ ] source 不出現在摘要

## Blocked by

- Blocked by `issues/001-migration-script.md`

## User stories addressed

- User story 15
- User story 16
