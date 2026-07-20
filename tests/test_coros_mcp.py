"""Test COROS MCP service：純文字解析 + token rotation 邏輯（不打外網）。"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from services.coros_mcp import (
    CorosMCPError,
    fetch_and_persist,
    load_token,
    parse_daily_health,
    parse_user_weight,
    refresh_access_token,
    refresh_with_fallback,
    save_token,
)


# ── parse_daily_health ─────────────────────────────────────

class TestParseDailyHealth:
    def test_typical_three_days(self):
        text = (
            "Daily Health Data — Last 3 days | Resting HR: 42 bpm\n\n"
            "--- 20260522 ---\n"
            "Steps: 22,807 | Calories: 1,437 kcal | Exercise: 1h 13min\n"
            "Stress: Avg 32\n\n"
            "--- 20260523 ---\n"
            "Steps: 6,547 | Calories: 644 kcal | Exercise: 48 min\n\n"
            "--- 20260524 ---\n"
            "Steps: 12 | Calories: 7 kcal | Exercise: 0 min\n"
        )
        result = parse_daily_health(text)
        assert result == {
            date(2026, 5, 22): 1437,
            date(2026, 5, 23): 644,
            date(2026, 5, 24): 7,
        }

    def test_comma_separated_thousands(self):
        text = "--- 20260101 ---\nCalories: 2,345 kcal\n"
        assert parse_daily_health(text) == {date(2026, 1, 1): 2345}

    def test_rest_day_low_calories(self):
        text = "--- 20260514 ---\nSteps: 6,873 | Calories: 428 kcal | Exercise: 0 min\n"
        assert parse_daily_health(text) == {date(2026, 5, 14): 428}

    def test_empty_input(self):
        assert parse_daily_health("") == {}

    def test_no_calorie_line(self):
        text = "--- 20260524 ---\nSteps: 100\n"
        assert parse_daily_health(text) == {}

    def test_orphan_calorie_without_date_header(self):
        text = "Calories: 1,000 kcal\n"
        assert parse_daily_health(text) == {}

    def test_date_header_then_skipped_if_no_calorie(self):
        text = (
            "--- 20260101 ---\n"
            "Steps: 100\n"
            "--- 20260102 ---\n"
            "Calories: 500 kcal\n"
        )
        assert parse_daily_health(text) == {date(2026, 1, 2): 500}


# ── parse_user_weight ──────────────────────────────────────

class TestParseUserWeight:
    FULL_PROFILE = (
        "User Profile Information\n"
        "========================\n\n"
        "Height: 170.0 cm\n"
        "Weight: 70.7 kg\n"
        "Birthday: 1986-10-02 (Age: 39)\n"
        "Gender: Male\n"
        "Nickname: LinShuHuan\n"
    )

    def test_full_profile_block(self):
        assert parse_user_weight(self.FULL_PROFILE) == 70.7

    def test_integer_value(self):
        assert parse_user_weight("Weight: 71 kg") == 71.0

    def test_two_decimal_places(self):
        assert parse_user_weight("Weight: 68.45 kg") == 68.45

    def test_surrounding_noise(self):
        text = "blah\nHeight: 170.0 cm\n   Weight:   72.3 kg   \nGender: Male\n"
        assert parse_user_weight(text) == 72.3

    def test_case_insensitive(self):
        assert parse_user_weight("weight: 70.0 KG") == 70.0

    def test_does_not_pick_up_height(self):
        # 只有 Height、沒有 Weight → None（不可誤抓 170.0）
        assert parse_user_weight("Height: 170.0 cm\n") is None

    def test_missing_weight_field(self):
        assert parse_user_weight("Gender: Male\nNickname: x\n") is None

    def test_empty_string(self):
        assert parse_user_weight("") is None

    def test_malformed_number(self):
        assert parse_user_weight("Weight: 70.7.5 kg") is None

    def test_no_number_before_unit(self):
        assert parse_user_weight("Weight: kg") is None


# ── Token 持久化 ─────────────────────────────────────────────

class TestTokenPersistence:
    def test_save_then_load_roundtrip(self, tmp_path: Path):
        path = tmp_path / "tok.json"
        tok = {"client_id": "abc", "refresh_token": "r1", "access_token": "a1"}
        save_token(path, tok)
        assert load_token(path) == tok

    def test_load_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(CorosMCPError, match="不存在"):
            load_token(tmp_path / "nope.json")

    def test_load_corrupt_json_raises(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(CorosMCPError, match="損壞"):
            load_token(path)

    def test_save_is_atomic_no_temp_file_left_after_success(self, tmp_path: Path):
        path = tmp_path / "tok.json"
        save_token(path, {"client_id": "x"})
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".coros-token-")]
        assert leftovers == [], f"留下了暫存檔：{leftovers}"

    def test_save_overwrites_existing(self, tmp_path: Path):
        path = tmp_path / "tok.json"
        save_token(path, {"v": 1})
        save_token(path, {"v": 2})
        assert load_token(path) == {"v": 2}


# ── Refresh + rotation ──────────────────────────────────────

class TestRefreshAccessToken:
    def test_rotates_refresh_token_and_preserves_extras(self):
        original = {
            "client_id": "client-1",
            "refresh_token": "old-r",
            "access_token": "old-a",
            "token_url": "https://example/token",
            "mcp_url": "https://example/mcp",
            "scope": "openid mcp.tools offline_access",
        }
        with patch("services.coros_mcp_core.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                "access_token": "new-a",
                "refresh_token": "new-r",
                "expires_in": 2592000,
                "scope": "mcp.tools openid offline_access",
            }).encode()
            new = refresh_access_token(original)
        assert new["access_token"] == "new-a"
        assert new["refresh_token"] == "new-r"  # rotated
        assert new["client_id"] == "client-1"  # preserved
        assert new["token_url"] == "https://example/token"  # preserved
        assert new["mcp_url"] == "https://example/mcp"  # preserved
        assert original["refresh_token"] == "old-r", "原 dict 不可被改"

    def test_keeps_old_refresh_token_if_server_doesnt_return_new(self):
        original = {"client_id": "c", "refresh_token": "keep-me"}
        with patch("services.coros_mcp_core.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                "access_token": "new-a",
                "expires_in": 100,
            }).encode()
            new = refresh_access_token(original)
        assert new["refresh_token"] == "keep-me"


# ── refresh_with_fallback ───────────────────────────────────

def _token_file(tmp_path: Path) -> Path:
    path = tmp_path / "tok.json"
    save_token(path, {"client_id": "c", "refresh_token": "r-1", "access_token": "a-1"})
    return path


class TestRefreshWithFallback:
    def test_refresh_ok_saves_rotated_token_no_warning(self, tmp_path: Path):
        path = _token_file(tmp_path)
        with patch("services.coros_mcp_core.refresh_access_token", return_value={
                "client_id": "c", "refresh_token": "r-2", "access_token": "a-2"}):
            token, warn = refresh_with_fallback(path)
        assert warn is None
        assert token["access_token"] == "a-2"
        assert load_token(path)["refresh_token"] == "r-2"  # rotated + 已寫回

    def test_refresh_fail_returns_existing_token_with_warning(self, tmp_path: Path):
        path = _token_file(tmp_path)
        with patch("services.coros_mcp_core.refresh_access_token",
                   side_effect=CorosMCPError("refresh 失敗 status=500")):
            token, warn = refresh_with_fallback(path)
        assert warn is not None and "500" in warn
        assert token["access_token"] == "a-1"              # 既存 token 續行
        assert load_token(path)["refresh_token"] == "r-1"  # 檔案不動


# ── fetch_and_persist：流程整合 ──────────────────────────────

class TestFetchAndPersist:
    def test_refreshes_saves_then_fetches(self, tmp_path: Path):
        """確認：load → refresh → save (rotated) → fetch → parse 的順序，
        且 save 在 fetch 之前發生（refresh_token rotation 必須先持久化）。"""
        path = tmp_path / "tok.json"
        save_token(path, {
            "client_id": "c",
            "refresh_token": "r-old",
            "access_token": "a-old",
        })

        order: list[str] = []

        def fake_refresh(tok: dict) -> dict:
            order.append("refresh")
            return {**tok, "access_token": "a-new", "refresh_token": "r-new"}

        def fake_fetch(tok: dict, days: int = 2, tz: str = "Asia/Taipei") -> str:
            order.append("fetch")
            assert tok["refresh_token"] == "r-new", "fetch 時必須拿到新 token"
            # 同時驗證 save 已經寫入磁碟
            disk = json.loads(path.read_text(encoding="utf-8"))
            assert disk["refresh_token"] == "r-new", "save 必須在 fetch 之前完成"
            return "--- 20260524 ---\nCalories: 500 kcal\n"

        with patch("services.coros_mcp_core.refresh_access_token", side_effect=fake_refresh):
            with patch("services.coros_mcp.fetch_daily_health", side_effect=fake_fetch):
                result, warn = fetch_and_persist(path)

        assert order == ["refresh", "fetch"]
        assert result == {date(2026, 5, 24): 500}
        assert warn is None

    def test_refresh_failure_falls_back_and_keeps_token_file(self, tmp_path: Path):
        """refresh 失敗不再中止（2026-07-18 COROS refresh 500 實案）：
        改用既存 access_token 續撈，回傳 warning，token 檔不被半成品蓋掉。"""
        path = tmp_path / "tok.json"
        original = {
            "client_id": "c",
            "refresh_token": "r-old",
            "access_token": "a-old",
        }
        save_token(path, original)

        def boom(tok: dict) -> dict:
            raise CorosMCPError("refresh 失敗 status=500")

        def fake_fetch(tok: dict, days: int = 2, tz: str = "Asia/Taipei") -> str:
            assert tok["access_token"] == "a-old", "必須用既存 access_token 續行"
            return "--- 20260718 ---\nCalories: 800 kcal\n"

        with patch("services.coros_mcp_core.refresh_access_token", side_effect=boom):
            with patch("services.coros_mcp.fetch_daily_health", side_effect=fake_fetch):
                result, warn = fetch_and_persist(path)

        assert result == {date(2026, 7, 18): 800}
        assert warn is not None and "500" in warn
        assert load_token(path) == original

    def test_both_layers_fail_raises_combined_message(self, tmp_path: Path):
        path = _token_file(tmp_path)
        with patch("services.coros_mcp_core.refresh_access_token",
                   side_effect=CorosMCPError("refresh 失敗 status=500")), \
             patch("services.coros_mcp.fetch_daily_health",
                   side_effect=CorosMCPError("MCP 呼叫失敗 status=503")):
            with pytest.raises(CorosMCPError) as ei:
                fetch_and_persist(path)
        # 兩層脈絡都要在訊息裡（告警可區分是哪裡的問題）
        assert "503" in str(ei.value) and "500" in str(ei.value)
