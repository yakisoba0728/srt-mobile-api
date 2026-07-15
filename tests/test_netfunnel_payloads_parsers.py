from dataclasses import replace
import traceback

import pytest

from srt_mobile_api.errors import SrtAppError, SrtNetFunnelError, SrtProtocolError
from srt_mobile_api.models import HtmlPage, PassengerCounts, TrainSearchQuery, TrainSummary
from srt_mobile_api.netfunnel import build_act10_url, parse_netfunnel_response
from srt_mobile_api.parsers import (
    parse_fare_page,
    parse_search_has_following_page,
    parse_search_page_state,
    parse_timetable_page,
    parse_train_search_response,
)
from srt_mobile_api.payloads import (
    date_selector_payload,
    fare_payload,
    group_search_ajax_payload,
    passenger_selector_payload,
    search_ajax_payload,
    search_continuation_payload,
    search_page_payload,
    seat_page_payload,
    seat_option_selector_payload,
    station_map_selector_payload,
    station_selector_payload,
    timetable_payload,
    train_group_selector_payload,
)


def test_parse_netfunnel_response_extracts_key(load_text_fixture):
    token = parse_netfunnel_response(load_text_fixture("netfunnel_act10.js"), action="act_10")
    assert token.action == "act_10"
    assert token.code == "5101"
    assert token.key == "ABC123"


def test_parse_netfunnel_response_accepts_plan_evidenced_three_part_success():
    token = parse_netfunnel_response(
        "NetFunnel.gControl.result='5101:5101:key=NF';",
        action="act_10",
    )
    assert token.raw_type == "5101"
    assert token.code == "5101"
    assert token.key == "NF"


def test_parse_netfunnel_response_accepts_evidenced_5002_wrapper(load_text_fixture):
    token = parse_netfunnel_response(
        load_text_fixture("netfunnel_act10_5002.js"),
        action="act_10",
    )

    assert token.action == "act_10"
    assert token.raw_type == "5002"
    assert token.code == "200"
    assert token.key == "SYNTHETIC_KEY_5002"
    assert token.params["nnext"] == "7"


def test_parse_netfunnel_response_requires_key():
    body = "NetFunnel.gControl.result='5101:5101:opcode=5002&nwait=0&ip=127.0.0.1';"

    with pytest.raises(SrtNetFunnelError, match="key"):
        parse_netfunnel_response(body, action="act_10")


def test_build_act10_url_is_deterministic():
    url = build_act10_url("https://nf.letskorail.com:443", timestamp_ms=1712345678901)
    assert "aid=act_10" in url
    assert "sid=service_1" in url
    assert url.endswith("&1712345678901")


def test_missing_netfunnel_token_is_classified_with_fields():
    with pytest.raises(SrtNetFunnelError) as exc_info:
        parse_netfunnel_response("not a token", action="act_10")
    assert exc_info.value.code is None
    assert exc_info.value.message == "NetFunnel response did not include a result token"


@pytest.mark.parametrize(
    "body",
    [
        "Other.result='5101:5101:key=key-secret';",
        "var text='5101:5101:key=key-secret';",
        "NetFunnel.gControl.resultText='5101:5101:key=key-secret';",
        "var before=1; NetFunnel.gControl.result='5101:5101:key=key-secret';",
        "NetFunnel.gControl.result='5101:5101:key=key-secret'; trailing();",
        "NetFunnel.gRtype=4000;NetFunnel.gControl.result='5002:200:key=key-secret';",
        "NetFunnel.gControl.result='5002:200:key=key-secret'; Other._showResult();",
        "NetFunnel.gControl.result='5002:200:key=key-secret'; "
        "NetFunnel.gControl._showResult(); trailing();",
        "NetFunnel.gControl.result='5002:200:key=key-secret\";",
        "NetFunnel.gControl.result='5101:5101:key=key-secret';"
        "NetFunnel.gControl.result='5002:200:key=key-secret';",
    ],
)
def test_netfunnel_parser_requires_exact_result_assignment(body):
    with pytest.raises(SrtNetFunnelError, match="result token") as exc_info:
        parse_netfunnel_response(body, action="act_10")
    rendered = "".join(traceback.format_exception(exc_info.value))
    assert "key-secret" not in str(exc_info.value)
    assert "key-secret" not in repr(exc_info.value)
    assert "key-secret" not in rendered


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("NetFunnel.gControl.result='5101:FAIL:key=key-secret';", "FAIL"),
        ("NetFunnel.gControl.result='5002:FAIL:key=key-secret';", "FAIL"),
        ("NetFunnel.gControl.result='5002:5101:key=key-secret';", "5101"),
        ("NetFunnel.gControl.result='5101:200:key=key-secret';", "200"),
        ("NetFunnel.gControl.result='2002:5101:key=key-secret';", "5101"),
        ("NetFunnel.gControl.result='NetFunnel.gRtype=5002;5101:key=key-secret';", None),
        ("NetFunnel.gControl.result='invalid:5101:key=key-secret';", None),
    ],
)
def test_netfunnel_parser_rejects_malformed_or_non_success_tokens(body, code):
    with pytest.raises(SrtNetFunnelError) as exc_info:
        parse_netfunnel_response(body, action="act_10")
    assert exc_info.value.code == code
    assert "key-secret" not in str(exc_info.value)
    assert "key-secret" not in repr(exc_info.value)


def test_search_payloads_include_expected_keys():
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=1),
        train_group_code="300",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    hydrated_fields = {"serverNonce": "nonce-1", "dptRsStnCdNm1": "수서", "psgTpCd1": "1"}
    page_payload = search_page_payload(query, "NF")
    ajax_payload = search_ajax_payload(query, "NF", hydrated_fields=hydrated_fields)
    group_payload = group_search_ajax_payload(query, "NF", hydrated_fields=hydrated_fields)

    assert page_payload["dptRsStnCd1"] == "0551"
    assert page_payload["arvRsStnCdNm1"] == "부산"
    assert page_payload["stlbTrnClsfCd1"] == "17"
    assert page_payload["trnGpNm1"] == "SRT"
    assert ajax_payload["netfunnelKey"] == "NF"
    assert ajax_payload["psgNum"] == "1"
    assert ajax_payload["serverNonce"] == "nonce-1"
    assert group_payload["psgNum"] == "10"
    assert group_payload["grpDv"] == "1"


def test_search_continuation_payload_preserves_hydrated_state_and_changes_cursor_only():
    base = {
        "dptTm": "060000",
        "dptTm1": "060000",
        "trnNo": "00303",
        "netfunnelKey": "NF",
        "unknownField": "keep-me",
        "grpDv": "1",
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": "10",
    }

    continuation = search_continuation_payload(base, "061234")

    assert continuation == {
        **base,
        "dptTm": "061231",
        "trnNo": "",
    }
    assert base["dptTm"] == "060000"
    assert continuation["dptTm1"] == "060000"
    assert continuation["netfunnelKey"] == "NF"
    assert continuation["unknownField"] == "keep-me"
    assert continuation["grpDv"] == "1"
    assert continuation["psgInfoPerPrnb1"] == "10"
    assert "fllwPgExt" not in continuation


def test_search_payloads_never_send_response_only_following_page_flag():
    query = TrainSearchQuery("0551", "0020", "20260710")
    payload = search_ajax_payload(
        query,
        "NF",
        hydrated_fields={"fllwPgExt": "Y", "unknownField": "keep-me"},
    )
    continuation = search_continuation_payload(
        {**payload, "fllwPgExt": "Y"},
        "060000",
    )

    assert "fllwPgExt" not in payload
    assert "fllwPgExt" not in continuation
    assert continuation["unknownField"] == "keep-me"


@pytest.mark.parametrize(
    "last_departure_time",
    [None, "", "06000", "0600000", "06:00:00", " 060000", "060000 ", "٠٦٠٠٠٠"],
)
def test_search_continuation_payload_requires_six_ascii_digits(last_departure_time):
    with pytest.raises(ValueError, match="last_departure_time"):
        search_continuation_payload({"dptTm": "060000", "trnNo": ""}, last_departure_time)


@pytest.mark.parametrize("container", ["list", "object"])
@pytest.mark.parametrize(("flag", "expected"), [("Y", True), ("N", False)])
def test_search_following_page_metadata_accepts_exact_flags(container, flag, expected):
    metadata = {"msgCd": "IRG000000", "strResult": "SUCC", "fllwPgExt": flag}
    data = {
        "ErrorCode": "0",
        "outDataSets": {
            "dsOutput0": [metadata] if container == "list" else metadata,
            "dsOutput1": [],
        },
    }

    assert parse_search_has_following_page(data) is expected


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        [],
        ["not-an-object"],
        {"fllwPgExt": ""},
        {"fllwPgExt": "y"},
        {"fllwPgExt": " Y"},
        {"fllwPgExt": True},
        {"fllwPgExt": 1},
        {"fllwPgExt": []},
        {"fllwPgExt": {}},
        "not-metadata",
    ],
)
def test_search_following_page_metadata_rejects_missing_or_invalid_flag(metadata):
    data = {
        "ErrorCode": "0",
        "outDataSets": {"dsOutput0": metadata, "dsOutput1": []},
    }

    with pytest.raises(SrtProtocolError, match="fllwPgExt|dsOutput0"):
        parse_search_has_following_page(data)


def test_station_selector_payload_is_exact():
    assert station_selector_payload("수서", "부산", "0551", "0020") == {
        "reqCode": "1",
        "sDptStnNm": "수서",
        "sArvStnNm": "부산",
        "sDptStnCd": "0551",
        "sArvStnCd": "0020",
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def test_station_map_selector_payload_is_exact():
    assert station_map_selector_payload() == {
        "reqCode": "2",
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def test_date_selector_payload_is_exact():
    assert date_selector_payload("20260714", "06") == {
        "reqCode": "3",
        "selectDay": "",
        "selectDt": "20260714",
        "selectTime": "06",
    }


def test_passenger_selector_payload_keeps_six_slots_and_server_typo():
    passengers = PassengerCounts(
        adult=1,
        child=2,
        senior=3,
        disability_1_to_3=4,
        disability_4_to_6=5,
        infant=6,
    )
    assert passenger_selector_payload(passengers) == {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": "1",
        "passenger2": "2",
        "passenger3": "3",
        "passenger4": "4",
        "passenger5": "5",
        "passenger6": "6",
        "totalPessnger": "21",
    }


def test_seat_option_selector_payload_is_exact():
    assert seat_option_selector_payload("015", "000", "일반/기본") == {
        "reqCode": "5",
        "rqSeatAttCd": "015",
        "locSeatAttCd": "000",
        "seatAttNm": "일반/기본",
    }


def test_train_group_selector_payload_is_exact():
    assert train_group_selector_payload("109", "전체") == {
        "reqCode": "7",
        "trnGpCd": "109",
        "trnGpCdNm": "전체",
    }


@pytest.mark.parametrize(
    ("builder", "args"),
    [
        (station_selector_payload, ("", "부산", "0551", "0020")),
        (station_selector_payload, ("수서", "", "0551", "0020")),
        (station_selector_payload, ("수서", "부산", "", "0020")),
        (station_selector_payload, ("수서", "부산", "0551", "")),
        (date_selector_payload, ("2026-07-14", "06")),
        (date_selector_payload, ("20260714", "24")),
        (seat_option_selector_payload, ("", "000", "일반/기본")),
        (seat_option_selector_payload, ("015", "", "일반/기본")),
        (seat_option_selector_payload, ("015", "000", "")),
        (train_group_selector_payload, ("999", "전체")),
        (train_group_selector_payload, ("109", "")),
    ],
)
def test_selector_payloads_reject_invalid_input(builder, args):
    with pytest.raises(ValueError):
        builder(*args)


def test_search_page_state_preserves_unknown_and_station_name_fields(load_text_fixture):
    state = parse_search_page_state(load_text_fixture("search_page.html"))
    assert state.hidden_fields["serverNonce"] == "nonce-1"
    assert state.hidden_fields["unknownField"] == "keep-me"
    assert state.hidden_fields["dptRsStnCdNm1"] == "수서"


def test_search_page_state_uses_final_duplicate_named_input():
    state = parse_search_page_state(
        '<form><input name="duplicate" value="first"><input name="duplicate" value="final"></form>'
    )
    assert state.hidden_fields["duplicate"] == "final"


def test_hydrated_ajax_payload_overlays_only_caller_fields(load_text_fixture):
    state = parse_search_page_state(load_text_fixture("search_page.html"))
    query = TrainSearchQuery("0551", "0020", "20260710", train_group_code="300")
    payload = search_ajax_payload(query, "NF", hydrated_fields=state.hidden_fields)
    assert payload["serverNonce"] == "nonce-1"
    assert payload["unknownField"] == "keep-me"
    assert payload["dptRsStnCdNm1"] == "수서"
    assert payload["stlbTrnClsfCd"] == "17"
    assert payload["trnGpCd"] == "300"


def test_passenger_fields_use_protocol_codes_and_preserve_nonempty_hydrated_code():
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=0, child=1, senior=1, infant=1),
    )
    payload = search_ajax_payload(
        query,
        "NF",
        hydrated_fields={"psgTpCd1": "hydrated-adult", "psgTpCd2": "hydrated-child"},
    )
    assert payload["psgTpCd1"] == ""
    assert payload["psgTpCd2"] == "hydrated-child"
    assert payload["psgTpCd3"] == "4"
    assert payload["psgTpCd6"] == "6"
    assert payload["infantCnt"] == "1"


def test_parse_train_search_response_normalizes_list_and_object_result(load_json_fixture):
    result = parse_train_search_response(
        load_json_fixture("search_success.json"),
        request_context={
            "dptRsStnCd1": "0551",
            "dptRsStnCdNm1": "Synthetic Departure",
            "arvRsStnCd1": "0020",
            "arvRsStnCdNm1": "Synthetic Arrival",
        },
    )
    group = parse_train_search_response(load_json_fixture("group_search_success.json"))
    empty = parse_train_search_response(load_json_fixture("search_empty.json"))

    assert result.result["msgCd"] == "IRG000000"
    assert result.trains[0].train_no == "303"
    assert result.trains[0].departure_station_name == "Synthetic Departure"
    assert result.trains[0].arrival_station_name == "Synthetic Arrival"
    assert group.trains[0].train_no == "301"
    assert empty.trains == []


def _complete_seat_page_train() -> TrainSummary:
    return TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
    )


def test_search_parser_preserves_seat_page_fields(load_json_fixture):
    train = parse_train_search_response(
        load_json_fixture("search_success.json")
    ).trains[0]

    assert train.departure_run_order == "000001"
    assert train.arrival_run_order == "000010"
    assert train.seat_attr_code == "015"


def test_seat_page_payload_is_the_exact_fixed_contract():
    assert seat_page_payload(_complete_seat_page_train()) == {
        "reqCode": "9",
        "runDt": "20260710",
        "dptDt": "20260710",
        "trnNo": "00303",
        "dptTm": "060000",
        "trnGpCd": "300",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "psrmClCd": "1",
        "seatAttCd": "015",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000010",
        "choiceSeatCount": "1",
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"train_no": ""}, "train_no"),
        ({"train_no": "123456"}, "train_no"),
        ({"train_no": "30A"}, "train_no"),
        ({"train_group_code": "900"}, "train_group_code"),
        ({"run_date": None}, "run_date"),
        ({"departure_date": "2026-07-10"}, "departure_date"),
        ({"departure_time": "0600"}, "departure_time"),
        ({"departure_station_code": None}, "departure_station_code"),
        ({"arrival_station_code": "20"}, "arrival_station_code"),
        ({"departure_run_order": None}, "departure_run_order"),
        ({"arrival_run_order": "A10"}, "arrival_run_order"),
        ({"seat_attr_code": "15"}, "seat_attr_code"),
    ],
)
def test_seat_page_payload_rejects_incomplete_or_malformed_train(changes, message):
    with pytest.raises(ValueError, match=message):
        seat_page_payload(replace(_complete_seat_page_train(), **changes))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"train_no": "٣٠٣"}, "train_no"),
        ({"departure_station_code": "٠٥٥١"}, "departure_station_code"),
    ],
)
def test_seat_page_payload_rejects_non_ascii_digits(changes, message):
    with pytest.raises(ValueError, match=message):
        seat_page_payload(replace(_complete_seat_page_train(), **changes))


def test_parse_train_search_response_classifies_netfunnel_failure(load_json_fixture):
    with pytest.raises(SrtNetFunnelError) as exc_info:
        parse_train_search_response(load_json_fixture("search_netfunnel_failure.json"))

    assert exc_info.value.code == "NET000001"
    assert exc_info.value.message == "NetFunnel key required"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ErrorCode": "ERR", "ErrorMsg": "wrapper failed"},
        {"ErrorCode": "0", "outDataSets": {}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [], "dsOutput1": []}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "", "strResult": ""}], "dsOutput1": []}},
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}],
                "dsOutput1": {},
            },
        },
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}],
                "dsOutput1": ["not-an-object"],
            },
        },
        {
            "ErrorCode": "0",
            "outDataSets": {
                "dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}],
                "dsOutput1": [{}],
            },
        },
    ],
)
def test_search_parser_rejects_unproven_or_malformed_success(payload):
    with pytest.raises((SrtProtocolError, SrtAppError)):
        parse_train_search_response(payload)


@pytest.mark.parametrize("error_code", [[], {}, False, 0, None])
def test_search_parser_rejects_nonstring_wrapper_code(error_code):
    with pytest.raises(SrtProtocolError, match="ErrorCode"):
        parse_train_search_response(
            {
                "ErrorCode": error_code,
                "outDataSets": {
                    "dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}],
                    "dsOutput1": [],
                },
            }
        )


@pytest.mark.parametrize("error_message", [[], {}, False, 0, None])
def test_search_parser_rejects_nonstring_wrapper_message(error_message):
    with pytest.raises(SrtProtocolError, match="ErrorMsg"):
        parse_train_search_response(
            {
                "ErrorCode": "0",
                "ErrorMsg": error_message,
                "outDataSets": {
                    "dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}],
                    "dsOutput1": [],
                },
            }
        )


def test_empty_rows_are_valid_only_after_exact_success(load_json_fixture):
    result = parse_train_search_response(load_json_fixture("search_empty.json"))
    assert result.result["msgCd"] == "IRG000000"
    assert result.result["strResult"] == "SUCC"
    assert result.trains == []


def test_timetable_and_fare_parsers_return_html_compatible_models(load_text_fixture):
    timetable = parse_timetable_page(load_text_fixture("timetable.html"))
    fare = parse_fare_page(load_text_fixture("fare.html"))
    assert isinstance(timetable, HtmlPage)
    assert timetable.rows[0].station_name == "Synthetic Origin"
    assert timetable.rows[0].times == ("05:01",)
    assert "05:01" in timetable.text
    assert "<table>" in timetable.raw
    assert isinstance(fare, HtmlPage)
    assert fare.items[0].label == "Synthetic A1"
    assert fare.items[0].amount == 12340
    assert fare.items[0].raw_amount == "12,340원"
    assert "12,340원" in fare.text
    assert "<table>" in fare.raw


def test_detail_parsers_reject_pages_without_required_structure():
    with pytest.raises(SrtProtocolError):
        parse_timetable_page("<html><body>no schedule</body></html>")
    with pytest.raises(SrtProtocolError):
        parse_fare_page("<html><body>no fare</body></html>")


def test_fare_payload_contains_all_six_passenger_slots():
    train = TrainSummary(
        train_no="303",
        service_class_code="17",
        run_date="20260710",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    passengers = PassengerCounts(
        adult=1,
        child=1,
        senior=1,
        disability_1_to_3=1,
        disability_4_to_6=1,
        infant=1,
    )
    timetable = timetable_payload(train)
    payload = fare_payload(train, passengers)
    assert timetable == {
        "stnCourseNm": "수서-부산",
        "trnSort": "SRT",
        "runDt": "20260710",
        "trnNo": "00303",
    }
    assert [payload[f"psgTpCd{index}"] for index in range(1, 7)] == ["1", "5", "4", "2", "3", "6"]
    assert [payload[f"psgInfoPerPrnb{index}"] for index in range(1, 7)] == ["1"] * 6
    assert payload["psgTpCd6"] == "6"
    assert payload["trnNo"] == "00303"
    assert payload["stnCourseNm"] == "수서-부산"
    assert payload["dptRsStnCd2"] == ""
    assert payload["arvRsStnCd2"] == ""
    assert payload["runDt2"] == ""
    assert payload["trnNo2"] == ""
