import asyncio
import json

import pytest

import services.ai
from services.ai import (
    FoodAnalysis,
    _analyze_claude_cli,
    _model_total_tokens,
    _normalize_model_name,
    analyze_food,
    consume_primary_alert,
    parse_ai_response,
    push_primary_alert,
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


class TestNoteSoftCheck:
    def test_compliant_note_no_warning(self, caplog):
        raw = '{"description":"奶茶","protein_g":1.0,"carbs_g":80.0,"fat_g":14.0,"confidence":"high","note":"推估：命中定值錨 700cc 奶精奶茶半糖 435 kcal"}'
        with caplog.at_level("WARNING", logger="services.ai"):
            result = parse_ai_response(raw)
        assert result.note.startswith("推估：")
        assert "note 未以標準關鍵字開頭" not in caplog.text

    def test_noncompliant_note_warns_but_passes(self, caplog):
        raw = '{"description":"奶茶","protein_g":1.0,"carbs_g":80.0,"fat_g":14.0,"confidence":"high","note":"大概是半糖的量"}'
        with caplog.at_level("WARNING", logger="services.ai"):
            result = parse_ai_response(raw)
        assert result.note == "大概是半糖的量"  # 不擋不改值
        assert "note 未以標準關鍵字開頭" in caplog.text

    def test_official_long_note_passthrough(self):
        long_note = "官方值：CITY CAFE 官方熱量標示 188 kcal，三大營養素依全脂鮮奶拿鐵比例回填。" + "補充說明" * 60
        raw = json.dumps(
            {"description": "7-11 CITY CAFE 大杯冰拿鐵", "protein_g": 10.0, "carbs_g": 15.0,
             "fat_g": 10.0, "confidence": "high", "note": long_note},
            ensure_ascii=False,
        )
        result = parse_ai_response(raw)
        assert result.note == long_note
        assert result.calories == 190  # 10×4 + 15×4 + 10×9

    def test_leading_text_json_extracted(self):
        raw = '以下是分析結果：\n{"description":"滷肉飯","protein_g":28.0,"carbs_g":88.0,"fat_g":20.0,"confidence":"high","note":"推估：白飯+滷肉"}'
        result = parse_ai_response(raw)
        assert result.description == "滷肉飯"
        assert result.calories == 644


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
    async def fake_claude(text=None, image_paths=None):
        calls.append("claude")
        return _stub_analysis("claude-api")

    async def fake_gemini(text=None, image_paths=None):
        calls.append("gemini")
        if gemini_raises:
            raise RuntimeError("gemini boom")
        return _stub_analysis("gemini")

    async def fake_cli(text=None, image_paths=None):
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
    def _run_and_capture(self, monkeypatch, image_path=None, image_paths=None):
        captured = {}

        async def fake_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc()

        if image_paths is None and image_path:
            image_paths = [image_path]
        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        result = asyncio.run(_analyze_claude_cli(text="滷肉飯", image_paths=image_paths))
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

    def test_system_prompt_in_append_flag_not_in_p(self, monkeypatch):
        """指令/資料分離：SYSTEM_PROMPT 走 --append-system-prompt，-p 只放使用者輸入。"""
        cmd, _ = self._run_and_capture(monkeypatch)
        i = cmd.index("--append-system-prompt")
        assert cmd[i + 1] == services.ai.SYSTEM_PROMPT
        p = cmd.index("-p")
        assert services.ai.SYSTEM_PROMPT not in cmd[p + 1]
        assert "滷肉飯" in cmd[p + 1]

    def test_image_path_in_p_prompt(self, monkeypatch):
        cmd, _ = self._run_and_capture(monkeypatch, image_path="/tmp/fake.jpg")
        p = cmd.index("-p")
        assert "fake.jpg" in cmd[p + 1]
        assert services.ai.SYSTEM_PROMPT not in cmd[p + 1]

    def test_multiple_images_listed_once_with_merge_instruction(self, monkeypatch):
        """相簿多張：全部列進同一個 -p，並要求合併成一筆、勿重複計算。"""
        cmd, _ = self._run_and_capture(
            monkeypatch, image_paths=["/tmp/a.jpg", "/tmp/b.jpg", "/tmp/c.jpg"],
        )
        p = cmd.index("-p")
        prompt = cmd[p + 1]
        assert "a.jpg" in prompt and "b.jpg" in prompt and "c.jpg" in prompt
        assert "3 張照片" in prompt
        assert "勿重複計算" in prompt
        assert "--allowedTools" in cmd

    def test_leading_dash_text_framed(self, monkeypatch):
        """使用者文字以 - 開頭時，-p 引數不得以 - 開頭（避免被 CLI 當 option 解析）。"""
        captured = {}

        async def fake_exec(*cmd, **kwargs):
            captured["cmd"] = cmd
            return _FakeProc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
        asyncio.run(_analyze_claude_cli(text="-18度C冰淇淋 x2"))
        p = captured["cmd"].index("-p")
        assert not captured["cmd"][p + 1].startswith("-")
        assert "-18度C冰淇淋" in captured["cmd"][p + 1]


class _FakeProcMultiModel:
    """新版 CLI 的 modelUsage 併入內部 haiku（第一個 key），主判讀模型 token 較大。"""

    returncode = 0

    async def communicate(self):
        envelope = json.dumps(
            {
                "result": '{"description":"滷肉飯","protein_g":15.0,"carbs_g":65.0,"fat_g":20.0,"confidence":"high","note":""}',
                "usage": {"input_tokens": 2740, "output_tokens": 116},
                "modelUsage": {
                    "claude-haiku-4-5-20251001": {"inputTokens": 537, "outputTokens": 21},
                    "claude-sonnet-5": {"inputTokens": 2740, "outputTokens": 116},
                },
            }
        )
        return envelope.encode("utf-8"), b""


def test_ai_model_picks_main_model_not_internal_haiku(monkeypatch):
    """modelUsage 多 key 時取用量最大的主判讀模型，而非第一個 key 的內部 haiku。"""
    async def fake_exec(*cmd, **kwargs):
        return _FakeProcMultiModel()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(_analyze_claude_cli(text="滷肉飯"))
    assert result.ai_model == "claude-sonnet-5"


class _FakeProcCachedMainModel:
    """CLI 2.1.222 實測 envelope：主判讀模型的 prompt 幾乎全進 cache，
    inputTokens 只剩個位數，總量得含 cacheRead/cacheCreation 才勝過內部 haiku。"""

    returncode = 0

    async def communicate(self):
        envelope = json.dumps(
            {
                "result": '{"description":"葡式蛋塔 1顆","protein_g":4.0,"carbs_g":18.0,"fat_g":11.0,"confidence":"medium","note":"推估：市售 60g/顆"}',
                "usage": {"input_tokens": 2, "output_tokens": 88},
                "modelUsage": {
                    "claude-haiku-4-5-20251001": {
                        "inputTokens": 911,
                        "outputTokens": 15,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                    },
                    "claude-sonnet-5": {
                        "inputTokens": 2,
                        "outputTokens": 88,
                        "cacheReadInputTokens": 18543,
                        "cacheCreationInputTokens": 21219,
                    },
                },
            }
        )
        return envelope.encode("utf-8"), b""


def test_ai_model_counts_cache_tokens(monkeypatch):
    """主判讀模型走 prompt cache 時仍要被選中（不含 cache 會誤記成 haiku）。"""
    async def fake_exec(*cmd, **kwargs):
        return _FakeProcCachedMainModel()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = asyncio.run(_analyze_claude_cli(text="葡式蛋塔 1顆"))
    assert result.ai_model == "claude-sonnet-5"


class TestModelTotalTokens:
    def test_sums_all_token_fields(self):
        usage = {
            "inputTokens": 2,
            "outputTokens": 88,
            "cacheReadInputTokens": 18543,
            "cacheCreationInputTokens": 21219,
        }
        assert _model_total_tokens(usage) == 39852

    def test_missing_cache_fields_default_to_zero(self):
        assert _model_total_tokens({"inputTokens": 911, "outputTokens": 15}) == 926

    def test_none_values_treated_as_zero(self):
        usage = {"inputTokens": None, "outputTokens": 88, "cacheReadInputTokens": None}
        assert _model_total_tokens(usage) == 88

    def test_empty_usage(self):
        assert _model_total_tokens({}) == 0


# ── 主路徑失敗告警 ────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_primary_alert_state():
    """module-level 狀態，測試間必須歸零。"""
    services.ai._primary_down = False
    services.ai._pending_alert = None
    yield
    services.ai._primary_down = False
    services.ai._pending_alert = None


class TestPrimaryPathAlert:
    def test_first_failure_produces_alert(self, monkeypatch):
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, calls, gemini_raises=True)
        asyncio.run(analyze_food(text="滷肉飯"))
        msg = consume_primary_alert()
        assert msg is not None
        assert "gemini" in msg
        assert "gemini boom" in msg

    def test_repeated_failure_alerts_only_once(self, monkeypatch):
        """持續失敗不重複推播（每餐都推等於噪音）。"""
        calls = []
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, calls, gemini_raises=True)
        asyncio.run(analyze_food(text="滷肉飯"))
        assert consume_primary_alert() is not None
        asyncio.run(analyze_food(text="鮪魚蛋餅"))
        asyncio.run(analyze_food(text="葡式蛋塔"))
        assert consume_primary_alert() is None

    def test_recovery_produces_alert(self, monkeypatch):
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, [], gemini_raises=True)
        asyncio.run(analyze_food(text="滷肉飯"))
        consume_primary_alert()

        _patch_analyzers(monkeypatch, [], gemini_raises=False)
        asyncio.run(analyze_food(text="滷肉飯"))
        msg = consume_primary_alert()
        assert msg is not None
        assert "恢復" in msg

    def test_healthy_path_stays_silent(self, monkeypatch):
        """一路正常 → 完全不推播。"""
        monkeypatch.setattr("services.ai.AI_PROVIDER", "gemini")
        _patch_analyzers(monkeypatch, [], gemini_raises=False)
        asyncio.run(analyze_food(text="滷肉飯"))
        asyncio.run(analyze_food(text="鮪魚蛋餅"))
        assert consume_primary_alert() is None

    def test_consume_clears_state(self):
        services.ai._pending_alert = "測試訊息"
        assert consume_primary_alert() == "測試訊息"
        assert consume_primary_alert() is None


class TestPushPrimaryAlert:
    def test_sends_pending_message(self):
        sent = []

        async def fake_send(msg):
            sent.append(msg)

        services.ai._pending_alert = "測試訊息"
        asyncio.run(push_primary_alert(fake_send))
        assert sent == ["測試訊息"]

    def test_no_message_no_send(self):
        sent = []

        async def fake_send(msg):
            sent.append(msg)

        asyncio.run(push_primary_alert(fake_send))
        assert sent == []

    def test_send_failure_is_swallowed(self):
        """推播失敗不能影響本來要回給使用者的判讀結果。"""
        async def boom(msg):
            raise RuntimeError("telegram down")

        services.ai._pending_alert = "測試訊息"
        asyncio.run(push_primary_alert(boom))  # 不得往外拋
