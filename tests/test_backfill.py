import pytest
from datetime import date, datetime, timedelta, timezone


class TestParseBackfillArgs:
    """parse_backfill_args(text) -> (meal_type, target_date, food_text)"""

    def _yesterday(self):
        from handlers.backfill import TW_TZ

        now_tw = datetime.now(TW_TZ)
        return (now_tw - timedelta(days=1)).date()

    def test_text_only(self):
        from handlers.backfill import parse_backfill_args

        meal_type, target_date, food_text = parse_backfill_args("雞排便當")
        assert meal_type == "其他"
        assert target_date == self._yesterday()
        assert food_text == "雞排便當"

    def test_with_meal_type(self):
        from handlers.backfill import parse_backfill_args

        meal_type, target_date, food_text = parse_backfill_args("2 雞排便當")
        assert meal_type == "午餐"
        assert target_date == self._yesterday()
        assert food_text == "雞排便當"

    def test_with_date(self):
        from handlers.backfill import parse_backfill_args

        meal_type, target_date, food_text = parse_backfill_args("雞排便當 0315")
        assert meal_type == "其他"
        assert target_date.month == 3
        assert target_date.day == 15
        assert food_text == "雞排便當"

    def test_with_meal_type_and_date(self):
        from handlers.backfill import parse_backfill_args

        meal_type, target_date, food_text = parse_backfill_args("2 雞排便當 0315")
        assert meal_type == "午餐"
        assert target_date.month == 3
        assert target_date.day == 15
        assert food_text == "雞排便當"

    def test_empty_raises(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("")

    def test_only_meal_type_no_food(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("2")

    def test_only_date_no_food(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("0315")

    def test_meal_type_and_date_no_food(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("2 0315")

    def test_future_date_rolls_back_year(self):
        from handlers.backfill import TW_TZ, parse_backfill_args

        now_tw = datetime.now(TW_TZ)
        tomorrow = now_tw.date() + timedelta(days=1)
        mmdd = f"{tomorrow.month:02d}{tomorrow.day:02d}"
        _, target_date, _ = parse_backfill_args(f"雞排便當 {mmdd}")
        assert target_date.year == now_tw.year - 1
        assert target_date.month == tomorrow.month
        assert target_date.day == tomorrow.day

    def test_today_date_rolls_back_year(self):
        from handlers.backfill import TW_TZ, parse_backfill_args

        now_tw = datetime.now(TW_TZ)
        mmdd = f"{now_tw.month:02d}{now_tw.day:02d}"
        _, target_date, _ = parse_backfill_args(f"雞排便當 {mmdd}")
        assert target_date.year == now_tw.year - 1
        assert target_date.month == now_tw.month
        assert target_date.day == now_tw.day

    def test_invalid_date_0230(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("雞排便當 0230")

    def test_invalid_date_0000(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("雞排便當 0000")

    def test_invalid_date_1301(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("雞排便當 1301")

    def test_photo_caption_meal_and_date_no_food(self):
        from handlers.backfill import parse_backfill_args

        with pytest.raises(ValueError):
            parse_backfill_args("2 0325")

    def test_photo_caption_with_hint(self):
        from handlers.backfill import parse_backfill_args

        meal_type, target_date, food_text = parse_backfill_args("2 滷肉飯 0325")
        assert meal_type == "午餐"
        assert target_date.month == 3
        assert target_date.day == 25
        assert food_text == "滷肉飯"

    def test_multi_word_food(self):
        from handlers.backfill import parse_backfill_args

        _, _, food_text = parse_backfill_args("2 起司 雞排 便當 0315")
        assert food_text == "起司 雞排 便當"
