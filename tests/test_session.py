import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtApiError, SrtAuthError


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


def test_failed_relogin_clears_existing_session_and_cookies(load_json_fixture):
    responses = iter(
        [
            httpx.Response(200, text="<html>login</html>"),
            httpx.Response(200, json=load_json_fixture("login_success.json")),
            httpx.Response(200, text="<html>main</html>"),
            httpx.Response(200, text="<html>booking</html>"),
            httpx.Response(200, text="<html>login</html>"),
            httpx.Response(200, json=load_json_fixture("login_failure.json")),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.login("login-id", "pw")
    client.http.cookies.set("JSESSIONID", "stale")

    try:
        client.login("other-id", "bad")
    except SrtAuthError:
        pass
    else:
        raise AssertionError("SrtAuthError was not raised")

    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


def test_clear_session_and_logout_clear_current_and_cookies(load_json_fixture):
    responses = iter(
        [
            httpx.Response(200, text="<html>login</html>"),
            httpx.Response(200, json=load_json_fixture("login_success.json")),
            httpx.Response(200, text="<html>main</html>"),
            httpx.Response(200, text="<html>booking</html>"),
            httpx.Response(200, text="<html>login</html>"),
            httpx.Response(200, json=load_json_fixture("login_success.json")),
            httpx.Response(200, text="<html>main</html>"),
            httpx.Response(200, text="<html>booking</html>"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.login("login-id", "pw")
    client.http.cookies.set("JSESSIONID", "keep")
    client.clear_session()

    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies

    client.login("login-id", "pw")
    client.http.cookies.set("JSESSIONID", "keep")
    client.logout()

    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


@pytest.mark.parametrize(
    "failure_path",
    [
        "/login/login.do",
        "/apb/selectListApb01080_n.do",
        "/main/main.do",
        "/ara/ara0101v.do",
    ],
)
def test_login_rolls_back_cookie_and_current_on_every_step(failure_path, load_json_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failure_path:
            return httpx.Response(503, text="failed")
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(
                200,
                json=load_json_fixture("login_success.json"),
                headers={"Set-Cookie": "JSESSIONID=new-cookie; Path=/"},
            )
        return httpx.Response(200, text="<html>ok</html>")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.http.cookies.set("JSESSIONID", "old-cookie")
    with pytest.raises(SrtApiError):
        client.login("login-id", "pw")
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies
