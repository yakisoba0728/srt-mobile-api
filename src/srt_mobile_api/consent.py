"""상태변경 동의와 미리보기 — 기본값은 아무것도 하지 않는 것.

- :class:`MutationConsent`: allow_* 전부 False, dry_run=True 기본.
- fake_card_only / real_card_acknowledged: 정확히 하나 켜야 전송 허용.
- 5개 범주 중 4개만 전송 가능 (coupon은 preview만).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .errors import SrtMutationNotAllowedError
from .redaction import redact_payload


MUTATION_CATEGORIES = ("reserve", "payment", "cancel", "refund", "coupon")

#: :func:`require_mutation_consent` 가 아는 다섯 가지 상태변경 범주. 서버가 주는
#: 코드가 아니라 이 라이브러리 자신의 게이트 어휘이므로 집합이 완전히 닫혀 있고,
#: 각 값은 :class:`MutationConsent` 의 ``allow_<범주>`` 플래그 하나에 대응합니다.
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
    """범주별 명시적 동의. 기본: 전부 거절, dry_run=True.

    fake_card_only와 real_card_acknowledged는 배타적 주장 — 전송 게이트가
    정확히 하나를 요구. 이 두 플래그는 아무것도 제한하지 않습니다 — 카드번호를
    검사하지 않으며, 실제 청구를 가르는 것은 allow_payment과 dry_run.
    """

    allow_reserve: bool = False
    allow_payment: bool = False
    allow_cancel: bool = False
    allow_refund: bool = False
    dry_run: bool = True
    fake_card_only: bool = True
    #: 실제 카드 청구를 인정하는 표시.
    real_card_acknowledged: bool = False
    #: 할인쿠폰 등록. 켜도 전송 불가 (SRT_LIVE_MUTATION_CATEGORIES 밖).
    allow_coupon: bool = False


@dataclass(frozen=True)
class MutationPreview:
    """dry-run 결과 — 만들어졌지만 보내지지 않은 요청. payload는 항상 마스킹됨."""

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
    """consent가 category를 명시 허용하지 않으면 SrtMutationNotAllowedError."""
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
    """결제 consent가 fake_card_only / real_card_acknowledged 중 정확히 하나를 요구."""
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
