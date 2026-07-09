import httpx

from srt_mobile_api import SrtConfig
from srt_mobile_api.http import SrtHttpClient
from srt_mobile_api.errors import SrtProtocolError
from srt_mobile_api.parsers import extract_text, normalize_result_row


def test_post_form_adds_ajax_headers_and_form_encoding():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    result = client.post_form(
        "/example.do",
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
    assert extract_text("<html><body><h1>열차조회</h1><p>  test </p></body></html>") == "열차조회 test"


def test_get_json_returns_object():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

    assert client.get_json("/example.do") == {"ok": True}


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
            client.get_json("/example.do")
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
            client.post_form("/example.do", {"a": "b"}, accept="application/json")
        except SrtProtocolError:
            pass
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("expected SrtProtocolError")


def test_post_form_returns_html_when_html_is_requested():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>ok</body></html>", headers={"content-type": "text/html"})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))

    assert client.post_form("/example.do", {"a": "b"}, accept="text/html, */*; q=0.01") == {
        "html": "<html><body>ok</body></html>"
    }
