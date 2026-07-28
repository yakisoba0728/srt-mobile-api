"""SRT 모바일 앱 API 파이썬 클라이언트의 공개면.

여기서 import 할 수 있는 이름이 이 패키지가 지원하는 전부다. ``__all__`` 에
없는 것은 하위 모듈에 있더라도 예고 없이 바뀐다.

시작점은 셋이다 — :class:`~srt_mobile_api.client.SrtClient`(모든 호출),
:class:`~srt_mobile_api.config.SrtConfig`(타임아웃·User-Agent·기기키),
:class:`~srt_mobile_api.consent.MutationConsent`(상태를 바꾸는 호출을 여는
열쇠). SRT 앱은 WebView 껍데기라 응답 상당수가 서버가 렌더링한 HTML 이고,
그것을 타입 붙은 값으로 바꾼 결과가 :mod:`srt_mobile_api.models` 다.

실패는 :class:`~srt_mobile_api.errors.SrtApiError` 아래로 모이며, 응답 본문의
코드를 예외로 옮기는 규칙은
:func:`~srt_mobile_api.errors.classify_app_error` 하나에 있다.
"""

#: 배포된 버전. ``pyproject.toml`` 의 ``[project] version`` 과 같은지는
#: ``test_release_readiness.test_package_version_matches_project_metadata`` 가
#: 지킨다. ``__all__`` 에 넣지 않는 것은 의도다 — 던더는 export 하는 이름
#: 집합이 아니고, ``from ... import *`` 가 호출자의 같은 이름을 덮으면 안 된다.
__version__ = "1.0.0"

from .client import SrtClient
from .config import SrtConfig
from .consent import (
    MutationCategory,
    MutationConsent,
    MutationPreview,
    require_card_kind_claim,
    require_mutation_consent,
)
from .errors import (
    SrtApiError,
    SrtAppError,
    SrtAuthError,
    SrtInvalidRequestError,
    SrtIpBlockedError,
    SrtMutationNotAllowedError,
    SrtNetFunnelError,
    SrtNetFunnelKeyError,
    SrtNoDirectTrainError,
    SrtNoResultsError,
    SrtProtocolError,
    SrtQueueRejectedError,
    SrtSeatUnavailableError,
    SrtSessionExpiredError,
    SrtTransportError,
    classify_app_error,
)
from .models import (
    DiscountCoupon,
    DiscountCouponList,
    FareItem,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    Notice,
    NoticeListResult,
    PassengerCounts,
    PublicDiscountEntitlement,
    PublicDiscountPage,
    PublicDiscountSelection,
    SeatCarOption,
    SeatDesignation,
    SeatGrid,
    SeatGridSeat,
    SeatSelectionPage,
    SeatType,
    SrtCancelResult,
    SrtCouponRegistrationResult,
    SrtPaymentCard,
    SrtPaymentResult,
    SrtRefundResult,
    SrtRefundTicketInfo,
    SrtReservationHold,
    SrtReservationListResult,
    SrtReservationSummary,
    SrtSeatAttrCode,
    SrtSession,
    SrtTrainGroupCode,
    TimetablePage,
    TimetableRow,
    TrainSearchMetadata,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
    TransferItinerary,
    TransferSearchResult,
    UnpairedTransferGroup,
)


#: Deliberately NOT re-exported here: ``parsers`` and the request/attempt models
#: that only its functions produce. ``SrtClient`` already calls every one of
#: those parsers on the caller's behalf, so a caller who imports one is reaching
#: past the client into the wire layer. They remain importable at their defining
#: path -- ``from srt_mobile_api.parsers import ...``,
#: ``from srt_mobile_api.models import ...`` -- because this is a move, not a
#: deletion. ``tests/test_public_surface_rule.py`` is what keeps them down.

__all__ = [
    "SrtClient",
    "SrtConfig",
    "MutationCategory",
    "MutationConsent",
    "MutationPreview",
    "require_card_kind_claim",
    "require_mutation_consent",
    "SrtApiError",
    "SrtAppError",
    "SrtAuthError",
    "SrtInvalidRequestError",
    "SrtIpBlockedError",
    "SrtMutationNotAllowedError",
    "SrtNetFunnelError",
    "SrtNetFunnelKeyError",
    "SrtNoDirectTrainError",
    "SrtNoResultsError",
    "SrtProtocolError",
    "SrtQueueRejectedError",
    "SrtSeatUnavailableError",
    "SrtSessionExpiredError",
    "SrtTransportError",
    "classify_app_error",
    "DiscountCoupon",
    "DiscountCouponList",
    "FareItem",
    "FarePage",
    "HtmlPage",
    "MutualVerificationResult",
    "Notice",
    "NoticeListResult",
    "PassengerCounts",
    "PublicDiscountEntitlement",
    "PublicDiscountPage",
    "PublicDiscountSelection",
    "SeatCarOption",
    "SeatDesignation",
    "SeatGrid",
    "SeatGridSeat",
    "SeatSelectionPage",
    "SeatType",
    "SrtCancelResult",
    "SrtCouponRegistrationResult",
    "SrtPaymentCard",
    "SrtPaymentResult",
    "SrtRefundResult",
    "SrtRefundTicketInfo",
    "SrtReservationHold",
    "SrtReservationListResult",
    "SrtReservationSummary",
    "SrtSeatAttrCode",
    "SrtSession",
    "SrtTrainGroupCode",
    "TimetablePage",
    "TimetableRow",
    "TrainSearchQuery",
    "TrainSearchMetadata",
    "TrainSearchResult",
    "TrainSummary",
    "TransferItinerary",
    "TransferSearchResult",
    "UnpairedTransferGroup",
]
