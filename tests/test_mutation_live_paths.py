"""Offline contract tests for the SRT reserve send path and the mutation gate.

These exercise ``reserve(dry_run=False)`` and the triple-gated
``SrtHttpClient.post_mutation_form`` against an ``httpx.MockTransport`` that
records requests and returns synthetic envelopes. No real network, no real
credentials, no real card. They prove a live reserve goes ONLY to the evidenced
reserve route, only with a non-dry-run consent that opts into "reserve", that
the reserve form matches the srtgo wire exactly, and that the read-only path
still refuses every mutation route.
"""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    PassengerCounts,
    SeatType,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtProtocolError,
    SrtReservationHold,
    SrtSession,
    TrainSummary,
)
from srt_mobile_api.errors import SrtAppError
from srt_mobile_api.payloads import personal_reservation_payload

RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
CANCEL_ROUTE = "/ard/selectListArd02045_n.do"
READ_ROUTE = "/ara/selectListAra10007_n.do"

SYNTHETIC_NF = "SYNTHETIC_NETFUNNEL_KEY"


def _eligible_train() -> TrainSummary:
    return TrainSummary(
        train_no="303",
        service_class_code="17",
        train_group_code="300",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="060000",
        arrival_time="083000",
        departure_station_name="수서",
        arrival_station_name="부산",
        departure_run_order="1",
        arrival_run_order="10",
        departure_consist_order="1",
        arrival_consist_order="2",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )


class _Recorder:
    """A MockTransport handler that records requests and replies by path."""

    def __init__(self, replies: dict[str, dict]) -> None:
        self.replies = replies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.replies.get(request.url.path)
        if reply is None:  # pragma: no cover - guards test wiring mistakes
            raise AssertionError(f"unexpected request to {request.url.path}")
        return httpx.Response(200, json=reply)


def _client_with(replies: dict[str, dict]) -> tuple[SrtClient, _Recorder]:
    recorder = _Recorder(replies)
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(recorder))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, recorder


def _live(**allow: bool) -> MutationConsent:
    return MutationConsent(dry_run=False, **allow)


# --- the reserve form matches the srtgo _reserve wire exactly ---------------


def test_reserve_form_matches_the_srtgo_personal_reserve_wire():
    form = personal_reservation_payload(
        _eligible_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )
    # Field-by-field reproduction of srtgo _reserve (srt.py:962-997) for a single
    # adult personal reservation with a general seat available and no window
    # preference. mblPhone is intentionally ABSENT (srtgo passes None, which
    # requests drops from the wire).
    assert form == {
        "jobId": "1101",
        "jrnyCnt": "1",
        "jrnyTpCd": "11",
        "jrnySqno1": "001",
        "stndFlg": "N",
        "trnGpCd1": "300",
        "trnGpCd": "109",
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": "17",
        "dptRsStnCd1": "0551",
        "dptRsStnCdNm1": "수서",
        "arvRsStnCd1": "0020",
        "arvRsStnCdNm1": "부산",
        "dptDt1": "20990101",
        "dptTm1": "060000",
        "arvTm1": "083000",
        "trnNo1": "00303",
        "runDt1": "20990101",
        "dptStnConsOrdr1": "1",
        "arvStnConsOrdr1": "2",
        "dptStnRunOrdr1": "1",
        "arvStnRunOrdr1": "10",
        "netfunnelKey": SYNTHETIC_NF,
        "reserveType": "11",
        "totPrnb": "1",
        "psgGridcnt": "1",
        "locSeatAttCd1": "000",
        "rqSeatAttCd1": "015",
        "dirSeatAttCd1": "009",
        "smkSeatAttCd1": "000",
        "etcSeatAttCd1": "000",
        "psrmClCd1": "1",
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": "1",
    }
    assert "mblPhone" not in form


def test_reserve_form_special_only_sets_first_class_cabin():
    form = personal_reservation_payload(
        _eligible_train(),
        PassengerCounts(adult=1),
        seat_type=SeatType.SPECIAL_ONLY,
        netfunnel_key=SYNTHETIC_NF,
    )
    assert form["psrmClCd1"] == "2"


def test_reserve_form_general_first_falls_back_to_special_when_general_sold_out():
    sold_out_general = dataclasses.replace(
        _eligible_train(),
        general_seat_availability="매진",
        special_seat_availability="예약가능",
    )
    form = personal_reservation_payload(
        sold_out_general,
        PassengerCounts(adult=1),
        seat_type=SeatType.GENERAL_FIRST,
        netfunnel_key=SYNTHETIC_NF,
    )
    # srtgo is_special_seat = not general_seat_available() -> True here.
    assert form["psrmClCd1"] == "2"


def test_reserve_form_window_seat_sets_location_code():
    form = personal_reservation_payload(
        _eligible_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        window_seat=True,
    )
    # srtgo WINDOW_SEAT[True] == "012".
    assert form["locSeatAttCd1"] == "012"


def test_reserve_form_compacts_multiple_passenger_types_in_canonical_order():
    form = personal_reservation_payload(
        _eligible_train(),
        PassengerCounts(adult=2, senior=1),
        netfunnel_key=SYNTHETIC_NF,
    )
    # Compacted, canonical psgTpCd order: adult (1) then senior (4).
    assert form["totPrnb"] == "3"
    assert form["psgGridcnt"] == "2"
    assert form["psgTpCd1"] == "1" and form["psgInfoPerPrnb1"] == "2"
    assert form["psgTpCd2"] == "4" and form["psgInfoPerPrnb2"] == "1"
    assert "psgTpCd3" not in form


# --- reserve(dry_run=False) live send (offline via MockTransport) -----------


def test_reserve_refuses_live_send_until_cancel_and_verification():
    # Live SRT reserve is deliberately disabled: there is no callable cancel to
    # release a created hold and the live wiring is unverified. Even with full
    # consent (dry_run=False + allow_reserve) reserve must refuse and send nothing.
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve(
            _eligible_train(),
            consent=_live(allow_reserve=True),
            netfunnel_key=SYNTHETIC_NF,
        )
    assert recorder.requests == []


def test_reserve_live_still_requires_matching_consent():
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    # dry_run=False but no allow_reserve: denied before any send.
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve(
            _eligible_train(),
            consent=_live(allow_cancel=True),
            netfunnel_key=SYNTHETIC_NF,
        )
    assert recorder.requests == []


def test_reservation_hold_parser_raises_app_error_on_fail_envelope():
    # The reserve-response parser (wired for the future live path) still surfaces
    # a FAIL envelope as SrtAppError, exercised directly since the live path is
    # not callable yet.
    from srt_mobile_api import parse_reservation_hold_response

    with pytest.raises(SrtAppError):
        parse_reservation_hold_response(
            {
                "resultMap": [
                    {
                        "strResult": "FAIL",
                        "msgCd": "WRR000100",
                        "msgTxt": "synthetic no seat",
                    }
                ]
            }
        )


# --- reserve dry-run sends nothing even with a recording transport ----------


def test_reserve_dry_run_sends_nothing_to_a_recording_transport():
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    preview = client.reserve(
        _eligible_train(), consent=MutationConsent(allow_reserve=True)
    )
    assert isinstance(preview, MutationPreview)
    assert recorder.requests == []


# --- post_mutation_form triple-gate -----------------------------------------


def _reserve_form() -> dict[str, str]:
    return personal_reservation_payload(
        _eligible_train(), PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )


def test_post_mutation_form_refuses_a_dry_run_consent():
    # The send boundary itself refuses to transmit a dry-run consent, so a
    # preview can never reach the network even via the low-level send path.
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            RESERVE_ROUTE,
            _reserve_form(),
            consent=MutationConsent(allow_reserve=True),  # dry_run defaults True
            category="reserve",
        )
    assert recorder.requests == []


def test_post_mutation_form_refuses_a_non_mutation_route():
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    # A read route (or any non-mutation route) is rejected by assert_mutation_route.
    with pytest.raises(SrtProtocolError):
        client.http.post_mutation_form(
            READ_ROUTE,
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="reserve",
        )
    assert recorder.requests == []


def test_post_mutation_form_refuses_none_and_unknown_category():
    client, recorder = _client_with({RESERVE_ROUTE: {}})
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            RESERVE_ROUTE, _reserve_form(), consent=None, category="reserve"  # type: ignore[arg-type]
        )
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            RESERVE_ROUTE,
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="checkin",
        )
    assert recorder.requests == []


def test_post_mutation_form_rejects_category_route_mismatch():
    # A consent/category for one route cannot be used to POST another route.
    client, recorder = _client_with({CANCEL_ROUTE: {}})
    with pytest.raises(SrtProtocolError):
        client.http.post_mutation_form(
            CANCEL_ROUTE,  # cancel route ...
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="reserve",  # ... but a reserve category
        )
    assert recorder.requests == []


def test_post_mutation_form_refuses_real_card_payment_at_the_send_gate():
    # Defense-in-depth: even a hand-assembled low-level call cannot transmit a
    # payment with fake_card_only disabled. The transport gate itself refuses.
    client, recorder = _client_with({})
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            "/ata/selectListAta09036_n.do",
            {"pnrNo": "SYNTHETIC"},
            consent=MutationConsent(
                allow_payment=True, dry_run=False, fake_card_only=False
            ),
            category="payment",
        )
    assert recorder.requests == []
