"""Offline tests for the SRT unpaid-reservation cancel (예약취소) surface.

Everything here is offline: synthetic PNRs, synthetic envelopes, and an
``httpx.MockTransport`` recorder that proves how many requests were actually
issued (always zero). No real network, no real credentials, no real PNR.

**Provenance.** The cancel wire shape under test is srtgo-attested only and is
UNCONFIRMED against our v2.0.41 app: ``/ard/selectListArd02045_n.do`` has zero
hits across all 21,673 files of the offline evidence bundle
(``docs/analysis/cross-validation-2026-07-21.md``). These tests pin what we
implemented from srtgo's evidence; they cannot and do not prove the server
accepts it.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import httpx
import pytest

import srt_mobile_api
from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    SrtCancelResult,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtReservationHold,
    SrtSession,
)
from srt_mobile_api.errors import (
    SrtAppError,
    SrtAuthError,
    SrtProtocolError,
    SrtSessionExpiredError,
)
from srt_mobile_api.parsers import parse_unpaid_cancel_response
from srt_mobile_api.payloads import unpaid_reservation_cancel_payload
from srt_mobile_api.safety import (
    SRT_LIVE_MUTATION_CATEGORIES,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
    MutationRoute,
    assert_read_only_request,
)


CANCEL_ROUTE = "/ard/selectListArd02045_n.do"


FAKE_PNR = "SYNTHETIC_PNR_REFERENCE"


def _hold(pnr: str = FAKE_PNR, **overrides) -> SrtReservationHold:
    return SrtReservationHold(pnr_no=pnr, **overrides)


# --- the form is exactly srtgo's three fields --------------------------------


def test_cancel_form_matches_the_srtgo_cancel_wire():
    # Field-by-field reproduction of srtgo _cancel (srt.py:1138): pnrNo plus the
    # two constants. Nothing else is sent.
    assert unpaid_reservation_cancel_payload(_hold()) == {
        "pnrNo": FAKE_PNR,
        "jrnyCnt": "1",
        "rsvChgTno": "0",
    }


def test_cancel_form_accepts_a_bare_pnr_string():
    # A caller recovering from a partial failure may hold nothing but the PNR.
    # That path must produce the identical form, or the hold cannot be released.
    assert unpaid_reservation_cancel_payload(FAKE_PNR) == (
        unpaid_reservation_cancel_payload(_hold())
    )


def test_cancel_form_ignores_hold_fields_that_are_not_on_the_wire():
    # totSeatNum/JRNYLIST_KEY are carried by the hold but are NOT cancel fields.
    form = unpaid_reservation_cancel_payload(
        _hold(journey_list_key="SYNTHETIC-JOURNEY-KEY", total_seat_count="2")
    )

    assert set(form) == {"pnrNo", "jrnyCnt", "rsvChgTno"}
    # In particular the seat count must not leak into jrnyCnt: two seats on one
    # journey is still one journey.
    assert form["jrnyCnt"] == "1"


def test_cancel_form_strips_surrounding_pnr_whitespace():
    assert unpaid_reservation_cancel_payload(f"  {FAKE_PNR}\n")["pnrNo"] == FAKE_PNR


# --- jrnyCnt tolerance: the korail regression must not repeat ----------------


def test_cancel_form_accepts_a_zero_padded_journey_count():
    # THE korail REGRESSION (korail commit 3d7e8a5). There, a real live reserve
    # returned h_jrny_cnt="0001" while the cancel builder required exactly "1";
    # it refused, the auto-cancel never ran, and a genuine unpaid hold was left
    # dangling. Compare numerically so a zero-padded value is accepted, and send
    # the unpadded value srtgo attests.
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count="0001"
    )["jrnyCnt"] == "1"


@pytest.mark.parametrize(
    "journey_count", ["1", " 1 ", "0001", "\t000001\n", "01"]
)
def test_cancel_form_normalizes_every_single_journey_spelling(journey_count):
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count=journey_count
    )["jrnyCnt"] == "1"


def test_cancel_form_preserves_a_genuine_multi_journey_count_unpadded():
    assert unpaid_reservation_cancel_payload(
        _hold(), journey_count="0002"
    )["jrnyCnt"] == "2"


@pytest.mark.parametrize(
    "journey_count",
    ["", "   ", "x", "1x", "-1", "1.0", "١", None, 1, object()],
)
def test_cancel_form_never_refuses_over_a_journey_count_formatting_problem(
    journey_count,
):
    # A refused cancel form means an uncancellable hold, which is strictly worse
    # than sending the single-journey default srtgo attests works. So an
    # unusable journey count falls back to "1" instead of raising — for ANY
    # shape, including non-strings and non-ASCII digits.
    form = unpaid_reservation_cancel_payload(_hold(), journey_count=journey_count)

    assert form["jrnyCnt"] == "1"
    assert form["pnrNo"] == FAKE_PNR


@pytest.mark.parametrize(
    "journey_count",
    [
        # Past CPython's int/str conversion limit (4300 significant digits), on
        # which int() raises ValueError. "Never refuses" has to hold for inputs
        # no server would ever send too, or the promise is not a promise.
        "0" * 5000,
        "1" * 5000,
        "0" * 5000 + "1" * 5000,
        # ... and the padding-only variants must still de-pad, not blow up.
        "0" * 5000 + "2",
    ],
)
def test_cancel_form_never_raises_on_an_unconvertible_journey_count(journey_count):
    form = unpaid_reservation_cancel_payload(_hold(), journey_count=journey_count)

    assert form["pnrNo"] == FAKE_PNR
    # Either the de-padded value or the default, but never an exception and
    # never an absurd number of digits on the wire.
    assert form["jrnyCnt"] in {"1", "2"}


def test_cancel_form_default_journey_count_is_not_derived_from_the_hold():
    # The reserve response carries no journey count at all (reservListMap has
    # totSeatNum, a SEAT count), so SrtReservationHold has nothing to derive
    # from and the builder defaults instead. Two very different holds must
    # therefore produce the same jrnyCnt.
    sparse = unpaid_reservation_cancel_payload(_hold())
    rich = unpaid_reservation_cancel_payload(
        _hold(journey_list_key="K", total_seat_count="9")
    )

    assert sparse["jrnyCnt"] == rich["jrnyCnt"] == "1"


# --- the PNR, and only the PNR, is mandatory ---------------------------------


@pytest.mark.parametrize("pnr", ["", "   "])
def test_cancel_form_rejects_an_empty_pnr(pnr):
    # Not a formatting technicality: with no PNR there is nothing to cancel.
    with pytest.raises(ValueError, match="PNR"):
        unpaid_reservation_cancel_payload(pnr)
    with pytest.raises(ValueError, match="PNR"):
        unpaid_reservation_cancel_payload(_hold(pnr))


@pytest.mark.parametrize("reservation", [None, 7, b"pnr", {"pnrNo": FAKE_PNR}])
def test_cancel_form_rejects_a_foreign_reservation_type(reservation):
    with pytest.raises(ValueError):
        unpaid_reservation_cancel_payload(reservation)


@pytest.mark.parametrize("reservation", [7, _hold(7)])
def test_cancel_form_tells_an_int_caller_to_pass_the_pnr_as_a_string(reservation):
    # An int PNR stays refused — str(int(pnr)) would silently drop leading zeros
    # and cancel the wrong reservation, or none — but the refusal must say what
    # to do instead, because this is the one rejection a caller is likely to
    # read as pedantry and work around by hand.
    with pytest.raises(ValueError, match="not an int") as exc_info:
        unpaid_reservation_cancel_payload(reservation)

    assert "leading zeros" in str(exc_info.value)


# --- a subclass is still a hold, and still a PNR -----------------------------


class _AnnotatedHold(SrtReservationHold):
    """What a downstream caller's own hold type looks like."""


class _AnnotatedPnr(str):
    """What a downstream caller's own PNR type looks like."""


def test_cancel_form_accepts_a_hold_subclass():
    # Refusing a subclass over its exact type is precisely the formatting
    # technicality that leaves a real hold unreleasable.
    assert unpaid_reservation_cancel_payload(_AnnotatedHold(pnr_no=FAKE_PNR)) == (
        unpaid_reservation_cancel_payload(_hold())
    )


def test_cancel_form_accepts_a_str_subclass_pnr():
    assert unpaid_reservation_cancel_payload(_AnnotatedPnr(FAKE_PNR)) == (
        unpaid_reservation_cancel_payload(_hold())
    )


def test_cancel_accepts_a_hold_subclass_through_the_client():
    client, recorder = _client_with(_cancel_reply())

    preview = client.cancel(
        _AnnotatedHold(pnr_no=FAKE_PNR),
        consent=MutationConsent(allow_cancel=True),
    )

    assert preview.payload["jrnyCnt"] == "1"
    assert recorder.requests == []


# --- response parsing: SUCC and FAIL are both data, not exceptions -----------


def _envelope(status: str, **fields) -> dict:
    row = {"strResult": status}
    row.update(fields)
    return {"resultMap": [row]}


def test_cancel_parser_reads_a_success_envelope():
    payload = _envelope(
        "SUCC", msgCd="SYNTHETIC-CANCEL-OK", msgTxt="synthetic cancelled"
    )

    result = parse_unpaid_cancel_response(payload)

    assert isinstance(result, SrtCancelResult)
    assert result.succeeded is True
    assert result.status == "SUCC"
    assert result.message_code == "SYNTHETIC-CANCEL-OK"
    assert result.message == "synthetic cancelled"
    assert result.raw is payload


def test_cancel_parser_reports_a_failure_without_raising():
    # A FAIL must be readable as data: pushing "was my hold released?" into an
    # exception path is how holds get orphaned.
    payload = _envelope(
        "FAIL", msgCd="SYNTHETIC-CANCEL-FAIL", msgTxt="synthetic refusal"
    )

    result = parse_unpaid_cancel_response(payload)

    assert result.succeeded is False
    assert result.status == "FAIL"
    assert result.message_code == "SYNTHETIC-CANCEL-FAIL"
    assert result.message == "synthetic refusal"
    assert result.raw is payload


def test_cancel_parser_treats_only_succ_as_success():
    assert parse_unpaid_cancel_response(_envelope("succ")).succeeded is False


def test_cancel_parser_accepts_the_dsoutput0_envelope_spelling():
    # The exact container is unconfirmed for this route, so the shared
    # normalize_result_row handling (resultMap OR outDataSets.dsOutput0) is
    # reused rather than one layout being asserted.
    payload = {"outDataSets": {"dsOutput0": [{"strResult": "SUCC"}]}}

    assert parse_unpaid_cancel_response(payload).succeeded is True


def test_cancel_parser_treats_a_missing_message_code_as_informational():
    # srtgo gates a cancel purely on strResult and never reads msgCd; refusing a
    # response over a field nobody reads would hide a real cancellation outcome.
    result = parse_unpaid_cancel_response(_envelope("SUCC"))

    assert result.succeeded is True
    assert result.message_code == ""
    assert result.message == ""


def test_cancel_result_is_frozen_and_repr_safe():
    result = parse_unpaid_cancel_response(
        _envelope("SUCC", msgCd="OK", msgTxt="synthetic detail")
    )

    assert "synthetic detail" not in repr(result)
    assert "resultMap" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.status = "FAIL"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        "SUCC",
        None,
        {"resultMap": []},
        {"resultMap": [{}]},
        # A NON-EMPTY row with no strResult key at all. {"resultMap": [{}]}
        # above never reaches the status check (the empty-row guard fires
        # first), so without this case the parser could default a missing
        # status to "SUCC" and report a cancel that never happened. Whether a
        # hold was released is the one thing a caller must not be misled about.
        {"resultMap": [{"msgCd": "SYNTHETIC", "msgTxt": "synthetic"}]},
        {"outDataSets": {"dsOutput0": [{"msgCd": "SYNTHETIC"}]}},
        {"resultMap": [{"strResult": ""}]},
        {"resultMap": [{"strResult": 1}]},
        {"resultMap": [{"strResult": "SUCC", "msgCd": 7}]},
        {"resultMap": [{"strResult": "SUCC", "msgTxt": 7}]},
        {"ERROR_CODE": "0"},
    ],
)
def test_cancel_parser_rejects_a_malformed_envelope(payload):
    with pytest.raises(SrtProtocolError):
        parse_unpaid_cancel_response(payload)


def test_cancel_parser_surfaces_an_app_level_rejection():
    payload = {
        "ERROR_CODE": "SYNTHETIC-ERROR",
        "ERROR_MSG": "synthetic app rejection",
        "resultMap": [{"strResult": "SUCC"}],
    }

    with pytest.raises(SrtAppError) as exc_info:
        parse_unpaid_cancel_response(payload)

    assert exc_info.value.code == "SYNTHETIC-ERROR"
    assert exc_info.value.raw is payload


def test_cancel_model_and_parser_are_exported():
    assert srt_mobile_api.SrtCancelResult is SrtCancelResult
    assert (
        srt_mobile_api.parse_unpaid_cancel_response is parse_unpaid_cancel_response
    )


# --- SrtClient.cancel: consent gating, dry-run default, and the live gate -----


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


def _cancel_reply() -> dict[str, dict]:
    # The route answers 200 with a success envelope, so a leaked request would be
    # RECORDED (and caught by `requests == []`) rather than dying in transport.
    return {CANCEL_ROUTE: {"resultMap": [{"strResult": "SUCC"}]}}


def test_cancel_dry_run_previews_the_form_and_sends_nothing():
    client, recorder = _client_with(_cancel_reply())

    preview = client.cancel(_hold(), consent=MutationConsent(allow_cancel=True))

    assert isinstance(preview, MutationPreview)
    assert preview.category == "cancel"
    assert preview.method == "POST"
    assert preview.route == CANCEL_ROUTE
    # dry_run defaults to True on MutationConsent, so this IS the default path.
    assert MutationConsent().dry_run is True
    assert recorder.requests == []


def test_cancel_preview_redacts_the_reservation_identity():
    client, _recorder = _client_with(_cancel_reply())

    preview = client.cancel(_hold(), consent=MutationConsent(allow_cancel=True))

    assert preview.payload["pnrNo"] == "[REDACTED]"
    assert preview.payload["rsvChgTno"] == "[REDACTED]"
    assert preview.payload["jrnyCnt"] == "1"
    assert FAKE_PNR not in repr(preview)


def test_cancel_accepts_a_bare_pnr_and_a_hold_identically():
    client, recorder = _client_with(_cancel_reply())
    consent = MutationConsent(allow_cancel=True)

    from_hold = client.cancel(_hold(), consent=consent)
    from_pnr = client.cancel(FAKE_PNR, consent=consent)

    assert dict(from_pnr.payload) == dict(from_hold.payload)
    assert recorder.requests == []


def test_cancel_threads_a_journey_count_override_through_to_the_form():
    # The korail-lesson normalization is only worth having if it is reachable.
    # If live capture ever shows a multi-leg PNR needing jrnyCnt="2", a caller
    # must be able to say so HERE; hand-rolling payloads + post_mutation_form is
    # the path that orphans holds.
    client, recorder = _client_with(_cancel_reply())
    consent = MutationConsent(allow_cancel=True)

    preview = client.cancel(_hold(), consent=consent, journey_count="0002")

    assert preview.payload["jrnyCnt"] == "2"
    assert recorder.requests == []


def test_cancel_default_journey_count_is_unchanged():
    client, _recorder = _client_with(_cancel_reply())
    consent = MutationConsent(allow_cancel=True)

    implicit = client.cancel(_hold(), consent=consent)
    explicit = client.cancel(_hold(), consent=consent, journey_count=None)

    assert implicit.payload["jrnyCnt"] == explicit.payload["jrnyCnt"] == "1"


@pytest.mark.parametrize("journey_count", ["", "  ", "x", "-1", 2, object()])
def test_cancel_never_refuses_over_a_journey_count_from_the_client(journey_count):
    # The builder's "never refuses" guarantee must survive the client hop too.
    client, _recorder = _client_with(_cancel_reply())

    preview = client.cancel(
        _hold(),
        consent=MutationConsent(allow_cancel=True),
        journey_count=journey_count,
    )

    assert preview.payload["jrnyCnt"] == "1"


def test_cancel_live_path_carries_the_journey_count_override():
    client, recorder = _client_with(_cancel_reply())
    sent: dict = {}

    def _stub(path, data, *, consent, category, **kwargs):
        sent.update(data=dict(data))
        return {"resultMap": [{"strResult": "SUCC"}]}

    client.http.post_mutation_form = _stub  # type: ignore[method-assign]

    client.cancel(
        _hold(),
        consent=MutationConsent(allow_cancel=True, dry_run=False),
        journey_count="0002",
    )

    assert sent["data"]["jrnyCnt"] == "2"
    assert recorder.requests == []
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset()


def test_cancel_journey_count_is_keyword_only():
    client, _recorder = _client_with(_cancel_reply())

    with pytest.raises(TypeError):
        client.cancel(  # type: ignore[misc]
            _hold(), MutationConsent(allow_cancel=True), "2"
        )


@pytest.mark.parametrize(
    "consent",
    [
        None,
        MutationConsent(),
        MutationConsent(allow_reserve=True),
        MutationConsent(allow_payment=True, allow_refund=True),
        MutationConsent(allow_reserve=True, dry_run=False),
    ],
)
def test_cancel_denies_a_missing_or_wrong_category_consent(consent):
    client, recorder = _client_with(_cancel_reply())

    with pytest.raises(SrtMutationNotAllowedError):
        client.cancel(_hold(), consent=consent)

    assert recorder.requests == []


def test_cancel_requires_an_authenticated_session():
    client, recorder = _client_with(_cancel_reply())
    client.session.current = None

    with pytest.raises(SrtAuthError):
        client.cancel(_hold(), consent=MutationConsent(allow_cancel=True))

    assert recorder.requests == []


def test_cancel_consent_gate_runs_before_the_session_check():
    # Ordering: an unconsented call is denied even without a session, so a
    # caller can never learn anything by probing with the wrong consent.
    client, recorder = _client_with(_cancel_reply())
    client.session.current = None

    with pytest.raises(SrtMutationNotAllowedError):
        client.cancel(_hold(), consent=MutationConsent())

    assert recorder.requests == []


def test_cancel_live_send_is_refused_by_the_live_gate_with_zero_requests():
    # dry_run=False with full cancel consent reaches post_mutation_form, which
    # refuses because SRT_LIVE_MUTATION_CATEGORIES is empty. This is the
    # intended state: the wire shape has never been verified live.
    client, recorder = _client_with(_cancel_reply())

    with pytest.raises(SrtMutationNotAllowedError) as exc_info:
        client.cancel(
            _hold(), consent=MutationConsent(allow_cancel=True, dry_run=False)
        )

    assert "not live-enabled" in str(exc_info.value)
    assert recorder.requests == []


def test_cancel_live_send_is_refused_for_a_bare_pnr_too():
    client, recorder = _client_with(_cancel_reply())

    with pytest.raises(SrtMutationNotAllowedError):
        client.cancel(
            FAKE_PNR, consent=MutationConsent(allow_cancel=True, dry_run=False)
        )

    assert recorder.requests == []


def test_cancel_is_bound_to_the_cancel_route_and_category():
    assert SRT_MUTATION_ROUTE_CATEGORIES[CANCEL_ROUTE] == "cancel"
    assert (
        MutationRoute("POST", "app", CANCEL_ROUTE) in SRT_MUTATION_ROUTES
    )
    # And the route is NOT reachable through the read-only send path.
    request = httpx.Request("POST", f"{SrtConfig().base_url}{CANCEL_ROUTE}")
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(request, SrtConfig())


def test_cancel_cannot_be_transmitted_while_the_gate_is_closed():
    # The gate this whole surface depends on. If this fails, someone
    # live-enabled a category: verify the live round trip actually happened
    # before touching it.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset()


def test_cancel_live_path_wiring_parses_the_envelope_without_opening_the_gate():
    # The send path cannot be exercised for real (and must not be: the gate
    # stays closed), so stub the ONE call cancel makes and assert what it hands
    # over and what it does with the answer. This pins the route, category,
    # consent and form that a live send would carry, and that the response is
    # returned as a parsed SrtCancelResult rather than a raw dict.
    client, recorder = _client_with(_cancel_reply())
    consent = MutationConsent(allow_cancel=True, dry_run=False)
    sent: dict = {}

    def _stub(path, data, *, consent, category, **kwargs):
        sent.update(path=path, data=dict(data), consent=consent, category=category)
        return {"resultMap": [{"strResult": "SUCC", "msgCd": "SYNTHETIC-OK"}]}

    client.http.post_mutation_form = _stub  # type: ignore[method-assign]

    result = client.cancel(_hold(), consent=consent)

    assert isinstance(result, SrtCancelResult)
    assert result.succeeded is True
    assert result.message_code == "SYNTHETIC-OK"
    assert sent["path"] == CANCEL_ROUTE
    assert sent["category"] == "cancel"
    assert sent["consent"] is consent
    assert sent["data"] == {
        "pnrNo": FAKE_PNR,
        "jrnyCnt": "1",
        "rsvChgTno": "0",
    }
    # The real transport still saw nothing.
    assert recorder.requests == []
    # And the gate the stub bypassed is still shut.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset()


def test_cancel_live_path_returns_a_failure_envelope_as_data():
    client, _recorder = _client_with(_cancel_reply())

    client.http.post_mutation_form = lambda *a, **k: {  # type: ignore[method-assign]
        "resultMap": [{"strResult": "FAIL", "msgCd": "SYNTHETIC-NO", "msgTxt": "no"}]
    }

    result = client.cancel(
        FAKE_PNR, consent=MutationConsent(allow_cancel=True, dry_run=False)
    )

    assert result.succeeded is False
    assert result.message_code == "SYNTHETIC-NO"


def test_cancel_clears_the_session_when_the_send_reports_expiry():
    client, _recorder = _client_with(_cancel_reply())

    def _expire(*args, **kwargs):
        raise SrtSessionExpiredError("synthetic expiry")

    client.http.post_mutation_form = _expire  # type: ignore[method-assign]

    with pytest.raises(SrtSessionExpiredError):
        client.cancel(
            _hold(), consent=MutationConsent(allow_cancel=True, dry_run=False)
        )

    assert client.session.current is None
