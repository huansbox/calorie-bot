"""COROS teamapi（帳密路徑）測試：體重解析 + 登入表單解析。不打外網。"""
import pytest

from services.coros_oauth import _parse_login_form
from services.coros_mcp_core import CorosMCPError
from services.coros_web import parse_profile_weight


class TestParseProfileWeight:
    """login 回應的 data 直接帶 profile 體重，不必再打第二個端點。"""

    def test_typical(self):
        assert parse_profile_weight({"weight": 72.0, "stature": 170.0}) == 72.0

    def test_int_value(self):
        assert parse_profile_weight({"weight": 72}) == 72.0

    @pytest.mark.parametrize("data", [
        {},                    # 缺欄位
        {"weight": None},
        {"weight": "72.0"},    # 字串不接受（避免格式假設）
        {"weight": True},      # bool 是 int 的子類，但不是體重
        {"weight": 0},         # COROS 未設定體重時給 0，不是合法體重
    ])
    def test_missing_or_invalid_returns_none(self, data):
        assert parse_profile_weight(data) is None


_FORM_PAGE = """
<html><body>
<form id="authForm" class="form-box" action="/oauth2/authorize" method="post">
  <input type="hidden" name="client_id" value="68mnvu3ma928t8j5s0ceb0vyinsz66fk">
  <input type="hidden" name="redirect_uri" value="https://mcpus.coros.com/api/v1/coros/callback">
  <input type="hidden" name="state" value="abc&amp;def">
  <input type="hidden" name="scope" value="">
  <input type="hidden" name="response_type" value="code">
  <input type="hidden" name="country" id="country" value="CN">
  <input autocomplete="off" type="text" name="userName" id="txt_userName" value="">
  <input autocomplete="off" type="password" name="password" id="psw_password" value="">
  <input type="hidden" name="checkStatus" id="checkStatus" value="">
</form>
</body></html>
"""


class TestParseLoginForm:
    def test_extracts_action_and_all_fields(self):
        action, fields = _parse_login_form(_FORM_PAGE)
        assert action == "/oauth2/authorize"
        assert fields["client_id"] == "68mnvu3ma928t8j5s0ceb0vyinsz66fk"
        assert fields["state"] == "abc&def"        # HTML entity 要還原
        assert fields["scope"] == ""               # 空 value 保留
        assert fields["userName"] == "" and fields["password"] == ""
        assert fields["country"] == "CN"           # 呼叫端會覆寫成 TW

    def test_missing_form_raises(self):
        with pytest.raises(CorosMCPError, match="登入表單"):
            _parse_login_form("<html><body>沒有表單</body></html>")

    def test_form_without_credentials_fields_raises(self):
        page = '<form id="authForm" action="/x"><input name="state" value="s"></form>'
        with pytest.raises(CorosMCPError, match="帳密欄位"):
            _parse_login_form(page)
