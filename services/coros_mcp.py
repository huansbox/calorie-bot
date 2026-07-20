"""COROS MCP client（calobot 端）：queryDailyHealthData / queryUserInfo + 文字解析 + 編排。

token 持久化 / OAuth refresh（含 fallback）/ MCP 傳輸在 services/coros_mcp_core.py——
與 strava-sync 逐字節共用的複本，修改規範見該檔頭。本檔只放 calobot 專屬的
fetcher / 解析 / 編排。

Bootstrap 流程見 docs/coros-mcp-setup.md。
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path

from services.coros_mcp_core import (  # noqa: F401 — re-export，呼叫端與測試沿用本模組名
    CorosMCPError,
    call_mcp_tool,
    load_token,
    refresh_access_token,
    refresh_with_fallback,
    save_token,
)

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^---\s*(\d{8})\s*---")
_CAL_RE = re.compile(r"Calories:\s*([\d,]+)\s*kcal")
_WEIGHT_RE = re.compile(r"Weight:\s*([\d.]+)\s*kg", re.IGNORECASE)


# ── Fetcher ─────────────────────────────────────────────────

def fetch_daily_health(token: dict, days: int = 2, tz: str = "Asia/Taipei") -> str:
    """呼叫 MCP queryDailyHealthData 回傳純文字。需要 token['access_token']。"""
    return call_mcp_tool(token, "queryDailyHealthData", {"days": days, "timezone": tz})


def fetch_user_info(token: dict) -> str:
    """呼叫 MCP queryUserInfo（無參數）回傳 user profile 純文字。需要 token['access_token']。

    比照 fetch_daily_health：只用既有 access_token 發 MCP call，不 refresh。
    體重同步走 load_token → fetch_user_info，**不可複用 fetch_and_persist**
    （它把 refresh+fetch 綁在一起，會違反「體重同步不 refresh」的要求，見 PRD US22）。
    """
    return call_mcp_tool(token, "queryUserInfo", {})


# ── 文字解析 ────────────────────────────────────────────────

def parse_daily_health(text: str) -> dict[date, int]:
    """從 queryDailyHealthData 的文字輸出解出 {date: active_kcal}。"""
    out: dict[date, int] = {}
    current_date: date | None = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _DATE_RE.match(line)
        if m:
            current_date = datetime.strptime(m.group(1), "%Y%m%d").date()
            continue
        if current_date is None:
            continue
        m = _CAL_RE.search(line)
        if m:
            out[current_date] = int(m.group(1).replace(",", ""))
            current_date = None
    return out


def parse_user_weight(text: str) -> float | None:
    """從 queryUserInfo 文字輸出解出體重（kg），解析不到回 None。

    格式（實測，見 issues/003）：

        User Profile Information
        ========================

        Height: 170.0 cm
        Weight: 70.7 kg
        ...

    缺 Weight 欄位、空字串、數值畸形皆回 None（比照 parse_daily_health 的容錯風格）。
    """
    m = _WEIGHT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# ── 高階介面（給 scheduler 用）─────────────────────────────

def fetch_and_persist(
    token_path: Path, days: int = 2, tz: str = "Asia/Taipei",
) -> tuple[dict[date, int], str | None]:
    """完整流程：load → refresh（失敗退用既存 access_token）→ fetch → parse。

    回傳 (parsed, refresh 失敗訊息或 None)。refresh 失敗不中斷撈取（COROS 端
    refresh 故障實案見 coros_mcp_core.refresh_with_fallback）；撈取失敗 raise
    CorosMCPError，若 refresh 亦失敗，訊息合併兩層脈絡。
    """
    token, refresh_warning = refresh_with_fallback(token_path)
    try:
        text = fetch_daily_health(token, days=days, tz=tz)
    except CorosMCPError as e:
        if refresh_warning:
            raise CorosMCPError(
                f"{e}（且 token refresh 亦失敗：{refresh_warning}）") from e
        raise
    parsed = parse_daily_health(text)
    logger.info("COROS MCP: 取得 %d 天 daily health data", len(parsed))
    return parsed, refresh_warning
