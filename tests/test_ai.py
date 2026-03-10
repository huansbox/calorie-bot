import pytest

from services.ai import FoodAnalysis, parse_ai_response


class TestParseAiResponse:
    def test_clean_json(self):
        raw = '{"description":"滷肉飯","calories":680,"protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":""}'
        result = parse_ai_response(raw)
        assert result == FoodAnalysis(
            description="滷肉飯",
            calories=680,
            protein_g=28.0,
            carbs_g=88.0,
            fat_g=20.0,
            confidence="high",
            note="",
        )

    def test_json_with_code_fence(self):
        raw = '```json\n{"description":"拿鐵","calories":210,"protein_g":8.0,"carbs_g":18.0,"fat_g":10.0,"confidence":"medium","note":"以中杯估算"}\n```'
        result = parse_ai_response(raw)
        assert result.description == "拿鐵"
        assert result.calories == 210
        assert result.confidence == "medium"
        assert result.note == "以中杯估算"

    def test_json_with_plain_code_fence(self):
        raw = '```\n{"description":"水餃10顆","calories":450,"protein_g":20.0,"carbs_g":50.0,"fat_g":15.0,"confidence":"high","note":""}\n```'
        result = parse_ai_response(raw)
        assert result.description == "水餃10顆"
        assert result.calories == 450

    def test_json_with_whitespace(self):
        raw = '  \n{"description":"蛋餅","calories":320,"protein_g":12.0,"carbs_g":35.0,"fat_g":14.0,"confidence":"high","note":""}\n  '
        result = parse_ai_response(raw)
        assert result.description == "蛋餅"

    def test_missing_note_defaults_empty(self):
        raw = '{"description":"豆漿","calories":120,"protein_g":8.0,"carbs_g":10.0,"fat_g":4.0,"confidence":"high"}'
        result = parse_ai_response(raw)
        assert result.note == ""

    def test_numeric_types_coerced(self):
        raw = '{"description":"飯糰","calories":"380","protein_g":"12","carbs_g":"55","fat_g":"10","confidence":"medium","note":""}'
        result = parse_ai_response(raw)
        assert result.calories == 380
        assert isinstance(result.calories, int)
        assert isinstance(result.protein_g, float)

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            parse_ai_response("this is not json")
