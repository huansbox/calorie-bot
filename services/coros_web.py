"""COROS teamapi 直撈（calobot 端）：帳密登入 → profile 體重。純 stdlib，零新依賴。

與 strava-sync `coros_web.py` 走同一組端點與同一種登入方式（`POST /account/login`，
密碼 md5、無 OAuth），但**不是共用複本**：那邊的檔案含 TE / LT2 / 運動感受等
strava-sync 專屬邏輯，憑證來源也不同（那邊讀 coros-api 的 .env，這邊走 1Password
注入的環境變數）。calobot 唯一逐字節共用的檔案仍只有 `services/coros_mcp_core.py`。

選 teamapi 當體重主路徑的理由：COROS 的 OAuth `/oauth2/token` refresh 自 2026-07-18
起對有效 token 一律回 500，access_token 30 天到期後整條 MCP 路徑會斷；帳密登入每次
現場換證，沒有會壞掉的 rotation 狀態。TDEE（每日活動消耗含 NEAT）teamapi 沒有，
仍走 MCP（見 services/coros_mcp.py）。

憑證衛生：絕不 log 或放進例外訊息 password / accessToken（md5 等同明文）。例外只帶
HTTP status 與 result 碼。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

BASE_URL = "https://teamapi.coros.com"


class CorosWebError(Exception):
    """所有 teamapi 撈取失敗的統一 exception（訊息不含憑證）。"""


def _md5_hex(password: str) -> str:
    """COROS login 要的 pwd = md5(password) 小寫 hex，無 salt。"""
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def _read_maybe_gzip(resp) -> bytes:
    """讀回應 body，gzip（magic 0x1f8b）則解壓。urllib 不自動解壓。"""
    raw = resp.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw


def login(email: str, password: str, *, timeout: int = 15) -> dict:
    """POST /account/login → 回應的 ``data`` dict。

    body JSON ``{account, accountType:2, pwd: md5(password)}``。``result`` 才是狀態
    （認證失效 HTTP 仍 200）→ ``!= "0000"`` 視為失敗。

    ``data`` 除 ``accessToken`` 外直接帶 profile（``weight`` / ``stature`` / ``rhr``
    等），所以取體重不必再打第二個端點。
    """
    body = json.dumps({
        "account": email,
        "accountType": 2,
        "pwd": _md5_hex(password),
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/account/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            resp = json.loads(_read_maybe_gzip(r))
    except urllib.error.HTTPError as e:
        raise CorosWebError(f"login 失敗 status={e.code}") from e
    except urllib.error.URLError as e:
        raise CorosWebError(f"login 網路錯誤: {e.reason}") from e
    if resp.get("result") != "0000":
        raise CorosWebError(f"login 認證失敗 result={resp.get('result')}")
    data = resp.get("data")
    if not data:
        raise CorosWebError("login 回應缺 data")
    return data


def parse_profile_weight(data: dict) -> float | None:
    """login/account 回應的 ``data`` → 體重（kg）；缺欄或非數值回 None。

    bool 排除（``isinstance(True, int)`` 為 True，但此欄不該收 bool）；0 視為無資料
    （COROS 未設定體重時給 0，不是合法體重）。
    """
    w = data.get("weight")
    if isinstance(w, bool) or not isinstance(w, (int, float)):
        return None
    return float(w) if w > 0 else None


def fetch_weight(email: str, password: str) -> float | None:
    """帳密登入 → 取 profile 體重（kg）。失敗 raise CorosWebError。"""
    weight = parse_profile_weight(login(email, password))
    logger.info("COROS teamapi: 取得 profile 體重 %s kg", weight)
    return weight
