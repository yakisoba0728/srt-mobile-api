import json
import traceback

import httpx
import pytest

from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtProtocolError, SrtSessionExpiredError, SrtTransportError
from srt_mobile_api.http import SrtHttpClient
from srt_mobile_api.parsers import extract_text, normalize_result_row


LOGIN_FORM = '<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>'


def test_post_form_adds_ajax_headers_and_form_encoding():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    result = client.post_form(
        "/main/noticeList.do",
        {"a": "b"},
        accept="application/json",
        referer="https://app.srail.or.kr/main/main.do",
    )

    assert result["ok"] is True
    assert captured["headers"]["origin"] == "https://app.srail.or.kr"
    assert captured["headers"]["x-requested-with"] == "XMLHttpRequest"
    assert captured["headers"]["content-type"] == "application/x-www-form-urlencoded; charset=UTF-8"
    assert captured["body"] == "a=b"


def test_normalize_result_row_accepts_list_and_object():
    assert normalize_result_row({"outDataSets": {"dsOutput0": [{"msgCd": "A"}]}})["msgCd"] == "A"
    assert normalize_result_row({"outDataSets": {"dsOutput0": {"msgCd": "B"}}})["msgCd"] == "B"
    assert normalize_result_row({"resultMap": [{"msgCd": "C"}]})["msgCd"] == "C"


def test_extract_text_collapses_html_text():
    assert (
        extract_text("<html><body><h1>열차조회</h1><p>  test </p></body></html>")
        == "열차조회 test"
    )


def test_get_json_returns_object():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

    assert client.get_json("/main/main.do") == {"ok": True}


def test_get_json_raises_protocol_error_for_malformed_or_non_json():
    responses = [
        httpx.Response(200, content=b"{"),
        httpx.Response(200, text="not json", headers={"content-type": "text/html"}),
        httpx.Response(200, content=b"[1]", headers={"content-type": "application/json"}),
    ]

    for response in responses:
        def handler(_: httpx.Request, response=response) -> httpx.Response:
            return response

        client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

        try:
            client.get_json("/main/main.do")
        except SrtProtocolError:
            pass
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("expected SrtProtocolError")


def test_post_form_raises_protocol_error_for_invalid_json_when_json_is_requested():
    responses = [
        httpx.Response(200, content=b"{", headers={"content-type": "application/json"}),
        httpx.Response(200, text="not json", headers={"content-type": "text/html"}),
        httpx.Response(200, content=b"[1]", headers={"content-type": "application/json"}),
    ]

    for response in responses:
        def handler(_: httpx.Request, response=response) -> httpx.Response:
            return response

        client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

        try:
            client.post_form("/main/noticeList.do", {"a": "b"}, accept="application/json")
        except SrtProtocolError:
            pass
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("expected SrtProtocolError")


def test_post_form_returns_html_when_html_is_requested():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html><body>ok</body></html>", headers={"content-type": "text/html"}
        )

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

    assert client.post_form(
        "/ara/selectListAra12009_n.do",
        {"a": "b"},
        accept="text/html, */*; q=0.01",
    ) == {
        "html": "<html><body>ok</body></html>"
    }


@pytest.mark.parametrize(
    ("accept", "content_type"),
    [
        ("application/json", "text/plain"),
        ("text/html, */*; q=0.01", "application/json"),
    ],
)
def test_post_form_parses_valid_json_before_scanning_string_contents(accept, content_type):
    login_markup = "<form action='/apb/selectListApb01080_n.do'><input name='hmpgPwdCphd'></form>"
    payload = {"ordinary": login_markup}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps(payload),
            headers={"Content-Type": content_type},
        )

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

    assert client.post_form("/main/noticeList.do", {}, accept=accept) == payload


def test_http_rejects_unknown_route_before_transport():
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtProtocolError):
        client.post_form("/arc/selectListArc05013_n.do", {})
    assert called is False


@pytest.mark.parametrize(
    ("status_code", "location", "error_type"),
    [
        (302, "/login/login.do", SrtSessionExpiredError),
        (302, "https://app.srail.or.kr/login/login.do?return=main", SrtSessionExpiredError),
        (302, "https://evil.example/login/login.do", SrtTransportError),
        (302, "//evil.example/login/login.do", SrtTransportError),
        (302, "/maintenance.do?next=/login/login.do", SrtTransportError),
        (302, "/login/login.do.evil", SrtTransportError),
        (302, "/maintenance.do", SrtTransportError),
        (503, "", SrtTransportError),
    ],
)
def test_http_classifies_redirects_and_error_statuses(status_code, location, error_type):
    def handler(_: httpx.Request) -> httpx.Response:
        headers = {"Location": location} if location else {}
        return httpx.Response(status_code, headers=headers)

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(error_type):
        client.get_text("/main/main.do")


@pytest.mark.parametrize(
    ("path", "accept"),
    [
        ("/main/noticeList.do", "application/json"),
        ("/ara/selectListAra13010_n.do", "text/html, */*; q=0.01"),
    ],
    ids=["invalid-json", "authenticated-html"],
)
def test_http_classifies_actual_login_form_after_response_framing(path, accept):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=LOGIN_FORM, headers={"Content-Type": "text/html"})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtSessionExpiredError):
        client.post_form(path, {}, accept=accept)


def test_http_wraps_transport_errors_without_exposing_query_values():
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network failed")

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtTransportError) as exc_info:
        client.get_text("/main/main.do", params={"safe": "value-secret"})
    assert "value-secret" not in str(exc_info.value)


def test_transport_traceback_suppresses_sensitive_httpx_cause():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(
            'failed {"hmpgPwdCphd":"password-secret"} '
            "https://member-secret:password-secret@host/path?netfunnelKey=key-secret",
            request=request,
        )

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtTransportError) as exc_info:
        client.get_text("/main/main.do")
    rendered = "".join(traceback.format_exception(exc_info.value))
    for secret in ("member-secret", "password-secret", "key-secret"):
        assert secret not in rendered
