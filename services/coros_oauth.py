"""COROS MCP token 自動重新授權：用帳密跑完整 OAuth authorize flow，免人工開瀏覽器。

【為什麼需要這個】
COROS `/oauth2/token` 的 refresh handler 自 2026-07-18 起對有效 refresh_token 一律回
500（伺服器端故障，換全新 client 重跑 bootstrap 也一樣）。access_token 有 30 天效期，
到期後整條 MCP 路徑會斷。每日活動消耗（含 NEAT 的 TDEE）只有 MCP 有、teamapi 沒有，
所以 MCP 不能退場，只能讓它自己續命：token 快到期就用帳密重跑一次完整授權。

【流程】與 scripts/coros_mcp_bootstrap.py 同一條 OAuth flow，差別只在第 2 步不開瀏覽器：
1. DCR 註冊 OAuth client（免開發者帳號）；token 檔已有 client_id + redirect_uri 就重用
2. GET /oauth2/authorize（帶 PKCE）→ 302 到 openus.coros.com 的登入頁（純 HTML 表單）
3. 帶隱藏欄位 + 帳密 POST 回 openus → 302 到 mcpus callback → 再 302 到 redirect_uri
   （localhost，不需真的起 server：攔截這個 302 直接取 code）
4. code + code_verifier 換 access_token / refresh_token

【實測踩到的兩個坑（2026-07-30）】
- 表單預設 `country=CN`，照送會回 `{"result":"1001","message":"Service exceptions"}`；
  改 `TW` 才過。
- POST 需帶 `Origin` 與像瀏覽器的 `User-Agent`，否則同樣回 1001。

憑證衛生：絕不 log 或放進例外訊息 password / token / code。
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import html
import http.cookiejar
import json
import logging
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from services.coros_mcp_core import CorosMCPError, save_token

logger = logging.getLogger(__name__)

BASE = "https://mcpus.coros.com"
REGISTRATION_URL = f"{BASE}/connect/register"
AUTHORIZE_URL = f"{BASE}/oauth2/authorize"
TOKEN_URL = f"{BASE}/oauth2/token"
MCP_URL = f"{BASE}/mcp"
SCOPES = "openid mcp.tools offline_access"

# localhost callback 只是 OAuth 規格要求的落點，我們攔 302 直接取 code，不會真的連線，
# 所以固定 port 即可（固定才能把 client_id 存起來重用，不必每次重新註冊）。
DEFAULT_REDIRECT_URI = "http://localhost:8765/callback"
LOGIN_COUNTRY = "TW"
LOGIN_LANGUAGE = "en"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0"


class _CaptureLocalhostRedirect(urllib.request.HTTPRedirectHandler):
    """攔下往 localhost 的 302（OAuth callback），不讓 urllib 真的去連。"""

    def __init__(self) -> None:
        self.captured: str | None = None

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl.startswith("http://localhost:"):
            self.captured = newurl
            return None  # 停止 redirect；urllib 會把這個 302 當 HTTPError 丟出
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read(resp) -> str:
    raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


def _make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _register_client(opener, redirect_uri: str) -> str:
    """DCR 動態註冊 OAuth client，回 client_id。"""
    req = urllib.request.Request(
        REGISTRATION_URL,
        data=json.dumps({
            "client_name": "calobot-tdee-sync",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPES,
            "application_type": "native",
        }).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with opener.open(req, timeout=20) as r:
            reg = json.loads(_read(r))
    except urllib.error.HTTPError as e:
        raise CorosMCPError(f"OAuth client 註冊失敗 status={e.code}") from e
    except urllib.error.URLError as e:
        raise CorosMCPError(f"OAuth client 註冊網路錯誤: {e.reason}") from e
    client_id = reg.get("client_id")
    if not client_id:
        raise CorosMCPError("OAuth client 註冊回應缺 client_id")
    return client_id


def _parse_login_form(page: str) -> tuple[str, dict[str, str]]:
    """從授權頁抽出登入表單的 action 與所有 input 欄位（含 hidden 的 state 等）。"""
    form_match = re.search(r'<form id="authForm".*?</form>', page, re.S | re.I)
    if not form_match:
        raise CorosMCPError("COROS 授權頁找不到登入表單（頁面可能改版）")
    form = form_match.group(0)

    action_match = re.search(r'action="([^"]+)"', form)
    if not action_match:
        raise CorosMCPError("COROS 授權頁登入表單缺 action（頁面可能改版）")

    fields: dict[str, str] = {}
    for m in re.finditer(r"<input[^>]*>", form, re.I):
        tag = m.group(0)
        name = re.search(r'name="([^"]+)"', tag)
        if not name:
            continue
        value = re.search(r'value="([^"]*)"', tag)
        fields[name.group(1)] = html.unescape(value.group(1)) if value else ""
    if "userName" not in fields or "password" not in fields:
        raise CorosMCPError("COROS 授權頁表單缺帳密欄位（頁面可能改版）")
    return action_match.group(1), fields


def _login_for_code(
    opener,
    capture: _CaptureLocalhostRedirect,
    email: str,
    password: str,
    client_id: str,
    redirect_uri: str,
    challenge: str,
    state: str,
) -> str:
    """走 authorize → 帳密登入 → 攔 callback 302，回 authorization code。"""
    auth_url = f"{AUTHORIZE_URL}?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    try:
        with opener.open(auth_url, timeout=20) as r:
            page, page_url = _read(r), r.geturl()
    except urllib.error.HTTPError as e:
        raise CorosMCPError(f"取授權頁失敗 status={e.code}") from e
    except urllib.error.URLError as e:
        raise CorosMCPError(f"取授權頁網路錯誤: {e.reason}") from e

    action, fields = _parse_login_form(page)
    fields["userName"] = email
    fields["password"] = password
    fields["checkStatus"] = "1"          # 頁面上的條款勾選，未帶前端不讓送出
    fields["country"] = LOGIN_COUNTRY    # 預設 CN 會被判成錯區、回 1001
    fields["language"] = LOGIN_LANGUAGE

    login_url = urllib.parse.urljoin(page_url, action)
    req = urllib.request.Request(
        login_url,
        data=urllib.parse.urlencode(fields).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Referer": page_url,
            # Origin 與瀏覽器型 UA 缺一不可，否則回 1001 Service exceptions
            "Origin": f"{urllib.parse.urlparse(login_url).scheme}://"
                      f"{urllib.parse.urlparse(login_url).netloc}",
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=25) as r:
            body = _read(r)
    except urllib.error.HTTPError as e:
        # 攔到 localhost 302 時 urllib 會走這裡（redirect_request 回 None）
        body = _read(e)
    except urllib.error.URLError as e:
        raise CorosMCPError(f"COROS 登入網路錯誤: {e.reason}") from e

    if not capture.captured:
        detail = ""
        try:
            payload = json.loads(body)
            detail = f"（result={payload.get('result')}）"
        except (json.JSONDecodeError, AttributeError):
            pass
        raise CorosMCPError(f"COROS 登入未取得 authorization code{detail}")

    query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(capture.captured).query))
    if query.get("state") != state:
        raise CorosMCPError("OAuth callback 的 state 不符")
    code = query.get("code")
    if not code:
        raise CorosMCPError(f"OAuth callback 沒有 code（error={query.get('error')}）")
    return code


def _exchange_code(opener, code: str, verifier: str, client_id: str, redirect_uri: str) -> dict:
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        }).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with opener.open(req, timeout=20) as r:
            tok = json.loads(_read(r))
    except urllib.error.HTTPError as e:
        raise CorosMCPError(f"code 換 token 失敗 status={e.code}") from e
    except urllib.error.URLError as e:
        raise CorosMCPError(f"code 換 token 網路錯誤: {e.reason}") from e
    if not tok.get("access_token") or not tok.get("refresh_token"):
        raise CorosMCPError("token 回應缺 access_token 或 refresh_token")
    return tok


def bootstrap_token(
    email: str, password: str, token_path: Path, existing: dict | None = None,
) -> dict:
    """帳密跑完整授權流程 → 寫回 token 檔（atomic）→ 回新 token dict。

    existing 帶既有 token 時，重用其 client_id / redirect_uri（省一次 DCR 註冊）；
    沒有或缺欄位就重新註冊一個 client。任一步失敗 raise CorosMCPError。
    """
    if not email or not password:
        raise CorosMCPError("缺 COROS_EMAIL / COROS_PASSWORD，無法自動重新授權")

    capture = _CaptureLocalhostRedirect()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), capture,
    )
    opener.addheaders = [("User-Agent", BROWSER_UA)]

    existing = existing or {}
    redirect_uri = existing.get("redirect_uri") or DEFAULT_REDIRECT_URI
    client_id = existing.get("client_id") if existing.get("redirect_uri") else None
    if not client_id:
        client_id = _register_client(opener, redirect_uri)
        logger.info("COROS OAuth: 已註冊新 client")

    verifier, challenge = _make_pkce()
    state = secrets.token_urlsafe(16)
    code = _login_for_code(
        opener, capture, email, password, client_id, redirect_uri, challenge, state,
    )
    tok = _exchange_code(opener, code, verifier, client_id, redirect_uri)

    token = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "refresh_token": tok["refresh_token"],
        "access_token": tok["access_token"],
        "expires_in": tok.get("expires_in"),
        "scope": tok.get("scope"),
        "token_url": TOKEN_URL,
        "mcp_url": MCP_URL,
    }
    save_token(token_path, token)
    logger.info("COROS OAuth: 已用帳密重新授權並寫回 %s", token_path)
    return token
