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
from typing import Literal

from .errors import SrtMutationNotAllowedError
from .redaction import redact_payload


MUTATION_CATEGORIES = ("reserve", "payment", "cancel", "refund", "coupon")

#: :func:`require_mutation_consent` 가 아는 다섯 가지 상태변경 범주. 서버가 주는
#: 코드가 아니라 이 라이브러리 자신의 게이트 어휘이므로 집합이 완전히 닫혀 있다 —
#: 각 값은 :class:`MutationConsent` 의 ``allow_<범주>`` 플래그 하나에 대응한다.
#: ``"reserve"`` 예약, ``"payment"`` 결제, ``"cancel"`` 예약취소, ``"refund"``
#: 환불, ``"coupon"`` 할인쿠폰 등록.
MutationCategory = Literal["reserve", "payment", "cancel", "refund", "coupon"]

_CONSENT_FLAG_BY_CATEGORY = {
    "reserve": "allow_reserve",
    "payment": "allow_payment",
    "cancel": "allow_cancel",
    "refund": "allow_refund",
    "coupon": "allow_coupon",
}


@dataclass(frozen=True)
class MutationConsent:
    """상태를 바꾸는 SRT 요청에 범주별로 따로 주는 명시적 동의.

    ``allow_*`` 플래그는 범주 하나씩에 독립으로 붙고 전부 ``False`` 가 기본이다 —
    consent 는 이름을 적은 것만 허락한다. ``dry_run`` 은 ``True`` 가 기본이라,
    상태 변경 메서드는 폼을 만들어 검증만 하고 :class:`MutationPreview` 를
    돌려주며 아무것도 전송하지 않는다.

    ``fake_card_only``(기본 ``True``)와 ``real_card_acknowledged``(기본
    ``False``)는 **어떤 종류의 카드를 보낸다고 주장하는지**를 적는 자리다. 서로
    배타적인 주장이고 전송 게이트
    (:func:`require_card_kind_claim`)는 **정확히 하나**를 요구한다 — 둘 다 켠
    consent 는 모순이라 어느 쪽으로도 해석하지 않고 거절하며, 둘 다 끈 consent 도
    거절한다. 종류를 밝히지 않은 상태가 바로 결제를 보내면 안 되는 상태다.

    .. warning::
       이 두 플래그는 아무것도 제한하지 않는다. 카드번호를 들여다보는 코드는 없다
       — :class:`~srt_mobile_api.models.SrtPaymentCard` 가 밝히듯 이 라이브러리는
       어떤 카드번호가 진짜인지 알려 주는 물건이 되지 않는다. 따라서
       ``fake_card_only=True`` 는 주장을 기록할 뿐 검증하지 않는다. **기본값 그대로
       ``fake_card_only=True``, ``real_card_acknowledged=False`` 인 consent 도
       ``allow_payment=True`` 와 ``dry_run=False`` 만 붙으면 받은 카드번호를 그대로
       전송한다.** 실제 청구를 가르는 것은 카드 종류 주장이 아니라
       ``allow_payment`` 와 ``dry_run`` 둘이다.

    ``real_card_acknowledged`` 를 켜는 것이 결제를 열어 주는 것도 아니다. 라이브
    활성화는 :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 와
    ``allow_payment`` 의 몫이고, 이 플래그는 폼에 든 카드가 어느 쪽인지만 말한다.
    다만 ``payment`` 는 이미 라이브 범주라, 이 주장이 실제 카드번호가 나가기 전
    마지막 관문이다.
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
    category: MutationCategory,
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
