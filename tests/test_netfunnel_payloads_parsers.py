import pytest

from srt_mobile_api.errors import SrtAppError, SrtNetFunnelError
from srt_mobile_api.models import PassengerCounts, TrainSearchQuery
from srt_mobile_api.netfunnel import parse_netfunnel_response
from srt_mobile_api.parsers import parse_train_search_response
from srt_mobile_api.payloads import group_search_ajax_payload, search_ajax_payload, search_page_payload


def test_parse_netfunnel_response_extracts_key(load_text_fixture):
    token = parse_netfunnel_response(load_text_fixture("netfunnel_act10.js"), action="act_10")
    assert token.action == "act_10"
    assert token.code == "5101"
    assert token.key == "ABC123"


def test_parse_netfunnel_response_requires_key():
    body = "NetFunnel.gControl.result='2002:5101:opcode=5002&nwait=0&ip=127.0.0.1';"

    with pytest.raises(SrtNetFunnelError, match="key"):
        parse_netfunnel_response(body, action="act_10")


def test_search_payloads_include_expected_keys():
    query = TrainSearchQuery("0551", "0020", "20260710", passengers=PassengerCounts(adult=1))
    page_payload = search_page_payload(query, "수서", "부산", "NF")
    ajax_payload = search_ajax_payload(query, "NF")
    group_payload = group_search_ajax_payload(query, "NF")

    assert page_payload["dptRsStnCd1"] == "0551"
    assert page_payload["arvRsStnCdNm1"] == "부산"
    assert ajax_payload["netfunnelKey"] == "NF"
    assert ajax_payload["psgNum"] == "1"
    assert group_payload["psgNum"] == "10"
    assert group_payload["grpDv"] == "1"


def test_parse_train_search_response_normalizes_list_and_object_result(load_json_fixture):
    result = parse_train_search_response(load_json_fixture("search_success.json"))
    group = parse_train_search_response(load_json_fixture("group_search_success.json"))
    empty = parse_train_search_response(load_json_fixture("search_empty.json"))

    assert result.result["msgCd"] == "IRG000000"
    assert result.trains[0].train_no == "303"
    assert group.trains[0].train_no == "301"
    assert empty.trains == []


def test_parse_train_search_response_raises_on_app_failure(load_json_fixture):
    with pytest.raises(SrtAppError) as exc_info:
        parse_train_search_response(load_json_fixture("search_netfunnel_failure.json"))

    assert exc_info.value.code == "NET000001"
    assert exc_info.value.message == "NetFunnel key required"
