from dataclasses import fields

import pytest

import srt_mobile_api
from srt_mobile_api import models
from srt_mobile_api.errors import SrtAppError, SrtProtocolError
from srt_mobile_api.models import (
    FareItem,
    TrainSearchResult,
    TrainSummary,
)
from srt_mobile_api.parsers import (
    parse_fare_page,
    parse_notice_list_response,
    parse_timetable_page,
    parse_train_search_response,
)


def _success_response(
    *,
    wrapper: str = "mixed",
    rows: list[object] | None = None,
) -> dict[str, object]:
    wrapper_values = (
        {"ErrorCode": "0", "ErrorMsg": ""}
        if wrapper == "mixed"
        else {"ERROR_CODE": "0", "ERROR_MSG": ""}
    )
    return {
        **wrapper_values,
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": "IRG000000",
                    "strResult": "SUCC",
                    "msgTxt": "synthetic metadata message",
                    "qryCnqeCnt": len(rows or []),
                    "fllwPgExt": "N",
                }
            ],
            "dsOutput1": rows or [],
        },
    }


@pytest.mark.parametrize("wrapper", ["mixed", "upper"])
def test_search_parser_accepts_each_exact_observed_wrapper(wrapper):
    result = parse_train_search_response(
        _success_response(wrapper=wrapper, rows=[{"trnNo": "811"}])
    )

    assert result.trains[0].train_no == "811"


@pytest.mark.parametrize(
    "partial",
    [
        {},
        {"ErrorCode": "0"},
        {"ErrorMsg": ""},
        {"ERROR_CODE": "0"},
        {"ERROR_MSG": ""},
    ],
)
def test_search_parser_rejects_partial_wrapper_pairs(partial):
    payload = _success_response()
    payload.pop("ErrorCode")
    payload.pop("ErrorMsg")
    payload.update(partial)

    with pytest.raises(SrtProtocolError, match="wrapper"):
        parse_train_search_response(payload)


def test_search_parser_rejects_dual_wrapper_pairs_even_when_values_match():
    payload = _success_response()
    payload.update({"ERROR_CODE": "0", "ERROR_MSG": ""})

    with pytest.raises(SrtProtocolError, match="wrapper"):
        parse_train_search_response(payload)


@pytest.mark.parametrize("wrapper", ["mixed", "upper"])
@pytest.mark.parametrize("member", ["code", "message"])
@pytest.mark.parametrize("wrong_value", [None, 0, False, [], {}])
def test_search_parser_rejects_wrong_typed_wrapper_members(
    wrapper,
    member,
    wrong_value,
):
    payload = _success_response(wrapper=wrapper)
    keys = {
        ("mixed", "code"): "ErrorCode",
        ("mixed", "message"): "ErrorMsg",
        ("upper", "code"): "ERROR_CODE",
        ("upper", "message"): "ERROR_MSG",
    }
    payload[keys[(wrapper, member)]] = wrong_value

    with pytest.raises(SrtProtocolError, match="string"):
        parse_train_search_response(payload)


@pytest.mark.parametrize(
    ("wrapper", "code_key", "message_key"),
    [
        ("mixed", "ErrorCode", "ErrorMsg"),
        ("upper", "ERROR_CODE", "ERROR_MSG"),
    ],
)
def test_search_wrapper_app_error_wins_over_success_looking_datasets(
    wrapper,
    code_key,
    message_key,
):
    payload = _success_response(wrapper=wrapper, rows=[{"trnNo": "811"}])
    payload[code_key] = "SYNTHETIC_FAILURE"
    payload[message_key] = "synthetic wrapper detail"

    with pytest.raises(SrtAppError) as exc_info:
        parse_train_search_response(payload)

    assert exc_info.value.code == "SYNTHETIC_FAILURE"
    assert exc_info.value.raw is payload
    assert "trnNo" not in repr(exc_info.value)


def test_timetable_skips_leading_empty_cells_and_keeps_all_semantic_rows(
    load_text_fixture,
):
    page = parse_timetable_page(load_text_fixture("timetable.html"))

    assert len(page.rows) == 7
    assert [row.station_name for row in page.rows] == [
        "Synthetic Origin",
        "Synthetic Stop 1",
        "Synthetic Stop 2",
        "Synthetic Stop 3",
        "Synthetic Stop 4",
        "Synthetic Stop 5",
        "Synthetic Destination",
    ]
    assert page.rows[0].times == ("05:01",)
    assert page.rows[-1].times == ("07:31",)
    assert "Synthetic Origin 05:01" not in repr(page.rows[0])


def test_notice_parser_returns_typed_uppercase_contract(load_json_fixture):
    result = parse_notice_list_response(load_json_fixture("notice_list.json"))

    assert isinstance(result, models.NoticeListResult)
    assert result.notices == (
        models.Notice(
            is_main="N",
            page_id="SYNTHETIC_PAGE",
            body="synthetic body marker",
            post_no=42,
            create_date="20990102",
            is_notice="Y",
            subject="Synthetic subject",
            raw={
                "IS_MAIN": "N",
                "PAGE_ID": "SYNTHETIC_PAGE",
                "BODY": "synthetic body marker",
                "POST_NO": 42,
                "CREATE_DATE": "20990102",
                "IS_NOTICE": "Y",
                "SUBJ": "Synthetic subject",
            },
        ),
    )
    assert "synthetic body marker" not in repr(result.notices[0])
    assert "synthetic body marker" not in repr(result)


@pytest.mark.parametrize(
    "row",
    [
        "not-an-object",
        {},
        {
            "IS_MAIN": "N",
            "PAGE_ID": "SYNTHETIC_PAGE",
            "BODY": "body",
            "POST_NO": "42",
            "CREATE_DATE": "20990102",
            "IS_NOTICE": "Y",
            "SUBJ": "subject",
        },
        {
            "IS_MAIN": "N",
            "PAGE_ID": "SYNTHETIC_PAGE",
            "BODY": 42,
            "POST_NO": 42,
            "CREATE_DATE": "20990102",
            "IS_NOTICE": "Y",
            "SUBJ": "subject",
        },
    ],
)
def test_notice_parser_rejects_non_object_incomplete_and_wrong_typed_rows(row):
    with pytest.raises(SrtProtocolError, match="notice"):
        parse_notice_list_response({"noticeList": [row]})


def test_fare_parser_retains_numeric_and_unavailable_semantic_rows(
    load_text_fixture,
):
    """One leg's worth of rows, keeping the unavailable ones as semantic rows.

    The fixture carries two fare tables because the real page always does: it is
    laid out for a transfer itinerary. Only the first is the leg we requested --
    ``fare_payload`` hard-codes the second leg's fields empty -- so only its rows
    may be returned. See ``parse_fare_page`` for the live capture that made the
    difference matter: the real second table repeats the first table's LABELS
    with ``0원`` amounts, so reading both produced duplicate labels priced at
    zero.
    """
    page = parse_fare_page(load_text_fixture("fare.html"))

    assert len(page.items) == 5
    assert all(item.amount is not None for item in page.items)
    assert page.available_items == page.items
    assert len(page.semantic_items) == 6
    assert page.items[0] == FareItem(
        label="Synthetic A1",
        amount=12340,
        raw_amount="12,340원",
        available=True,
        status=None,
    )
    unavailable = next(
        item for item in page.semantic_items if item.label == "Synthetic A3"
    )
    assert unavailable.amount is None
    assert unavailable.available is False
    assert unavailable.status == "Unavailable-A"
    assert unavailable.raw_amount == "Unavailable-A"
    # Nothing from the second table survives, under either accessor.
    assert not [item for item in page.semantic_items if item.label.startswith("Synthetic B")]


def test_search_parser_exposes_typed_metadata_and_optional_train_fields():
    row = {
        "trnNo": "811",
        "trnGpCd": "300",
        "stlbTrnClsfCd": "17",
        "runTm": "021500",
        "trnOrdrNo": 4,
        "dptStnConsOrdr": "11",
        "arvStnConsOrdr": "22",
        "curDlayTm": "3",
        "expDlayTm": "5",
        "gnrmRsvPsbStr": "GENERAL-AVAILABLE",
        "sprmRsvPsbStr": "SPECIAL-UNAVAILABLE",
        "rsvWaitPsbCd": "WAIT-OPEN",
        "stmpRsvPsbFlgCd": "STANDING-CLOSED",
        "rcvdAmt": "12340",
        "trainDiscGenRt": "7",
    }

    result = parse_train_search_response(_success_response(rows=[row]))
    train = result.trains[0]

    assert isinstance(result.metadata, models.TrainSearchMetadata)
    assert result.metadata.message_code == "IRG000000"
    assert result.metadata.status == "SUCC"
    assert result.metadata.message == "synthetic metadata message"
    assert result.metadata.query_count == 1
    assert result.metadata.has_following_page is False
    assert "synthetic metadata message" not in repr(result.metadata)
    assert train.run_time == "021500"
    assert train.train_run_order == 4
    assert train.departure_consist_order == "11"
    assert train.arrival_consist_order == "22"
    assert train.current_delay == 3
    assert train.expected_delay == "5"
    assert train.general_seat_availability == "GENERAL-AVAILABLE"
    assert train.special_seat_availability == "SPECIAL-UNAVAILABLE"
    assert train.reservation_wait_availability == "WAIT-OPEN"
    assert train.standing_availability == "STANDING-CLOSED"
    assert train.received_amount == "12340"
    assert train.discount_rate == "7"


@pytest.mark.parametrize(
    ("fixture_name", "expected_keys", "expected_delay", "composition"),
    [
        (
            "search_personal_shape_success.json",
            {
                "arvDt", "arvRsStnCd", "arvStnConsOrdr", "arvStnRunOrdr",
                "arvTm", "chtnDvCd", "dlaySaleFlg", "doReserv", "dptDt",
                "dptRsStnCd", "dptStnConsOrdr", "dptStnRunOrdr", "dptTm",
                "etcRsvPsbCdNm", "expnDptDlayTnum", "fresOprCno",
                "fresRsvPsbCdNm", "gnrmRsvPsbCdNm", "gnrmRsvPsbColor",
                "gnrmRsvPsbImg", "gnrmRsvPsbStr", "ocurDlayTnum",
                "payTable", "rcvdAmt", "rcvdFare", "rsvWaitPsbCd",
                "rsvWaitPsbCdNm", "runDt", "runTm", "seatAttCd",
                "seatSelect", "sprmRsvPsbCdNm", "sprmRsvPsbColor",
                "sprmRsvPsbImg", "sprmRsvPsbStr", "stlbDturDvCd",
                "stlbTrnClsfCd", "stmpRsvPsbFlgCd", "stndRsvPsbCdNm",
                "timeTable", "trainDiscGenRt", "trnCpsCd1", "trnCpsCd2",
                "trnCpsCd3", "trnCpsCd4", "trnCpsCd5", "trnGpCd",
                "trnNo", "trnNstpLeadInfo", "trnOrdrNo", "ymsAplFlg",
            },
            "5",
            ("C1", "C2", "C3", "C4", "C5"),
        ),
        (
            "search_group_shape_success.json",
            {
                "arvDt", "arvRsStnCd", "arvStnConsOrdr", "arvStnRunOrdr",
                "arvTm", "chtnDvCd", "chtnTrnOrdrNo", "doReserv", "dptDt",
                "dptRsStnCd", "dptStnConsOrdr", "dptStnRunOrdr", "dptTm",
                "gnrmRsvPsbCdNm", "gnrmRsvPsbColor", "gnrmRsvPsbImg",
                "gnrmRsvPsbStr", "ocurDlayTnum", "payTable", "rcvdAmt",
                "rcvdFare", "runDt", "runTm", "seatAttCd", "seatSelect",
                "sprmRsvPsbCdNm", "sprmRsvPsbColor", "sprmRsvPsbImg",
                "sprmRsvPsbStr", "stlbCarTpCd", "stlbDturDvCd",
                "stlbTrnClsfCd", "timeTable", "trainDiscGenRt",
                "trnCpsCd1", "trnCpsCd2", "trnCpsCd3", "trnCpsCd4",
                "trnCpsCd5", "trnGpCd", "trnNo", "trnOrdrNo", "ymsAplFlg",
            },
            None,
            ("G1", "G2", "G3", "G4", "G5"),
        ),
    ],
)
def test_sanitized_search_shapes_cover_observed_keys_and_modeled_fields(
    load_json_fixture,
    fixture_name,
    expected_keys,
    expected_delay,
    composition,
):
    payload = load_json_fixture(fixture_name)
    row = payload["outDataSets"]["dsOutput1"][0]

    assert set(row) == expected_keys
    assert type(row["trnOrdrNo"]) is int
    assert type(row["ocurDlayTnum"]) is int
    if "fresRsvPsbCdNm" in row:
        assert row["fresRsvPsbCdNm"] is None

    train = parse_train_search_response(
        payload,
        request_context={
            "dptRsStnCd1": "1001",
            "dptRsStnCdNm1": "Synthetic Departure",
            "arvRsStnCd1": "2002",
            "arvRsStnCdNm1": "Synthetic Arrival",
        },
    ).trains[0]

    assert train.departure_station_name == "Synthetic Departure"
    assert train.arrival_station_name == "Synthetic Arrival"
    assert train.departure_run_order == "31"
    assert train.arrival_run_order == "32"
    assert train.departure_consist_order == "11"
    assert train.arrival_consist_order == "22"
    assert train.run_time == "030000"
    assert train.train_run_order in {4, 5}
    assert train.current_delay in {2, 3}
    assert train.expected_delay == expected_delay
    assert train.general_seat_availability == "synthetic-general-availability"
    assert train.special_seat_availability == "synthetic-special-availability"
    assert train.received_amount in {"12340", "23450"}
    assert train.received_fare in {"12000", "23000"}
    assert train.discount_rate in {"7", "8"}
    assert train.train_composition_codes == composition


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("ocurDlayTnum", True),
        ("rcvdFare", 1),
        ("trnCpsCd3", 3),
    ],
)
def test_sanitized_search_shape_rejects_wrong_typed_promoted_fields(
    load_json_fixture,
    field_name,
    bad_value,
):
    payload = load_json_fixture("search_personal_shape_success.json")
    payload["outDataSets"]["dsOutput1"][0][field_name] = bad_value

    with pytest.raises(SrtProtocolError, match=field_name):
        parse_train_search_response(payload)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("qryCnqeCnt", True),
        ("qryCnqeCnt", 1.0),
        ("qryCnqeCnt", -1),
        ("qryCnqeCnt", None),
        ("qryCnqeCnt", "one"),
        ("qryCnqeCnt", " 1"),
        ("qryCnqeCnt", "１"),
        ("fllwPgExt", True),
        ("fllwPgExt", "MAYBE"),
    ],
)
def test_search_parser_rejects_wrong_typed_metadata(field_name, bad_value):
    payload = _success_response()
    payload["outDataSets"]["dsOutput0"][0][field_name] = bad_value

    with pytest.raises(SrtProtocolError, match=field_name):
        parse_train_search_response(payload)


@pytest.mark.parametrize("query_count", [1, "1"])
def test_search_parser_accepts_observed_and_legacy_query_count_types(query_count):
    payload = _success_response(rows=[{"trnNo": "811"}])
    payload["outDataSets"]["dsOutput0"][0]["qryCnqeCnt"] = query_count

    assert parse_train_search_response(payload).metadata.query_count == 1


@pytest.mark.parametrize("train_order", [4, "4"])
def test_search_parser_normalizes_observed_and_legacy_train_order(train_order):
    payload = _success_response(
        rows=[{"trnNo": "811", "trnOrdrNo": train_order}]
    )

    assert parse_train_search_response(payload).trains[0].train_run_order == 4


@pytest.mark.parametrize(
    "bad_value",
    [True, 4.0, -1, " 4", "４", "four"],
)
def test_search_parser_rejects_invalid_train_order(bad_value):
    payload = _success_response(
        rows=[{"trnNo": "811", "trnOrdrNo": bad_value}]
    )

    with pytest.raises(SrtProtocolError, match="trnOrdrNo"):
        parse_train_search_response(payload)


def test_search_parser_reads_a_null_train_order_as_absent():
    """JSON null is this API's spelling of "no value", not a protocol error.

    ``None`` used to sit in the rejection list above. The live server refutes
    that: every dsOutput1 row it sent on 2026-07-26 carried
    ``"fresRsvPsbCdNm": null``, so null is ordinary in these rows -- and an
    optional field raising takes the WHOLE search down, not just the field.
    Every other malformed value still rejects.
    """
    payload = _success_response(
        rows=[{"trnNo": "811", "trnOrdrNo": None}]
    )

    train = parse_train_search_response(payload).trains[0]
    assert train.train_run_order is None
    assert train.train_no == "811"


@pytest.mark.parametrize("target", ["query_count", "train_order"])
def test_search_parser_wraps_oversized_decimal_conversion(target):
    payload = _success_response(rows=[{"trnNo": "811"}])
    oversized = "9" * 5000
    if target == "query_count":
        payload["outDataSets"]["dsOutput0"][0]["qryCnqeCnt"] = oversized
    else:
        payload["outDataSets"]["dsOutput1"][0]["trnOrdrNo"] = oversized

    with pytest.raises(SrtProtocolError):
        parse_train_search_response(payload)


def test_search_parser_enriches_missing_station_names_from_request_context():
    row = {
        "trnNo": "811",
        "dptRsStnCd": "1001",
        "arvRsStnCd": "2002",
    }
    context = {
        "dptRsStnCd1": "1001",
        "dptRsStnCdNm1": "Synthetic Departure",
        "arvRsStnCd1": "2002",
        "arvRsStnCdNm1": "Synthetic Arrival",
    }

    train = parse_train_search_response(
        _success_response(rows=[row]),
        request_context=context,
    ).trains[0]

    assert train.departure_station_name == "Synthetic Departure"
    assert train.arrival_station_name == "Synthetic Arrival"


@pytest.mark.parametrize(
    "context",
    [
        None,
        {},
        {"dptRsStnCdNm1": "  ", "arvRsStnCdNm1": ""},
        {"dptRsStnCdNm1": "1001", "arvRsStnCdNm1": "2002"},
        {
            "dptRsStnCd1": "9999",
            "dptRsStnCdNm1": "Wrong Departure",
            "arvRsStnCd1": "8888",
            "arvRsStnCdNm1": "Wrong Arrival",
        },
    ],
)
def test_search_parser_does_not_invent_station_names_from_absent_context(context):
    row = {
        "trnNo": "811",
        "dptRsStnCd": "1001",
        "arvRsStnCd": "2002",
    }

    train = parse_train_search_response(
        _success_response(rows=[row]),
        request_context=context,
    ).trains[0]

    assert train.departure_station_name is None
    assert train.arrival_station_name is None


def test_search_parser_requires_response_station_codes_for_context_enrichment():
    train = parse_train_search_response(
        _success_response(rows=[{"trnNo": "811"}]),
        request_context={
            "dptRsStnCd1": "1001",
            "dptRsStnCdNm1": "Synthetic Departure",
            "arvRsStnCd1": "2002",
            "arvRsStnCdNm1": "Synthetic Arrival",
        },
    ).trains[0]

    assert train.departure_station_name is None
    assert train.arrival_station_name is None


def test_search_parser_does_not_promote_trimmed_code_as_station_name():
    train = parse_train_search_response(
        _success_response(
            rows=[
                {
                    "trnNo": "811",
                    "dptRsStnCd": " 1001 ",
                    "arvRsStnCd": " 2002 ",
                }
            ]
        ),
        request_context={
            "dptRsStnCd1": "1001",
            "dptRsStnCdNm1": "1001",
            "arvRsStnCd1": "2002",
            "arvRsStnCdNm1": "2002",
        },
    ).trains[0]

    assert train.departure_station_name is None
    assert train.arrival_station_name is None


def test_new_typed_models_are_exported_without_moving_legacy_positional_fields():
    assert srt_mobile_api.Notice is models.Notice
    assert srt_mobile_api.NoticeListResult is models.NoticeListResult
    assert srt_mobile_api.TrainSearchMetadata is models.TrainSearchMetadata
    assert (
        srt_mobile_api.SrtClient.get_typed_notice_list.__annotations__["return"]
        == "NoticeListResult"
    )
    assert (
        srt_mobile_api.SrtClient.get_notice_list.__annotations__["return"]
        == "dict[str, Any]"
    )
    assert [field.name for field in fields(TrainSummary)][:16] == [
        "train_no",
        "train_group_code",
        "service_class_code",
        "run_date",
        "departure_date",
        "departure_time",
        "arrival_date",
        "arrival_time",
        "departure_station_code",
        "arrival_station_code",
        "raw",
        "departure_station_name",
        "arrival_station_name",
        "departure_run_order",
        "arrival_run_order",
        "seat_attr_code",
    ]
    assert [field.name for field in fields(TrainSearchResult)][:3] == [
        "trains",
        "result",
        "raw",
    ]
    assert [field.name for field in fields(FareItem)][:3] == [
        "label",
        "amount",
        "raw_amount",
    ]


# --------------------------------------------------------------------------
# The search row's numeric-identifier path. This is the OPPOSITE direction
# from the reservation-list padding bug: here a JSON number made the whole
# search raise rather than quietly corrupting a value, so it was safe. It
# stopped being safe the moment the reservation-list readers learned to take
# a number and these did not -- the obvious next edit is "make them match",
# and making them match WITHOUT padding is how 06:30 becomes "63000".
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "sent", "expected"),
    [
        ("dptTm", 63000, "063000"),
        ("arvTm", 82500, "082500"),
        ("dptDt", 20990102, "20990102"),
        ("arvDt", 20990102, "20990102"),
        ("runDt", 20990102, "20990102"),
        ("dptRsStnCd", 551, "0551"),
        ("arvRsStnCd", 20, "0020"),
        ("seatAttCd", 15, "015"),
        ("stlbTrnClsfCd", 0, "00"),
    ],
)
def test_a_numeric_search_row_identifier_keeps_its_width(key, sent, expected):
    from srt_mobile_api import parsers

    assert parsers._row_scalar(sent, key) == expected


def test_a_number_is_refused_on_a_key_with_no_registered_width():
    """Widening and padding are one decision, so they cannot be separated.

    A key can only accept a number by being given a width. That is what stops
    a future "make these readers match the reservation-list ones" edit from
    landing the relaxation without the repair.
    """
    from srt_mobile_api import parsers

    assert parsers._row_scalar(42, "gnrmRsvPsbStr") is None
    assert parsers._row_scalar(1, "rcvdFare") is None
    # bool is an int subclass; it is not a number SRT sends for these.
    assert parsers._row_scalar(True, "dptTm") is None


def test_trn_no_is_deliberately_not_width_registered():
    """It repairs itself, and padding it here would be wrong.

    SRT train numbers vary in width, so a registered width would CREATE the
    corruption this table repairs. payloads.py already zfill(5)s train_no on
    the way out, which is where the five-character form is actually required.
    """
    from srt_mobile_api import parsers

    assert "trnNo" not in parsers._ZERO_PADDED_SEARCH_ROW_COLUMNS


def test_every_width_registered_search_column_is_covered_by_a_test():
    """Guard the guard, the same way the reservation-list table is guarded."""
    from srt_mobile_api import parsers

    covered = {
        case[0]
        for case in test_a_numeric_search_row_identifier_keeps_its_width.pytestmark[
            0
        ].args[1]
    }

    assert covered == set(parsers._ZERO_PADDED_SEARCH_ROW_COLUMNS)
