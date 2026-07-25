"""Offline contract tests for the SRT mutation send gate.

These exercise ``reserve`` and the gated ``SrtHttpClient.post_mutation_form``
against an ``httpx.MockTransport`` that records requests and returns synthetic
envelopes. No real network, no real credentials, no real card.

The invariant under test has two halves, and both are enforced at the transport
layer rather than by the presence or absence of a client method:

* **payment and refund transmit nothing, ever.** ``post_mutation_form`` — the
  only method that can send a state-changing request — refuses every category
  outside ``safety.SRT_LIVE_MUTATION_CATEGORIES``, and the true send boundary
  (``_send_mutation_request``) re-asserts the same membership AND the
  route/category binding, so an enabled category cannot be aimed at the payment
  or refund path either. The tests below pin that refusal for both under a fully
  permissive consent (including one that drops ``fake_card_only``), pin it for
  direct calls to the send boundary in both forms, and confirm a recording
  transport saw ZERO requests each time.
* **reserve and cancel may transmit**, under an explicit per-category consent
  with ``dry_run=False``, so that the operator-run reserve->cancel round trip
  is possible. The tests pin that they now clear the live-enablement block and
  are stopped only by the route/category binding behind it.

A canary pins the enabled set to exactly ``{"reserve", "cancel"}``, so either
adding payment/refund or removing a half of the pair fails loudly. The gate
ordering ahead of everything (consent, then dry-run) and the reserve form's
wire fidelity to srtgo are pinned here too.
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
from srt_mobile_api.errors import SrtAppError, SrtAuthError, SrtSessionExpiredError
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


# --- the reserve form is the srtgo _reserve wire, plus the app's arvDt1 ------


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
    #
    # ONE deliberate addition to srtgo's field set: arvDt1. srtgo omits it (it
    # sends only arvTm1) purely because SRTTrain has no arrival date; OUR app
    # writes it, in the same block as the fields srtgo does send
    # (ara1001l.js:1464), and cross-validation-2026-07-21.md already recorded
    # that specific divergence. The value here is "" because this fixture train
    # carries no arrival_date, matching the app's own #rsvForm seed
    # (arvDt1=""); a train that has one sends it, pinned below.
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
        "arvDt1": "",
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


def test_reserve_form_sends_the_arrival_date_in_arv_dt1():
    # ara1001l.js:1464 `"arvDt1": item.arvDt` -- written in the same block as
    # dptDt1/dptTm1/arvTm1, all of which we already sent. This is the only
    # mutation route whose shape can be checked statically, so the omission is
    # closed rather than left unverified. arvDt1 sits between dptTm1 and arvTm1,
    # the app's own field position (:1462-1465).
    arriving = dataclasses.replace(_eligible_train(), arrival_date="20990102")

    form = personal_reservation_payload(
        arriving,
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )

    assert form["arvDt1"] == "20990102"
    assert list(form).index("arvDt1") == list(form).index("dptTm1") + 1
    assert list(form).index("arvTm1") == list(form).index("arvDt1") + 1


def test_reserve_form_sends_a_blank_arv_dt1_without_an_arrival_date():
    # Blank, not an error. The app's own #rsvForm seed ships arvDt1="" and the
    # server accepts a body without the key at all (srtgo's trimmed form is what
    # the 2026-07-25 live round trip sent), so a row that omits arvDt must still
    # produce a buildable reservation form.
    for missing in (None, ""):
        form = personal_reservation_payload(
            dataclasses.replace(_eligible_train(), arrival_date=missing),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
        )
        assert form["arvDt1"] == ""


def test_reserve_form_rejects_a_malformed_arrival_date():
    for bad in ("2099010", "20990102x", "abcdefgh"):
        with pytest.raises(ValueError):
            personal_reservation_payload(
                dataclasses.replace(_eligible_train(), arrival_date=bad),
                PassengerCounts(adult=1),
                netfunnel_key=SYNTHETIC_NF,
            )


def test_reserve_form_sends_the_operating_date_in_run_dt1():
    # The app writes runDt1 and dptDt1 from two DIFFERENT row fields in the same
    # block: ara1001l.js:1460 `"runDt1": item.runDt` (운행일자) and :1462
    # `"dptDt1": item.dptDt` (출발일자). srtgo could not distinguish them
    # (SRTTrain has no run date), so this builder used to send the departure date
    # for both. A past-midnight service is where that diverges: the train
    # operates on the 1st and boards on the 2nd.
    overnight = dataclasses.replace(
        _eligible_train(),
        run_date="20990101",
        departure_date="20990102",
    )

    form = personal_reservation_payload(
        overnight,
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )

    assert form["runDt1"] == "20990101"
    assert form["dptDt1"] == "20990102"


def test_reserve_form_falls_back_to_the_departure_date_without_a_run_date():
    # A row that omits runDt must still build a form -- refusing would mean a
    # reservation that cannot be made -- so the departure date is the fallback,
    # exactly as timetable_payload and fare_payload already do. This is also the
    # srtgo-equivalent case, and the reason the wire-fidelity test above is
    # unchanged: its fixture carries no run_date.
    no_run_date = dataclasses.replace(_eligible_train(), run_date=None)

    form = personal_reservation_payload(
        no_run_date,
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )

    assert form["runDt1"] == form["dptDt1"] == "20990101"

    blank_run_date = dataclasses.replace(_eligible_train(), run_date="")
    assert (
        personal_reservation_payload(
            blank_run_date, PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
        )["runDt1"]
        == "20990101"
    )


def test_reserve_form_rejects_a_malformed_run_date():
    # Present but not an 8-digit date is a parse problem, not a missing field:
    # do not silently substitute the departure date for it.
    for bad in ("2099010", "20990101x", "abcdefgh"):
        with pytest.raises(ValueError):
            personal_reservation_payload(
                dataclasses.replace(_eligible_train(), run_date=bad),
                PassengerCounts(adult=1),
                netfunnel_key=SYNTHETIC_NF,
            )


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


NETFUNNEL_PATH = "/ts.wseq"
ACQUIRED_NF = "ACQUIRED_NETFUNNEL_KEY"
NETFUNNEL_BODY = (
    "NetFunnel.gRtype=5101;"
    f"NetFunnel.gControl.result='5101:200:key={ACQUIRED_NF}&nwait=0&nnext=0';"
)


class _LiveRecorder:
    """Records requests, answering the act_10 GET and the reserve POST."""

    def __init__(self, reserve_reply: dict, *, reserve_status: int = 200) -> None:
        self.reserve_reply = reserve_reply
        self.reserve_status = reserve_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == NETFUNNEL_PATH:
            return httpx.Response(200, text=NETFUNNEL_BODY)
        if request.url.path == RESERVE_ROUTE:
            return httpx.Response(self.reserve_status, json=self.reserve_reply)
        raise AssertionError(f"unexpected request to {request.url.path}")

    @property
    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def reserve_form(self) -> dict[str, str]:
        posts = [r for r in self.requests if r.url.path == RESERVE_ROUTE]
        assert len(posts) == 1, f"expected exactly one reserve POST, got {len(posts)}"
        return dict(httpx.QueryParams(posts[0].content.decode()))


def _live_client(reserve_reply: dict, **kwargs) -> tuple[SrtClient, _LiveRecorder]:
    recorder = _LiveRecorder(reserve_reply, **kwargs)
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(recorder))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, recorder


def test_reserve_live_send_acquires_an_act10_key_and_returns_a_hold(
    load_json_fixture,
):
    # The whole point of opening the gate: a consented dry_run=False reserve now
    # transmits. It must acquire the act_10 key itself (the SAME key flow train
    # search uses -- srtgo srt.py:987 -- not act_19), put that key on the
    # reserve form, and hand back a hold carrying the PNR.
    reply = load_json_fixture("reservation_attempt_success.json")
    client, recorder = _live_client(reply)

    hold = client.reserve(_eligible_train(), consent=_live(allow_reserve=True))

    assert isinstance(hold, SrtReservationHold)
    assert hold.pnr_no == "NOT-A-REAL-PNR"
    # Key acquired first, then exactly one reserve POST. A reserve is never
    # retried: a retry could double-book.
    assert recorder.paths == [NETFUNNEL_PATH, RESERVE_ROUTE]
    netfunnel_request = recorder.requests[0]
    assert netfunnel_request.url.params["aid"] == "act_10"
    assert recorder.reserve_form()["netfunnelKey"] == ACQUIRED_NF
    assert recorder.reserve_form()["jobId"] == "1101"


def test_reserve_live_send_honours_a_caller_supplied_netfunnel_key(
    load_json_fixture,
):
    # A caller who already has a key (e.g. from the search that chose the train)
    # can pass it; the client must then NOT acquire a second one.
    client, recorder = _live_client(
        load_json_fixture("reservation_attempt_success.json")
    )

    hold = client.reserve(
        _eligible_train(),
        consent=_live(allow_reserve=True),
        netfunnel_key=SYNTHETIC_NF,
    )

    assert isinstance(hold, SrtReservationHold)
    assert recorder.paths == [RESERVE_ROUTE]
    assert recorder.reserve_form()["netfunnelKey"] == SYNTHETIC_NF


def test_reserve_live_send_salvages_a_cancelable_hold_from_a_malformed_reply(
    load_json_fixture,
):
    # THE safety property of this method. The server has created a real hold by
    # the time we parse. If strict parsing then trips over an unrelated
    # malformed field, raising would orphan that hold -- nobody would know the
    # PNR to cancel. A degraded hold must come back instead.
    reply = load_json_fixture("reservation_attempt_success.json")
    del reply["trainListMap"]  # unrelated to the PNR, fatal to strict parsing
    client, recorder = _live_client(reply)

    hold = client.reserve(_eligible_train(), consent=_live(allow_reserve=True))

    assert isinstance(hold, SrtReservationHold)
    # The identity that lets the caller release the hold survived.
    assert hold.pnr_no == "NOT-A-REAL-PNR"
    assert recorder.paths == [NETFUNNEL_PATH, RESERVE_ROUTE]


def test_reserve_live_send_does_not_invent_a_hold_from_a_declared_failure():
    # The mirror image, and equally important: telling a caller a reservation
    # exists when it does not makes them stop trying to recover. A declared FAIL
    # must raise, never salvage.
    client, _recorder = _live_client(
        {
            "resultMap": [
                {
                    "strResult": "FAIL",
                    "msgCd": "WRR000100",
                    "msgTxt": "synthetic no seat",
                    "pnrNo": "NOT-A-REAL-PNR",
                }
            ]
        }
    )

    with pytest.raises(SrtAppError):
        client.reserve(_eligible_train(), consent=_live(allow_reserve=True))


def test_reserve_live_send_clears_the_session_on_expiry_and_re_raises():
    # Matches every other authenticated call: an expired session is cleared
    # locally and the error propagates. S111 on a reserve means the reservation
    # was REJECTED, so there is no hold to lose here.
    client, _recorder = _live_client(
        {"resultMap": [{"strResult": "FAIL", "msgCd": "S111", "msgTxt": "relogin"}]}
    )

    with pytest.raises(SrtSessionExpiredError):
        client.reserve(_eligible_train(), consent=_live(allow_reserve=True))

    assert client.session.current is None


def test_reserve_live_send_requires_an_authenticated_session():
    client, recorder = _live_client({})
    client.session.current = None

    with pytest.raises(SrtAuthError):
        client.reserve(_eligible_train(), consent=_live(allow_reserve=True))

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


def test_live_mutation_categories_is_exactly_reserve_and_cancel_canary():
    # CANARY. SRT_LIVE_MUTATION_CATEGORIES is the single switch that decides
    # which state-changing requests may leave this library. It holds exactly the
    # reversible pair: reserve creates an unpaid hold, cancel releases one, and
    # neither is safe to enable without the other.
    #
    # If this test fails because payment or refund appeared, do NOT "fix" the
    # test. Neither has a client method, neither has a live-verified wire
    # format, and a payment transmits a PAN in the clear. If it fails because a
    # category was REMOVED, the round-trip verification script can no longer
    # run. Either way, confirm the intent and update the safety comment, README
    # and CHANGELOG in the same change.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset({"reserve", "cancel"})
    assert "payment" not in SRT_LIVE_MUTATION_CATEGORIES
    assert "refund" not in SRT_LIVE_MUTATION_CATEGORIES


REFUSED_CATEGORIES = ("payment", "refund")


@pytest.mark.parametrize("category", REFUSED_CATEGORIES)
def test_post_mutation_form_refuses_payment_and_refund_under_full_consent(category):
    # The core invariant for the two categories that stay shut: even a
    # hand-assembled low-level call with a consent that opts into everything
    # and sets dry_run=False cannot transmit. The absence of a client method is
    # NOT what holds the line here — post_mutation_form itself refuses.
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


@pytest.mark.parametrize("category", REFUSED_CATEGORIES)
def test_post_mutation_form_issues_zero_requests_when_refusing(category):
    # Same refusal, but the assertion of record is the transport's own view: the
    # mock transport must observe no request at all, including under a consent
    # that also drops the fake-card restriction (which for payment would
    # otherwise be the only remaining guard).
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
    # function that calls httpx.Client.send, so it re-checks membership instead
    # of trusting post_mutation_form. Called directly — i.e. bypassing every
    # gate above it — a non-enabled category still refuses before building or
    # sending anything.
    client, recorder = _client_with(_all_routes_reply())
    for category in REFUSED_CATEGORIES:
        with pytest.raises(SrtMutationNotAllowedError) as excinfo:
            client.http._send_mutation_request(
                ROUTE_BY_CATEGORY[category],
                category=category,
                data=_reserve_form(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert "not live-enabled" in str(excinfo.value)
    assert recorder.requests == []


@pytest.mark.parametrize("category", ("reserve", "cancel"))
@pytest.mark.parametrize("route_category", REFUSED_CATEGORIES)
def test_send_mutation_request_refuses_an_enabled_category_on_a_foreign_route(
    category, route_category
):
    # The half the membership check alone does NOT cover, and the case the test
    # above never exercised because it only ever passed refused categories: a
    # category that IS live-enabled, aimed at a route belonging to a different
    # category. Membership passes here by construction, so if the route/category
    # binding lived only in post_mutation_form a direct call would build and
    # send a POST to the payment or refund endpoint carrying whatever `data`
    # held — for a payment, a PAN in the clear. The send boundary must apply
    # assert_mutation_route_category itself.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http._send_mutation_request(
            ROUTE_BY_CATEGORY[route_category],
            category=category,
            data={"stlCrCrdNo1": "4111111111111111"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    assert "does not match route" in str(excinfo.value)
    assert recorder.requests == []


@pytest.mark.parametrize("category", ("reserve", "cancel"))
def test_send_mutation_request_refuses_an_unregistered_route(category):
    # The route allowlist half, likewise re-asserted at the send boundary: an
    # enabled category cannot be used to POST an endpoint that is not one of the
    # four registered mutation routes at all, including a read-only route.
    client, recorder = _client_with(_all_routes_reply())
    for path in (READ_ROUTE, "/ara/madeUpRoute.do"):
        with pytest.raises(SrtProtocolError) as excinfo:
            client.http._send_mutation_request(
                path,
                category=category,
                data=_reserve_form(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        assert "not allowed" in str(excinfo.value)
    assert recorder.requests == []


@pytest.mark.parametrize("category", ("reserve", "cancel"))
def test_send_mutation_request_transmits_its_own_category_route(category):
    # The positive control for the two tests above: the binding refuses foreign
    # routes without also blocking the pair the gate exists to allow. Called
    # directly with its OWN route, an enabled category still reaches the wire.
    client, recorder = _client_with(_all_routes_reply())
    response = client.http._send_mutation_request(
        ROUTE_BY_CATEGORY[category],
        category=category,
        data=_reserve_form(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    assert [request.url.path for request in recorder.requests] == [
        ROUTE_BY_CATEGORY[category]
    ]


@pytest.mark.parametrize("category", ("reserve", "cancel"))
def test_post_mutation_form_lets_the_enabled_pair_reach_the_later_gates(category):
    # The other half of the new invariant, and the reason the tests above had to
    # be narrowed rather than deleted: reserve and cancel are no longer stopped
    # at the live-enablement block. They now pass it and reach the route/
    # category binding gates below it, which is what makes the operator's live
    # round trip possible. Proven by sending to the WRONG route for the
    # category: the error must be the route-binding SrtProtocolError, not the
    # live-enablement refusal, and nothing may be transmitted.
    wrong_route = ROUTE_BY_CATEGORY["refund" if category == "reserve" else "payment"]
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http.post_mutation_form(
            wrong_route,
            _reserve_form(),
            consent=_fully_permissive(),
            category=category,
        )
    assert "does not match route" in str(excinfo.value)
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
    # A read route is refused even for a live-enabled category. reserve now
    # clears the live-enablement block, so this exercises assert_mutation_route
    # for real rather than being short-circuited ahead of it: the mutation send
    # path cannot be repurposed to reach a read endpoint.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtProtocolError):
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
    # With reserve live-enabled this is now the gate that actually stops the
    # call, so a reserve consent can never be redirected onto the cancel route.
    client, recorder = _client_with(_all_routes_reply())
    with pytest.raises(SrtProtocolError):
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
    # Defense-in-depth: a payment with fake_card_only disabled is refused. The
    # live-enablement block refuses it first (payment is deliberately NOT in the
    # enabled pair); the fake-card gate remains behind it as the second line for
    # the day a payment category is implemented and verified.
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
