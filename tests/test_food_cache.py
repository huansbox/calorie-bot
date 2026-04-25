from handlers.food_cache import is_cache_number, parse_cache_number


class TestParseCacheNumber:
    def test_lower_bound(self):
        assert parse_cache_number("11") == (11, 1.0)

    def test_upper_bound(self):
        assert parse_cache_number("99") == (99, 1.0)

    def test_below_range(self):
        # 1-4 是餐別覆蓋，10 也不算快取
        assert parse_cache_number("10") is None
        assert parse_cache_number("1") is None
        assert parse_cache_number("4") is None

    def test_above_range(self):
        assert parse_cache_number("100") is None
        assert parse_cache_number("999") is None

    def test_with_integer_multiplier(self):
        assert parse_cache_number("11 x2") == (11, 2.0)

    def test_with_decimal_multiplier(self):
        assert parse_cache_number("26 x0.5") == (26, 0.5)

    def test_uppercase_x(self):
        assert parse_cache_number("26 X2") == (26, 2.0)

    def test_no_space_before_x(self):
        assert parse_cache_number("11x2") == (11, 2.0)

    def test_strips_whitespace(self):
        assert parse_cache_number("  11  ") == (11, 1.0)
        assert parse_cache_number("  11 x2  ") == (11, 2.0)

    def test_invalid_text(self):
        assert parse_cache_number("abc") is None
        assert parse_cache_number("") is None

    def test_invalid_multiplier(self):
        assert parse_cache_number("11 x") is None
        assert parse_cache_number("11 abc") is None
        assert parse_cache_number("11 x-2") is None


class TestIsCacheNumber:
    def test_valid(self):
        assert is_cache_number("11") is True
        assert is_cache_number("99") is True
        assert is_cache_number("11 x2") is True

    def test_invalid(self):
        assert is_cache_number("1") is False
        assert is_cache_number("100") is False
        assert is_cache_number("abc") is False
