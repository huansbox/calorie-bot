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
