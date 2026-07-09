import httpx

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtAuthError


def test_login_flow_posts_expected_fields(load_json_fixture):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.method, request.url.path, request.content.decode()))
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        if request.url.path == "/main/main.do":
            return httpx.Response(200, text="<html>main</html>")
        if request.url.path == "/ara/ara0101v.do":
            return httpx.Response(200, text="<html>booking</html>")
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    session = client.login("login-id", "pw")

    assert session.login_id == "login-id"
    login_body = captured[1][2]
    assert "srchDvCd=3" in login_body
    assert "srchDvNm=login-id" in login_body
    assert "hmpgPwdCphd=pw" in login_body


def test_login_failure_raises_auth_error(load_json_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, json=load_json_fixture("login_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    try:
        client.login("login-id", "pw")
    except SrtAuthError as exc:
        assert "로그인 실패" in str(exc)
    else:
        raise AssertionError("SrtAuthError was not raised")
