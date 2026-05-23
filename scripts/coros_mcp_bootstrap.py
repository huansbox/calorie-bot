"""COROS MCP OAuth bootstrap — 一次性跑這支，產生 token JSON 給排程用。

流程：
1. 動態註冊 OAuth client（COROS DCR endpoint，免開發者帳號）
2. 起 localhost callback server，自動開瀏覽器到 COROS 授權頁
3. 你在瀏覽器登入 + 同意
4. callback 拿到 code → PKCE 換 access_token + refresh_token
5. 存到 token 檔（預設 data/coros-token.json，可用 COROS_TOKEN_PATH 覆寫）

執行：
    uv run python scripts/coros_mcp_bootstrap.py
    COROS_TOKEN_PATH=/etc/calorie-bot/coros-token.json uv run python scripts/coros_mcp_bootstrap.py

產生的 token JSON 結構（給 services/coros_mcp.py 使用）：
    {
      "client_id": "...",
      "refresh_token": "...",
      "access_token": "...",
      "expires_in": 2591999,
      "scope": "mcp.tools openid offline_access",
      "token_url": "https://mcpus.coros.com/oauth2/token",
      "mcp_url": "https://mcpus.coros.com/mcp"
    }

VPS 搬移：scp 本機跑出來的 JSON 到 VPS：
    scp data/coros-token.json root@VPS:/etc/calorie-bot/coros-token.json
    ssh root@VPS chown botuser:botuser /etc/calorie-bot/coros-token.json
    ssh root@VPS chmod 600 /etc/calorie-bot/coros-token.json

註：refresh_token 會 rotate（每次 refresh 換新），所以本機產生的這份只是 bootstrap，
VPS 跑起來後本機這份就會跟 VPS 不同步 — 那是預期的，刪掉即可。
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import COROS_TOKEN_PATH  # noqa: E402

BASE = "https://mcpus.coros.com"
REGISTRATION_URL = f"{BASE}/connect/register"
AUTHORIZE_URL = f"{BASE}/oauth2/authorize"
TOKEN_URL = f"{BASE}/oauth2/token"
MCP_URL = f"{BASE}/mcp"
SCOPES = "openid mcp.tools offline_access"


def http_post_json(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode(errors="replace")}


def http_post_form(url: str, form: dict) -> tuple[int, dict]:
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {"_error": ""}


def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    captured: dict[str, str] = {}

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        CallbackHandler.captured.update(dict(urllib.parse.parse_qsl(parsed.query)))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><body><h1>OK, you can close this tab.</h1></body></html>")

    def log_message(self, *_args) -> None:
        return


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

    target = COROS_TOKEN_PATH
    if target.exists():
        print(f"⚠ {target} 已存在，繼續會覆寫。Ctrl-C 取消，Enter 繼續：", end="", flush=True)
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            print()
            return 1

    port = find_free_port()
    redirect_uri = f"http://localhost:{port}/callback"

    print("Step 1/4: 註冊 OAuth client")
    status, reg = http_post_json(REGISTRATION_URL, {
        "client_name": "calobot-tdee-sync",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPES,
        "application_type": "native",
    })
    if status >= 400:
        print(f"  失敗 status={status}: {reg}")
        return 1
    client_id = reg["client_id"]
    print(f"  client_id={client_id}")

    print("\nStep 2/4: 起 localhost callback server + 開瀏覽器")
    server = http.server.HTTPServer(("127.0.0.1", port), CallbackHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    state = secrets.token_urlsafe(16)
    verifier, challenge = make_pkce()
    auth_url = f"{AUTHORIZE_URL}?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    print(f"  瀏覽器將開：{auth_url[:80]}...")
    print("  若未自動開，請手動複製上面 URL")
    webbrowser.open(auth_url)
    print("  等你在瀏覽器登入 COROS 並按同意（最多 5 分鐘）...")

    deadline = time.time() + 300
    while time.time() < deadline:
        if "code" in CallbackHandler.captured or "error" in CallbackHandler.captured:
            break
        time.sleep(0.5)
    server.shutdown()

    if "error" in CallbackHandler.captured:
        print(f"  授權被拒：{CallbackHandler.captured}")
        return 1
    if "code" not in CallbackHandler.captured:
        print("  逾時 5 分鐘沒拿到 code")
        return 1
    if CallbackHandler.captured.get("state") != state:
        print("  state 不對，可能 CSRF")
        return 1

    code = CallbackHandler.captured["code"]
    print(f"  拿到 code (前 10 字)：{code[:10]}...")

    print("\nStep 3/4: 換 access_token + refresh_token")
    status, tok = http_post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
    })
    if status >= 400:
        print(f"  失敗 status={status}: {tok}")
        return 1
    print(f"  access_token len={len(tok['access_token'])}")
    print(f"  refresh_token={'有' if tok.get('refresh_token') else '無'}")
    print(f"  expires_in={tok.get('expires_in')}s, scope={tok.get('scope')}")
    if not tok.get("refresh_token"):
        print("  ❌ 沒拿到 refresh_token — 排程無法長期運作")
        return 1

    print(f"\nStep 4/4: 存到 {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "client_id": client_id,
        "refresh_token": tok["refresh_token"],
        "access_token": tok["access_token"],
        "expires_in": tok.get("expires_in"),
        "scope": tok.get("scope"),
        "token_url": TOKEN_URL,
        "mcp_url": MCP_URL,
    }, indent=2), encoding="utf-8")
    print("  ✅ Bootstrap 完成")
    print("\n下一步：")
    print(f"  scp {target} root@VPS:/etc/calorie-bot/coros-token.json")
    print("  ssh root@VPS chown botuser:botuser /etc/calorie-bot/coros-token.json")
    print("  ssh root@VPS chmod 600 /etc/calorie-bot/coros-token.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
