import pytest

from services.ai import FoodAnalysis, parse_ai_response


class TestParseAiResponse:
    def test_clean_json(self):
        raw = '{"description":"滷肉飯","calories":680,"protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":""}'
        result = parse_ai_response(raw)
        # calories 由 macro 計算: 28×4 + 88×4 + 20×9 = 644（忽略 AI 回傳的 680）
        assert result.calories == 644
        assert result.description == "滷肉飯"
        assert result.protein_g == 28.0
        assert result.carbs_g == 88.0
        assert result.fat_g == 20.0
        assert result.confidence == "high"
        assert result.note == ""

    def test_json_with_code_fence(self):
        raw = '```json\n{"description":"拿鐵","calories":210,"protein_g":8.0,"carbs_g":18.0,"fat_g":10.0,"confidence":"medium","note":"以中杯估算"}\n```'
        result = parse_ai_response(raw)
        assert result.description == "拿鐵"
        assert result.calories == 194  # 8×4 + 18×4 + 10×9
        assert result.confidence == "medium"
        assert result.note == "以中杯估算"

    def test_json_with_plain_code_fence(self):
        raw = '```\n{"description":"水餃10顆","calories":450,"protein_g":20.0,"carbs_g":50.0,"fat_g":15.0,"confidence":"high","note":""}\n```'
        result = parse_ai_response(raw)
        assert result.description == "水餃10顆"
        assert result.calories == 415  # 20×4 + 50×4 + 15×9

    def test_json_with_whitespace(self):
        raw = '  \n{"description":"蛋餅","calories":320,"protein_g":12.0,"carbs_g":35.0,"fat_g":14.0,"confidence":"high","note":""}\n  '
        result = parse_ai_response(raw)
        assert result.description == "蛋餅"
        assert result.calories == 314  # 12×4 + 35×4 + 14×9

    def test_missing_note_defaults_empty(self):
        raw = '{"description":"豆漿","calories":120,"protein_g":8.0,"carbs_g":10.0,"fat_g":4.0,"confidence":"high"}'
        result = parse_ai_response(raw)
        assert result.note == ""
        assert result.calories == 108  # 8×4 + 10×4 + 4×9

    def test_numeric_types_coerced(self):
        raw = '{"description":"飯糰","calories":"380","protein_g":"12","carbs_g":"55","fat_g":"10","confidence":"medium","note":""}'
        result = parse_ai_response(raw)
        assert result.calories == 358  # 12×4 + 55×4 + 10×9
        assert isinstance(result.calories, int)
        assert isinstance(result.protein_g, float)

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_ai_response("this is not json")

    def test_json_without_calories(self):
        """AI 不回傳 calories，由 macro 計算"""
        raw = '{"description":"滷肉飯","protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":""}'
        result = parse_ai_response(raw)
        assert result.calories == 644  # 28×4 + 88×4 + 20×9
        assert result.protein_g == 28.0

    def test_json_with_calories_ignored(self):
        """即使 AI 回傳 calories，也以 macro 計算覆蓋"""
        raw = '{"description":"滷肉飯","calories":999,"protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":""}'
        result = parse_ai_response(raw)
        assert result.calories == 644  # not 999
