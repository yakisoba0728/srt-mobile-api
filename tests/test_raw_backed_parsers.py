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
                    "qryCnqeCnt": str(len(rows or [])),
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
    page = parse_fare_page(load_text_fixture("fare.html"))

    assert len(page.items) == 12
    assert sum(item.amount is not None for item in page.items) == 9
    assert len(page.available_items) == 9
    assert page.items[0] == FareItem(
        label="Synthetic A1",
        amount=12340,
        raw_amount="12,340 won",
        available=True,
        status=None,
    )
    unavailable = next(item for item in page.items if item.label == "Synthetic A3")
    assert unavailable.amount is None
    assert unavailable.available is False
    assert unavailable.status == "Unavailable-A"
    assert unavailable.raw_amount == "Unavailable-A"


def test_search_parser_exposes_typed_metadata_and_optional_train_fields():
    row = {
        "trnNo": "811",
        "trnGpCd": "300",
        "stlbTrnClsfCd": "17",
        "runTm": "021500",
        "trnRunOrdr": "4",
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
    assert train.train_run_order == "4"
    assert train.departure_consist_order == "11"
    assert train.arrival_consist_order == "22"
    assert train.current_delay == "3"
    assert train.expected_delay == "5"
    assert train.general_seat_availability == "GENERAL-AVAILABLE"
    assert train.special_seat_availability == "SPECIAL-UNAVAILABLE"
    assert train.reservation_wait_availability == "WAIT-OPEN"
    assert train.standing_availability == "STANDING-CLOSED"
    assert train.received_amount == "12340"
    assert train.discount_rate == "7"


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("qryCnqeCnt", 1),
        ("qryCnqeCnt", "one"),
        ("fllwPgExt", True),
        ("fllwPgExt", "MAYBE"),
    ],
)
def test_search_parser_rejects_wrong_typed_metadata(field_name, bad_value):
    payload = _success_response()
    payload["outDataSets"]["dsOutput0"][0][field_name] = bad_value

    with pytest.raises(SrtProtocolError, match=field_name):
        parse_train_search_response(payload)


def test_search_parser_enriches_missing_station_names_from_request_context():
    row = {
        "trnNo": "811",
        "dptRsStnCd": "1001",
        "arvRsStnCd": "2002",
    }
    context = {
        "dptRsStnCdNm1": "Synthetic Departure",
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


def test_new_typed_models_are_exported_without_moving_legacy_positional_fields():
    assert srt_mobile_api.Notice is models.Notice
    assert srt_mobile_api.NoticeListResult is models.NoticeListResult
    assert srt_mobile_api.TrainSearchMetadata is models.TrainSearchMetadata
    assert (
        srt_mobile_api.SrtClient.get_notice_list.__annotations__["return"]
        == "NoticeListResult"
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
