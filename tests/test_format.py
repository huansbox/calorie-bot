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
            {"meal_type": "其他", "description": "優格", "calories": 150},
        ]
        result = format_meal_groups(meals, force_meal_types=["早餐", "午餐", "晚餐"])
        assert "【晚餐】（無）" in result
        assert "【其他】150 kcal" in result

    def test_force_does_not_force_other(self):
        from services.format import format_meal_groups
        meals = [
            {"meal_type": "早餐", "description": "燕麥", "calories": 300},
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
        assert "【午餐】900 kcal" in result
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
