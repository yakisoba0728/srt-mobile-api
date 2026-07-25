"""Offline contract tests for the SRT mutation send gate.

These exercise ``reserve`` and the gated ``SrtHttpClient.post_mutation_form``
against an ``httpx.MockTransport`` that records requests and returns synthetic
envelopes. No real network, no real credentials, no real card.

The invariant under test is the strong one: **this library transmits no SRT
mutation at all**, and that is enforced at the transport layer, not merely by
``SrtClient.reserve`` being preview-only. ``post_mutation_form`` — the only
method that could send a state-changing request — refuses every category
outside ``safety.SRT_LIVE_MUTATION_CATEGORIES``, which is empty; the true send
boundary (``_send_mutation_request``) re-asserts the same membership. The tests
below pin that refusal for all four categories under a fully permissive
consent, confirm a recording transport saw ZERO requests in each case, pin the
gate ordering ahead of it (consent, then dry-run), keep the route/category
tiering covered, and carry a canary that fails loudly if anyone live-enables a
category. The reserve form's wire fidelity to srtgo is pinned here too, so the
payload stays correct for the day a live path is verified.
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
from srt_mobile_api.safety import (
    SRT_LIVE_MUTATION_CATEGORIES,
    assert_mutation_route,
    assert_mutation_route_category,
)

RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
CANCEL_ROUTE = "/ard/selectListArd02045_n.do"
PAYMENT_ROUTE = "/ata/selectListAta09036_n.do"
REFUND_ROUTE = "/atc/selectListAtc02063_n.do"
READ_ROUTE = "/ara/selectListAra10007_n.do"

ROUTE_BY_CATEGORY = {
    "reserve": RESERVE_ROUTE,
    "cancel": CANCEL_ROUTE,
    "payment": PAYMENT_ROUTE,
    "refund": REFUND_ROUTE,
}

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


# --- post_mutation_form: the transport-layer "no mutation is transmitted" gate --


def _reserve_form() -> dict[str, str]:
    return personal_reservation_payload(
        _eligible_train(), PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )


def _all_routes_reply() -> dict[str, dict]:
    # Every mutation route answers 200, so a leak would be RECORDED (and caught
    # by the `requests == []` assertion) rather than blowing up in the transport.
    return {route: {"ok": True} for route in ROUTE_BY_CATEGORY.values()}


def _fully_permissive(*, fake_card_only: bool = True) -> MutationConsent:
    return MutationConsent(
        allow_reserve=True,
        allow_cancel=True,
        allow_payment=True,
        allow_refund=True,
        dry_run=False,
        fake_card_only=fake_card_only,
    )


def test_live_mutation_categories_is_empty_canary():
    # CANARY. SRT_LIVE_MUTATION_CATEGORIES is the single switch that decides
    # whether ANY state-changing request may leave this library. It must stay
    # empty until (a) a cancel method exists, so a created hold can be released,
    # and (b) the category's wire format has been verified against the live
    # server. If this test fails, someone enabled a category: do not "fix" the
    # test — confirm the live verification actually happened, and update the
    # safety docs, README and CHANGELOG in the same change.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset()


@pytest.mark.parametrize("category", sorted(ROUTE_BY_CATEGORY))
def test_post_mutation_form_refuses_every_category_under_full_consent(category):
    # The core invariant: even a hand-assembled low-level call with a consent
    # that opts into everything and sets dry_run=False cannot transmit. The
    # method-level hardening in SrtClient.reserve is NOT what holds the line
    # here — post_mutation_form itself refuses.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        client.http.post_mutation_form(
            ROUTE_BY_CATEGORY[category],
            _reserve_form(),
            consent=_fully_permissive(),
            category=category,
        )
    assert "not live-enabled" in str(excinfo.value)
    assert recorder.requests == []


@pytest.mark.parametrize("category", sorted(ROUTE_BY_CATEGORY))
def test_post_mutation_form_issues_zero_requests_when_refusing(category):
    # Same refusal, but the assertion of record is the transport's own view: the
    # mock transport must observe no request at all for any category, including
    # a consent that also drops the fake-card restriction.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            ROUTE_BY_CATEGORY[category],
            _reserve_form(),
            consent=_fully_permissive(fake_card_only=False),
            category=category,
        )
    assert recorder.requests == []


def test_send_mutation_request_asserts_live_enablement_itself():
    # Defense in depth at the TRUE send boundary: _send_mutation_request is the
    # function that calls httpx.Client.send, so it re-checks the invariant
    # instead of trusting post_mutation_form. Called directly with a
    # non-enabled category (i.e. all of them today) it refuses before building
    # or sending anything.
    client, recorder = _client_with(_all_routes_reply())
    for category, route in sorted(ROUTE_BY_CATEGORY.items()):
        with pytest.raises(SrtMutationNotAllowedError) as excinfo:
            client.http._send_mutation_request(
                route,
                category=category,
                data=_reserve_form(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert "not live-enabled" in str(excinfo.value)
    assert recorder.requests == []


# --- gate ordering ahead of the live-enablement block ------------------------


def test_post_mutation_form_refuses_a_missing_consent_first():
    # Ordering: require_mutation_consent runs before the live-enablement block,
    # so a missing/mismatched consent still reports the consent problem.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        client.http.post_mutation_form(
            RESERVE_ROUTE, _reserve_form(), consent=None, category="reserve"  # type: ignore[arg-type]
        )
    assert "requires an explicit MutationConsent" in str(excinfo.value)
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        client.http.post_mutation_form(
            RESERVE_ROUTE,
            _reserve_form(),
            consent=_live(allow_cancel=True),
            category="reserve",
        )
    assert "not permitted by the provided consent" in str(excinfo.value)
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        client.http.post_mutation_form(
            RESERVE_ROUTE,
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="checkin",
        )
    assert "unknown mutation category" in str(excinfo.value)
    assert recorder.requests == []


def test_post_mutation_form_refuses_a_dry_run_consent_before_live_check():
    # Ordering: the dry-run gate also runs before the live-enablement block, so
    # a preview consent keeps reporting the dry-run problem (a preview must
    # never be transmitted, independently of live enablement).
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        client.http.post_mutation_form(
            RESERVE_ROUTE,
            _reserve_form(),
            consent=MutationConsent(allow_reserve=True),  # dry_run defaults True
            category="reserve",
        )
    assert "requires consent.dry_run=False" in str(excinfo.value)
    assert recorder.requests == []


# --- route tiering stays enforced (now behind the live-enablement block) -----


def test_post_mutation_form_refuses_a_non_mutation_route():
    # A read route is refused. Today the live-enablement block fires first, so
    # the error is the live-enablement one; assert_mutation_route (which would
    # be the gate if a category were ever enabled) is pinned directly below.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            READ_ROUTE,
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="reserve",
        )
    assert recorder.requests == []
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("POST", READ_ROUTE)


def test_mutation_route_category_binding_rejects_a_mismatch():
    # A consent/category for one route cannot be used to POST another route.
    # Same structure: the live-enablement block refuses the call outright, and
    # the underlying category<->route binding is pinned directly.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            CANCEL_ROUTE,  # cancel route ...
            _reserve_form(),
            consent=_live(allow_reserve=True),
            category="reserve",  # ... but a reserve category
        )
    assert recorder.requests == []
    with pytest.raises(SrtProtocolError):
        assert_mutation_route_category(CANCEL_ROUTE, "reserve")
    assert_mutation_route_category(CANCEL_ROUTE, "cancel")


def test_post_mutation_form_refuses_real_card_payment_at_the_send_gate():
    # Defense-in-depth: a payment with fake_card_only disabled is refused. Today
    # the live-enablement block refuses it first (payment is not live-enabled at
    # all); the fake-card gate remains in place behind it as the second line for
    # the day a payment category is enabled.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtMutationNotAllowedError):
        client.http.post_mutation_form(
            PAYMENT_ROUTE,
            {"pnrNo": "SYNTHETIC"},
            consent=MutationConsent(
                allow_payment=True, dry_run=False, fake_card_only=False
            ),
            category="payment",
        )
    assert recorder.requests == []
