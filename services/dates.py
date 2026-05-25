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
