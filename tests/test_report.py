from datetime import date

import pytest

from handlers.report import (
    _build_balance_section,
    _build_daily_intake_map,
    _build_daily_tdee_map,
    _build_macro_section,
    _build_meal_type_section,
    _build_weight_section,
)


def _meal(recorded_at: str, calories: int = 500, protein_g: float = 0.0,
          carbs_g: float = 0.0, fat_g: float = 0.0, meal_type: str = "午餐") -> dict:
    return {
        "recorded_at": recorded_at,
        "calories": calories,
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "meal_type": meal_type,
    }


class TestBuildDailyIntakeMap:
    def test_empty(self):
        assert _build_daily_intake_map([]) == {}

    def test_single_meal_taiwan_morning(self):
        # 台灣 4/19 09:00 = UTC 4/19 01:00
        meals = [_meal("2026-04-19T01:00:00+00:00", 500)]
        result = _build_daily_intake_map(meals)
        assert result == {date(2026, 4, 19): 500}

    def test_crosses_date_boundary(self):
        # UTC 4/19 16:00 = 台灣 4/20 00:00 → 應算 4/20
        meals = [_meal("2026-04-19T16:00:00+00:00", 500)]
        result = _build_daily_intake_map(meals)
        assert result == {date(2026, 4, 20): 500}

    def test_multiple_meals_same_day_accumulate(self):
        meals = [
            _meal("2026-04-19T01:00:00+00:00", 500),
            _meal("2026-04-19T05:00:00+00:00", 700),
        ]
        result = _build_daily_intake_map(meals)
        assert result == {date(2026, 4, 19): 1200}

    def test_calories_none_treated_as_zero(self):
        meals = [_meal("2026-04-19T01:00:00+00:00", calories=None)]
        result = _build_daily_intake_map(meals)
        assert result == {date(2026, 4, 19): 0}

    def test_naive_iso_format(self):
        # 沒 timezone 後綴也應能處理（fallback：當作 UTC）
        meals = [_meal("2026-04-19T01:00:00", 500)]
        result = _build_daily_intake_map(meals)
        assert result == {date(2026, 4, 19): 500}


class TestBuildDailyTdeeMap:
    def test_empty(self):
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 19), {}, [])
        assert result == {}

    def test_actual_tdee(self):
        tdee_rows = [{"date": "2026-04-19", "tdee_kcal": 2200}]
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 19), {}, tdee_rows)
        assert result == {date(2026, 4, 19): (2200, False)}

    def test_meal_without_tdee_uses_bmr(self):
        from config import BMR

        daily_cal = {date(2026, 4, 19): 1500}
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 19), daily_cal, [])
        assert result == {date(2026, 4, 19): (BMR, True)}

    def test_no_data_day_in_range_skipped(self):
        # 多日範圍，中間 4/20 無資料 → 不出現在 map（其他天有資料）
        daily_cal = {date(2026, 4, 19): 1500}
        tdee_rows = [{"date": "2026-04-21", "tdee_kcal": 2000}]
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 21), daily_cal, tdee_rows)
        assert date(2026, 4, 19) in result
        assert date(2026, 4, 20) not in result
        assert date(2026, 4, 21) in result

    def test_mixed_range(self):
        from config import BMR

        # 4/19 有實際 TDEE、4/20 只有食物（用 BMR）、4/21 都沒有
        daily_cal = {date(2026, 4, 20): 1800}
        tdee_rows = [{"date": "2026-04-19", "tdee_kcal": 2400}]
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 21), daily_cal, tdee_rows)
        assert result == {
            date(2026, 4, 19): (2400, False),
            date(2026, 4, 20): (BMR, True),
        }

    def test_actual_tdee_overrides_bmr_fallback(self):
        # 有食物 + 有 TDEE → 用實際 TDEE，不用 BMR
        daily_cal = {date(2026, 4, 19): 1500}
        tdee_rows = [{"date": "2026-04-19", "tdee_kcal": 2200}]
        result = _build_daily_tdee_map(date(2026, 4, 19), date(2026, 4, 19), daily_cal, tdee_rows)
        assert result == {date(2026, 4, 19): (2200, False)}


class TestBuildMacroSection:
    def test_empty_meals(self):
        lines = _build_macro_section([])
        assert lines == ["── 營養素結構 ──", "本週無記錄"]

    def test_all_zero_macros(self):
        meals = [_meal("2026-04-19T01:00:00+00:00", protein_g=0, carbs_g=0, fat_g=0)]
        lines = _build_macro_section(meals)
        assert lines == ["── 營養素結構 ──", "本週無記錄"]

    def test_balanced_macros(self):
        # 蛋白質 50g (200 cal) + 碳水 100g (400 cal) + 脂肪 22.2g (199.8 cal) ≈ 800 cal
        # 25% / 50% / 25%
        meals = [_meal("2026-04-19T01:00:00+00:00", protein_g=50, carbs_g=100, fat_g=22.2)]
        lines = _build_macro_section(meals)
        assert lines[0] == "── 營養素結構 ──"
        assert "蛋白質 25%" in lines[1]
        assert "碳水 50%" in lines[1]
        assert "脂肪 25%" in lines[1]

    def test_macro_none_treated_as_zero(self):
        meals = [_meal("x", protein_g=None, carbs_g=None, fat_g=None)]
        lines = _build_macro_section(meals)
        assert lines == ["── 營養素結構 ──", "本週無記錄"]


class TestBuildMealTypeSection:
    def test_empty_meals(self):
        lines = _build_meal_type_section([])
        assert lines == ["── 正餐 vs 非正餐 ──", "本週無記錄"]

    def test_all_zero_calories(self):
        meals = [_meal("x", calories=0, meal_type="午餐")]
        lines = _build_meal_type_section(meals)
        assert lines == ["── 正餐 vs 非正餐 ──", "本週無記錄"]

    def test_all_regular(self):
        meals = [
            _meal("x", calories=500, meal_type="早餐"),
            _meal("x", calories=700, meal_type="午餐"),
            _meal("x", calories=600, meal_type="晚餐"),
        ]
        lines = _build_meal_type_section(meals)
        assert lines[1] == "正餐（早午晚）：100%　其他：0%"

    def test_all_other(self):
        meals = [_meal("x", calories=300, meal_type="其他")]
        lines = _build_meal_type_section(meals)
        assert lines[1] == "正餐（早午晚）：0%　其他：100%"

    def test_mixed(self):
        # 正餐 600 / 其他 400 → 60% / 40%
        meals = [
            _meal("x", calories=600, meal_type="午餐"),
            _meal("x", calories=400, meal_type="其他"),
        ]
        lines = _build_meal_type_section(meals)
        assert lines[1] == "正餐（早午晚）：60%　其他：40%"

    def test_calories_none(self):
        meals = [_meal("x", calories=None, meal_type="午餐")]
        lines = _build_meal_type_section(meals)
        assert lines == ["── 正餐 vs 非正餐 ──", "本週無記錄"]


class TestBuildBalanceSection:
    def test_no_tdee(self):
        lines = _build_balance_section(total_intake=10000, total_tdee=0, tdee_days=0)
        assert lines[0] == "── 週累積收支 ──"
        assert "本週未記錄 TDEE" in lines

    def test_deficit(self):
        # intake < tdee → 缺口（負值）
        lines = _build_balance_section(total_intake=12000, total_tdee=15000, tdee_days=7)
        assert any("累積缺口" in l for l in lines)
        assert any("-3,000" in l for l in lines)

    def test_surplus(self):
        # intake > tdee → 盈餘（正值）
        lines = _build_balance_section(total_intake=18000, total_tdee=15000, tdee_days=7)
        assert any("累積盈餘" in l for l in lines)
        assert any("+3,000" in l for l in lines)

    def test_zero_gap_counts_as_deficit(self):
        # gap == 0 走 <= 0 分支 → 顯示為缺口
        lines = _build_balance_section(total_intake=15000, total_tdee=15000, tdee_days=7)
        assert any("累積缺口" in l for l in lines)
        assert any("+0" in l for l in lines)


class TestBuildWeightSection:
    @pytest.fixture(autouse=True)
    def _mock_moving_avg(self, monkeypatch):
        # 預設 7 日均線回 None，個別測試可覆寫
        from services import db

        monkeypatch.setattr(db, "get_weight_moving_avg", lambda n=7: None)

    def test_no_weights_no_tdee(self):
        lines = _build_weight_section(weights=[], total_intake=0, total_tdee=0, tdee_days=0)
        assert any("無法計算" in l for l in lines)
        assert any("本週無體重記錄" in l for l in lines)

    def test_no_weights_with_tdee(self):
        # 缺口 -7700 → 預估 -1.00 kg
        lines = _build_weight_section(weights=[], total_intake=10000, total_tdee=17700, tdee_days=7)
        assert any("-1.00 kg" in l for l in lines)
        assert any("本週無體重記錄" in l for l in lines)

    def test_single_weight(self):
        weights = [{"weight_kg": 70.5}]
        lines = _build_weight_section(weights=weights, total_intake=0, total_tdee=0, tdee_days=0)
        assert any("僅一筆記錄" in l for l in lines)
        assert any("70.5 kg" in l for l in lines)

    def test_two_weights_loss(self):
        weights = [{"weight_kg": 71.0}, {"weight_kg": 70.2}]
        lines = _build_weight_section(weights=weights, total_intake=0, total_tdee=0, tdee_days=0)
        assert any("-0.8 kg" in l for l in lines)
        assert any("71.0 → 70.2" in l for l in lines)

    def test_moving_avg_appended(self, monkeypatch):
        from services import db

        monkeypatch.setattr(db, "get_weight_moving_avg", lambda n=7: 70.42)
        lines = _build_weight_section(weights=[], total_intake=0, total_tdee=0, tdee_days=0)
        assert any("7日均線：70.4 kg" in l for l in lines)
