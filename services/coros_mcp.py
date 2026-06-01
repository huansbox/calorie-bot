"""COROS MCP client：OAuth refresh + queryDailyHealthData + 文字解析。

設計：
- Token 存 JSON 檔（rotation 必須 atomic 寫回，否則 refresh_token 失效後排程整體掛掉）
- access_token 約 30 天有效，但每次排程都先 refresh 一次（換新 refresh_token，續命）
- MCP 一次 tool call 流程：initialize → initialized notification → tools/call

Bootstrap 流程見 docs/coros-mcp-setup.md。
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_URL = "https://mcpus.coros.com/oauth2/token"
DEFAULT_MCP_URL = "https://mcpus.coros.com/mcp"
MCP_PROTOCOL_VERSION = "2024-11-05"

_DATE_RE = re.compile(r"^---\s*(\d{8})\s*---")
_CAL_RE = re.compile(r"Calories:\s*([\d,]+)\s*kcal")
_WEIGHT_RE = re.compile(r"Weight:\s*([\d.]+)\s*kg", re.IGNORECASE)


class CorosMCPError(Exception):
    """所有 COROS MCP 相關失敗的統一 exception。"""


# ── Token 持久化 ────────────────────────────────────────────

def load_token(path: Path) -> dict:
    if not path.exists():
        raise CorosMCPError(
            f"token 檔不存在：{path}（請先跑 bootstrap：scripts/coros_mcp_bootstrap.py）"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CorosMCPError(f"token 檔損壞：{path} ({e})") from e


def save_token(path: Path, token: dict) -> None:
    """Atomic write — 寫到同目錄的暫存檔再 rename，避免 refresh 中途斷電留下半成品。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".coros-token-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(token, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ── OAuth refresh ──────────────────────────────────────────

def refresh_access_token(token: dict) -> dict:
    """用 refresh_token 換新 access_token。會 rotate refresh_token，呼叫端必須寫回。

    回傳的 dict 結構保留 token 原本的 client_id / token_url / mcp_url 等欄位。
    """
    token_url = token.get("token_url", DEFAULT_TOKEN_URL)
    client_id = token["client_id"]
    refresh = token["refresh_token"]

    form = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": client_id,
    }).encode()

    req = urllib.request.Request(
        token_url,
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise CorosMCPError(f"refresh 失敗 status={e.code}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise CorosMCPError(f"refresh 網路錯誤: {e}") from e

    new = dict(token)
    new["access_token"] = resp["access_token"]
    if resp.get("refresh_token"):
        new["refresh_token"] = resp["refresh_token"]
    new["expires_in"] = resp.get("expires_in")
    new["scope"] = resp.get("scope", new.get("scope"))
    return new


# ── MCP 呼叫 ───────────────────────────────────────────────

def _mcp_call(
    mcp_url: str,
    access_token: str,
    method: str,
    params: dict,
    session: str | None = None,
    req_id: int = 1,
    timeout: int = 30,
) -> tuple[dict, str | None]:
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {access_token}",
    }
    if session:
        headers["Mcp-Session-Id"] = session

    req = urllib.request.Request(
        mcp_url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            sess = r.headers.get("Mcp-Session-Id") or session
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")
        raise CorosMCPError(f"MCP {method} 失敗 status={e.code}: {body_text[:300]}") from e

    if "text/event-stream" in ctype:
        for line in raw.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload), sess
        raise CorosMCPError(f"MCP {method}：SSE 回應沒有 data 行")
    return json.loads(raw), sess


def _mcp_notify(mcp_url: str, access_token: str, session: str, method: str, params: dict) -> None:
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    req = urllib.request.Request(
        mcp_url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {access_token}",
            "Mcp-Session-Id": session,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def _call_mcp_tool(token: dict, tool_name: str, arguments: dict) -> str:
    """共用的 MCP tool 呼叫流程：initialize → initialized → tools/call → 取回 text。

    只用既有 token['access_token']，**不 refresh**（refresh 由 fetch_and_persist 負責）。
    體重同步刻意走 load_token → fetch_user_info（見 PRD「Token 處理」），就靠這條
    不綁 refresh 的路徑成立。
    """
    mcp_url = token.get("mcp_url", DEFAULT_MCP_URL)
    access_token = token["access_token"]

    _, sess = _mcp_call(mcp_url, access_token, "initialize", {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "calobot", "version": "1.0.0"},
    })
    if not sess:
        raise CorosMCPError("MCP initialize 沒拿到 session id")
    _mcp_notify(mcp_url, access_token, sess, "notifications/initialized", {})

    call_resp, _ = _mcp_call(mcp_url, access_token, "tools/call", {
        "name": tool_name,
        "arguments": arguments,
    }, session=sess, req_id=2)

    if "error" in call_resp:
        raise CorosMCPError(f"{tool_name} 回應 error: {call_resp['error']}")
    result = call_resp.get("result", {})
    contents = result.get("content", [])
    if not contents:
        raise CorosMCPError(f"{tool_name} 回應沒有 content")
    text = contents[0].get("text", "")
    # COROS 回的 text 是 JSON 字串包了一層真的文字，剝掉
    if text.startswith('"') and text.endswith('"'):
        try:
            text = json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def fetch_daily_health(token: dict, days: int = 2, tz: str = "Asia/Taipei") -> str:
    """呼叫 MCP queryDailyHealthData 回傳純文字。需要 token['access_token']。"""
    return _call_mcp_tool(token, "queryDailyHealthData", {"days": days, "timezone": tz})


def fetch_user_info(token: dict) -> str:
    """呼叫 MCP queryUserInfo（無參數）回傳 user profile 純文字。需要 token['access_token']。

    比照 fetch_daily_health：只用既有 access_token 發 MCP call，不 refresh。
    體重同步走 load_token → fetch_user_info，**不可複用 fetch_and_persist**
    （它把 refresh+save+fetch 綁死，會違反「體重同步不 refresh」的要求，見 PRD US22）。
    """
    return _call_mcp_tool(token, "queryUserInfo", {})


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

def fetch_and_persist(token_path: Path, days: int = 2, tz: str = "Asia/Taipei") -> dict[date, int]:
    """完整流程：load → refresh → save → fetch → parse。

    refresh 永遠先做（換新 refresh_token，避免 token 因不活躍過期）。
    """
    token = load_token(token_path)
    logger.info("COROS MCP: refresh access_token ...")
    token = refresh_access_token(token)
    save_token(token_path, token)
    logger.info("COROS MCP: token 已更新（refresh_token rotated）")

    text = fetch_daily_health(token, days=days, tz=tz)
    parsed = parse_daily_health(text)
    logger.info("COROS MCP: 取得 %d 天 daily health data", len(parsed))
    return parsed
