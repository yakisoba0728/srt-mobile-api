"""Offline contract tests for the SRT card payment (카드결제) surface.

Nothing here touches a network, a credential or a card. Every value is
obviously synthetic -- the PAN is sixteen zeros -- and no fixture may ever
acquire a real one.

WHAT IS AND IS NOT BEING PINNED. These tests pin that the form is BUILT the way
the reference implementation's live runs built it, that the odd
``outDataSets.dsOutput0`` envelope parses, and — since the 2026-07-26 live
verification opened the gate — that a payment is GATED AND ROUTED correctly on
its way to the wire.

The old central claim of this file was "a payment cannot be transmitted". That
claim is dead: one real charge against the real server answered ``SUCC`` /
``IRT000000`` (7,500 KRW, 수서 → 동탄, one adult), and a prior fake-card probe
answered ``FAIL`` / ``WRT100170``. The pins were not deleted with it — they were
moved onto the invariants that survive, each of which now matters MORE than it
did while the route was welded shut:

* consent gating: no consent, a default consent, another category's consent and
  ``dry_run=True`` all still refuse, and still issue zero requests;
* the card-kind claim: exactly one of ``fake_card_only`` /
  ``real_card_acknowledged``, neither and both refused;
* the route/category binding, in both directions;
* and ``safety.assert_no_card_secrets`` — card secret fields may travel ONLY as
  a payment, which is now the sole thing keeping a hand-built card form off a
  read route, off the reserve and cancel routes, and out of the private send
  boundary under a non-payment category.

What is still NOT pinned here is the server's acceptance of anything the live
run did not exercise: ``/ata/selectListAta09036_n.do`` is 0-hit across all
21,673 files of our v2.0.41 offline decompile, our own app pays through a
WebView page plus the TransKey keypad and RaonSecure FIDO instead, the two
reference libraries that document this form are one vendored source counted
twice, and the run covered one single-journey one-adult personal-card lump sum.
Group, multi-leg, corporate cards and instalments remain "we build what srtgo
builds".

Nothing here touches a network, a credential or a card: every send is against an
``httpx.MockTransport``.
"""

from __future__ import annotations

import dataclasses
from urllib.parse import parse_qsl

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    SrtAuthError,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtPaymentCard,
    SrtPaymentResult,
    SrtProtocolError,
    SrtReservationSummary,
    SrtSession,
)
from srt_mobile_api.parsers import parse_card_payment_response
from srt_mobile_api.payloads import card_payment_payload
from srt_mobile_api.safety import SRT_LIVE_MUTATION_CATEGORIES


PAYMENT_ROUTE = "/ata/selectListAta09036_n.do"

# Obviously-fake, non-chargeable placeholders. NEVER a real PAN.
FAKE_PAN = "0000000000000000"
FAKE_PIN_PREFIX = "00"
FAKE_BIRTHDATE = "000101"
FAKE_EXPIRY = "0101"
FAKE_MEMBERSHIP = "SYNTHETIC-MEMBERSHIP"
FAKE_PNR = "SYNTHETIC-PNR"
SETTLEMENT_DATE = "20990101"


def _card(**overrides) -> SrtPaymentCard:
    fields = {
        "card_number": FAKE_PAN,
        "card_password": FAKE_PIN_PREFIX,
        "card_validation_number": FAKE_BIRTHDATE,
        "card_expire_date": FAKE_EXPIRY,
    }
    fields.update(overrides)
    return SrtPaymentCard(**fields)


def _reservation(**overrides) -> SrtReservationSummary:
    # The subset of an atc14016 row this form draws on. Every one of these
    # names is srtgo-attested only: the single live probe of that read
    # (2026-07-26) saw an EMPTY account, so no populated row has ever been
    # observed by this repository.
    fields = {
        "pnr_no": FAKE_PNR,
        "received_amount": "36900",  # rcvdAmt, the collectable 수납금액
        "ticket_special_number": "2",  # tkSpecNum -> totPrnb
        "departure_time": "060000",
        "arrival_time": "083000",
    }
    fields.update(overrides)
    return SrtReservationSummary(**fields)


def _form(**kwargs) -> dict[str, str]:
    parameters = {
        "membership_number": FAKE_MEMBERSHIP,
        "settlement_date": SETTLEMENT_DATE,
    }
    parameters.update(kwargs)
    reservation = parameters.pop("reservation", None) or _reservation()
    card = parameters.pop("card", None) or _card()
    return card_payment_payload(reservation, card, **parameters)


class _Recorder:
    def __init__(self, reply: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.reply = {"ok": True} if reply is None else reply

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.reply)


def _client(reply: dict | None = None) -> tuple[SrtClient, _Recorder]:
    recorder = _Recorder(reply)
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(recorder))
    client.session.current = SrtSession(
        login_id="synthetic", user_map={"MB_CRD_NO": FAKE_MEMBERSHIP}
    )
    return client, recorder


# --- The wire contract --------------------------------------------------------


def test_payment_form_carries_exactly_the_documented_field_set():
    # All 31 fields, no more and no fewer. If this fails because a field was
    # added, the addition needs its own provenance -- there is no live capture
    # to check it against.
    assert set(_form()) == {
        "stlDmnDt",
        "mbCrdNo",
        "stlMnsSqno1",
        "ststlGridcnt",
        "totNewStlAmt",
        "athnDvCd1",
        "vanPwd1",
        "crdVlidTrm1",
        "stlMnsCd1",
        "rsvChgTno",
        "chgMcs",
        "ismtMnthNum1",
        "ctlDvCd",
        "cgPsId",
        "pnrNo",
        "totPrnb",
        "mnsStlAmt1",
        "crdInpWayCd1",
        "athnVal1",
        "stlCrCrdNo1",
        "jrnyCnt",
        "strJobId",
        "inrecmnsGridcnt",
        "dptTm",
        "arvTm",
        "dptStnConsOrdr2",
        "arvStnConsOrdr2",
        "trnGpCd",
        "pageNo",
        "rowCnt",
        "pageUrl",
    }


def test_payment_form_fixed_values_match_the_documented_constants():
    form = _form()
    assert form["stlMnsSqno1"] == "1"
    assert form["ststlGridcnt"] == "1"
    assert form["inrecmnsGridcnt"] == "1"
    assert form["stlMnsCd1"] == "02"  # 신용카드
    assert form["crdInpWayCd1"] == "@"  # 신용카드/OK포인트
    assert form["rsvChgTno"] == "0"
    assert form["chgMcs"] == "0"
    assert form["ctlDvCd"] == "3102"
    assert form["strJobId"] == "3102"
    assert form["cgPsId"] == "korail"
    assert form["jrnyCnt"] == "1"
    assert form["trnGpCd"] == "300"
    assert form["dptStnConsOrdr2"] == "000000"
    assert form["arvStnConsOrdr2"] == "000000"
    assert form["pageNo"] == "-"
    assert form["rowCnt"] == "-"
    assert form["pageUrl"] == ""


def test_payment_form_is_all_strings_on_the_wire():
    # Including ismtMnthNum1, which the reference implementation passes as a
    # bare int.
    assert all(type(value) is str for value in _form().values())


def test_payment_form_sources_identity_and_times_from_the_reservation():
    form = _form()
    assert form["pnrNo"] == FAKE_PNR
    assert form["dptTm"] == "060000"
    assert form["arvTm"] == "083000"
    assert form["mbCrdNo"] == FAKE_MEMBERSHIP
    assert form["stlDmnDt"] == SETTLEMENT_DATE


def test_payment_form_carries_the_card_fields():
    form = _form(card=_card(installment_months=3, card_type="S",
                            card_validation_number="0000000000"))
    assert form["stlCrCrdNo1"] == FAKE_PAN
    assert form["vanPwd1"] == FAKE_PIN_PREFIX
    assert form["crdVlidTrm1"] == FAKE_EXPIRY
    assert form["athnDvCd1"] == "S"
    assert form["athnVal1"] == "0000000000"
    assert form["ismtMnthNum1"] == "3"


# --- Amount fidelity ----------------------------------------------------------
#
# The korail lesson: it sent a DISPLAY total instead of the collectable amount,
# and the gap only appeared on a special-class ticket (h_tot_prc 59,800 vs
# h_tot_rcvd_amt 83,700).


def test_payment_amount_comes_from_the_collectable_received_amount():
    # rcvdAmt (수납금액, post-discount) feeds BOTH amount fields, because this
    # form expresses exactly one payment means.
    form = _form(reservation=_reservation(received_amount="83700"))
    assert form["totNewStlAmt"] == "83700"
    assert form["mnsStlAmt1"] == "83700"
    assert form["totNewStlAmt"] == form["mnsStlAmt1"]


def test_payment_amount_strips_the_servers_zero_padding():
    # The server sends this zero-padded. The two reference implementations
    # diverge -- ryanking13/SRT posts the padded string back, srtgo casts to int
    # and posts the bare digits -- and only srtgo's form is attested by the live
    # runs this route rests on. UNRESOLVED; this pins the choice, not the truth.
    form = _form(reservation=_reservation(received_amount="00000036900"))
    assert form["totNewStlAmt"] == "36900"
    assert form["mnsStlAmt1"] == "36900"


@pytest.mark.parametrize("amount", [None, "", "   ", "not-a-number", "0", "0000"])
def test_payment_refuses_an_unusable_amount_rather_than_defaulting(amount):
    # Refusing to build a payment means no payment, which is safe. This is the
    # opposite of the cancel builder, which never raises because a form it
    # cannot build is a hold it cannot release.
    with pytest.raises(ValueError):
        _form(reservation=_reservation(received_amount=amount))


def test_payment_amount_has_no_caller_override():
    # Deliberate: an override is the seam through which a display total gets
    # substituted for the collectable one. The only amount is rcvdAmt.
    import inspect

    assert "amount" not in inspect.signature(card_payment_payload).parameters


# --- Passenger count ----------------------------------------------------------


def test_payment_passenger_count_comes_from_the_ticket_special_number():
    assert _form(reservation=_reservation(ticket_special_number="0003"))["totPrnb"] == "3"


def test_payment_refuses_to_substitute_a_seat_number_for_a_passenger_count():
    # The reference implementation falls back to `int(seatNum)`; seat_number is
    # a seat IDENTIFIER, and substituting it here would mis-state how many
    # people are being settled for. The fallback is deliberately not copied.
    reservation = _reservation(ticket_special_number=None, seat_number="7A")
    with pytest.raises(ValueError) as excinfo:
        _form(reservation=reservation)
    assert "seat_number is a seat identifier" in str(excinfo.value)


def test_payment_passenger_count_accepts_an_explicit_override():
    assert _form(
        reservation=_reservation(ticket_special_number=None), passenger_count="4"
    )["totPrnb"] == "4"


# --- Required inputs ----------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"pnr_no": "   "},
        {"departure_time": None},
        {"arrival_time": "bad"},
    ],
)
def test_payment_refuses_an_incomplete_reservation(overrides):
    with pytest.raises(ValueError):
        _form(reservation=_reservation(**overrides))


def test_payment_refuses_a_missing_membership_number():
    with pytest.raises(ValueError):
        _form(membership_number="")


def test_payment_refuses_a_foreign_reservation_type():
    with pytest.raises(ValueError):
        card_payment_payload(
            "SYNTHETIC-PNR",  # type: ignore[arg-type]
            _card(),
            membership_number=FAKE_MEMBERSHIP,
            settlement_date=SETTLEMENT_DATE,
        )


# --- The card type ------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"card_type": "X"},
        {"installment_months": 1},
        {"installment_months": 13},
        {"installment_months": 25},
        {"card_number": "0000"},
        {"card_number": "0000-0000-0000-0000"},
        {"card_password": "0"},
        {"card_password": "0000"},
        {"card_expire_date": "011"},
        {"card_expire_date": "0113"},  # month 13
        {"card_validation_number": "00010"},  # not YYMMDD
    ],
)
def test_payment_card_refuses_a_malformed_field(overrides):
    with pytest.raises(ValueError):
        _card(**overrides)


def test_payment_card_corporate_requires_a_business_number():
    with pytest.raises(ValueError):
        _card(card_type="S")  # a YYMMDD birthdate is not a 사업자등록번호
    assert _card(card_type="S", card_validation_number="0000000000").card_type == "S"


@pytest.mark.parametrize("months", [0, 2, 12, 24])
def test_payment_card_accepts_the_documented_installment_terms(months):
    assert _card(installment_months=months).installment_months == months


def test_payment_card_hides_every_secret_from_repr():
    rendered = repr(_card())
    for secret in (FAKE_PAN, FAKE_PIN_PREFIX, FAKE_BIRTHDATE, FAKE_EXPIRY):
        assert secret not in rendered


# --- The response envelope ----------------------------------------------------
#
# THE ONE GENUINELY INTERESTING FACT about this route: unlike every other SRT
# mutation, success is read from outDataSets.dsOutput0[0], not resultMap.


def _payment_response(container: str, **row) -> dict:
    payload = {"strResult": "SUCC", "msgTxt": "정상발매처리,정상발권처리"}
    payload.update(row)
    if container == "outDataSets":
        return {"outDataSets": {"dsOutput0": [payload]}}
    return {"resultMap": [payload]}


def test_payment_reads_its_result_from_out_data_sets_not_result_map():
    result = parse_card_payment_response(_payment_response("outDataSets"))
    assert isinstance(result, SrtPaymentResult)
    assert result.status == "SUCC"
    assert result.succeeded is True
    assert result.failed is False
    assert result.message == "정상발매처리,정상발권처리"


def test_payment_envelope_differs_from_the_cancel_envelope():
    # Pinned side by side, because this asymmetry is the thing a future reader
    # will assume is a typo. The payment answers in outDataSets.dsOutput0; the
    # cancel and the reservation list answer in resultMap. normalize_result_row
    # already accepted both spellings, which is why supporting the difference
    # cost no third code path -- so a payment that answered in resultMap after
    # all still parses.
    from srt_mobile_api.parsers import parse_unpaid_cancel_response

    out_data_sets = _payment_response("outDataSets")
    result_map = _payment_response("resultMap")
    assert "resultMap" not in out_data_sets
    assert "outDataSets" not in result_map
    assert parse_card_payment_response(out_data_sets).status == "SUCC"
    assert parse_card_payment_response(result_map).status == "SUCC"
    assert parse_unpaid_cancel_response(result_map).status == "SUCC"


def test_payment_business_failure_is_returned_not_raised():
    # A caller asking "was my card charged?" must be able to read the answer
    # without exception handling.
    result = parse_card_payment_response(
        _payment_response("outDataSets", strResult="FAIL", msgTxt="한도초과")
    )
    assert result.succeeded is False
    assert result.failed is True
    assert result.message == "한도초과"


def test_payment_unknown_status_is_neither_success_nor_failure():
    # succeeded and failed are NOT complements, deliberately. For a payment both
    # mistakes are expensive, so an unrecognised status means "unknown, go and
    # check" rather than a guess in either direction.
    result = parse_card_payment_response(
        _payment_response("outDataSets", strResult="MAYBE")
    )
    assert result.succeeded is False
    assert result.failed is False


def test_payment_msg_cd_is_optional():
    # The documented dsOutput0 payload names only strResult and msgTxt.
    assert parse_card_payment_response(_payment_response("outDataSets")).message_code == ""
    assert (
        parse_card_payment_response(
            _payment_response("outDataSets", msgCd="IRZ000001")
        ).message_code
        == "IRZ000001"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"outDataSets": {"dsOutput0": []}},
        {"outDataSets": {"dsOutput0": [{"msgTxt": "no status"}]}},
        {"outDataSets": {"dsOutput0": [{"strResult": ""}]}},
        {"outDataSets": {"dsOutput0": [{"strResult": "SUCC", "msgTxt": 7}]}},
    ],
)
def test_payment_refuses_a_malformed_envelope(payload):
    with pytest.raises(SrtProtocolError):
        parse_card_payment_response(payload)


# --- Consent gating and the preview -------------------------------------------


@pytest.mark.parametrize(
    "consent",
    [None, MutationConsent(), MutationConsent(allow_reserve=True, allow_cancel=True)],
)
def test_pay_with_card_denies_a_consent_that_does_not_allow_payment(consent):
    client, recorder = _client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.pay_with_card(_reservation(), _card(), consent=consent)
    assert recorder.requests == []


def test_pay_with_card_requires_an_authenticated_session():
    client, _recorder = _client()
    client.session.current = None
    with pytest.raises(SrtAuthError):
        client.pay_with_card(
            _reservation(), _card(), consent=MutationConsent(allow_payment=True)
        )


def test_pay_with_card_requires_a_membership_number_from_the_session():
    # An empty MB_CRD_NO is how the app itself spells "not logged in", and the
    # caller is never asked to supply the number by hand.
    client, _recorder = _client()
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    with pytest.raises(SrtAuthError) as excinfo:
        client.pay_with_card(
            _reservation(), _card(), consent=MutationConsent(allow_payment=True)
        )
    assert "MB_CRD_NO" in str(excinfo.value)


def test_pay_with_card_threads_the_membership_number_from_the_session():
    client, _recorder = _client()
    preview = client.pay_with_card(
        _reservation(),
        _card(),
        consent=MutationConsent(allow_payment=True),
        settlement_date=SETTLEMENT_DATE,
    )
    # mbCrdNo is redacted in the preview, so the threading is verified by the
    # builder taking it and by the session exposing it.
    assert preview.payload["mbCrdNo"] == "[REDACTED]"
    assert client.session.current.membership_number == FAKE_MEMBERSHIP


def test_pay_with_card_dry_run_previews_without_sending():
    client, recorder = _client()
    preview = client.pay_with_card(
        _reservation(),
        _card(),
        consent=MutationConsent(allow_payment=True),
        settlement_date=SETTLEMENT_DATE,
    )
    assert isinstance(preview, MutationPreview)
    assert preview.category == "payment"
    assert preview.method == "POST"
    assert preview.route == PAYMENT_ROUTE
    assert preview.note == "dry-run: not sent"
    assert recorder.requests == []


def test_pay_with_card_preview_redacts_every_secret():
    client, _recorder = _client()
    preview = client.pay_with_card(
        _reservation(),
        _card(),
        consent=MutationConsent(allow_payment=True),
        settlement_date=SETTLEMENT_DATE,
    )
    for masked in (
        "stlCrCrdNo1",
        "vanPwd1",
        "crdVlidTrm1",
        "athnVal1",
        "athnDvCd1",
        "ismtMnthNum1",
        "crdInpWayCd1",
        "mbCrdNo",
        "pnrNo",
        "rsvChgTno",
    ):
        assert preview.payload[masked] == "[REDACTED]"
    rendered = repr(preview)
    for secret in (FAKE_PAN, FAKE_BIRTHDATE, FAKE_MEMBERSHIP, FAKE_PNR):
        assert secret not in rendered
    # The protocol constants and the amount stay legible, or a preview says
    # nothing at all.
    assert preview.payload["totNewStlAmt"] == "36900"
    assert preview.payload["stlMnsCd1"] == "02"


def test_pay_with_card_defaults_the_settlement_date_to_today():
    import time

    client, _recorder = _client()
    # Both bounds captured around the call, so a midnight rollover between them
    # widens the accepted set instead of failing the suite.
    before = time.strftime("%Y%m%d")
    preview = client.pay_with_card(
        _reservation(), _card(), consent=MutationConsent(allow_payment=True)
    )
    after = time.strftime("%Y%m%d")
    assert preview.payload["stlDmnDt"] in {before, after}


@pytest.mark.parametrize("settlement_date", ["", "   ", "2099", "not-a-date"])
def test_pay_with_card_refuses_an_explicit_but_unusable_settlement_date(settlement_date):
    # `is None`, not `or`: an explicitly supplied bad value must be REFUSED, not
    # silently replaced with today. Everywhere else on this path an unusable
    # input raises rather than being substituted, and a payment settled under a
    # date the caller did not choose is the same class of quiet wrongness.
    client, _recorder = _client()
    with pytest.raises(ValueError):
        client.pay_with_card(
            _reservation(),
            _card(),
            consent=MutationConsent(allow_payment=True),
            settlement_date=settlement_date,
        )


def test_payment_passenger_count_override_tolerates_surrounding_whitespace():
    # The explicit override used to be STRICTER than the inferred value: " 4 "
    # raised while a reservation carrying " 4 " did not.
    assert _form(passenger_count=" 4 ")["totPrnb"] == "4"
    assert _form(reservation=_reservation(ticket_special_number=" 2 "))["totPrnb"] == "2"


# --- THE KILL SWITCH ----------------------------------------------------------


def test_payment_is_live_enabled_alongside_the_other_three_canary():
    # CANARY, inverted rather than deleted on 2026-07-26. It used to pin
    # "payment is not in the set". The set now means "a live run answered this
    # category's wire format", and payment qualifies: SUCC / IRT000000 for a
    # real 7,500 KRW charge, after a fake-card probe drew FAIL / WRT100170.
    #
    # The exact contents are still pinned, so a FIFTH category cannot appear
    # quietly. If this fails because one did, do NOT fix the test — membership
    # is granted for having been answered by the real server, not for being
    # implemented, and for payment it also means a PAN travels in the clear.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset(
        {"reserve", "cancel", "payment", "refund"}
    )
    assert "payment" in SRT_LIVE_MUTATION_CATEGORIES


@pytest.mark.parametrize(
    ("fake_card_only", "real_card_acknowledged"),
    [
        (True, False),  # a consent claiming a non-chargeable test card
        (False, True),  # ... and one acknowledging a REAL, chargeable card
    ],
)
def test_a_fully_valid_payment_consent_puts_the_documented_form_on_the_wire(
    fake_card_only, real_card_acknowledged
):
    # WAS "a fully permissive payment consent still cannot transmit", which was
    # this file's central invariant until the live verification refuted it. The
    # pin moved to the question that replaced it: when every gate IS satisfied,
    # what exactly goes out?
    #
    # Answer, asserted on the recorded request rather than on the builder: one
    # POST, to the payment route and nothing else, form-encoded, carrying the
    # thirty-one fields card_payment_payload built — the PAN, the PIN prefix,
    # the expiry, the birthdate, the PNR, the amount and the membership number
    # among them, byte for byte. Both card-kind claims are exercised, since the
    # real-card acknowledgement is the most permissive consent this library can
    # express and must behave identically on the wire.
    #
    # The stubbed reply carries the code the LIVE server returned on 2026-07-26
    # (SUCC / IRT000000), so the round trip pinned here is the one that actually
    # happened rather than an invented envelope.
    client, recorder = _client(
        _payment_response("outDataSets", msgCd="IRT000000")
    )
    consent = MutationConsent(
        allow_reserve=True,
        allow_payment=True,
        allow_cancel=True,
        allow_refund=True,
        dry_run=False,
        fake_card_only=fake_card_only,
        real_card_acknowledged=real_card_acknowledged,
    )
    result = client.pay_with_card(
        _reservation(),
        _card(),
        consent=consent,
        settlement_date=SETTLEMENT_DATE,
    )
    assert isinstance(result, SrtPaymentResult)
    assert result.succeeded is True
    assert result.message_code == "IRT000000"
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == PAYMENT_ROUTE
    assert request.headers["Content-Type"].startswith(
        "application/x-www-form-urlencoded"
    )
    sent = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
    assert sent == _form()
    # Named explicitly, because these are the values a live send actually
    # charges on, and "sent == _form()" alone would keep passing if _form()
    # itself ever stopped carrying them.
    assert sent["stlCrCrdNo1"] == FAKE_PAN
    assert sent["vanPwd1"] == FAKE_PIN_PREFIX
    assert sent["crdVlidTrm1"] == FAKE_EXPIRY
    assert sent["athnVal1"] == FAKE_BIRTHDATE
    assert sent["pnrNo"] == FAKE_PNR
    assert sent["mbCrdNo"] == FAKE_MEMBERSHIP
    assert sent["stlDmnDt"] == SETTLEMENT_DATE
    assert sent["totNewStlAmt"] == "36900"


@pytest.mark.parametrize(
    ("fake_card_only", "real_card_acknowledged"),
    [(False, False), (True, True)],
)
def test_pay_with_card_refuses_an_unstated_or_contradictory_card_kind(
    fake_card_only, real_card_acknowledged
):
    # A transmit-path requirement, not a preview one: exactly one of the two
    # claims must hold. Neither and both are refused, and nothing is sent.
    # Since 2026-07-26 this is the last gate before a real charge — the
    # live-enablement block used to refuse every payment ahead of it — so the
    # XOR is what an ambiguous consent now runs into instead of a closed door.
    client, recorder = _client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.pay_with_card(
            _reservation(),
            _card(),
            consent=MutationConsent(
                allow_payment=True,
                dry_run=False,
                fake_card_only=fake_card_only,
                real_card_acknowledged=real_card_acknowledged,
            ),
            settlement_date=SETTLEMENT_DATE,
        )
    assert recorder.requests == []


def test_a_dry_run_preview_does_not_require_a_card_kind_claim():
    # The counterpart: a preview transmits nothing, so requiring the claim to
    # preview would buy no safety and just make previewing harder.
    client, recorder = _client()
    preview = client.pay_with_card(
        _reservation(),
        _card(),
        consent=MutationConsent(allow_payment=True, fake_card_only=False),
        settlement_date=SETTLEMENT_DATE,
    )
    assert isinstance(preview, MutationPreview)
    assert recorder.requests == []


@pytest.mark.parametrize(
    "foreign_route",
    [
        "/arc/selectListArc05013_n.do",  # reserve
        "/ard/selectListArd02045_n.do",  # cancel
        "/atc/selectListAtc02063_n.do",  # refund
    ],
)
def test_a_payment_consent_cannot_be_aimed_at_another_categorys_route(foreign_route):
    # The pin that used to read "the live-enablement gate refuses this first,
    # and the route binding would refuse it anyway". The first half is gone —
    # payment clears membership since 2026-07-26 — so the second half is now the
    # ONLY thing stopping a genuine payment consent from POSTing a card form to
    # the reserve, cancel or refund endpoint. It is asserted through the public
    # send path (so the real gate ordering is exercised) and directly on
    # assert_mutation_route_category (so the rule itself is pinned, not just its
    # current position in the chain).
    from srt_mobile_api.safety import assert_mutation_route_category

    client, recorder = _client()
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http.post_mutation_form(
            foreign_route,
            _form(),
            consent=MutationConsent(
                allow_payment=True, dry_run=False, fake_card_only=True
            ),
            category="payment",
        )
    assert "does not match route" in str(excinfo.value)
    assert recorder.requests == []

    with pytest.raises(SrtProtocolError):
        assert_mutation_route_category(foreign_route, "payment")
    assert_mutation_route_category(PAYMENT_ROUTE, "payment")


def test_the_payment_route_refuses_every_other_categorys_consent():
    # The same cross-check from the other side: the payment route is the one
    # route that may carry card secrets, so a consent for any OTHER category
    # must not be able to reach it.
    from srt_mobile_api.safety import assert_mutation_route_category

    for category in ("reserve", "cancel", "refund"):
        with pytest.raises(SrtProtocolError):
            assert_mutation_route_category(PAYMENT_ROUTE, category)


def test_the_payment_route_is_not_reachable_through_a_read():
    # assert_read_only_request refuses the payment route by allowlist, so the
    # read path cannot be used to smuggle one out.
    from srt_mobile_api.safety import assert_read_only_request

    request = httpx.Request(
        "POST", f"{SrtConfig().base_url}{PAYMENT_ROUTE}", data=_form()
    )
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(request, SrtConfig())


# --- A PAN may leave this process ONLY as a payment ---------------------------
#
# The route/category rules could not close one case: a caller hand-assembles a
# payment body and posts it to a DIFFERENT, permitted route. That is neither a
# category violation nor a route violation, so nothing else refuses it. These
# pin the guard stated on the DATA instead.
#
# THIS SECTION GOT MORE IMPORTANT ON 2026-07-26, NOT LESS. While payment was
# outside SRT_LIVE_MUTATION_CATEGORIES the practical consequence of these tests
# was already guaranteed by the membership gate — card secrets could not leave
# by ANY path, because no payment could leave at all. Now that payment is
# live-enabled, assert_no_card_secrets is the only thing left standing between a
# hand-built card form and the wire on every route that is not the payment
# route. Each test below is therefore load-bearing on its own, and none of them
# may be relaxed on the grounds that "some other gate catches it".


def test_card_secret_fields_are_the_four_wire_secrets():
    from srt_mobile_api.safety import CARD_SECRET_FIELDS

    assert CARD_SECRET_FIELDS == frozenset(
        {"stlCrCrdNo1", "vanPwd1", "crdVlidTrm1", "athnVal1"}
    )


def test_a_card_body_cannot_be_posted_to_the_live_enabled_reserve_route():
    # The exact hole: category="reserve" is valid, the reserve route is
    # live-enabled, and the consent is genuine -- only the BODY is a card form.
    client, recorder = _client()
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http.post_mutation_form(
            "/arc/selectListArc05013_n.do",
            _form(),
            consent=MutationConsent(allow_reserve=True, dry_run=False),
            category="reserve",
        )
    assert "card-secret fields" in str(excinfo.value)
    assert recorder.requests == []


def test_a_card_body_cannot_be_posted_to_the_cancel_route_either():
    client, recorder = _client()
    with pytest.raises(SrtProtocolError):
        client.http.post_mutation_form(
            "/ard/selectListArd02045_n.do",
            _form(),
            consent=MutationConsent(allow_cancel=True, dry_run=False),
            category="cancel",
        )
    assert recorder.requests == []


def test_a_card_body_cannot_be_posted_to_the_send_boundary_directly():
    client, recorder = _client()
    with pytest.raises(SrtProtocolError):
        client.http._send_mutation_request(
            "/arc/selectListArc05013_n.do",
            category="reserve",
            data=_form(),
            headers={},
        )
    assert recorder.requests == []


def test_a_card_body_cannot_travel_on_any_read_route():
    client, recorder = _client()
    with pytest.raises(SrtProtocolError):
        client.http.post_form("/main/noticeList.do", _form())
    assert recorder.requests == []


def test_a_card_field_cannot_travel_in_a_read_query_string():
    client, recorder = _client()
    with pytest.raises(SrtProtocolError):
        client.http.get_text("/main/main.do", params={"stlCrCrdNo1": FAKE_PAN})
    assert recorder.requests == []


@pytest.mark.parametrize(
    "field", ["stlCrCrdNo1", "vanPwd1", "crdVlidTrm1", "athnVal1"]
)
def test_each_card_secret_field_is_refused_individually(field):
    client, recorder = _client()
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http.post_form("/main/noticeList.do", {field: "0000"})
    assert field in str(excinfo.value)
    assert recorder.requests == []


def test_an_ordinary_read_body_is_unaffected_by_the_card_guard():
    # The guard must not become a general body allowlist; normal reads still go.
    client, recorder = _client()
    client.http.post_form("/main/noticeList.do", {"pageId": "MB0101000000"})
    assert len(recorder.requests) == 1


def test_payment_result_hides_the_raw_envelope_from_repr():
    result = dataclasses.replace(
        parse_card_payment_response(_payment_response("outDataSets")),
        message="정상발매처리",
    )
    assert "정상발매처리" not in repr(result)
