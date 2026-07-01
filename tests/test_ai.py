import asyncio
import json

import pytest

import services.ai
from services.ai import (
    FoodAnalysis,
    _analyze_claude_cli,
    _normalize_model_name,
    analyze_food,
    parse_ai_response,
)


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

    def test_numeric_confidence_high(self):
        raw = '{"description":"牛肉麵","protein_g":30.0,"carbs_g":60.0,"fat_g":15.0,"confidence":0.9,"note":""}'
        result = parse_ai_response(raw)
        assert result.confidence == "high"

    def test_numeric_confidence_medium(self):
        raw = '{"description":"牛肉麵","protein_g":30.0,"carbs_g":60.0,"fat_g":15.0,"confidence":0.6,"note":""}'
        result = parse_ai_response(raw)
        assert result.confidence == "medium"

    def test_numeric_confidence_low(self):
        raw = '{"description":"牛肉麵","protein_g":30.0,"carbs_g":60.0,"fat_g":15.0,"confidence":0.3,"note":""}'
        result = parse_ai_response(raw)
        assert result.confidence == "low"


class TestNormalizeModelName:
    def test_strips_context_window_suffix(self):
        assert _normalize_model_name("claude-opus-4-7[1m]") == "claude-opus-4-7"

    def test_no_suffix_unchanged(self):
        assert _normalize_model_name("claude-opus-4-7") == "claude-opus-4-7"

    def test_strips_other_bracket_variants(self):
        assert _normalize_model_name("claude-sonnet-4-6[200k]") == "claude-sonnet-4-6"

    def test_strips_trailing_whitespace(self):
        assert _normalize_model_name("  claude-opus-4-7  ") == "claude-opus-4-7"


def _stub_analysis(provider: str) -> FoodAnalysis:
    return FoodAnalysis(
        description="test",
        calories=100,
        protein_g=10.0,
        carbs_g=10.0,
        fat_g=2.0,
        confidence="high",
        note="",
        provider=provider,
    )


def _patch_analyzers(monkeypatch, calls: list, gemini_raises: bool = False):
    """把三個 _analyze_* 換成記錄呼叫的 stub。AI_PROVIDER 需另外 monkeypatch。"""
    async def fake_claude(text=None, image_path=None):
        calls.append("claude")
        return _stub_analysis("claude-api")

    async def fake_gemini(text=None, image_path=None):
        calls.append("gemini")
        if gemini_raises:
            raise RuntimeError("gemini boom")
        return _stub_analysis("gemini")

    async def fake_cli(text=None, image_path=None):
        calls.append("cli")
        return _stub_analysis("claude-cli")

    monkeypatch.setattr("services.ai._analyze_claude", fake_claude)
    monkeypatch.setattr("services.ai._analyze_gemini", fake_gemini)
    monkeypatch.setattr("services.ai._analyze_claude_cli", fake_cli)


class TestAnalyzeFoodRouting:
    def test_default_claude_cli_only(self, monkeypatch):
        """預設（claude-cli）：只走 claude -p，不碰 Gemini。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "claude-cli")
        _patch_analyzers(monkeypatch, calls)
        result = asyncio.run(analyze_food(text="滷肉飯"))
        assert calls == ["cli"]
        assert result.provider == "claude-cli"

    def test_unknown_provider_falls_to_claude_cli(self, monkeypatch):
        """未知值也落到 claude-cli 分支（無 fallback）。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "something-else")
        _patch_analyzers(monkeypatch, calls)
        result = asyncio.run(analyze_food(text="滷肉飯"))
        assert calls == ["cli"]

    def test_claude_api_branch(self, monkeypatch):
        """AI_PROVIDER=claude → Claude API，無 fallback。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "claude")
        _patch_analyzers(monkeypatch, calls)
        result = asyncio.run(analyze_food(text="滷肉飯"))
        assert calls == ["claude"]
        assert result.provider == "claude-api"

    def test_gemini_branch_no_fallback_on_success(self, monkeypatch):
        """AI_PROVIDER=gemini 成功 → 只走 Gemini，不 fallback。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, calls)
        result = asyncio.run(analyze_food(text="滷肉飯"))
        assert calls == ["gemini"]
        assert result.provider == "gemini"

    def test_gemini_branch_falls_back_to_cli(self, monkeypatch):
        """AI_PROVIDER=gemini 失敗 → fallback 到 claude -p。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, calls, gemini_raises=True)
        result = asyncio.run(analyze_food(text="滷肉飯"))
        assert calls == ["gemini", "cli"]
        assert result.provider == "claude-cli"


class _FakeProc:
    returncode = 0

    async def communicate(self):
        envelope = json.dumps(
            {
                "result": '{"description":"滷肉飯","protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":""}',
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "modelUsage": {"claude-sonnet-4-6[1m]": {}},
            }
        )
        return envelope.encode("utf-8"), b""


class TestClaudeCliModelArg:
    def _run_and_capture(self, monkeypatch, image_path=None):
        captured = {}

        async def fake_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        result = asyncio.run(_analyze_claude_cli(text="滷肉飯", image_path=image_path))
        return captured["cmd"], result

    def test_model_flag_passed(self, monkeypatch):
        cmd, _ = self._run_and_capture(monkeypatch)
        assert "--model" in cmd
        i = cmd.index("--model")
        assert cmd[i + 1] == services.ai.CLAUDE_CLI_MODEL

    def test_image_adds_allowed_tools_and_keeps_model(self, monkeypatch):
        cmd, _ = self._run_and_capture(monkeypatch, image_path="/tmp/fake.jpg")
        assert "--model" in cmd
        assert "--allowedTools" in cmd
        j = cmd.index("--allowedTools")
        assert cmd[j + 1] == "Read"
