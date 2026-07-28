"""상태변경 동의와 미리보기 타입 — 기본값은 아무것도 하지 않는 것이다.

상태를 바꾸는 메서드가 공통으로 쓰는 옵트인·미리보기 타입만 들어 있다. 여기서
I/O 를 하는 코드는 없고, 이 모듈이 전송 능력을 더해 주지도 않는다.

* 갓 만든 :class:`MutationConsent` 는 아무것도 허락하지 않는다 — ``allow_*`` 는
  전부 ``False`` 가 기본이다.
* ``dry_run`` 은 ``True`` 가 기본이다. 상태변경 호출은 요청을 만들고 검증한 뒤
  **보내지 않고** :class:`MutationPreview` 를 돌려준다.
* ``fake_card_only`` / ``real_card_acknowledged`` 는 어떤 카드를 보내는지에 대한
  **주장**이지 제약이 아니다. 전송 게이트는 정확히 하나가 켜져 있기를 요구하고,
  둘 다 켜도 둘 다 꺼도 거절한다. 카드번호를 들여다보는 코드는 없다.
* :func:`require_mutation_consent` 는 기본이 거절이다. 범주를 명시적으로 켜지
  않았으면 요청을 만들기도 전에
  :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 를 올린다.

범주는 다섯이고 그중 넷만 실제로 전송될 수 있다. ``"coupon"``(할인쿠폰 등록)이
따로 있는 이유는 쿠폰 등록이 예약도 결제도 아니기 때문이다 — 넷 중 하나에
끼워 넣었다면 좌석을 예약하겠다는 동의가 쿠폰을 쓰는 것까지 허락하게 된다.
:data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 는
``{"reserve", "cancel", "payment", "refund"}`` 이므로 ``allow_coupon`` 으로 얻는
것은 미리보기뿐이다. **동의와 라이브 활성화는 다른 질문이다.** 앞은 호출자가
정하고, 뒤는 그 범주의 전송 형식이 실제 응답으로 확인됐는지에 달려 있다.
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
    #: 실제로 청구되는 카드번호가 평문으로 나가고 돈이 움직인다는 것을 호출자가
    #: 인정한다는 표시. 추론되지도, 기본으로 켜지지도 않는다 — 클래스 docstring 참고.
    real_card_acknowledged: bool = False
    #: 할인쿠폰 등록(``POST /arb/selectListArb02A01_n.do``). 넷 중 하나를 재사용하지
    #: 않고 다섯 번째 범주로 둔 이유는 쿠폰 등록이 예약도 돈의 이동도 아니기
    #: 때문이다 — 무기명 자격을 계정에 귀속시키는 일이고, 예약이나 결제에 동의한
    #: 사람이 쿠폰을 쓰는 데 동의한 것은 아니다. 형제인 korail 클라이언트도 할인카드
    #: 구매를 같은 이유로 따로 뗐다(``discount_card``).
    #:
    #: **켜도 전송되지는 않는다.**
    #: :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 는
    #: ``{"reserve", "cancel", "payment", "refund"}`` 이므로 ``"coupon"`` 이 낼 수
    #: 있는 것은 dry-run :class:`MutationPreview` 뿐이고, ``dry_run=False`` 는 전송
    #: 게이트에서 거절된다. 이 플래그는 나갈 요청을 정확히 미리 보게 해 줄 뿐이다.
    allow_coupon: bool = False


@dataclass(frozen=True)
class MutationPreview:
    """dry-run 상태변경 호출의 결과 — 만들어졌지만 보내지지 않은 요청.

    ``category``/``method``/``route`` 는 이 요청이 실제로 나갔다면 갔을 곳이고,
    ``payload`` 는 그때 실렸을 폼 본문이다.

    ``payload`` 는 **항상 마스킹된 채로 보관된다.** 생성 시점에
    :func:`~srt_mobile_api.redaction.redact_payload` 를 거치므로, 호출자가 무엇을
    넣었든 카드번호·개인정보·PNR·NetFunnel 키가 원본 그대로 남지 않는다. 미리보기를
    로그에 찍어도 되게 하려는 것이고, 대신 여기 보이는 값이 서버로 갈 값과
    글자까지 같지는 않다.
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
    """``consent`` 가 ``category`` 를 명시적으로 켜지 않았으면 거절한다.

    ``category`` 는 ``"reserve"``, ``"payment"``, ``"cancel"``, ``"refund"``,
    ``"coupon"`` 중 하나다. 다음 네 경우에
    :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 를 올린다 —
    ``consent`` 가 ``None`` 일 때, :class:`MutationConsent` 가 아닐 때, 모르는
    범주일 때, 해당 ``allow_<범주>`` 가 ``False`` 일 때.

    허락되면 조용히 ``None`` 을 돌려준다. **가장 먼저 지나는 관문이라 요청이 만들어지기
    전에 끝난다.** I/O 는 하지 않는다.
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
    """결제 consent 가 어떤 종류의 카드인지 한 가지로 밝히도록 요구한다.

    결제는 카드번호를 평문으로 보내므로, consent 는 서로 배타적인 두 주장 가운데
    **정확히 하나**를 말해야 한다.

    * ``fake_card_only=True`` — 청구되지 않는 테스트 카드(기본값).
    * ``real_card_acknowledged=True`` — 실제 카드, 돈이 움직인다.

    둘 다 꺼져 있으면 종류를 밝히지 않은 것이라 거절한다. 둘 다 켜져 있으면 테스트
    카드라고 주장하면서 동시에 실제 청구를 인정하는 모순이라, 어느 쪽으로도 해석하지
    않고 역시 거절한다. 애매한 consent 로 결제를 보내는 것이 바로 이 관문이 막으려는
    실수다.

    **전송할 때만 부르는 요구조건이다.** dry-run 은 아무것도 보내지 않으므로 미리보기
    경로에서는 부르지 않는다. 어느 쪽이 켜져 있는지 볼 뿐 카드번호는 보지 않고, I/O 도
    하지 않는다.
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
