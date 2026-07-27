import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtApiError, SrtAuthError


def test_login_flow_posts_expected_fields(load_json_fixture):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(
            (request.method, request.url.path, request.content.decode(), request.url.query.decode())
        )
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
    # "login-id" is neither email nor phone → membership number (srchDvCd=1).
    assert "srchDvCd=1" in login_body
    assert "srchDvNm=login-id" in login_body
    assert "hmpgPwdCphd=pw" in login_body
    # The login deviceKey is the server-rendered constant "-" (srtgo srt.py:704),
    # never the ANDROID_ID-shaped config.device_key.
    assert "deviceKey=-" in login_body
    assert f"deviceKey={SrtConfig().device_key}" not in login_body
    # config.device_key still carries the ANDROID_ID-shaped value on /main/main.do.
    main_query = next(query for _m, path, _b, query in captured if path == "/main/main.do")
    assert f"deviceId={SrtConfig().device_key}" in main_query


@pytest.mark.parametrize(
    ("login_id", "expected_srch_dv_cd", "expected_srch_dv_nm"),
    [
        # Auto-detected from the identifier (srtgo srt.py:691-698):
        ("user@example.com", "2", "user%40example.com"),  # email → 2
        ("010-1234-5678", "3", "01012345678"),  # phone → 3, dashes stripped
        ("01012345678", "3", "01012345678"),  # dashless Korean mobile → 3
        ("1234567890", "1", "1234567890"),  # all-digit membership number → 1
    ],
)
def test_login_type_is_auto_detected_from_identifier(
    load_json_fixture, login_id, expected_srch_dv_cd, expected_srch_dv_nm
):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, request.content.decode()))
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        return httpx.Response(200, text="<html>ok</html>")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.login(login_id, "pw")

    login_body = captured[1][1]
    assert f"srchDvCd={expected_srch_dv_cd}" in login_body
    assert f"srchDvNm={expected_srch_dv_nm}" in login_body


def test_login_type_explicit_override_is_preserved(load_json_fixture):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, request.content.decode()))
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        return httpx.Response(200, text="<html>ok</html>")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    # An explicit login_type overrides auto-detection; a "3" override still strips dashes.
    client.login("010-1234-5678", "pw", login_type="3")
    assert "srchDvCd=3" in captured[1][1]
    assert "srchDvNm=01012345678" in captured[1][1]

    captured.clear()
    client.login("user@example.com", "pw", login_type="1")
    assert "srchDvCd=1" in captured[1][1]
    assert "srchDvNm=user%40example.com" in captured[1][1]


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


def test_login_failure_reads_top_level_msg_without_user_map(load_json_fixture):
    # srtgo's failure path reads the TOP-LEVEL MSG (r.json()["MSG"], srt.py:716,718)
    # and raises an auth error; userMap is absent on a wrong-password attempt. We must
    # surface that Korean message as SrtAuthError, NOT raise SrtProtocolError.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, json=load_json_fixture("login_failure_toplevel.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtAuthError) as exc_info:
        client.login("login-id", "bad")
    assert "비밀번호 오류입니다." in str(exc_info.value)
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


def test_login_ip_block_raises_auth_error_not_protocol_error():
    # An IP block returns a non-JSON plain-text body; srtgo surfaces it as a login failure
    # (srt.py:719-720). It must be a catchable SrtAuthError (with the block reason), not a
    # generic SrtProtocolError raised before the auth branch.
    block_body = "Your IP Address Blocked. Please contact the administrator."

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, text=block_body, headers={"Content-Type": "text/html"})

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.http.cookies.set("JSESSIONID", "stale")
    with pytest.raises(SrtAuthError) as exc_info:
        client.login("login-id", "pw")
    assert "Your IP Address Blocked" in str(exc_info.value)
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


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


def test_zero_config_client_logs_in_with_no_configuration(load_json_fixture):
    """The README quickstart's bare ``SrtClient()`` must actually be able to log in.

    README.md:66 opens with ``client = SrtClient()`` and README.md:92-94 states
    that "``SrtClient()`` needs no configuration". That was prose only, and the
    sibling KORAIL client is the reason it cannot stay prose: there a bare
    ``KorailConfig()`` announced the library instead of the app in the
    User-Agent and left the anti-macro token off, so the server refused the
    login as a bot -- while every read still worked, which is exactly what makes
    the trap quiet. This pins that SRT does not share it, by driving the WHOLE
    login path (``session.py:37-94``: login page, login POST, main, booking) on
    a client constructed with no ``config`` argument at all.

    The transport is the only injection, and it refuses any host but
    ``app.srail.or.kr``: login must not need a NetFunnel round trip either
    (``nf.letskorail.com`` is only reached by the ``act_10`` search/reserve gate,
    never by ``SrtSessionClient.login``).
    """
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.url.path, request.headers["User-Agent"]))
        if request.url.host != "app.srail.or.kr":
            raise AssertionError(f"login reached a non-app host: {request.url.host}")
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        if request.url.path == "/main/main.do":
            return httpx.Response(200, text="<html>main</html>")
        if request.url.path == "/ara/ara0101v.do":
            return httpx.Response(200, text="<html>booking</html>")
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(transport=httpx.MockTransport(handler))
    session = client.login("login-id", "pw")

    assert session.login_id == "login-id"
    assert client.session.current is session
    # The bare client really did carry the frozen defaults -- nothing was filled
    # in for it along the way.
    assert client.config == SrtConfig()
    # All four steps ran, all four on the app origin only.
    assert [path for _host, path, _ua in seen] == [
        "/login/login.do",
        "/apb/selectListApb01080_n.do",
        "/main/main.do",
        "/ara/ara0101v.do",
    ]


def test_default_user_agent_impersonates_the_app_on_every_login_request(
    load_json_fixture,
):
    """The default UA is the app's, and names neither this library nor httpx.

    This is the precise shape of the KORAIL defect: a default User-Agent that
    identifies the client library is what the server reads as a bot, and it
    reports that as a "please update the app" message rather than as a refusal.
    ``http.py:56-61`` sends ``config.user_agent`` verbatim on every request, so
    the default is what a zero-config caller transmits.

    The ``537.36SRT-APP-Android`` assertion is deliberate and is NOT a typo to
    be tidied: the app concatenates its suffix onto the WebView UA with no
    separator (``SRWebActivity.java:2642-2645``; confirmed as faithful, not a
    defect, in ``docs/audit-2026-07-27/phase1/08-misc.md:134``), and srtgo
    matches (``srt.py:20-23``). ``test_models.py`` only checks that the suffix is
    present somewhere, which passes with or without the space.
    """
    agents = []

    def handler(request: httpx.Request) -> httpx.Response:
        agents.append(request.headers["User-Agent"])
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        return httpx.Response(200, text="<html>ok</html>")

    client = SrtClient(transport=httpx.MockTransport(handler))
    client.login("login-id", "pw")

    assert len(agents) == 4
    assert set(agents) == {SrtConfig().user_agent}
    for agent in agents:
        assert "SRT-APP-Android V." in agent
        # No space before the suffix: the app emits none.
        assert "537.36SRT-APP-Android" in agent
        lowered = agent.casefold()
        for library_name in ("srt_mobile_api", "srt-mobile-api", "httpx", "python"):
            assert library_name not in lowered
