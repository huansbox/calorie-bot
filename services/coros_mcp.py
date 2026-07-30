"""COROS MCP client（calobot 端）：queryDailyHealthData / queryUserInfo + 文字解析 + 編排。

token 持久化 / OAuth refresh（含 fallback）/ MCP 傳輸在 services/coros_mcp_core.py——
與 strava-sync 逐字節共用的複本，修改規範見該檔頭。本檔只放 calobot 專屬的
fetcher / 解析 / 編排。

Bootstrap 流程見 docs/coros-mcp-setup.md。
"""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import COROS_EMAIL, COROS_PASSWORD
from services.coros_mcp_core import (  # noqa: F401 — re-export，呼叫端與測試沿用本模組名
    CorosMCPError,
    call_mcp_tool,
    load_token,
    refresh_access_token,
    refresh_with_fallback,
    save_token,
)
from services.coros_oauth import bootstrap_token

logger = logging.getLogger(__name__)

# access_token 剩這麼久就先用帳密重新授權（留足夠餘裕給連續失敗的日子重試）
RENEW_BEFORE = timedelta(days=3)

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


# ── Token 續命 ─────────────────────────────────────────────

def access_token_expires_at(token: dict) -> datetime | None:
    """從 access_token（JWT）的 exp 解出到期時間；非 JWT／缺 exp／解不開回 None。"""
    parts = (token.get("access_token") or "").split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        exp = payload["exp"]
    except (binascii.Error, json.JSONDecodeError, KeyError, ValueError):
        return None
    return datetime.fromtimestamp(exp, timezone.utc)


def ensure_token(token_path: Path) -> tuple[dict, str | None]:
    """取一份可用的 token，回 (token, 要通知使用者的訊息或 None)。

    access_token 快到期 → 用帳密跑完整授權換新的一份（coros_oauth.bootstrap_token）。
    這是 refresh 續命的替代路徑：COROS 的 refresh handler 自 2026-07-18 起對有效
    token 一律回 500，靠它無法續命。

    還沒接近到期（或解不出效期）→ 照常試 refresh（COROS 若修好就恢復 rotation
    續命），失敗只記 log 不推播——有自動重新授權兜底，天天推「refresh 又 500」
    只是噪音。解不出效期時不主動重新授權：真的失效會在撈取時現形，由
    fetch_and_persist 的重試分支補救，比憑猜測每天重新授權好。

    沒設 COROS_EMAIL / COROS_PASSWORD 時退回舊行為：refresh 失敗回警示訊息，
    接近到期則提醒人工重跑 bootstrap。
    """
    token = load_token(token_path)
    expires_at = access_token_expires_at(token)
    remaining = expires_at - datetime.now(timezone.utc) if expires_at else None

    if remaining is not None and remaining < RENEW_BEFORE:
        if COROS_EMAIL and COROS_PASSWORD:
            logger.info("COROS token 剩 %s，改用帳密重新授權", remaining)
            token = bootstrap_token(COROS_EMAIL, COROS_PASSWORD, token_path, existing=token)
            new_exp = access_token_expires_at(token)
            return token, (
                "🔑 COROS token 已自動重新授權"
                + (f"（新效期至 {new_exp:%Y-%m-%d}）" if new_exp else "")
            )
        return token, (
            f"⚠️ COROS access_token 即將到期（{expires_at:%Y-%m-%d %H:%M} UTC），"
            "且未設 COROS_EMAIL / COROS_PASSWORD 無法自動續期，"
            "請跑 scripts/coros_mcp_bootstrap.py"
        )

    token, refresh_warning = refresh_with_fallback(token_path)
    if refresh_warning and not (COROS_EMAIL and COROS_PASSWORD):
        expiry_line = (
            f"access_token 效期至 {expires_at:%Y-%m-%d %H:%M} UTC"
            if expires_at else "access_token 效期不明"
        )
        return token, (
            "⚠️ COROS token refresh 失敗（已用既存 access_token 續行，同步正常）\n"
            f"{refresh_warning}\n{expiry_line}"
        )
    return token, None


# ── 高階介面（給 scheduler 用）─────────────────────────────

def fetch_and_persist(
    token_path: Path, days: int = 2, tz: str = "Asia/Taipei",
) -> tuple[dict[date, int], str | None]:
    """完整流程：ensure_token（近到期則帳密重新授權，否則 refresh）→ fetch → parse。

    回傳 (parsed, 要通知使用者的訊息或 None)。撈取失敗 raise CorosMCPError，
    若 token 端也有話要說，訊息合併兩層脈絡。
    """
    token, notice = ensure_token(token_path)
    try:
        text = fetch_daily_health(token, days=days, tz=tz)
    except CorosMCPError as e:
        # token 還沒到期卻被 COROS 拒收（提早失效／被撤銷）→ 帳密重新授權再試一次。
        # notice 有值代表本輪已經重新授權過（或已在警示狀態），不再重試。
        if notice:
            raise CorosMCPError(f"{e}（token 端狀況：{notice}）") from e
        if not (COROS_EMAIL and COROS_PASSWORD):
            raise
        logger.warning("COROS 撈取失敗，改用帳密重新授權後重試: %s", e)
        token = bootstrap_token(COROS_EMAIL, COROS_PASSWORD, token_path, existing=token)
        text = fetch_daily_health(token, days=days, tz=tz)
        notice = "🔑 COROS 撈取失敗後已自動重新授權，本次同步已成功"
    parsed = parse_daily_health(text)
    logger.info("COROS MCP: 取得 %d 天 daily health data", len(parsed))
    return parsed, notice
