"""COROS MCP 共用核心：token 持久化 + OAuth refresh（含 fallback）+ MCP JSON-RPC 傳輸。

【共用複本】此檔在兩個 repo 各有一份，必須逐字節相同：
- calobot:     services/coros_mcp_core.py
- strava-sync: lt2_auto/coros_mcp_core.py
改任何一份後，用 strava-sync 的 tools/sync_coros_core.py 複製到另一邊；
strava-sync sync.bat 的每小時 drift check 會在兩邊不一致時 ntfy 告警。
因此本檔嚴禁 repo 專屬內容：只用 stdlib、不 import 任一 repo 的模組、
註解不假設呼叫端。app 專屬的 fetcher／解析／編排放各 repo 的 coros_mcp.py。

設計重點：
- Token 存 JSON 檔，refresh 必須 atomic 寫回（refresh_token 每次 rotate，否則失效後整體掛掉）
- refresh 永遠先做（換新 refresh_token 續命）；失敗時 refresh_with_fallback 退用既存
  access_token 續行——COROS refresh endpoint 曾對有效 token 一律回 500（2026-07-18 起，
  伺服器端 bug），但 access_token 30 天有效、資料面正常
- MCP 一次 tool call 流程：initialize → notifications/initialized → tools/call
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_URL = "https://mcpus.coros.com/oauth2/token"
DEFAULT_MCP_URL = "https://mcpus.coros.com/mcp"
MCP_PROTOCOL_VERSION = "2024-11-05"


class CorosMCPError(Exception):
    """所有 COROS MCP 相關失敗的統一 exception。"""


# ── Token 持久化 ────────────────────────────────────────────

def load_token(path: Path) -> dict:
    if not path.exists():
        raise CorosMCPError(
            f"token 檔不存在：{path}（請先跑該 repo 的 coros_mcp_bootstrap.py）"
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

    回傳新 dict（不改原 dict），保留 client_id / token_url / mcp_url 等欄位。
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


def refresh_with_fallback(token_path: Path) -> tuple[dict, str | None]:
    """refresh 優先；失敗則退用既存 access_token 續行。

    refresh 成功 → atomic save 後回 (新 token, None)。
    refresh 失敗（COROS 端故障，2026-07-18 實案：refresh handler 對有效 token 500，
    但資料面與既存 access_token 均正常）→ 回 (既存 token, 失敗訊息)，由呼叫端
    決定告警；撈取功能不因 refresh 故障中斷。
    """
    token = load_token(token_path)
    logger.info("COROS MCP: refresh access_token ...")
    try:
        token = refresh_access_token(token)
    except CorosMCPError as e:
        logger.warning("COROS MCP: refresh 失敗，改用既存 access_token 續行: %s", e)
        return token, str(e)
    save_token(token_path, token)
    logger.info("COROS MCP: token 已更新（refresh_token rotated）")
    return token, None


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
    except urllib.error.URLError as e:
        # 非 HTTP 的網路錯誤（timeout / 連線失敗 / DNS）也統一成 CorosMCPError，
        # 否則裸 URLError 會繞過編排層的 except CorosMCPError，不發告警、印 traceback。
        raise CorosMCPError(f"MCP {method} 網路錯誤: {e}") from e

    if "text/event-stream" in ctype:
        for line in raw.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload), sess
        raise CorosMCPError(f"MCP {method}：SSE 回應沒有 data 行")
    return json.loads(raw), sess


def _mcp_notify(mcp_url: str, access_token: str, session: str | None, method: str, params: dict) -> None:
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {access_token}",
    }
    # session 為 None（server stateless）時不帶 Mcp-Session-Id header
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(
        mcp_url,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except urllib.error.URLError as e:
        # 同 _mcp_call：notifications/initialized 的網路錯誤也轉成 CorosMCPError
        raise CorosMCPError(f"MCP notify {method} 失敗: {e}") from e


def call_mcp_tool(token: dict, tool_name: str, arguments: dict) -> str:
    """共用 MCP tool 呼叫流程：initialize → initialized → tools/call → 取回 text。

    只用既有 token['access_token']，不 refresh——要不要 refresh、何時 refresh
    是編排層決策，由各 repo 的呼叫端負責（例如先走 refresh_with_fallback）。
    """
    mcp_url = token.get("mcp_url", DEFAULT_MCP_URL)
    access_token = token["access_token"]

    _, sess = _mcp_call(mcp_url, access_token, "initialize", {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "coros-mcp-client", "version": "1.0.0"},
    })
    # COROS MCP server（2026-06 升級至 Build2.11.15 / 協議 2025-06-18）改 stateless：
    # initialize 不再回 Mcp-Session-Id header。新版 MCP spec 下 session id 屬選用，
    # 沒有就代表後續呼叫不需帶該 header（_mcp_call / _mcp_notify 的 `if session:` 會略過）。
    # 舊版曾在此 `raise 沒拿到 session id` 而中止，會誤殺 stateless server。
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
