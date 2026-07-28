"""Offline tests for the SRT mutation safety-model foundation.

These cover the consent gate, the safe-by-default consent/preview types, the
payload redaction guarantee, and the route tiering. Only ``reserve`` is a
callable method (dry-run by default); cancel/payment/refund are tiered routes
only. No real network, no real credentials, no real card.
"""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    PassengerCounts,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtSession,
    TrainSummary,
    require_mutation_consent,
)
from srt_mobile_api.consent import require_card_kind_claim
from srt_mobile_api.errors import SrtApiError, SrtAuthError
from srt_mobile_api.redaction import redact_payload
from srt_mobile_api.safety import (
    SRT_MUTATION_ROUTES,
    MutationRoute,
    assert_read_only_request,
)


CATEGORIES = ("reserve", "payment", "cancel", "refund")

# Obviously-fake, non-chargeable placeholders. No real card / credential.
FAKE_CARD_NUMBER = "0000000000000000"
FAKE_PNR = "SYNTHETIC_PNR_REFERENCE"

RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
CANCEL_ROUTE = "/ard/selectListArd02045_n.do"
PAYMENT_ROUTE = "/ata/selectListAta09036_n.do"
REFUND_ROUTE = "/atc/selectListAtc02063_n.do"


def _eligible_train() -> TrainSummary:
    # An SRT train (service_class_code "17") with a general seat available.
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


def _no_network_client() -> SrtClient:
    # Any network use is a hard failure: reserve() dry-run must never send.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(
            f"reserve() must not send a request (saw {request.method} "
            f"{request.url.path})"
        )

    return SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))


def _logged_in_no_network_client() -> SrtClient:
    client = _no_network_client()
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client


def _allow(category: str) -> MutationConsent:
    return MutationConsent(**{f"allow_{category}": True})


# --- MutationConsent defaults -------------------------------------------------


def test_mutation_consent_defaults_are_safe():
    consent = MutationConsent()
    assert consent.allow_reserve is False
    assert consent.allow_payment is False
    assert consent.allow_cancel is False
    assert consent.allow_refund is False
    assert consent.dry_run is True
    assert consent.fake_card_only is True
    # Additive, and defaulted OFF: every consent written before this flag
    # existed still means exactly what it meant, and the default posture stays
    # fake-card-only.
    assert consent.real_card_acknowledged is False


def test_mutation_consent_is_frozen():
    consent = MutationConsent()
    with pytest.raises(dataclasses.FrozenInstanceError):
        consent.allow_payment = True  # type: ignore[misc]


# --- Consent gating -----------------------------------------------------------


@pytest.mark.parametrize("category", CATEGORIES)
def test_require_mutation_consent_rejects_none_consent(category):
    with pytest.raises(SrtMutationNotAllowedError):
        require_mutation_consent(None, category)


@pytest.mark.parametrize("category", CATEGORIES)
def test_require_mutation_consent_rejects_category_not_allowed(category):
    # A consent that opts into every OTHER category must still deny this one.
    other_flags = {
        f"allow_{name}": True for name in CATEGORIES if name != category
    }
    consent = MutationConsent(**other_flags)
    with pytest.raises(SrtMutationNotAllowedError):
        require_mutation_consent(consent, category)


@pytest.mark.parametrize("category", CATEGORIES)
def test_require_mutation_consent_allows_matching_category_returns_none(category):
    assert require_mutation_consent(_allow(category), category) is None


def test_require_mutation_consent_rejects_unknown_category():
    with pytest.raises(SrtMutationNotAllowedError):
        require_mutation_consent(
            MutationConsent(
                allow_reserve=True,
                allow_payment=True,
                allow_cancel=True,
                allow_refund=True,
            ),
            "checkin",
        )


def test_require_mutation_consent_rejects_non_consent_object():
    with pytest.raises(SrtMutationNotAllowedError):
        require_mutation_consent(object(), "reserve")  # type: ignore[arg-type]


def test_mutation_not_allowed_error_is_an_srt_api_error():
    assert issubclass(SrtMutationNotAllowedError, SrtApiError)


# --- MutationPreview construction + redaction ---------------------------------


def test_mutation_preview_has_safe_default_note_and_fields():
    preview = MutationPreview(
        category="reserve",
        method="POST",
        route=RESERVE_ROUTE,
        payload={"jobId": "1101"},
    )
    assert preview.category == "reserve"
    assert preview.method == "POST"
    assert preview.route == RESERVE_ROUTE
    assert preview.note == "dry-run: not sent"
    assert preview.payload == {"jobId": "1101"}


def test_mutation_preview_payload_is_redacted_masking_card_and_identity_values():
    preview = MutationPreview(
        category="payment",
        method="POST",
        route=PAYMENT_ROUTE,
        payload={
            "stlCrCrdNo1": FAKE_CARD_NUMBER,
            "vanPwd1": "00",
            "crdVlidTrm1": "9912",
            "athnVal1": "000000",
            "mbCrdNo": "SYNTHETIC_MEMBER",
            "pnrNo": FAKE_PNR,
            "netfunnelKey": "SYNTHETIC_NF",
        },
    )
    for key in (
        "stlCrCrdNo1",
        "vanPwd1",
        "crdVlidTrm1",
        "athnVal1",
        "mbCrdNo",
        "pnrNo",
        "netfunnelKey",
    ):
        assert preview.payload[key] == "[REDACTED]", key
    joined = "".join(preview.payload.values())
    assert FAKE_CARD_NUMBER not in joined
    assert FAKE_PNR not in joined
    assert "SYNTHETIC_NF" not in joined


def test_redact_payload_masks_bare_card_shaped_value_under_any_key():
    redacted = redact_payload({"someKey": "4111 1111 1111 1111"})
    assert "4111" not in redacted["someKey"]
    assert "[REDACTED_CARD]" in redacted["someKey"]


def test_mutation_preview_is_frozen():
    preview = MutationPreview(
        category="cancel",
        method="POST",
        route=CANCEL_ROUTE,
        payload={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        preview.note = "sent"  # type: ignore[misc]


# --- Route tiering ------------------------------------------------------------


def test_mutation_routes_are_classified_but_read_only_guard_refuses_them():
    expected = {
        MutationRoute("POST", "app", RESERVE_ROUTE),
        MutationRoute("POST", "app", CANCEL_ROUTE),
        MutationRoute("POST", "app", PAYMENT_ROUTE),
        MutationRoute("POST", "app", REFUND_ROUTE),
    }
    assert expected <= SRT_MUTATION_ROUTES
    # The enduring network guarantee: no code path can POST a mutation route via
    # the read-only guard, because none is in READ_ONLY_ROUTES.
    config = SrtConfig()
    for route in (RESERVE_ROUTE, CANCEL_ROUTE, PAYMENT_ROUTE, REFUND_ROUTE):
        request = httpx.Request("POST", config.base_url + route)
        with pytest.raises(SrtApiError):
            assert_read_only_request(request, config)


# --- reserve(): consent-gated, dry-run, never sends -------------------------


def test_reserve_denied_without_matching_consent_and_sends_nothing():
    client = _logged_in_no_network_client()
    train = _eligible_train()
    # Default consent opts into nothing; None is also denied. Neither sends.
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve(train, consent=MutationConsent())
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve(train, consent=None)  # type: ignore[arg-type]
    # A consent for another category is denied too.
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve(train, consent=MutationConsent(allow_cancel=True))


def test_reserve_dry_run_returns_preview_without_sending():
    client = _logged_in_no_network_client()
    preview = client.reserve(
        _eligible_train(),
        consent=MutationConsent(allow_reserve=True),
        passengers=PassengerCounts(adult=2),
    )
    assert isinstance(preview, MutationPreview)
    assert preview.category == "reserve"
    assert preview.method == "POST"
    assert preview.route == RESERVE_ROUTE
    assert preview.note == "dry-run: not sent"
    # The preview carries the exact form that WOULD be posted (built, not sent).
    assert preview.payload["jobId"] == "1101"
    assert preview.payload["reserveType"] == "11"
    assert preview.payload["jrnyTpCd"] == "11"
    assert preview.payload["totPrnb"] == "2"
    assert preview.payload["psrmClCd1"] == "1"
    # NetFunnel key is redacted even in the dry-run preview.
    assert preview.payload["netfunnelKey"] == "[REDACTED]"


def test_reserve_requires_authenticated_session():
    client = _no_network_client()  # no session established
    with pytest.raises(SrtAuthError):
        client.reserve(
            _eligible_train(), consent=MutationConsent(allow_reserve=True)
        )


def test_reserve_rejects_a_non_srt_train():
    client = _logged_in_no_network_client()
    non_srt = dataclasses.replace(_eligible_train(), service_class_code="00")
    with pytest.raises(ValueError):
        client.reserve(non_srt, consent=MutationConsent(allow_reserve=True))


# --- The card-kind claim ------------------------------------------------------
#
# Ported from the KORAIL port's real-card acknowledgement pattern
# (korail_mobile_api/consent.py, http.py). A payment transmits the PAN in the
# clear, so the consent must say WHICH kind of card it is -- exactly one of
# fake_card_only or real_card_acknowledged.


def test_card_kind_claim_accepts_a_default_fake_card_consent():
    # The historical default. It must keep meaning "a non-chargeable test card"
    # and must keep passing, or every consent written before the flag existed
    # would change meaning.
    require_card_kind_claim(MutationConsent(allow_payment=True))


def test_card_kind_claim_accepts_an_acknowledged_real_card():
    require_card_kind_claim(
        MutationConsent(
            allow_payment=True,
            dry_run=False,
            fake_card_only=False,
            real_card_acknowledged=True,
        )
    )


def test_card_kind_claim_refuses_an_unstated_card_kind():
    # Neither claim: the historical refusal, unchanged.
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        require_card_kind_claim(
            MutationConsent(
                allow_payment=True, dry_run=False, fake_card_only=False
            )
        )
    assert "unstated card kind is never sent" in str(excinfo.value)


def test_card_kind_claim_refuses_a_contradictory_consent():
    # BOTH claims. A consent cannot simultaneously be a test card and an
    # acknowledged real charge; it is refused rather than resolved in either
    # direction, because an ambiguous consent is exactly the state a payment
    # must never be sent on. Do not "fix" this by picking a winner.
    with pytest.raises(SrtMutationNotAllowedError) as excinfo:
        require_card_kind_claim(
            MutationConsent(
                allow_payment=True,
                dry_run=False,
                fake_card_only=True,
                real_card_acknowledged=True,
            )
        )
    assert "contradictory consent" in str(excinfo.value)


# --- what the card-kind flags actually do (2026-07-27 audit, H-1) -------------
#
# The class docstring used to say a real charge required inverting BOTH card
# flags. It never did. These pin the real behaviour so the prose cannot drift
# back: the flags are a mutually-exclusive CLAIM, and the things that gate a
# charge are allow_payment and dry_run.


@pytest.mark.parametrize(
    ("fake_card_only", "real_card_acknowledged", "transmits"),
    [
        (True, False, True),  # the DEFAULT pair -- it transmits
        (False, True, True),
        (True, True, False),  # ambiguous
        (False, False, False),  # unstated
    ],
)
def test_card_kind_claim_requires_exactly_one_flag_not_both(
    fake_card_only: bool, real_card_acknowledged: bool, transmits: bool
):
    consent = MutationConsent(
        allow_payment=True,
        dry_run=False,
        fake_card_only=fake_card_only,
        real_card_acknowledged=real_card_acknowledged,
    )
    if transmits:
        require_card_kind_claim(consent)
    else:
        with pytest.raises(SrtMutationNotAllowedError):
            require_card_kind_claim(consent)


def test_a_default_consent_states_a_card_kind_and_so_passes_the_card_gate():
    # The point of the audit finding: nothing about the DEFAULT card flags
    # stops a transmission. Only allow_payment and dry_run do.
    require_card_kind_claim(MutationConsent(allow_payment=True, dry_run=False))


def test_the_docstring_does_not_promise_that_both_flags_must_be_inverted():
    doc = MutationConsent.__doc__ or ""
    assert "needs both halves stated" not in doc
    assert "restricted to a non-chargeable test card" not in doc
    assert "do not restrict anything" in doc
