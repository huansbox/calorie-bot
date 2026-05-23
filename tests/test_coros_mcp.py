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
    refresh_access_token,
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
        with patch("services.coros_mcp.urllib.request.urlopen") as mock_open:
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
        with patch("services.coros_mcp.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = json.dumps({
                "access_token": "new-a",
                "expires_in": 100,
            }).encode()
            new = refresh_access_token(original)
        assert new["refresh_token"] == "keep-me"


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

        with patch("services.coros_mcp.refresh_access_token", side_effect=fake_refresh):
            with patch("services.coros_mcp.fetch_daily_health", side_effect=fake_fetch):
                result = fetch_and_persist(path)

        assert order == ["refresh", "fetch"]
        assert result == {date(2026, 5, 24): 500}

    def test_refresh_failure_does_not_corrupt_token_file(self, tmp_path: Path):
        path = tmp_path / "tok.json"
        original = {
            "client_id": "c",
            "refresh_token": "r-old",
            "access_token": "a-old",
        }
        save_token(path, original)

        def boom(tok: dict) -> dict:
            raise CorosMCPError("simulated refresh failure")

        with patch("services.coros_mcp.refresh_access_token", side_effect=boom):
            with pytest.raises(CorosMCPError):
                fetch_and_persist(path)

        # 磁碟上的 token 還是原本的，沒被半成品蓋掉
        assert load_token(path) == original
