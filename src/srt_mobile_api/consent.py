"""Safe-by-default consent and preview types for SRT mutations.

This module is pure infrastructure: it carries the opt-in and dry-run preview
types that every future mutation method uses, but it adds no capability to
send a state-changing request. Nothing here performs I/O.

The safety posture mirrors the KORAIL port:

* A freshly constructed :class:`MutationConsent` grants nothing — every
  per-category ``allow_*`` flag defaults to ``False``.
* ``dry_run`` defaults to ``True``: a mutation call builds and validates its
  request, then returns a :class:`MutationPreview` **without sending**.
* ``fake_card_only`` / ``real_card_acknowledged`` are a CLAIM about which kind
  of card is being sent, not a restriction on it. Exactly one must be set at
  the transmit gate; neither and both are refused. Nothing inspects the PAN --
  this library deliberately never tells a caller whether a card number is real
  (see ``models.py``) -- so ``fake_card_only=True`` records an assertion rather
  than enforcing one. What stands between a default consent and a real charge
  is ``allow_payment=True`` plus ``dry_run=False``, both of which the caller
  must set deliberately.
* :func:`require_mutation_consent` denies by default, raising
  :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` before any request
  is built unless the caller has explicitly opted into the exact category.

There are FIVE categories and only FOUR of them can reach the wire. ``"coupon"``
(할인쿠폰 등록) was added on 2026-07-26 because a coupon registration is a state
change that fits none of the other four — it is not a booking and it moves no
money — and squeezing it into one of them would have meant a consent for
reserving a seat silently also authorising the spending of a coupon.
:data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` is unchanged at
``{"reserve", "cancel", "payment", "refund"}``, so ``allow_coupon`` buys a
preview and nothing else. Consent and live-enablement are deliberately two
different questions in this library: the first is the caller's, the second rests
on a live run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .errors import SrtMutationNotAllowedError
from .redaction import redact_payload


MUTATION_CATEGORIES = ("reserve", "payment", "cancel", "refund", "coupon")

_CONSENT_FLAG_BY_CATEGORY = {
    "reserve": "allow_reserve",
    "payment": "allow_payment",
    "cancel": "allow_cancel",
    "refund": "allow_refund",
    "coupon": "allow_coupon",
}


@dataclass(frozen=True)
class MutationConsent:
    """Explicit, per-category opt-in for state-changing SRT requests.

    Each ``allow_*`` flag is an independent opt-in for exactly one category and
    defaults to ``False``; a consent grants only what is named explicitly.
    ``dry_run`` (default ``True``) makes a mutation call build-but-never-send,
    returning a :class:`MutationPreview`.

    ``fake_card_only`` (default ``True``) and ``real_card_acknowledged``
    (default ``False``) state WHICH KIND of card the caller believes it is
    sending. They are mutually exclusive claims, and the transmit gate requires
    exactly one: both set is a caller bug and is refused rather than resolved
    in either direction, and neither set is refused too, because an unstated
    card kind is exactly the state a payment must not be sent on.

    .. warning::
       These flags do not restrict anything. No code inspects the PAN, by
       design — see :class:`SrtPaymentCard`, which says outright that this
       library must never be the thing that tells a caller whether a card
       number is real. ``fake_card_only=True`` therefore records an assertion;
       it does not verify one. A default consent whose ``allow_payment`` and
       ``dry_run`` have been set to ``True``/``False`` WILL transmit whatever
       PAN it was given, including a real one. The two flags that actually gate
       a charge are ``allow_payment`` and ``dry_run``.

       This paragraph used to claim a real charge required inverting both card
       flags. It never did; the 2026-07-27 audit reproduced all four
       combinations and found ``(fake_card_only=True,
       real_card_acknowledged=False)`` transmits. The gate was correct and the
       description was not.

    Setting it is NOT what enables a payment. Live enablement is
    :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`'s job and
    ``allow_payment``'s; this flag only says which kind of card is in the form.
    The card-kind claim is a requirement to send, never a permission to — but
    since ``payment`` was live-enabled on 2026-07-26 it is the last gate before
    a real PAN goes out, so ``real_card_acknowledged=True`` now means money can
    actually move.
    """

    allow_reserve: bool = False
    allow_payment: bool = False
    allow_cancel: bool = False
    allow_refund: bool = False
    dry_run: bool = True
    fake_card_only: bool = True
    #: The caller acknowledges that a real, chargeable PAN will be transmitted
    #: in the clear and that money will actually move. Never inferred, never
    #: defaulted on; see the class docstring.
    real_card_acknowledged: bool = False
    #: 할인쿠폰 등록 (``POST /arb/selectListArb02A01_n.do``). A FIFTH category
    #: rather than a reuse of one of the four, because a coupon registration is
    #: neither a booking nor a movement of money: it redeems a bearer credential
    #: against the account, and nobody who opted into placing a reservation, or
    #: into paying for one, opted into spending a coupon. The sibling KORAIL port
    #: drew the same line for 할인카드 구매 (its ``discount_card`` category).
    #:
    #: APPENDED, after ``real_card_acknowledged`` rather than beside the other
    #: ``allow_*`` flags, for the same reason ``PassengerCounts.infant`` and
    #: ``.youth`` were appended: every positional construction written before
    #: this field existed keeps its exact meaning.
    #:
    #: Granting it does NOT make a registration transmittable.
    #: :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` stays
    #: ``{"reserve", "cancel", "payment", "refund"}`` — pinned by its own canary
    #: — so ``"coupon"`` can only ever produce a dry-run
    #: :class:`MutationPreview`, and ``dry_run=False`` is refused at the
    #: transmit gate. This flag is what lets a caller PREVIEW the exact request;
    #: live enablement is a separate decision resting on a live run, which this
    #: category has not had.
    allow_coupon: bool = False


@dataclass(frozen=True)
class MutationPreview:
    """The result of a dry-run mutation call: a described-but-unsent request.

    ``payload`` is always stored redacted — it is passed through
    :func:`~srt_mobile_api.redaction.redact_payload` on construction, so a
    ``MutationPreview`` can never hold raw card data, PII, PNR, or NetFunnel key
    regardless of what the caller supplies. ``note`` documents that nothing was
    transmitted.
    """

    category: str
    method: str
    route: str
    payload: Mapping[str, str]
    note: str = "dry-run: not sent"

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", redact_payload(self.payload))


def require_mutation_consent(
    consent: MutationConsent | None,
    category: str,
) -> None:
    """Deny a mutation unless ``consent`` explicitly opts into ``category``.

    ``category`` must be one of ``"reserve"``, ``"payment"``, ``"cancel"``,
    ``"refund"``, ``"coupon"``. Raises
    :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` when ``consent``
    is ``None``, is not a :class:`MutationConsent`, names an unknown category,
    or when the matching ``allow_<category>`` flag is False. Returns ``None``
    when the mutation is permitted. Performs no I/O.
    """
    flag = _CONSENT_FLAG_BY_CATEGORY.get(category)
    if flag is None:
        raise SrtMutationNotAllowedError(
            f"unknown mutation category: {category!r}"
        )
    if not isinstance(consent, MutationConsent):
        raise SrtMutationNotAllowedError(
            f"mutation category {category!r} requires an explicit "
            "MutationConsent"
        )
    if not getattr(consent, flag):
        raise SrtMutationNotAllowedError(
            f"mutation category {category!r} is not permitted by the "
            "provided consent"
        )


def require_card_kind_claim(consent: MutationConsent) -> None:
    """Require a payment consent to say, unambiguously, which kind of card it is.

    A payment transmits the PAN in the clear, so the consent must state EXACTLY
    ONE of two mutually exclusive claims:

    * ``fake_card_only=True`` — a non-chargeable test card (the default).
    * ``real_card_acknowledged=True`` — a real card, money will move.

    Neither set is the historical refusal, unchanged in meaning. BOTH set is a
    contradiction — the consent simultaneously claims a test card and
    acknowledges a real charge — and is refused rather than resolved in either
    direction, because sending a payment on an ambiguous consent is precisely
    the mistake this gate exists to prevent.

    This is a requirement to TRANSMIT, not to preview: a dry run sends nothing,
    so it is deliberately not called on the preview path. Performs no I/O.
    """
    if consent.fake_card_only and consent.real_card_acknowledged:
        raise SrtMutationNotAllowedError(
            "payment mutations refuse a contradictory consent: "
            "fake_card_only=True claims a non-chargeable test card while "
            "real_card_acknowledged=True acknowledges a real charge; set "
            "exactly one"
        )
    if not consent.fake_card_only and not consent.real_card_acknowledged:
        raise SrtMutationNotAllowedError(
            "payment mutations require consent.fake_card_only=True (a "
            "non-chargeable test card) or consent.real_card_acknowledged=True "
            "(an acknowledged real charge); the PAN is transmitted in the "
            "clear, so an unstated card kind is never sent"
        )
