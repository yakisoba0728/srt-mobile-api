"""Safe-by-default consent and preview types for SRT mutations.

This module is pure infrastructure: it carries the opt-in and dry-run preview
types that every future mutation method uses, but it adds no capability to
send a state-changing request. Nothing here performs I/O.

The safety posture mirrors the KORAIL port:

* A freshly constructed :class:`MutationConsent` grants nothing — every
  per-category ``allow_*`` flag defaults to ``False``.
* ``dry_run`` defaults to ``True``: a mutation call builds and validates its
  request, then returns a :class:`MutationPreview` **without sending**.
* ``fake_card_only`` defaults to ``True`` and ``real_card_acknowledged``
  defaults to ``False``, so a payment preview can only ever carry a
  non-chargeable test card. A real, chargeable card requires the caller to
  invert BOTH flags explicitly (``fake_card_only=False,
  real_card_acknowledged=True``); setting neither, or setting both, is refused
  at the transmit gate.
* :func:`require_mutation_consent` denies by default, raising
  :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` before any request
  is built unless the caller has explicitly opted into the exact category.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .errors import SrtMutationNotAllowedError
from .redaction import redact_payload


MUTATION_CATEGORIES = ("reserve", "payment", "cancel", "refund")

_CONSENT_FLAG_BY_CATEGORY = {
    "reserve": "allow_reserve",
    "payment": "allow_payment",
    "cancel": "allow_cancel",
    "refund": "allow_refund",
}


@dataclass(frozen=True)
class MutationConsent:
    """Explicit, per-category opt-in for state-changing SRT requests.

    Each ``allow_*`` flag is an independent opt-in for exactly one category and
    defaults to ``False``; a consent grants only what is named explicitly.
    ``dry_run`` (default ``True``) makes a mutation call build-but-never-send,
    returning a :class:`MutationPreview`. ``fake_card_only`` (default ``True``)
    keeps any payment path restricted to a non-chargeable test card.

    ``real_card_acknowledged`` (default ``False``) is the single, explicit
    acknowledgement that a REAL, CHARGEABLE card number will be transmitted in
    the clear and that money will actually move. It is purely ADDITIVE: because
    it defaults to ``False``, every consent written before it existed means
    exactly what it meant before, and the default posture is still
    fake-card-only. A real charge therefore needs both halves stated
    deliberately — ``fake_card_only=False`` (this is not a test card) and
    ``real_card_acknowledged=True`` (yes, charge it). The two are mutually
    exclusive claims: a consent that sets both is a caller bug and is refused
    rather than resolved in either direction, because an ambiguous consent is
    exactly the state a payment must never be sent on.

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
    ``"refund"``. Raises
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
