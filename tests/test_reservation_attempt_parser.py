from copy import deepcopy
from dataclasses import FrozenInstanceError, is_dataclass
from unittest import mock

import pytest

import srt_mobile_api
from srt_mobile_api import parsers
from srt_mobile_api.errors import (
    SrtAppError,
    SrtProtocolError,
    SrtSessionExpiredError,
)
from srt_mobile_api.models import (
    ReservationAttemptResult,
    ReservationRecord,
    ReservationTrain,
    SrtReservationHold,
)
from srt_mobile_api.parsers import (
    parse_reservation_attempt_response,
    parse_reservation_hold_response,
)
from srt_mobile_api.redaction import redact_value


def test_parse_reservation_attempt_success_returns_typed_repr_safe_result(
    load_json_fixture,
):
    payload = load_json_fixture("reservation_attempt_success.json")

    result = parse_reservation_attempt_response(payload)

    assert isinstance(result, ReservationAttemptResult)
    assert is_dataclass(result)
    assert result.message_code == "SYNTHETIC-SUCCESS"
    assert result.status == "SUCC"
    assert result.message == "synthetic success"
    assert result.total_received_amount == "12000"
    assert result.temporary_job_sequence == "SYNTHETIC-JOB"
    assert result.reservation.pnr_number == "NOT-A-REAL-PNR"
    assert result.reservation.journey_list_key == "SYNTHETIC-JOURNEY-KEY"
    assert result.reservation.departure_station_code == "SYNTHETIC-DEPARTURE"
    assert result.reservation.arrival_station_code == "SYNTHETIC-ARRIVAL"
    assert result.reservation.train_number == "SYNTHETIC-TRAIN"
    assert result.train.seat_number == "SYNTHETIC-SEAT"
    assert result.train.car_number == "SYNTHETIC-CAR"
    assert result.command == {"syntheticControl": "SYNTHETIC-CONTROL"}
    assert result.raw is payload
    rendered = repr(result)
    assert "NOT-A-REAL-PNR" not in rendered
    assert "SYNTHETIC-JOURNEY-KEY" not in rendered
    assert "SYNTHETIC-LUMP" not in rendered
    assert "SYNTHETIC-SEAT" not in rendered
    assert "SYNTHETIC-CAR" not in rendered
    assert "SYNTHETIC-CONTROL" not in rendered
    redacted = redact_value(result)
    assert redacted["reservation"]["pnr_number"] == "[REDACTED]"
    assert redacted["reservation"]["journey_list_key"] == "[REDACTED]"
    assert (
        redacted["reservation"]["lump_settlement_target_number"]
        == "[REDACTED]"
    )
    assert redacted["temporary_job_sequence"] == "[REDACTED]"
    assert redacted["train"]["seat_number"] == "[REDACTED]"
    assert redacted["train"]["car_number"] == "[REDACTED]"
    assert redacted["train"]["raw"]["seatNo"] == "[REDACTED]"
    assert redacted["train"]["raw"]["scarNo"] == "[REDACTED]"
    assert redacted["command"] == "[REDACTED]"
    assert redacted["raw"]["commandMap"] == "[REDACTED]"
    assert (
        redacted["raw"]["reservListMap"][0]["JRNYLIST_KEY"]
        == "[REDACTED]"
    )
    assert (
        redacted["raw"]["resultMap"][0]["tmpJobSqno1"]
        == "[REDACTED]"
    )
    assert (
        redacted["raw"]["reservListMap"][0]["lumpStlTgtNo"]
        == "[REDACTED]"
    )
    with pytest.raises(FrozenInstanceError):
        result.status = "FAIL"


def test_parse_reservation_attempt_surfaces_passenger_count_failure(
    load_json_fixture,
):
    payload = load_json_fixture("reservation_attempt_passenger_failure.json")

    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.code == "WRP011002"
    assert exc_info.value.message == "synthetic passenger count error"
    assert exc_info.value.raw is payload


def test_parse_reservation_attempt_surfaces_observed_input_validation_failure():
    payload = {
        "resultMap": [
            {
                "strResult": "FAIL",
                "msgCd": "WRR000100",
                "msgTxt": "synthetic input validation error",
            }
        ]
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.code == "WRR000100"
    assert exc_info.value.raw is payload


def test_parse_reservation_attempt_maps_s111_to_session_expired(load_json_fixture):
    payload = load_json_fixture("reserve_s111_relogin.json")

    with pytest.raises(SrtSessionExpiredError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.raw is payload


def test_parse_reservation_attempt_s111_is_not_a_generic_app_error(load_json_fixture):
    payload = load_json_fixture("reserve_s111_relogin.json")

    with pytest.raises(SrtSessionExpiredError):
        parse_reservation_attempt_response(payload)

    assert not issubclass(SrtSessionExpiredError, SrtAppError)


def test_parse_reservation_attempt_accepts_empty_success_message(load_json_fixture):
    payload = load_json_fixture("reservation_attempt_success.json")
    payload["resultMap"][0]["msgTxt"] = ""

    result = parse_reservation_attempt_response(payload)

    assert result.message == ""


def test_parse_reservation_attempt_rejects_observed_wrapper_error():
    payload = {
        "ERROR_CODE": "-1",
        "ERROR_MSG": "synthetic reservation rejection",
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.code == "-1"
    assert exc_info.value.message == "synthetic reservation rejection"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ERROR_CODE": "-1"},
        {"ERROR_MSG": "synthetic reservation rejection"},
        {"ERROR_CODE": -1, "ERROR_MSG": "synthetic reservation rejection"},
        {"ERROR_CODE": "-1", "ERROR_MSG": None},
        {"resultMap": []},
        {"resultMap": [{}]},
        {"resultMap": ["not-an-object"]},
    ],
)
def test_parse_reservation_attempt_rejects_empty_partial_or_malformed_failures(payload):
    with pytest.raises(SrtProtocolError):
        parse_reservation_attempt_response(payload)


# --- a DECLARED failure is classified before any optional field is read -------
#
# The server's strResult is authoritative about the outcome. A FAIL that is also
# missing or malforming an optional field is still a FAIL, and must surface as
# the business/session error it is rather than as a protocol error — otherwise
# parse_reservation_hold_response's salvage branch (which catches exactly
# SrtProtocolError) manufactures a hold for a reservation that never existed.


@pytest.mark.parametrize(
    ("result_row", "expected_code"),
    [
        # msgTxt missing: previously a SrtProtocolError, which is the shape that
        # leaked into the salvage branch.
        ({"strResult": "FAIL", "msgCd": "WRP011002"}, "WRP011002"),
        # msgCd missing entirely.
        ({"strResult": "FAIL", "msgTxt": "synthetic no seat"}, ""),
        # msgCd present but not a string.
        ({"strResult": "FAIL", "msgCd": 100, "msgTxt": "synthetic no seat"}, ""),
        # Neither optional field present at all.
        ({"strResult": "FAIL"}, ""),
    ],
)
def test_parse_reservation_attempt_reports_a_malformed_fail_as_a_business_error(
    result_row,
    expected_code,
):
    payload = {"resultMap": [result_row]}

    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.code == expected_code
    assert exc_info.value.raw is payload


@pytest.mark.parametrize(
    "result_row",
    [
        {"strResult": "FAIL", "msgCd": "S111"},
        {"strResult": "FAIL", "msgCd": "S111", "msgTxt": 7},
    ],
)
def test_parse_reservation_attempt_reports_a_malformed_s111_as_a_session_expiry(
    result_row,
):
    payload = {"resultMap": [result_row]}

    with pytest.raises(SrtSessionExpiredError) as exc_info:
        parse_reservation_attempt_response(payload)

    assert exc_info.value.raw is payload


@pytest.mark.parametrize(
    "result_row",
    [
        {"strResult": "SUCC"},
        {"strResult": "SUCC", "msgCd": 7, "msgTxt": "synthetic"},
        {"strResult": "SUCC", "msgCd": "SYNTHETIC-SUCCESS", "msgTxt": 7},
        {"strResult": "SUCC", "msgCd": "", "msgTxt": "synthetic"},
    ],
)
def test_parse_reservation_attempt_still_rejects_a_malformed_success_row(result_row):
    # The mirror image: classifying the declared status first must NOT stop a
    # declared SUCCESS from being validated strictly. Only FAIL short-circuits.
    with pytest.raises(SrtProtocolError):
        parse_reservation_attempt_response({"resultMap": [result_row]})


@pytest.mark.parametrize(
    ("container_name", "replacement"),
    [
        ("resultMap", []),
        ("resultMap", {}),
        ("resultMap", [{}, {}]),
        ("reservListMap", []),
        ("reservListMap", {}),
        ("reservListMap", ["not-an-object"]),
        ("trainListMap", []),
        ("trainListMap", {}),
        ("trainListMap", ["not-an-object"]),
        ("commandMap", []),
        ("commandMap", {}),
        ("commandMap", [{}]),
    ],
)
def test_parse_reservation_attempt_rejects_malformed_success_containers(
    load_json_fixture,
    container_name,
    replacement,
):
    payload = load_json_fixture("reservation_attempt_success.json")
    payload[container_name] = replacement

    with pytest.raises(SrtProtocolError, match=container_name):
        parse_reservation_attempt_response(payload)


@pytest.mark.parametrize(
    "missing_container",
    ["reservListMap", "trainListMap", "commandMap"],
)
def test_parse_reservation_attempt_rejects_partial_success(
    load_json_fixture,
    missing_container,
):
    payload = load_json_fixture("reservation_attempt_success.json")
    del payload[missing_container]

    with pytest.raises(SrtProtocolError, match=missing_container):
        parse_reservation_attempt_response(payload)


@pytest.mark.parametrize(
    ("container_name", "field_name"),
    [
        ("resultMap", "totRcvdAmt"),
        ("resultMap", "tmpJobSqno1"),
        ("reservListMap", "pnrNo"),
        ("reservListMap", "JRNYLIST_KEY"),
        ("reservListMap", "trnNo"),
        ("trainListMap", "seatNo"),
        ("trainListMap", "scarNo"),
    ],
)
def test_parse_reservation_attempt_rejects_partial_success_rows(
    load_json_fixture,
    container_name,
    field_name,
):
    payload = load_json_fixture("reservation_attempt_success.json")
    del payload[container_name][0][field_name]

    with pytest.raises(SrtProtocolError, match=field_name):
        parse_reservation_attempt_response(payload)


def test_parse_reservation_attempt_rejects_non_string_success_field(
    load_json_fixture,
):
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    payload["reservListMap"][0]["pnrNo"] = 7

    with pytest.raises(SrtProtocolError, match="pnrNo"):
        parse_reservation_attempt_response(payload)


def test_reservation_attempt_model_is_exported():
    assert srt_mobile_api.ReservationAttemptResult is ReservationAttemptResult
    assert srt_mobile_api.ReservationRecord is ReservationRecord
    assert srt_mobile_api.ReservationTrain is ReservationTrain
    assert (
        srt_mobile_api.parse_reservation_attempt_response
        is parse_reservation_attempt_response
    )


# --- the hold parser must never lose a PNR to a strict-validation failure -----
#
# A live reserve can create a real hold on the server BEFORE we parse its
# response, so a strict-validation failure on an unrelated field would leave an
# uncancellable reservation on a real account. korail hit exactly this class of
# problem and answered it with a minimal-hold fallback
# (KorailClient._hold_from_reservation_response); this is the SRT equivalent.


def _hold_payload_missing(load_json_fixture, container_name, field_name):
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    del payload[container_name][0][field_name]
    return payload


@pytest.mark.parametrize(
    ("container_name", "field_name"),
    [
        ("resultMap", "totRcvdAmt"),
        ("resultMap", "tmpJobSqno1"),
        ("reservListMap", "arvDt"),
        ("reservListMap", "lumpStlTgtNo"),
        ("trainListMap", "seatNo"),
        ("trainListMap", "scarNo"),
    ],
)
def test_hold_parser_keeps_the_pnr_when_strict_parsing_fails(
    load_json_fixture,
    container_name,
    field_name,
):
    payload = _hold_payload_missing(load_json_fixture, container_name, field_name)

    # Strict parsing rejects the payload outright ...
    with pytest.raises(SrtProtocolError):
        parse_reservation_attempt_response(payload)

    # ... but the hold parser still returns the identity needed to cancel.
    hold = parse_reservation_hold_response(payload)

    assert isinstance(hold, SrtReservationHold)
    assert hold.pnr_no == "NOT-A-REAL-PNR"
    assert hold.raw is payload
    assert "NOT-A-REAL-PNR" not in repr(hold)


def test_hold_parser_fallback_tolerates_a_malformed_optional_field(
    load_json_fixture,
):
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    payload["reservListMap"][0]["JRNYLIST_KEY"] = 7
    payload["reservListMap"][0]["totSeatNum"] = None

    hold = parse_reservation_hold_response(payload)

    assert hold.pnr_no == "NOT-A-REAL-PNR"
    # A non-string optional value is dropped, not propagated and not fatal.
    assert hold.journey_list_key == ""
    assert hold.total_seat_count == ""


def test_hold_parser_fallback_strips_the_salvaged_pnr(load_json_fixture):
    # Harmless on the wire (the cancel builder strips too), but a caller reading
    # hold.pnr_no — to log it, or to hand it back later as a bare PNR string —
    # must get the identity itself, not padding around it.
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    del payload["trainListMap"][0]["seatNo"]
    payload["reservListMap"][0]["pnrNo"] = "  NOT-A-REAL-PNR\n"

    hold = parse_reservation_hold_response(payload)

    assert hold.pnr_no == "NOT-A-REAL-PNR"


def test_hold_parser_reraises_when_there_is_no_pnr_to_lose(load_json_fixture):
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    del payload["reservListMap"][0]["pnrNo"]

    # No PNR means no hold can be orphaned, so the strict error stands.
    with pytest.raises(SrtProtocolError, match="pnrNo"):
        parse_reservation_hold_response(payload)


@pytest.mark.parametrize("pnr", ["", "   ", 7, None])
def test_hold_parser_reraises_for_an_unusable_pnr(load_json_fixture, pnr):
    payload = deepcopy(load_json_fixture("reservation_attempt_success.json"))
    del payload["trainListMap"][0]["seatNo"]
    payload["reservListMap"][0]["pnrNo"] = pnr

    with pytest.raises(SrtProtocolError):
        parse_reservation_hold_response(payload)


def test_hold_parser_does_not_salvage_a_business_failure():
    # A FAIL envelope means no reservation was created, so there is nothing to
    # rescue: it must keep raising instead of manufacturing a hold.
    payload = {
        "resultMap": [
            {
                "strResult": "FAIL",
                "msgCd": "WRR000100",
                "msgTxt": "synthetic no seat",
            }
        ],
        "reservListMap": [{"pnrNo": "NOT-A-REAL-PNR"}],
    }

    with pytest.raises(SrtAppError):
        parse_reservation_hold_response(payload)


def test_hold_parser_does_not_salvage_a_session_expiry(load_json_fixture):
    payload = deepcopy(load_json_fixture("reserve_s111_relogin.json"))
    payload["reservListMap"] = [{"pnrNo": "NOT-A-REAL-PNR"}]

    with pytest.raises(SrtSessionExpiredError):
        parse_reservation_hold_response(payload)


# A FAIL that is ALSO slightly malformed used to be rescued: the strict
# msgCd/msgTxt reads ran BEFORE the status was classified, so the parser raised
# SrtProtocolError — the one exception the salvage branch catches — and a hold
# was manufactured for a reservation the server had just refused. Telling a
# caller a reservation exists when it does not is as damaging as losing one that
# does: they stop trying to recover. Each case asserts the REASON, not merely
# that something raised.


@pytest.mark.parametrize(
    "result_row",
    [
        # No msgCd at all.
        {"strResult": "FAIL", "msgTxt": "synthetic no seat"},
        # msgCd present but an int rather than a str.
        {"strResult": "FAIL", "msgCd": 100, "msgTxt": "synthetic no seat"},
        # No msgTxt.
        {"strResult": "FAIL", "msgCd": "WRR000100"},
        # Neither optional field.
        {"strResult": "FAIL"},
    ],
)
def test_hold_parser_does_not_salvage_a_malformed_business_failure(result_row):
    payload = {
        "resultMap": [result_row],
        "reservListMap": [{"pnrNo": "NOT-A-REAL-PNR"}],
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_hold_response(payload)

    assert exc_info.value.raw is payload


@pytest.mark.parametrize(
    "result_row",
    [
        {"strResult": "FAIL", "msgCd": "S111"},
        {"strResult": "FAIL", "msgCd": "S111", "msgTxt": 7},
    ],
)
def test_hold_parser_does_not_salvage_a_malformed_session_expiry(result_row):
    payload = {
        "resultMap": [result_row],
        "reservListMap": [{"pnrNo": "NOT-A-REAL-PNR"}],
    }

    with pytest.raises(SrtSessionExpiredError) as exc_info:
        parse_reservation_hold_response(payload)

    assert exc_info.value.raw is payload


def test_hold_parser_refuses_to_salvage_a_declared_failure_independently():
    # Defense in depth for the same guarantee. The salvage branch re-reads
    # strResult off the RAW payload, so even if the parser's ordering regressed
    # and a declared FAIL reached it as a protocol error again, no hold is
    # manufactured. Simulated by making the parser raise SrtProtocolError for a
    # payload that declares FAIL.
    payload = {
        "resultMap": [{"strResult": "FAIL", "msgCd": "WRR000100"}],
        "reservListMap": [{"pnrNo": "NOT-A-REAL-PNR"}],
    }

    def _regressed(_data):
        raise SrtProtocolError("synthetic ordering regression", raw=payload)

    with mock.patch.object(
        parsers, "parse_reservation_attempt_response", _regressed
    ):
        with pytest.raises(SrtProtocolError):
            parse_reservation_hold_response(payload)


def test_hold_parser_still_salvages_when_no_status_is_declared():
    # The mirror-image guard: a response with NO strResult is malformed, not a
    # declared failure, and a PNR in it is exactly what the salvage path exists
    # to keep.
    payload = {
        "resultMap": [{"msgCd": "SYNTHETIC", "msgTxt": "synthetic"}],
        "reservListMap": [{"pnrNo": "NOT-A-REAL-PNR"}],
    }

    hold = parse_reservation_hold_response(payload)

    assert hold.pnr_no == "NOT-A-REAL-PNR"


def test_hold_parser_still_returns_the_strict_hold_for_a_clean_response(
    load_json_fixture,
):
    payload = load_json_fixture("reservation_attempt_success.json")

    hold = parse_reservation_hold_response(payload)

    assert hold.pnr_no == "NOT-A-REAL-PNR"
    assert hold.journey_list_key == "SYNTHETIC-JOURNEY-KEY"
    assert hold.total_seat_count == "1"
    assert hold.raw is payload
