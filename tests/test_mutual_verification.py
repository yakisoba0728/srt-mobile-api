import httpx
import pytest

from srt_mobile_api import SrtClient
from srt_mobile_api.errors import SrtAppError, SrtProtocolError, SrtSessionExpiredError
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


def test_mutual_parser_hides_verification_value_repeated_in_success_message():
    verification_secret = "synthetic-mutual-success-secret-72f530b1"
    payload = {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": "IRZ000008",
                    "msgTxt": verification_secret,
                    "strResult": "SUCC",
                    "mutMrkVrfCd": verification_secret,
                }
            ]
        },
    }

    result = parse_mutual_verification_response(payload)

    assert result.message == verification_secret
    assert result.verification_code == verification_secret
    assert verification_secret not in repr(result)


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
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": ""}]
            },
        },
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": 123}]
            },
        },
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [
                    {
                        "msgCd": "IRZ000008",
                        "msgTxt": 123,
                        "strResult": "SUCC",
                        "mutMrkVrfCd": "code",
                    }
                ]
            },
        },
    ],
)
def test_mutual_parser_rejects_malformed_framing(payload):
    with pytest.raises(SrtProtocolError):
        parse_mutual_verification_response(payload)


def test_mutual_parser_classifies_wrapper_failure():
    verification_secret = "synthetic-mutual-wrapper-secret-573ac90e"
    raw_only_marker = "synthetic-mutual-wrapper-raw-marker-24c916bd"
    payload = {
        "ErrorCode": "WRAPPER_ERR",
        "ErrorMsg": f"wrapper failed {verification_secret} {raw_only_marker}",
    }
    with pytest.raises(SrtAppError) as exc_info:
        parse_mutual_verification_response(payload)
    assert exc_info.value.raw is payload
    for exception_text in (str(exc_info.value), repr(exc_info.value)):
        assert verification_secret not in exception_text
        assert raw_only_marker not in exception_text


@pytest.mark.parametrize(
    ("message_code", "message", "status"),
    [
        # The app fails only on strResult == "FAIL" (ara1001l.js:234); it never gates on
        # msgCd, so a FAIL is a business failure regardless of the code carried.
        ("IRZ000008", "wrong status", "FAIL"),
        ("SOME_OTHER_CODE", "business fail", "FAIL"),
    ],
)
def test_mutual_parser_classifies_business_failures_without_leaking_raw_values(
    message_code,
    message,
    status,
):
    verification_secret = "synthetic-mutual-verification-secret-6f4b0e9c"
    raw_only_marker = "synthetic-mutual-raw-only-marker-a31d8c72"
    payload = {
        "ErrorCode": "0",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": message_code,
                    "msgTxt": f"{message} {verification_secret} {raw_only_marker}",
                    "strResult": status,
                    "mutMrkVrfCd": verification_secret,
                }
            ]
        },
        "syntheticRawOnlyMarker": raw_only_marker,
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_mutual_verification_response(payload)

    assert exc_info.value.raw is payload
    for exception_text in (str(exc_info.value), repr(exc_info.value)):
        assert verification_secret not in exception_text
        assert raw_only_marker not in exception_text


def test_mutual_parser_accepts_success_under_non_irz_msg_code():
    # The app reads mutMrkVrfCd whenever strResult != "FAIL" and never inspects msgCd
    # (ara1001l.js:234-241). A SUCC row with a populated mutMrkVrfCd under any msgCd must
    # be accepted, not mis-classified as an app error on the msgCd alone.
    payload = {
        "ErrorCode": "0",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": "OTHER",
                    "msgTxt": "ok",
                    "strResult": "SUCC",
                    "mutMrkVrfCd": "fixture-mutual-code",
                }
            ]
        },
    }

    result = parse_mutual_verification_response(payload)

    assert result.status == "SUCC"
    assert result.message_code == "OTHER"
    assert result.verification_code == "fixture-mutual-code"
    assert "fixture-mutual-code" not in repr(result)


def test_mutual_parser_accepts_success_without_msg_code():
    # The app never reads msgCd (ara1001l.js:234-241) and the documented Ara10130
    # dsOutput0 schema is {strResult, msgTxt, mutMrkVrfCd} with no msgCd. A valid SUCC
    # response lacking msgCd must be accepted (message_code = None), not rejected.
    payload = {
        "ErrorCode": "0",
        "outDataSets": {
            "dsOutput0": [
                {
                    "strResult": "SUCC",
                    "msgTxt": "ok",
                    "mutMrkVrfCd": "fixture-mutual-code",
                }
            ]
        },
    }

    result = parse_mutual_verification_response(payload)

    assert result.message_code is None
    assert result.status == "SUCC"
    assert result.verification_code == "fixture-mutual-code"


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
    configured_user_agent = client.config.user_agent
    client.http.cookies.set("JSESSIONID", "synthetic-mutual-session-cookie")
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
    assert request.headers["cookie"] == (
        "JSESSIONID=synthetic-mutual-session-cookie"
    )
    assert request.headers["user-agent"] == configured_user_agent


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
