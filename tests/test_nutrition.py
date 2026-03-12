from services.nutrition import calc_calories, format_macros


class TestCalcCalories:
    def test_basic(self):
        # 蛋白質10×4 + 碳水20×4 + 脂肪10×9 = 210
        assert calc_calories(10.0, 20.0, 10.0) == 210

    def test_zero(self):
        assert calc_calories(0, 0, 0) == 0

    def test_rounds(self):
        # 蛋白質1.5×4 + 碳水2.5×4 + 脂肪1.5×9 = 6+10+13.5 = 29.5 → 30
        assert calc_calories(1.5, 2.5, 1.5) == 30


class TestFormatMacros:
    def test_with_percentages(self):
        # total = 25×4 + 60×4 + 22×9 = 538
        # 蛋白質: 100/538=18.6%→19%, 碳水: 240/538=44.6%→45%, 脂肪: 198/538=36.8%→37%
        lines = format_macros(25.0, 60.0, 22.0)
        assert lines == [
            "🍗 蛋白質 25g (19%)",
            "🍚 碳水 60g (45%)",
            "🧈 脂肪 22g (37%)",
        ]

    def test_zero_calories(self):
        """全為 0 時不顯示百分比"""
        lines = format_macros(0, 0, 0)
        assert lines == [
            "🍗 蛋白質 0g",
            "🍚 碳水 0g",
            "🧈 脂肪 0g",
        ]
