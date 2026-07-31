"""예외 계층과 ``msgCd`` → 예외 분류.

계층::

    SrtApiError
    ├─ SrtTransportError          HTTP 실패
    ├─ SrtProtocolError           응답 모양 불일치 / 안전 가드 거절
    ├─ SrtAuthError               인증·세션
    │  ├─ SrtSessionExpiredError
    │  └─ SrtIpBlockedError
    ├─ SrtAppError                앱 수준 실패 (strResult=FAIL)
    │  ├─ SrtNoResultsError
    │  │  └─ SrtNoDirectTrainError
    │  ├─ SrtInvalidRequestError
    │  └─ SrtSeatUnavailableError
    ├─ SrtMutationNotAllowedError consent 게이트 거절
    └─ SrtNetFunnelError          대기열
       ├─ SrtNetFunnelKeyError
       └─ SrtQueueRejectedError
"""

from .redaction import redact_url


class SrtApiError(Exception):
    """모든 예외의 뿌리. 메시지는 :func:`redact_url` 을 거침."""

    def __init__(self, message: str = "SRT API request failed") -> None:
        super().__init__(redact_url(message))


class SrtTransportError(SrtApiError):
    """HTTP 자체 실패 — 연결 실패·타임아웃·4xx/5xx·비로그인 리다이렉트."""


class SrtProtocolError(SrtApiError):
    """응답 모양이 프로토콜과 다르거나, 안전 가드가 전송 전에 거절."""

    def __init__(
        self,
        message: str = "SRT protocol response was invalid",
        *,
        raw: object | None = None,
    ) -> None:
        self.raw = raw
        super().__init__(message)


class SrtAuthError(SrtApiError):
    """로그인 실패 또는 세션 없음."""

    def __init__(self, message: str = "SRT authentication failed") -> None:
        self.message = redact_url(message)
        super().__init__(self.message)


class SrtSessionExpiredError(SrtAuthError):
    """세션 만료 — 재로그인 후 재시도.

    두 신호: (1) 로그인 페이지/리다이렉트 응답, (2) 예약 응답에서
    strResult="FAIL" + msgCd="S111" (ara1001l.js:1562-1573).
    S111이 인증 오류가 되는 것은 예약 응답에서뿐 — 다른 엔드포인트는 SrtAppError.
    """

    def __init__(self, message: str = "SRT session expired", *, raw: object | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class SrtIpBlockedError(SrtAuthError):
    """IP 차단 — 재시도 무의미. "Your IP Address Blocked" 평문 응답.

    번들 0-hit (인프라 응답). srtgo srt.py:719-720 동일 처리.
    대기열 IP 차단(kTsIpBlock 302, SrtQueueRejectedError)과 별개.
    """


class SrtAppError(SrtApiError):
    """서버가 앱 수준 실패 선언 (HTTP 200, strResult="FAIL"). code=msgCd, raw=응답."""

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = redact_url(message or "")
        self.raw = raw
        safe_code = redact_url(str(code or "UNKNOWN"))
        super().__init__(f"{safe_code}: {self.message}".strip())


class SrtNoResultsError(SrtAppError):
    """조회 결과 없음 — 재시도 아닌 조건 변경 필요.

    WRG000000 "조회 결과가 없습니다." / WRT300005 "조회자료가 없습니다."
    이 서버는 빈 결과를 strResult=FAIL로 표현한다 (ara1001l.js:206-210).
    """


class SrtNoDirectTrainError(SrtNoResultsError):
    """WRD000061 — 직통 없음, 환승 가능. search_transfer_trains로 재조회 가능."""


class SrtInvalidRequestError(SrtAppError):
    """서버가 요청 자체를 거절 — 인자 수정 필요. WRP011002/WRR000100."""


class SrtSeatUnavailableError(SrtAppError):
    """좌석 선택 페이지가 오류 껍데기로 도착 — 매진 추정.

    code는 messages.js 키 "error001" (msgCd 아님, HTML 응답).
    """


class SrtMutationNotAllowedError(SrtApiError):
    """consent 없이 상태변경 시도 — 서버는 아무것도 받지 않음. 전송 전 거절."""


class SrtNetFunnelError(SrtApiError):
    """NetFunnel 대기열 단계 실패. code는 3자리 상태값 또는 앱 msgCd."""

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        raw: object | None = None,
    ) -> None:
        self.code = code
        self.message = redact_url(message or "NetFunnel request failed")
        self.raw = raw
        safe_code = redact_url(str(code or "NETFUNNEL"))
        super().__init__(f"{safe_code}: {self.message}")


class SrtNetFunnelKeyError(SrtNetFunnelError):
    """NET000001 — netfunnelKey 거부. 검색은 1회 자동 재시도, 예약은 재시도 안 함."""


class SrtQueueRejectedError(SrtNetFunnelError):
    """대기열 입장 거부 (kTsBlock 301, kTsIpBlock 302). 재시도 무의미.

    엣지 IP 차단(:class:`SrtIpBlockedError`)과 별개 — 여기는 NetFunnel 대기실.
    """


# ---------------------------------------------------------------------------
# msgCd → 예외 대응표
#
# 앱은 코드로 분기 (유일 분기: resultMap.msgCd=="S111", ara1001l.js:1565).
# 나머지는 strResult=="FAIL" / ErrorCode==-1로만 구분, 이유 미구분.
# 표에 없는 코드는 SrtAppError로 남음 (code/raw 포함).
# NET000001은 SrtNetFunnelKeyError, S111은 예약에서만 SessionExpired — 각 호출 지점 처리.
# ---------------------------------------------------------------------------

NO_RESULT_CODES = frozenset({"WRG000000", "WRT300005"})
# WRD000061: 직통 없음 + 환승 가능 — 더 좁은 분류로 별도 처리.
NO_DIRECT_TRAIN_CODE = "WRD000061"
INVALID_REQUEST_CODES = frozenset({"WRP011002", "WRR000100"})
NETFUNNEL_KEY_REQUIRED_CODE = "NET000001"
SESSION_EXPIRED_CODE = "S111"

_APP_ERROR_BY_CODE: dict[str, type[SrtAppError]] = {
    **{code: SrtNoResultsError for code in NO_RESULT_CODES},
    **{code: SrtInvalidRequestError for code in INVALID_REQUEST_CODES},
    NO_DIRECT_TRAIN_CODE: SrtNoDirectTrainError,
}


def classify_app_error(
    code: str | None,
    message: str | None,
    *,
    raw: object | None = None,
) -> SrtAppError:
    """msgCd에 대응하는 SrtAppError 하위 클래스 인스턴스를 반환(raise 안 함).

    NET000001(SrtNetFunnelKeyError)과 S111(SrtSessionExpiredError)은 여기서 다루지
    않음 — 각 호출 지점이 맥락을 알고 처리.
    """
    subclass = _APP_ERROR_BY_CODE.get(code or "", SrtAppError)
    return subclass(code, message, raw=raw)
