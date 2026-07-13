import pytest

from srt_mobile_api.errors import SrtAppError, SrtProtocolError
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
