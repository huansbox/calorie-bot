import re
from datetime import date, datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))

MEAL_TYPE_MAP = {
    "1": "早餐",
    "2": "午餐",
    "3": "晚餐",
    "4": "其他",
}


def parse_backfill_args(text: str) -> tuple[str, date, str]:
    """解析補記指令參數。

    Returns:
        (meal_type, target_date, food_text)

    Raises:
        ValueError: 輸入無法解析或缺少食物描述。
    """
    text = text.strip()
    if not text:
        raise ValueError("請輸入食物描述")

    tokens = text.split()

    # 1) 餐別：第一個 token 若為 1-4
    meal_type = "其他"
    if tokens and tokens[0] in MEAL_TYPE_MAP:
        meal_type = MEAL_TYPE_MAP[tokens.pop(0)]

    # 2) 日期：最後一個 token 若為合法 MMDD
    now_tw = datetime.now(TW_TZ)
    target_date = (now_tw - timedelta(days=1)).date()

    if tokens and re.fullmatch(r"\d{4}", tokens[-1]):
        mmdd = tokens.pop()
        try:
            parsed = datetime.strptime(f"2000{mmdd}", "%Y%m%d")
        except ValueError:
            raise ValueError(f"日期格式錯誤：{mmdd}")
        candidate = date(now_tw.year, parsed.month, parsed.day)
        if candidate >= now_tw.date():
            candidate = date(now_tw.year - 1, parsed.month, parsed.day)
        target_date = candidate

    # 3) 食物描述
    food_text = " ".join(tokens)
    if not food_text:
        raise ValueError("請輸入食物描述")

    return meal_type, target_date, food_text


def date_to_recorded_at(target_date: date) -> str:
    """將目標日期轉為 UTC ISO 字串（台灣正午 12:00 → UTC 04:00）。"""
    tw_noon = datetime(
        target_date.year, target_date.month, target_date.day,
        12, 0, 0, tzinfo=TW_TZ,
    )
    return tw_noon.astimezone(timezone.utc).isoformat()
