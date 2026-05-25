# 2026-05-25：昨日摘要食物清單 + /s 過去日期 + 移除每日目標

## 背景

三件事一起做，按 **T1 → T2 → T3** 序列執行（同一 session、三個獨立 commit）。

| Task | 目的 |
|------|------|
| T1 | 移除「每日攝取目標」顯示與 /g 指令 |
| T2 | /s 支援 `/s MMDD` 查過去日期 |
| T3 | 每日 08:00 昨日摘要加食物清單（早午晚必列、空顯示「（無）」） |

**序列原因**：三個 task 都動 `handlers/query.py`，T1/T3 都動 `scheduler.py`。序列做避免 merge conflict，且 T1 先清理讓 T2/T3 的 base 更乾淨。

## File Map

| 檔案 | T1 | T2 | T3 |
|------|----|----|----|
| `handlers/query.py` | 刪 1 行 + import | 大改 cmd_today | 改用 helper |
| `scheduler.py` | 改 1 行 + import | — | 大改 daily_summary |
| `handlers/meal.py` | 改 1 行 + import | — | — |
| `handlers/manual_meal.py` | 改 1 行 + import | — | — |
| `handlers/food_cache.py` | 改 1 行 + import | — | — |
| `handlers/correction.py` | 改 1 行 + import | — | — |
| `handlers/backfill.py` | 改 2 行 + 2 imports | 改用 parse_mmdd helper | — |
| `handlers/goal.py` | **刪整檔** | — | — |
| `main.py` | 刪 4 處（import / handler / help / CommandHandler） | — | — |
| `config.py` | 刪 `DAILY_CALORIE_GOAL` / `get_calorie_goal` / `set_calorie_goal` | — | — |
| `README.md` | 刪 /g 與 `DAILY_CALORIE_GOAL` 行 | — | — |
| `CLAUDE.md` | 刪 goal.py 描述、每日目標段落 | 更新檔案結構 | 更新檔案結構 |
| `services/dates.py` | — | **新增** | — |
| `services/format.py` | — | — | **新增** |
| `tests/test_dates.py` | — | **新增** | — |
| `tests/test_format.py` | — | — | **新增** |

## Function Interface Table

| 函式 | 簽名 | 呼叫者 |
|------|------|--------|
| `parse_mmdd` | `(mmdd: str, now_tw: datetime \| None = None) -> date` | `handlers/backfill.py`, `handlers/query.py` |
| `format_meal_groups` | `(meals: list[dict], *, force_meal_types: list[str] \| None = None, empty_placeholder: str = "（無）") -> list[str]` | `handlers/query.py`, `scheduler.py` |

---

## Task 1: 移除每日攝取目標顯示與 /g 指令

**Risk: Low** — 純機械化刪減，無新邏輯。先做這個讓後續 task 在乾淨 base 上開工。

### Steps

**1.1 `handlers/meal.py`**
- 刪除 import `get_calorie_goal`（line 8 的 `from config import MEDIA_DIR, get_calorie_goal` → 改 `from config import MEDIA_DIR`）
- 修改 line 119：
  ```python
  # 改前
  f"今日累計：{_format_number(total_cal)} / {_format_number(get_calorie_goal())} kcal",
  # 改後
  f"今日累計：{_format_number(total_cal)} kcal",
  ```

**1.2 `handlers/manual_meal.py`**
- 刪 line 134 的 `from config import get_calorie_goal`
- 修改 line 165：`今日累計：X / Y kcal` → `今日累計：X kcal`

**1.3 `handlers/food_cache.py`**
- 刪 line 7 的 `from config import get_calorie_goal`
- 修改 line 102：`今日累計：X / Y kcal` → `今日累計：X kcal`

**1.4 `handlers/correction.py`**
- 刪 line 62 的 `from config import get_calorie_goal`
- 修改 line 104：`今日累計：X / Y kcal` → `今日累計：X kcal`

**1.5 `handlers/backfill.py`**
- 刪 line 168 的 `from config import get_calorie_goal`（在 `_process_backfill_cache` 內）
- 修改 line 211：`{date_str} 累計：X / Y kcal` → `{date_str} 累計：X kcal`
- 刪 line 234 的 `from config import MEDIA_DIR, get_calorie_goal`（在 `_process_backfill` 內）→ 改 `from config import MEDIA_DIR`
- 修改 line 287：`{date_str} 累計：X / Y kcal` → `{date_str} 累計：X kcal`

**1.6 `handlers/query.py`**
- 刪 line 7 的 `from config import get_calorie_goal`
- 刪除 line 78-79（空行 + 「目標攝取參考」整段）：
  ```python
  lines.append("")
  lines.append(f"目標攝取參考：{_fmt(get_calorie_goal())} kcal")
  ```

**1.7 `scheduler.py`**
- 修改 line 8：移除 import 中的 `get_calorie_goal`
  ```python
  # 改前
  from config import BMR, COROS_TOKEN_PATH, PUSH_HOUR, TELEGRAM_CHAT_ID, get_calorie_goal
  # 改後
  from config import BMR, COROS_TOKEN_PATH, PUSH_HOUR, TELEGRAM_CHAT_ID
  ```
- 修改 line 50：
  ```python
  # 改前
  f"攝取：{_fmt(total_cal)} kcal　目標參考：{_fmt(get_calorie_goal())} kcal",
  # 改後
  f"攝取：{_fmt(total_cal)} kcal",
  ```

**1.8 刪除 `handlers/goal.py`** 整檔。

**1.9 `main.py`**
- 刪 line 32：`from handlers.goal import cmd_goal`
- 刪 line 119-121：`_cmd_goal` 整個函式
- 刪 line 180：`"/g 熱量 — 調整每日目標",`（help 文案那一行）
- 刪 line 221：`app.add_handler(CommandHandler("g", _cmd_goal))`

**1.10 `config.py`**
- 刪 line 18-28（`DAILY_CALORIE_GOAL`、`_calorie_goal`、`get_calorie_goal`、`set_calorie_goal`）。
- 注意：line 29 的 `BMR` 起始那行若被刪到要保留。

**1.11 `README.md`**
- 刪 line 21：`| \`/g 1800\` | 調整每日熱量目標（重啟回預設） |`
- 刪 line 77：`| \`DAILY_CALORIE_GOAL\` | 每日攝取目標 kcal (預設 2000) | 否 |`

**1.12 `CLAUDE.md`**
- 刪 line 35：`  goal.py            # /g 動態調整每日熱量目標`
- 刪 line 90：`- **每日目標**：/g 動態調整（記憶體內，重啟回 .env 預設值）`

**1.13 全域搜尋驗證**
執行 `grep -r "get_calorie_goal\|set_calorie_goal\|DAILY_CALORIE_GOAL" --include="*.py"`，預期 0 個 hit（除了已刪檔的歷史殘留）。
也檢查 `calorie-bot-spec.md`（如有引用，可保留歷史快照不動，這個檔是 spec 不是 active doc）。

### 測試

跑既有測試確認沒壞：
```bash
uv run pytest
```

預期：全綠（不會有測試直接 reference `get_calorie_goal`，因為各 handler 內的「今日累計」文字 assertion 也應該不存在於測試裡——若有，需更新）。

**先檢查**：`grep -r "今日累計\|目標攝取" tests/`，若有命中，updatesertion。

### Commit

```
refactor: remove daily calorie goal display and /g command

- 8 處顯示全拿（meal/manual_meal/food_cache/correction/backfill/query/scheduler）
- 刪除 handlers/goal.py 與 /g CommandHandler
- 移除 config.py 的 DAILY_CALORIE_GOAL、get_calorie_goal、set_calorie_goal
- 更新 README.md、CLAUDE.md
```

---

## Task 2: /s 支援 MMDD 過去日期

**Risk: Medium** — 抽 helper + 大改 cmd_today + 文案動態化 + 新測試。

### 2.1 新增 `services/dates.py`

```python
"""日期解析共用工具。"""
from datetime import date, datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))


def parse_mmdd(mmdd: str, now_tw: datetime | None = None) -> date:
    """將 MMDD 4 位數字串解析為 date。

    今天或未來日期自動退回上一年（比照 /b 行為）。

    Args:
        mmdd: 4 位數字字串，如 "0524"。
        now_tw: 注入「現在」用於測試；預設為當下台灣時間。

    Returns:
        解析後的 date 物件。

    Raises:
        ValueError: 格式不合法或月日無效（如 0230、abcd）。
    """
    if now_tw is None:
        now_tw = datetime.now(TW_TZ)

    if len(mmdd) != 4 or not mmdd.isdigit():
        raise ValueError(f"日期格式錯誤：{mmdd}")

    try:
        parsed = datetime.strptime(f"2000{mmdd}", "%Y%m%d")
        candidate = date(now_tw.year, parsed.month, parsed.day)
    except ValueError:
        raise ValueError(f"日期格式錯誤：{mmdd}")

    if candidate >= now_tw.date():
        try:
            candidate = date(now_tw.year - 1, parsed.month, parsed.day)
        except ValueError:
            raise ValueError(f"日期格式錯誤：{mmdd}")

    return candidate
```

### 2.2 重構 `handlers/backfill.py`

修改 `parse_backfill_args` 的 line 61-73 區塊，改用 helper：

```python
# 改前
if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
    mmdd = tokens.pop()
    try:
        parsed = datetime.strptime(f"2000{mmdd}", "%Y%m%d")
        candidate = date(now_tw.year, parsed.month, parsed.day)
    except ValueError:
        raise ValueError(f"日期格式錯誤：{mmdd}")
    if candidate >= now_tw.date():
        try:
            candidate = date(now_tw.year - 1, parsed.month, parsed.day)
        except ValueError:
            raise ValueError(f"日期格式錯誤：{mmdd}")
    target_date = candidate

# 改後
if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
    mmdd = tokens.pop()
    target_date = parse_mmdd(mmdd, now_tw=now_tw)
```

於檔頂新增 `from services.dates import parse_mmdd`。`re` import 仍保留（`re.fullmatch` 還在用）。

**驗證**：跑 `tests/test_backfill.py` 全綠（行為未變）。

### 2.3 重寫 `handlers/query.py` 的 `cmd_today`

完整改寫該函式（簽名不變）：

```python
async def cmd_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """處理 /s 指令，顯示今日或指定日期完整記錄。

    用法：
        /s         → 今日
        /s MMDD    → 指定日期（今天/未來自動退回上一年）
    """
    args = context.args
    now_tw = datetime.now(TW_TZ)

    if args:
        try:
            target_date = parse_mmdd(args[0], now_tw=now_tw)
        except ValueError as e:
            await update.message.reply_text(f"{e}\n\n用法：/s [MMDD]")
            return
        meals = get_meals_by_date(target_date)
        tdee_row = get_tdee_by_date(target_date)
        is_today = False
    else:
        target_date = now_tw.date()
        meals = get_today_meals()
        tdee_row = get_today_tdee()
        is_today = True

    date_str = target_date.strftime("%-m/%-d") if not _is_windows() else target_date.strftime("%#m/%#d")

    if not meals:
        await update.message.reply_text(f"📋 記錄（{date_str}）\n\n尚無記錄")
        return

    lines = [f"📋 記錄（{date_str}）"]

    total_cal = 0
    total_protein = 0.0
    total_carbs = 0.0
    total_fat = 0.0

    meal_order = ["早餐", "午餐", "晚餐", "其他"]
    grouped: dict[str, list] = {t: [] for t in meal_order}
    for m in meals:
        meal_type = m["meal_type"] or "其他"
        if meal_type not in grouped:
            grouped[meal_type] = []
        grouped[meal_type].append(m)
        total_cal += m["calories"] or 0
        total_protein += float(m["protein_g"] or 0)
        total_carbs += float(m["carbs_g"] or 0)
        total_fat += float(m["fat_g"] or 0)

    for mt in meal_order:
        items = grouped[mt]
        if not items:
            continue
        sub_cal = sum(m["calories"] or 0 for m in items)
        lines.append("")
        lines.append(f"【{mt}】{_fmt(sub_cal)} kcal")
        for m in items:
            lines.append(f"  {m['description'] or ''}　{_fmt(m['calories'] or 0)} kcal")

    lines.append("")
    lines.append(f"攝取合計：{_fmt(total_cal)} kcal")
    lines.extend(format_macros(total_protein, total_carbs, total_fat))

    lines.append("")
    if tdee_row:
        tdee = tdee_row["tdee_kcal"]
        deficit = total_cal - tdee
        lines.append(f"總消耗（TDEE）：{_fmt(tdee)} kcal")
        if deficit <= 0:
            lines.append(f"熱量缺口：{_fmt(deficit)} kcal")
        else:
            lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")
    else:
        if is_today:
            lines.append("今日尚未記錄 TDEE（/t <活動消耗> n）")
        else:
            lines.append(f"{date_str} 未記錄 TDEE")

    await update.message.reply_text("\n".join(lines))
```

**Imports 更新**：
- 加 `from services.dates import parse_mmdd`
- 加 `from services.db import get_meals_by_date, get_tdee_by_date`（既有的 `get_today_meals`、`get_today_tdee` 保留）

**注意**：本 task 還沒抽 `format_meal_groups` helper（Task 3 才做）。query.py 的分組邏輯先保留原樣，T3 再統一抽。

### 2.4 新增 `tests/test_dates.py`

```python
import pytest
from datetime import date, datetime, timedelta, timezone


TW_TZ = timezone(timedelta(hours=8))


class TestParseMmdd:
    def test_basic_past_date(self):
        from services.dates import parse_mmdd
        now = datetime(2026, 5, 25, 10, 0, tzinfo=TW_TZ)
        result = parse_mmdd("0524", now_tw=now)
        assert result == date(2026, 5, 24)

    def test_today_rolls_back_one_year(self):
        from services.dates import parse_mmdd
        now = datetime(2026, 5, 25, 10, 0, tzinfo=TW_TZ)
        result = parse_mmdd("0525", now_tw=now)
        assert result == date(2025, 5, 25)

    def test_future_rolls_back_one_year(self):
        from services.dates import parse_mmdd
        now = datetime(2026, 5, 25, 10, 0, tzinfo=TW_TZ)
        result = parse_mmdd("1231", now_tw=now)
        assert result == date(2025, 12, 31)

    def test_january_in_february_no_rollback(self):
        from services.dates import parse_mmdd
        now = datetime(2026, 2, 15, 10, 0, tzinfo=TW_TZ)
        result = parse_mmdd("0110", now_tw=now)
        assert result == date(2026, 1, 10)

    def test_invalid_format_too_short(self):
        from services.dates import parse_mmdd
        with pytest.raises(ValueError):
            parse_mmdd("525")

    def test_invalid_format_non_digit(self):
        from services.dates import parse_mmdd
        with pytest.raises(ValueError):
            parse_mmdd("abcd")

    def test_invalid_month(self):
        from services.dates import parse_mmdd
        with pytest.raises(ValueError):
            parse_mmdd("1335")

    def test_invalid_day(self):
        from services.dates import parse_mmdd
        with pytest.raises(ValueError):
            parse_mmdd("0230")
```

### 測試

```bash
uv run pytest tests/test_dates.py tests/test_backfill.py
```

預期：`test_dates.py` 8 case 全綠、`test_backfill.py` 不變（24 case 維持）。

### Commit

```
feat: /s supports MMDD for past dates

- 新增 services/dates.py 的 parse_mmdd helper（含今天/未來退一年邏輯）
- handlers/backfill.py 改用共用 helper（行為不變）
- /s 接 context.args，無參數→今日（維持原行為），MMDD→指定日期
- 文案動態化（標題日期、TDEE 未記錄提示）
- 補 tests/test_dates.py 8 case
```

---

## Task 3: 昨日摘要加食物清單（早午晚必列）

**Risk: Medium** — 抽 helper、兩處 caller 更新、新測試。

### 3.1 新增 `services/format.py`

```python
"""訊息格式化共用工具。"""


def format_meal_groups(
    meals: list[dict],
    *,
    force_meal_types: list[str] | None = None,
    empty_placeholder: str = "（無）",
) -> list[str]:
    """格式化餐別分組清單。

    Args:
        meals: meal dict 列表，每筆需含 meal_type / description / calories。
        force_meal_types: 強制列出的餐別（即使空也顯示）。預設不強制。
        empty_placeholder: force 模式下空餐別顯示的文字。

    Returns:
        多行字串 list，第一行為空行（用於與前文分隔）。
        meals 為空且無 force 時回傳 []。

    格式範例（force_meal_types=["早餐", "午餐", "晚餐"]）：
        ""
        "【早餐】580 kcal"
        "  燕麥豆漿　580 kcal"
        "【午餐】720 kcal"
        "  雞肉飯　720 kcal"
        "【晚餐】（無）"
        "【其他】180 kcal"
        "  優格　180 kcal"
    """
    meal_order = ["早餐", "午餐", "晚餐", "其他"]
    grouped: dict[str, list] = {t: [] for t in meal_order}
    for m in meals:
        meal_type = m.get("meal_type") or "其他"
        if meal_type not in grouped:
            grouped[meal_type] = []
        grouped[meal_type].append(m)

    force_set = set(force_meal_types or [])
    lines: list[str] = []

    for mt in meal_order:
        items = grouped[mt]
        if not items and mt not in force_set:
            continue
        if not items:
            lines.append(f"【{mt}】{empty_placeholder}")
        else:
            sub_cal = sum(m["calories"] or 0 for m in items)
            lines.append(f"【{mt}】{sub_cal:,} kcal")
            for m in items:
                desc = m.get("description") or ""
                cal = m.get("calories") or 0
                lines.append(f"  {desc}　{cal:,} kcal")

    if lines:
        lines.insert(0, "")  # 與前文分隔的空行

    return lines
```

**設計取捨**：
- 第一行空行由 helper 內部加，caller 直接 `lines.extend(format_meal_groups(...))` 即可。
- 空 list 不加空行（避免無內容時殘留空白）。
- 「其他」永遠走「有才列」邏輯（不會被 force_meal_types 強制顯示——除非 caller 明確傳入，但這違反設計意圖；caller 不傳即可）。

### 3.2 重構 `handlers/query.py` 用 helper

把 Task 2 留下的「分組邏輯」（line 約 38-58）取代為 helper 呼叫。

修改後的 cmd_today 中段：

```python
# 計算總計（這段保留，因為 TDEE 區塊需要 total_cal）
total_cal = 0
total_protein = 0.0
total_carbs = 0.0
total_fat = 0.0
for m in meals:
    total_cal += m["calories"] or 0
    total_protein += float(m["protein_g"] or 0)
    total_carbs += float(m["carbs_g"] or 0)
    total_fat += float(m["fat_g"] or 0)

# 餐別分組清單（用共用 helper，不強制空餐別）
lines.extend(format_meal_groups(meals))

lines.append("")
lines.append(f"攝取合計：{_fmt(total_cal)} kcal")
lines.extend(format_macros(total_protein, total_carbs, total_fat))

# ...TDEE 區塊（不變）
```

Import 加 `from services.format import format_meal_groups`。

### 3.3 重構 `scheduler.py` 的 `daily_summary`

```python
async def daily_summary(app: Application):
    """每日早上推播昨日摘要。"""
    now_tw = datetime.now(TW_TZ)
    yesterday = (now_tw - timedelta(days=1)).date()
    meals = get_meals_by_date(yesterday)

    if not meals:
        logger.info("No meals yesterday, skipping daily summary")
        return

    date_str = yesterday.strftime("%-m/%-d") if os.name != "nt" else yesterday.strftime("%#m/%#d")

    total_cal = sum(m["calories"] or 0 for m in meals)
    total_protein = sum(float(m["protein_g"] or 0) for m in meals)
    total_carbs = sum(float(m["carbs_g"] or 0) for m in meals)
    total_fat = sum(float(m["fat_g"] or 0) for m in meals)

    lines = [
        f"📊 昨日摘要（{date_str}）",
        "",
        f"攝取：{_fmt(total_cal)} kcal",
        *format_macros(total_protein, total_carbs, total_fat),
        f"記錄筆數：{len(meals)} 餐",
    ]

    # 食物清單（早午晚強制列出、空顯示「（無）」、其他有才列）
    lines.extend(format_meal_groups(meals, force_meal_types=["早餐", "午餐", "晚餐"]))

    tdee_row = get_tdee_by_date(yesterday)
    lines.append("")
    if tdee_row:
        tdee = tdee_row["tdee_kcal"]
        deficit = total_cal - tdee
        lines.append(f"總消耗（TDEE）：{_fmt(tdee)} kcal")
        if deficit <= 0:
            lines.append(f"熱量缺口：{_fmt(deficit)} kcal ✅")
        else:
            lines.append(f"熱量盈餘：+{_fmt(deficit)} kcal")
    else:
        lines.append("昨日未記錄 TDEE（/t <活動消耗>）")

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="\n".join(lines))
    logger.info("Daily summary sent")
```

Import 加 `from services.format import format_meal_groups`。

### 3.4 新增 `tests/test_format.py`

```python
class TestFormatMealGroups:
    def test_empty_meals_no_force(self):
        from services.format import format_meal_groups
        assert format_meal_groups([]) == []

    def test_single_meal_type(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "午餐", "description": "雞肉飯", "calories": 720},
        ]
        result = format_meal_groups(meals)
        assert result == [
            "",
            "【午餐】720 kcal",
            "  雞肉飯　720 kcal",
        ]

    def test_all_four_meal_types(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "早餐", "description": "燕麥", "calories": 300},
            {"meal_type": "午餐", "description": "便當", "calories": 700},
            {"meal_type": "晚餐", "description": "麵", "calories": 600},
            {"meal_type": "其他", "description": "優格", "calories": 150},
        ]
        result = format_meal_groups(meals)
        assert "【早餐】300 kcal" in result
        assert "【其他】150 kcal" in result

    def test_force_meal_types_shows_empty_placeholder(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "早餐", "description": "燕麥", "calories": 300},
            {"meal_type": "午餐", "description": "便當", "calories": 700},
            # 晚餐沒記
            {"meal_type": "其他", "description": "優格", "calories": 150},
        ]
        result = format_meal_groups(meals, force_meal_types=["早餐", "午餐", "晚餐"])
        assert "【晚餐】（無）" in result
        # 其他有才列
        assert "【其他】150 kcal" in result

    def test_force_does_not_force_other(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "早餐", "description": "燕麥", "calories": 300},
            # 其他沒記，不該出現
        ]
        result = format_meal_groups(meals, force_meal_types=["早餐", "午餐", "晚餐"])
        joined = "\n".join(result)
        assert "【其他】" not in joined
        assert "【午餐】（無）" in joined
        assert "【晚餐】（無）" in joined

    def test_multiple_items_same_meal_type(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "午餐", "description": "便當", "calories": 700},
            {"meal_type": "午餐", "description": "飲料", "calories": 200},
        ]
        result = format_meal_groups(meals)
        # 小計應為 900
        assert "【午餐】900 kcal" in result
        # 兩筆都列
        assert "  便當　700 kcal" in result
        assert "  飲料　200 kcal" in result

    def test_unknown_meal_type_falls_into_other(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": None, "description": "宵夜", "calories": 400},
        ]
        result = format_meal_groups(meals)
        assert "【其他】400 kcal" in result

    def test_thousand_separator(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "午餐", "description": "buffet", "calories": 1500},
        ]
        result = format_meal_groups(meals)
        assert "【午餐】1,500 kcal" in result
        assert "  buffet　1,500 kcal" in result
```

### 測試

```bash
uv run pytest tests/test_format.py
uv run pytest  # 全跑確認沒回歸
```

預期：`test_format.py` 8 case 全綠、整體測試集無回歸（query.py 抽 helper 後行為一致）。

### CLAUDE.md 更新

把檔案結構區塊更新：
- `services/` 加入 `dates.py # MMDD 日期解析 (有單元測試)` 與 `format.py # 訊息格式化 helper (有單元測試)`
- `tests/` 加入 `test_dates.py` 與 `test_format.py` 條目
- 「單元測試涵蓋」那行加入新測試檔
- 移除 `goal.py` 行（T1 已做但若漏更新，T3 補上）

### Commit

```
feat: yesterday summary includes meal-grouped food list

- 新增 services/format.py 的 format_meal_groups helper
- handlers/query.py 改用 helper（行為不變）
- scheduler.py 昨日摘要加入分餐別清單（早午晚必列，空顯示「（無）」）
- 補 tests/test_format.py 8 case
- 更新 CLAUDE.md 檔案結構
```

---

## 完成標準

- 三個 commit 各自綠燈通過（`uv run pytest`）
- `git diff main..HEAD` 預期改動約 8-10 個檔案
- 手動 sanity check（不強制）：
  - 啟動 bot 後 `/s` 顯示今日（無「目標」行）
  - `/s 0524` 顯示 5/24 記錄
  - `/g` 指令應該收不到回應（已刪）
  - 隔日 08:00 推播應含分餐別清單（無法在開發環境驗證，VPS 部署後觀察）

## 回報格式

完成後回報：
- Branch: `feat/summary-list-and-goal-removal`
- Commits: 3
- 測試：pass/fail + 未通過項
- 未解決：有/無 + 說明
