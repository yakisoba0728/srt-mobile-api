import httpx

from srt_mobile_api import SrtConfig
from srt_mobile_api.http import SrtHttpClient
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
