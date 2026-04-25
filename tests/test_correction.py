from handlers.correction import is_meal_type_correction


class TestIsMealTypeCorrection:
    def test_valid_codes(self):
        assert is_meal_type_correction("1") is True
        assert is_meal_type_correction("2") is True
        assert is_meal_type_correction("3") is True
        assert is_meal_type_correction("4") is True

    def test_strips_whitespace(self):
        assert is_meal_type_correction(" 1 ") is True
        assert is_meal_type_correction("\t2\n") is True

    def test_out_of_range(self):
        assert is_meal_type_correction("0") is False
        assert is_meal_type_correction("5") is False

    def test_cache_number_not_correction(self):
        # 11-99 是快取編號，不能誤判為餐別覆蓋
        assert is_meal_type_correction("11") is False
        assert is_meal_type_correction("99") is False

    def test_non_numeric(self):
        assert is_meal_type_correction("") is False
        assert is_meal_type_correction("abc") is False
        assert is_meal_type_correction("1.0") is False
