import httpx
import pytest

from srt_mobile_api import SrtClient
from srt_mobile_api.errors import SrtSessionExpiredError
from srt_mobile_api.errors import SrtAppError, SrtProtocolError
from srt_mobile_api.models import SrtSession
from srt_mobile_api.parsers import parse_mutual_verification_response


@pytest.mark.parametrize("object_shape", [False, True])
def test_mutual_parser_accepts_evidenced_list_and_object_rows(
    load_json_fixture,
    object_shape,
):
    payload = load_json_fixture("mutual_verification_success.json")
    if object_shape:
        payload["outDataSets"]["dsOutput0"] = payload["outDataSets"][
            "dsOutput0"
        ][0]
    result = parse_mutual_verification_response(payload)
    assert result.message_code == "IRZ000008"
    assert result.status == "SUCC"
    assert result.message == "Success"
    assert result.verification_code == "fixture-mutual-code"
    assert result.raw is payload
    assert "fixture-mutual-code" not in repr(result)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"ErrorCode": 0, "outDataSets": {}},
        {"ErrorCode": "0", "ErrorMsg": 123, "outDataSets": {}},
        {"ErrorCode": "0"},
        {"ErrorCode": "0", "outDataSets": None},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": []}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": ["row"]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": ""}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": 123}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "msgTxt": 123, "strResult": "SUCC", "mutMrkVrfCd": "code"}]}},
    ],
)
def test_mutual_parser_rejects_malformed_framing(payload):
    with pytest.raises(SrtProtocolError):
        parse_mutual_verification_response(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"ErrorCode": "WRAPPER_ERR", "ErrorMsg": "wrapper failed"},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "OTHER", "msgTxt": "wrong code", "strResult": "SUCC", "mutMrkVrfCd": "code"}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "msgTxt": "wrong status", "strResult": "FAIL", "mutMrkVrfCd": "code"}]}},
    ],
)
def test_mutual_parser_classifies_wrapper_and_business_failures(payload):
    with pytest.raises(SrtAppError) as exc_info:
        parse_mutual_verification_response(payload)
    assert exc_info.value.raw is payload


def test_client_sends_exact_empty_mutual_form_headers_and_referer(
    load_json_fixture,
):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=load_json_fixture("mutual_verification_success.json"),
        )

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        result = client.get_mutual_verification()
    finally:
        client.close()
    assert result.verification_code == "fixture-mutual-code"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/ara/selectListAra10130_n.do"
    assert request.content == b""
    assert request.headers["accept"] == (
        "application/json, text/javascript, */*; q=0.01"
    )
    assert request.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert request.headers["origin"] == "https://app.srail.or.kr"
    assert request.headers["x-requested-with"] == "XMLHttpRequest"
    assert request.headers["referer"] == (
        "https://app.srail.or.kr/ara/selectListAra10007_n.do"
    )


def test_mutual_login_form_clears_session_and_cookies():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<form action="/apb/selectListApb01080_n.do">'
                '<input name="hmpgPwdCphd"></form>'
            ),
            headers={"Content-Type": "text/html"},
        )

    client = SrtClient(transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="stale")
    client.http.cookies.set("JSESSIONID", "stale")
    try:
        with pytest.raises(SrtSessionExpiredError):
            client.get_mutual_verification()
        assert client.session.current is None
        assert not list(client.http.cookies.jar)
    finally:
        client.close()
