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
    personal_reservation_payload,
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
    assert token.raw_type == "5101"
    assert token.code == "200"
    assert token.key == "ABC123"


def test_parse_netfunnel_response_accepts_plan_evidenced_three_part_success():
    token = parse_netfunnel_response(
        "NetFunnel.gControl.result='5101:200:key=NF';",
        action="act_10",
    )
    assert token.raw_type == "5101"
    assert token.code == "200"
    assert token.key == "NF"


def test_parse_netfunnel_response_tolerates_echoed_grtype_prefix_and_status_success():
    # The real app response leads with the echoed sent opcode
    # (NetFunnel.gRtype=5101;) and reports success via the 3-digit status code.
    # kTsBypass=300 is a chkEnter pass (onBypass, no queue) alongside kSuccess=200.
    token = parse_netfunnel_response(
        "NetFunnel.gRtype=5101;NetFunnel.gControl.result='5101:300:key=NF';",
        action="act_10",
    )
    assert token.raw_type == "5101"
    assert token.code == "300"
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
    body = "NetFunnel.gControl.result='5101:200:opcode=5002&nwait=0&ip=127.0.0.1';"

    with pytest.raises(SrtNetFunnelError, match="key"):
        parse_netfunnel_response(body, action="act_10")


@pytest.mark.parametrize(
    "body",
    [
        "NetFunnel.gControl.result='5101:300:opcode=5002&nwait=0&ip=127.0.0.1';",
        "NetFunnel.gRtype=5101;NetFunnel.gControl.result='5101:300:nwait=0&nnext=0';",
        "NetFunnel.gControl.result='5101:300:key=';",
    ],
)
def test_parse_netfunnel_response_accepts_a_bypass_without_a_key(body):
    # kTsBypass=300 means the queue was BYPASSED: there is no place in line, so
    # there is nothing to issue a key for. The app's chkEnter handler sets
    # PS_N_RUNNING, stores the result cookie and fires onBypass without ever
    # reading getValue("key") (netfunnel.js, _showResultChkEnter). Accepting 300
    # as a success while still demanding a key made that acceptance unreachable
    # and aborted the search instead of proceeding.
    token = parse_netfunnel_response(body, action="act_10")

    assert token.code == "300"
    assert token.key == ""


def test_parse_netfunnel_response_still_requires_a_key_for_a_plain_success():
    # Deliberately NOT relaxed for kSuccess=200: a queue pass is identified by
    # its key, so a 200 without one stays anomalous.
    with pytest.raises(SrtNetFunnelError, match="key"):
        parse_netfunnel_response(
            "NetFunnel.gControl.result='5101:200:nwait=0&nnext=0';", action="act_10"
        )


def test_an_empty_netfunnel_key_is_inert_in_every_request_builder():
    # The other half of the relaxation: an absent key must not become a deferred
    # failure in a later request. Every builder that consumes one places it
    # verbatim, so a bypass yields netfunnelKey="" on the wire -- which is what
    # our own app sends anyway, its NetFunnel integration being commented out
    # (ara0101v.js:651-655, ara1001l.js:1734-1739 call netfunnel_callback()
    # directly) and the string "netfunnelKey" appearing nowhere in the bundle.
    query = TrainSearchQuery("0551", "0020", "20260710")

    assert search_page_payload(query, "")["netfunnelKey"] == ""
    assert search_ajax_payload(query, "", hydrated_fields={})["netfunnelKey"] == ""
    reservable = TrainSummary(
        train_no="303",
        service_class_code="17",
        train_group_code="300",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
        departure_date="20990101",
        departure_time="060000",
        arrival_time="083000",
        departure_run_order="1",
        arrival_run_order="10",
        departure_consist_order="1",
        arrival_consist_order="2",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )
    assert (
        personal_reservation_payload(
            reservable, PassengerCounts(adult=1), netfunnel_key=""
        )["netfunnelKey"]
        == ""
    )


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
        "NetFunnel.gRtype=5101;NetFunnel.gControl.result='5002:200:key=key-secret'; trailing();",
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
        ("NetFunnel.gControl.result='2002:5101:key=key-secret';", "5101"),
        # kTsErrorAComplete=502. We accept it for setComplete (5004) only, and
        # that acceptance is an INFERENCE rather than something the bundle
        # states -- _showResultSetComplete routes 502 to onError too, and we
        # take "already complete" as meaning our slot is not held. For a
        # chkEnter (5002/5101) parse it hits the switch default -> onError, so
        # it is NOT a success here either way (netfunnel.js:84 code table +
        # _showResultChkEnter default). See parse_set_complete_response.
        ("NetFunnel.gControl.result='5002:502:key=key-secret';", "502"),
        # kContinue=201 means keep-polling (onContinued). This parser is the
        # STRICT single-shot reading and does not model the loop, so 201 is a
        # documented non-success HERE; the client now goes through
        # parse_queue_response, which returns it as a wait (see
        # tests/test_netfunnel_queue.py).
        ("NetFunnel.gControl.result='5002:201:key=key-secret';", "201"),
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

    assert page_payload["dptRsStnCd1"] == "0551"
    assert page_payload["arvRsStnCdNm1"] == "부산"
    assert page_payload["stlbTrnClsfCd1"] == "17"
    assert page_payload["trnGpNm1"] == "SRT"
    # Single adult: one distinct type, so psgGridcnt coincides with the head count.
    assert page_payload["psgGridcnt"] == "1"
    assert ajax_payload["netfunnelKey"] == "NF"
    assert ajax_payload["psgNum"] == "1"
    assert ajax_payload["serverNonce"] == "nonce-1"

    # A group search requires totPrnb >= 10 (ara0101v.js:551-554) and sends
    # psgNum == totPrnb == total (ara1001l.js:104,165) -- never a clamped/bumped value.
    group_query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=10),
        train_group_code="300",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    group_hydrated = search_page_payload(group_query, "NF")
    group_payload = group_search_ajax_payload(
        group_query, "NF", hydrated_fields=group_hydrated
    )
    assert group_payload["psgNum"] == "10"
    assert group_payload["psgNum"] == group_hydrated["totPrnb"]
    assert group_payload["grpDv"] == "1"


def test_group_search_rejects_fewer_than_ten_passengers():
    # The app rejects a group search client-side when totPrnb < 10 (ara0101v.js:551-554)
    # rather than clamping psgNum; mirror that with a clear error.
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=1),
        train_group_code="300",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    hydrated = search_page_payload(query, "NF")
    with pytest.raises(ValueError, match="at least 10 passengers"):
        group_search_ajax_payload(query, "NF", hydrated_fields=hydrated)


def test_search_page_psg_gridcnt_counts_distinct_types_not_head_count():
    # psgGridcnt is the number of distinct passenger TYPES with count>0, not totPrnb
    # (ara0101v.js:826-836; srtgo len(combined_passengers)).
    two_adults = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=2),
        train_group_code="300",
    )
    payload = search_page_payload(two_adults, "NF")
    assert payload["totPrnb"] == "2"
    assert payload["psgGridcnt"] == "1"

    mixed = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=2, child=1, senior=1),
        train_group_code="300",
    )
    mixed_payload = search_page_payload(mixed, "NF")
    assert mixed_payload["totPrnb"] == "4"
    assert mixed_payload["psgGridcnt"] == "3"


def test_search_page_tot_prnb_equals_sum_of_psg_slots():
    # B2: the app guarantees totPrnb == sum(psgInfoPerPrnb1..5) via getPsgTotCnt()
    # (ara0101v.js:35). With the (protocol-less) infant field removed, every head-count
    # field must equal the sum of the five emitted psgInfoPerPrnb slots.
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(
            adult=1, child=2, senior=3, disability_1_to_3=4, disability_4_to_6=5
        ),
        train_group_code="300",
    )
    payload = search_page_payload(query, "NF")
    slot_sum = sum(int(payload[f"psgInfoPerPrnb{i}"]) for i in range(1, 6))
    assert int(payload["totPrnb"]) == slot_sum == 15
    assert payload["totPrnbNm"] == "15명"

    ajax = search_ajax_payload(query, "NF", hydrated_fields={})
    assert int(ajax["psgNum"]) == sum(
        int(ajax[f"psgInfoPerPrnb{i}"]) for i in range(1, 6)
    )


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
    # The app posts only these keys (ara0101v.js:158-165): no chk_rtrp/page/boolRtrp.
    assert station_selector_payload("수서", "부산", "0551", "0020") == {
        "reqCode": "1",
        "sDptStnNm": "수서",
        "sArvStnNm": "부산",
        "sDptStnCd": "0551",
        "sArvStnCd": "0020",
        "sNowSel": "1",
    }


def test_station_map_selector_payload_is_exact():
    assert station_map_selector_payload() == {
        "reqCode": "2",
        "sNowSel": "1",
    }


def test_date_selector_payload_is_exact():
    # The date picker returns a date only, so no selectTime (ara0101v.js:187-191).
    assert date_selector_payload("20260714") == {
        "reqCode": "3",
        "selectDay": "",
        "selectDt": "20260714",
    }


def test_passenger_selector_payload_uses_canonical_type_codes_and_server_typo():
    # Distinct counts per type so the code->slot mapping is unambiguous.
    # Canonical (commCode.js psgTpCd / ara0101v.js:213-238,795-804):
    #   passenger1=adult(1), passenger2=disability_1_to_3(2),
    #   passenger3=disability_4_to_6(3), passenger4=senior(4), passenger5=child(5).
    # No passenger6 slot (infant is not a picker type).
    passengers = PassengerCounts(
        adult=1,
        child=2,
        senior=3,
        disability_1_to_3=4,
        disability_4_to_6=5,
    )
    assert passenger_selector_payload(passengers) == {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": "1",
        "passenger2": "4",
        "passenger3": "5",
        "passenger4": "3",
        "passenger5": "2",
        "totalPessnger": "15",
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
        (date_selector_payload, ("2026-07-14",)),
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


def test_passenger_fields_compact_nonzero_types_and_preserve_nonempty_hydrated_code():
    # The app packs only count>0 types into contiguous psgTpCd slots in canonical psgTpCd
    # order (senior=code 4 before child=code 5), leaving the trailing slots empty over
    # exactly 5 slots, and sends no psgTpCd6 / infantCnt (ara0101v.js:808-836;
    # commCode.js psgTpCd 1..5). The live server DOES carry both -- see
    # payloads.PASSENGER_TYPE_CODES -- so what the last three assertions below pin
    # is this library's deliberate boundary, not the protocol's.
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        passengers=PassengerCounts(adult=0, child=1, senior=2),
    )
    payload = search_ajax_payload(
        query,
        "NF",
        hydrated_fields={"psgTpCd1": "hydrated-senior"},
    )
    # senior compacts to slot 1, child to slot 2; a non-empty hydrated code overrides the
    # computed type code at the filled slot.
    assert payload["psgTpCd1"] == "hydrated-senior"
    assert payload["psgInfoPerPrnb1"] == "2"
    assert payload["psgTpCd2"] == "5"
    assert payload["psgInfoPerPrnb2"] == "1"
    # Trailing slots are SENT empty (psgTpCd="" / psgInfoPerPrnb="0"), not omitted.
    assert payload["psgTpCd3"] == ""
    assert payload["psgInfoPerPrnb3"] == "0"
    assert payload["psgTpCd5"] == ""
    assert payload["psgInfoPerPrnb5"] == "0"
    # No infant / type-6 slot and no infantCnt are EMITTED. They exist on the live
    # server; this library does not send them, and that is what is pinned here.
    assert "psgTpCd6" not in payload
    assert "psgInfoPerPrnb6" not in payload
    assert "infantCnt" not in payload


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


def _search_response(msg_cd: str, str_result: str) -> dict:
    return {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": msg_cd,
                    "strResult": str_result,
                    "msgTxt": "",
                    "qryCnqeCnt": 1,
                    "fllwPgExt": "N",
                }
            ],
            "dsOutput1": [{"trnNo": "303", "stlbTrnClsfCd": "17"}],
        },
    }


def test_search_success_gated_on_str_result_not_exact_msg_cd():
    # B1: the app classifies purely on dsOutput0.strResult and never inspects msgCd
    # (ara1001l.js:206; srtgo srt.py:391-401). A non-FAIL response carrying any other
    # success/warning msgCd must still parse and keep its dsOutput1 rows — requiring the
    # exact "IRG000000" would discard them.
    result = parse_train_search_response(_search_response("IRG099999", "SUCC"))
    assert result.trains[0].train_no == "303"
    assert result.metadata is not None
    assert result.metadata.message_code == "IRG099999"  # kept as informational metadata

    # strResult == "FAIL" still fails, regardless of a success-looking msgCd.
    with pytest.raises(SrtAppError):
        parse_train_search_response(_search_response("IRG000000", "FAIL"))

    # The NET000001 NetFunnel-retry special-case is preserved.
    with pytest.raises(SrtNetFunnelError):
        parse_train_search_response(_search_response("NET000001", "FAIL"))


def _complete_seat_page_train() -> TrainSummary:
    # A genuine dsOutput1 row carries NO seatAttCd (the app/srtgo source it from the
    # request side), so the "complete" seat-page train deliberately omits seat_attr_code;
    # seat_page_payload must still build, defaulting seatAttCd to the request-side "015".
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
    )


def test_search_parser_preserves_seat_page_fields(load_json_fixture):
    train = parse_train_search_response(
        load_json_fixture("search_success.json")
    ).trains[0]

    assert train.departure_run_order == "000001"
    assert train.arrival_run_order == "000010"
    assert train.seat_attr_code == "015"


def test_search_parser_captures_train_class_code_when_present():
    # trnClsfCd (열차종별코드) is read from the dsOutput1 row by the app
    # (ara1001l.js:1184,1217); distinct from stlbTrnClsfCd/service_class_code.
    def _response(row: dict[str, str]) -> dict:
        return {
            "ErrorCode": "0",
            "ErrorMsg": "",
            "outDataSets": {
                "dsOutput0": [
                    {
                        "msgCd": "IRG000000",
                        "strResult": "SUCC",
                        "msgTxt": "",
                        "qryCnqeCnt": 1,
                        "fllwPgExt": "N",
                    }
                ],
                "dsOutput1": [row],
            },
        }

    with_code = parse_train_search_response(
        _response({"trnNo": "303", "stlbTrnClsfCd": "17", "trnClsfCd": "07"})
    ).trains[0]
    assert with_code.service_class_code == "17"
    assert with_code.train_class_code == "07"

    without_code = parse_train_search_response(
        _response({"trnNo": "303", "stlbTrnClsfCd": "17"})
    ).trains[0]
    assert without_code.train_class_code is None


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


def test_seat_page_payload_first_class_sends_psrmClCd_2():
    payload = seat_page_payload(_complete_seat_page_train(), "2")
    assert payload["psrmClCd"] == "2"
    # Everything else stays the fixed read-only contract.
    assert payload["trnGpCd"] == "300"
    # seat_count defaults to "1".
    assert payload["choiceSeatCount"] == "1"


def test_seat_page_payload_multi_seat_sends_requested_count():
    # choiceSeatCount is the total passenger count (totPrnb), not a fixed '1'.
    payload = seat_page_payload(_complete_seat_page_train(), "1", "3")
    assert payload["choiceSeatCount"] == "3"
    assert payload["trnGpCd"] == "300"


def test_seat_page_payload_sources_seat_att_cd_from_request_side_default():
    # seatAttCd is a REQUEST-SIDE constant (app: seatAttCd = lfn_getRsv("rqSeatAttCd1"),
    # seeded to "015"; ara1001l.js:1508 / ara0101v.js:132; srtgo srt.py:193). A genuine
    # search-response row omits seatAttCd, so the payload must still build and default the
    # field to "015" -- never require train.seat_attr_code.
    train = _complete_seat_page_train()
    assert train.seat_attr_code is None
    assert seat_page_payload(train)["seatAttCd"] == "015"


def test_seat_page_payload_accepts_caller_supplied_seat_att_cd():
    # A caller may pass the seat-attribute code they searched with (e.g. 021/028 wheelchair
    # per ara0101v.js:611,621); it is validated as a 3-digit code.
    payload = seat_page_payload(_complete_seat_page_train(), seat_attr_code="021")
    assert payload["seatAttCd"] == "021"


@pytest.mark.parametrize("seat_attr_code", ["", "15", "0155", "01a", "٠١٥"])
def test_seat_page_payload_rejects_malformed_seat_att_cd(seat_attr_code):
    with pytest.raises(ValueError, match="seat_attr_code"):
        seat_page_payload(_complete_seat_page_train(), seat_attr_code=seat_attr_code)


@pytest.mark.parametrize("seat_count", ["0", "", "1a", "-1", "٢", "01"])
def test_seat_page_payload_rejects_non_positive_seat_count(seat_count):
    with pytest.raises(ValueError, match="seat_count"):
        seat_page_payload(_complete_seat_page_train(), "1", seat_count)


@pytest.mark.parametrize("cabin_class", ["0", "3", "", "12", "١"])
def test_seat_page_payload_rejects_unknown_cabin_class(cabin_class):
    with pytest.raises(ValueError, match="cabin_class"):
        seat_page_payload(_complete_seat_page_train(), cabin_class)


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


def test_fare_payload_uses_canonical_passenger_slots_and_row_train_class():
    # Distinct counts so the slot<->type mapping is unambiguous. trnSort must be
    # the DISPLAY NAME getStlbTrnClsfCdNm(stlbTrnClsfCd) produces -- "SRT" for
    # 역무차종별코드 17 -- as the live search page's own fare and timetable call
    # sites do (captured 2026-07-26). It is NOT the raw code, and NOT trnClsfCd,
    # which no live search row carries at all.
    train = TrainSummary(
        train_no="303",
        service_class_code="17",
        train_class_code="07",
        run_date="20260710",
        departure_date="20260710",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    passengers = PassengerCounts(
        adult=1,
        child=2,
        senior=3,
        disability_1_to_3=4,
        disability_4_to_6=5,
    )
    timetable = timetable_payload(train)
    payload = fare_payload(train, passengers)
    assert timetable == {
        "stnCourseNm": "수서-부산",
        "trnSort": "SRT",
        "runDt": "20260710",
        "trnNo": "00303",
    }
    assert payload["trnSort"] == "SRT"
    # psgInfoPerPrnb1..5 are COMPACTED in canonical psgTpCd order (compaction at
    # ara0101v.js:824-836, unchanged). All five types are filled here, so the
    # compacted order is the full canonical order: adult(1), dis1-3(4),
    # dis4-6(5), senior(3), child(2).
    assert [payload[f"psgInfoPerPrnb{index}"] for index in range(1, 6)] == [
        "1",
        "4",
        "5",
        "3",
        "2",
    ]
    assert [payload[f"psgTpCd{index}"] for index in range(1, 6)] == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]
    # The live form carries a sixth, always-EMPTY slot -- and psgInfoPerPrnb6 is
    # "" rather than the "0" the other unfilled slots use, which is how the
    # search response's own commandMap echoed it back.
    assert payload["psgTpCd6"] == ""
    assert payload["psgInfoPerPrnb6"] == ""
    # passenger1..5 was our own invention; the live page contains no such field.
    assert not any(key.startswith("passenger") for key in payload)
    assert "infantCnt" not in payload
    assert payload["trnNo"] == "00303"
    assert payload["stnCourseNm"] == "수서-부산"
    assert payload["dptRsStnCd2"] == ""
    assert payload["arvRsStnCd2"] == ""
    assert payload["runDt2"] == ""
    assert payload["trnNo2"] == ""

    # Gap case that distinguishes COMPACTED from positional: 1 adult + 1 child. The app
    # compacts to psgInfoPerPrnb1=1, psgInfoPerPrnb2=1, psgInfoPerPrnb3..5=0 (child's count
    # moves up into the second contiguous slot), NOT positional slot 1 and slot 5.
    gap_payload = fare_payload(train, PassengerCounts(adult=1, child=1))
    assert [gap_payload[f"psgInfoPerPrnb{index}"] for index in range(1, 6)] == [
        "1",
        "1",
        "0",
        "0",
        "0",
    ]
    # ...and the type codes compact with them: adult stays "1", child's "5" moves
    # into slot 2, the rest empty.
    assert [gap_payload[f"psgTpCd{index}"] for index in range(1, 6)] == [
        "1",
        "5",
        "",
        "",
        "",
    ]
