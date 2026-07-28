"""이 라이브러리가 내는 예외 계층과 ``msgCd`` -> 예외 대응표.

계층은 전부 :class:`SrtApiError` 아래에 있다::

    SrtApiError
    ├─ SrtTransportError          HTTP 자체가 실패
    ├─ SrtProtocolError           응답 모양이 프로토콜과 다름
    ├─ SrtAuthError               로그인·세션
    │  ├─ SrtSessionExpiredError
    │  └─ SrtIpBlockedError
    ├─ SrtAppError                서버가 앱 수준 실패를 선언
    │  ├─ SrtNoResultsError
    │  │  └─ SrtNoDirectTrainError
    │  ├─ SrtInvalidRequestError
    │  └─ SrtSeatUnavailableError
    ├─ SrtMutationNotAllowedError consent 게이트가 막음
    └─ SrtNetFunnelError          대기열
       ├─ SrtNetFunnelKeyError
       └─ SrtQueueRejectedError

하위 클래스는 전부 상위의 **좁힘**이다. ``except SrtAppError`` 는 앱 수준 실패를
빠짐없이 잡고, ``except SrtApiError`` 하나면 이 라이브러리가 내는 모든 것을 잡는다.
"""

from .redaction import redact_url


class SrtApiError(Exception):
    """이 라이브러리가 내는 모든 예외의 뿌리.

    구체적으로 무엇이 틀렸는지 가리지 않고 한 번에 잡고 싶을 때 쓴다. 메시지는
    :func:`~srt_mobile_api.redaction.redact_url` 를 거치므로, URL 에 실려 온
    토큰이나 PNR 이 예외 문자열로 새어 나가지 않는다.
    """

    def __init__(self, message: str = "SRT API request failed") -> None:
        super().__init__(redact_url(message))


class SrtTransportError(SrtApiError):
    """앱 수준 응답을 읽어 보기도 전에 HTTP 가 실패했다.

    연결 실패·타임아웃 같은 ``httpx`` 오류, 4xx/5xx 응답, 그리고 로그인 리다이렉트가
    아닌 리다이렉트가 여기로 온다. 서버가 무엇을 거절했는지에 대한 정보는 없다 —
    ``msgCd`` 도 응답 본문도 없는 층이다. 세션 만료로 인한 로그인 리다이렉트만은
    :class:`SrtSessionExpiredError` 로 따로 갈라진다.
    """


class SrtProtocolError(SrtApiError):
    """요청은 오갔지만 응답 모양이 이 라이브러리가 아는 프로토콜과 다르다.

    JSON 이어야 할 자리에 JSON 이 아닌 것이 왔거나, 있어야 할 키가 없거나, 파싱이
    전제한 HTML 구조가 아닌 경우다. ``raw`` 에 받은 것이 그대로 담기므로 무엇이
    왔는지 직접 볼 수 있다.

    안전 가드도 이 예외를 쓴다 — 등록되지 않은 경로, 계약과 다른 폼 본문, 카드
    비밀정보를 실은 요청은 **전송 전에** 여기서 막힌다(:mod:`~srt_mobile_api.safety`).
    그 경우 서버는 아무것도 받지 않았다.
    """

    def __init__(
        self,
        message: str = "SRT protocol response was invalid",
        *,
        raw: object | None = None,
    ) -> None:
        self.raw = raw
        super().__init__(message)


class SrtAuthError(SrtApiError):
    """로그인이 실패했거나 인증된 세션이 아니다.

    :meth:`~srt_mobile_api.client.SrtClient.login` 이 자격증명을 거절당했을 때,
    그리고 로그인이 필요한 호출에 세션이 없을 때 오른다. 하위 두 클래스는 원인을
    좁힌 것이므로 ``except SrtAuthError`` 하나면 셋 다 잡힌다.
    """

    def __init__(self, message: str = "SRT authentication failed") -> None:
        self.message = redact_url(message)
        super().__init__(self.message)


class SrtSessionExpiredError(SrtAuthError):
    """세션이 끊겼다 — 다시 로그인하고 같은 호출을 하면 된다.

    두 가지 신호에서 오른다. 하나는 인증이 필요한 요청에 서버가 로그인 페이지나
    로그인 리다이렉트로 답한 경우다. 다른 하나는 예약 응답이
    ``strResult="FAIL"`` 과 함께 ``msgCd="S111"`` 을 말한 경우인데, 이것은 앱 자신의
    규칙이고 v2.0.41 번들 전체에서 ``msgCd`` 값으로 분기하는 유일한 자리다::

        if (resultMap.strResult == "FAIL") {
            var redirectToLogin = null
            if (resultMap.msgCd == "S111") {
                localStorage.setItem('userReservation', param);
                redirectToLogin = "memberShipLogin()";
            }
            srtAlertBoxDivShow("알림", resultMap.msgTxt, null, redirectToLogin);

    (``analysis/raw/base/assets/offline/js/ara/ara1001l.js:1562-1573``.)

    **S111 이 인증 오류가 되는 것은 예약 응답에서뿐이다.** 앱의 분기가 예약
    핸들러에만 있으므로, 다른 엔드포인트가 S111 을 주면 그대로
    :class:`SrtAppError` 로 남는다. srtgo 는 같은 상황을 메시지 "로그인 후
    사용하십시오" 로 판별하지만(``srtgo/srtgo.py:729``) 그 문자열은 번들에 없어서
    (가장 가까운 것이 ``messages.js:224`` 의 "로그인 후 사용하십시요"다) 여기서는
    앱이 실제로 읽는 코드로 가른다.
    """

    def __init__(self, message: str = "SRT session expired", *, raw: object | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class SrtIpBlockedError(SrtAuthError):
    """이 IP 가 차단됐다 — 자격증명 문제가 아니므로 재시도해도 소용없다.

    로그인 엔드포인트가 JSON 대신 "Your IP Address Blocked" 가 든 평문 본문으로
    답할 때 오른다. 본문을 직접 읽지 않고도 "이 회선이 막혔다"와 "비밀번호가
    틀렸다"를 구분하라고 따로 있는 클래스이고, 둘 다 :class:`SrtAuthError` 라
    ``login()`` 을 감싼 ``except SrtAuthError`` 의 뜻은 그대로다.

    번들에는 근거가 없다. 앱이 아니라 인프라가 주는 응답이고, 문자열이 v2.0.41
    번들에서 0회다. srtgo 가 같은 처리를 한다(``srt.py:719-720``).

    대기열의 IP 차단(``kTsIpBlock`` 302, :class:`SrtQueueRejectedError`)과는 다르다.
    그쪽은 NetFunnel 이 대기실 입장을 막는 것이고 앱 자체는 여전히 닿는다.
    """


class SrtAppError(SrtApiError):
    """요청은 도착했고, 서버가 앱 수준에서 실패를 선언했다.

    HTTP 는 200 이다 — 이 서버는 실패를 상태코드가 아니라 본문의
    ``strResult="FAIL"`` 로 말한다. ``code`` 는 서버의 ``msgCd``(또는 바깥 봉투의
    ``ErrorCode``/``ERROR_CODE``)를 손대지 않은 값이고, ``raw`` 는 응답 전체다.
    그래서 이 라이브러리가 하위 클래스를 두지 않은 실패라도 코드를 직접 보고
    분기할 수 있다.

    앱 수준 실패의 뿌리이며 아래 하위 클래스는 전부 좁힘이다 —
    ``except SrtAppError`` 는 그것들을 모두 잡는다.
    """

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = redact_url(message or "")
        self.raw = raw
        safe_code = redact_url(str(code or "UNKNOWN"))
        super().__init__(f"{safe_code}: {self.message}".strip())


class SrtNoResultsError(SrtAppError):
    """질의는 받아들여졌고 걸린 것이 하나도 없다 — 다시 물어도 같다.

    **이 서버에서 조회 결과 없음은 빈 목록이 아니라 선언된 실패다.** 빈 시간대를
    검색하면 ``strResult=FAIL`` / ``msgCd=WRG000000`` / "조회 결과가 없습니다." 가
    오고, 앱도 다른 FAIL 과 똑같이 알림을 띄운다(``ara1001l.js:206-210``). 그러니
    재시도가 아니라 날짜·시각·역을 바꿔야 한다.

    ``WRT300005``("조회자료가 없습니다.")도 여기로 온다. 다만 예약 목록 조회는 이
    코드를 만나지 않는다 —
    :func:`~srt_mobile_api.parsers.parse_reservation_list_response` 는 ``resultMap``
    만 읽고 그쪽은 예약이 없어도 ``SUCC`` 에 빈 배열이라 예외 없이 빈 목록을
    돌려준다. ``WRT300005`` 는 다른 엔드포인트가 이 코드를 읽는 봉투에 넣는 경우를
    위한 대응이다.

    번들은 이 실패를 다른 FAIL 과 구분하지 않는다 — 앱은 어느 쪽이든 ``msgTxt`` 를
    보여 주고 되돌아간다. 이 갈래는 실제로 관측된 코드 위에 이 라이브러리가 세운
    것이다.
    """


class SrtNoDirectTrainError(SrtNoResultsError):
    """직통은 없지만 환승은 된다 — 서버가 다음 질문까지 알려 준 조회 없음.

    ``msgCd=WRD000061`` "직통열차는 없지만, 환승으로 조회 가능합니다." 동대구(0015)
    -> 광주송정(0036)처럼 경부선과 호남선이 오송에서만 만나는 구간이 그렇다.

    그러므로 방금 예외를 낸 그 ``query`` 를 그대로
    :meth:`~srt_mobile_api.client.SrtClient.search_transfer_trains` 에 넘기면 된다.
    **환승 검색을 대신 보내 주지는 않는다** — 앱도 환승 재조회를 대화상자로 물어보고
    기다리며, 이 라이브러리는 호출자가 요청한 읽기 하나를 둘로 늘리지 않는다.

    :class:`SrtAppError` 가 아니라 :class:`SrtNoResultsError` 를 상속한다. WRD000061
    은 부모의 뜻과 정확히 같은 상황이기 때문이다 — 직통 검색이 받아들여졌고 걸린 것이
    없다. "이 질의는 아무것도 못 찾았다"는 뜻으로 ``except SrtNoResultsError`` 를
    쓰던 호출자는 이 응답에 대해서도 맞다. 형제인 korail 클라이언트도 같은 코드를
    ``KorailNoResultsError`` 아래 ``KorailNoDirectTrainError`` 로 분류한다 — 두 서버가
    같은 상황에 정말로 같은 코드를 준다.
    """


class SrtInvalidRequestError(SrtAppError):
    """서버가 우리가 만든 요청 자체를 거절했다 — 고칠 것은 입력이다.

    재시도가 아니라 인자를 고쳐야 한다. 두 코드 모두 이 저장소가 직접 관측한 것이다.

    * ``WRP011002`` "승객수 오류" — 예약에서 ``strResult=FAIL`` 과 함께 온 인원수
      거절(``docs/analysis/srt-app-api-library-spec-2026-07-09.md:359``);
    * ``WRR000100`` — 인원 0명으로 보냈을 때의 입력 검증 거절(같은 문서 :391).

    ``WRP011002`` 는 ``strResult`` 가 ``FAIL`` 이라고 말하지 않아도 실패로 다룬다.
    거절을 ``msgCd`` 에만 담아 보내는 응답을 예약 성립으로 읽지 않기 위해서다.
    """


class SrtSeatUnavailableError(SrtAppError):
    """좌석 선택 페이지가 오류 껍데기로 왔다 — 이 열차는 포기하고 다른 열차를 고른다.

    매진된 열차에 ``/arc/selectListArc02012_n.do`` 를 요청하면
    ``<select id="selectScarNo">`` 도 옵션도 폼도 없이 제목과 스크립트 한 줄만 온다::

        srtAlertBoxDivShow("알림", Sr.msgs.error001, null, "historyBack();");

    여기서 ``code`` 는 ``msgCd`` 가 아니라 그 알림의 ``messages.js`` **키**
    (``"error001"``)다. 이 응답은 HTML 이고 ``msgCd`` 를 아예 싣지 않는다. 키에
    붙은 문구는 앱의 일반적인 서비스 혼잡 문구("서비스가 접속이 원활하지 않습니다.
    잠시후 다시 시도하여 주시기 바랍니다.", ``messages.js:6``)이므로, 이 껍데기가
    엄밀히 말하는 것은 "고를 수 있는 호차가 없다"까지다. 매진은 관측된 원인이지
    서버의 주장이 아니다.

    srtgo 가 비치명적으로 다루는 "잔여석없음" 은 다른 신호다 — 예약 응답의
    ``msgTxt`` 이고 번들에서 0회다. 여기에 담지 않았다.
    """


class SrtMutationNotAllowedError(SrtApiError):
    """상태를 바꾸는 요청이 동의 없이 시도됐다 — 서버는 아무것도 받지 않았다.

    :class:`SrtAppError` 가 아니다. 서버가 거절한 것이 아니라 이 라이브러리가
    **전송 전에** 막은 것이므로, 고칠 곳은 넘긴
    :class:`~srt_mobile_api.consent.MutationConsent` 다. 게이트는 세 군데다.

    * :func:`~srt_mobile_api.consent.require_mutation_consent` — consent 가 없거나,
      :class:`~srt_mobile_api.consent.MutationConsent` 가 아니거나, 알 수 없는
      범주이거나, 해당 ``allow_<범주>`` 가 ``False`` 일 때.
    * :func:`~srt_mobile_api.consent.require_card_kind_claim` — 결제 전송인데
      ``fake_card_only`` 와 ``real_card_acknowledged`` 중 켜진 것이 정확히 하나가
      아닐 때(둘 다 켬도, 둘 다 끔도 거절).
    * 전송 계층 — ``dry_run=True`` 인 consent 로 실제 전송을 시도했거나, 범주가
      :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 에 없을 때
      (``"coupon"`` 은 미리보기까지만 된다).
    """


class SrtNetFunnelError(SrtApiError):
    """NetFunnel 대기열 토큰을 받거나 해석하는 데 실패했다.

    검색과 예약은 앱과 똑같이 대기열을 통과해야 하는데 그 단계에서 막힌 것이다.
    ``code`` 는 실패를 가리키는 코드로, ``/ts.wseq`` 응답이면 대기열 자신의 세 자리
    상태값(``netfunnel.js:84`` 의 표)이고, 앱이 키가 없다고 요청을 거절한 것이면
    앱의 ``msgCd`` 다. 정해진 횟수·시간 안에 입장하지 못한 경우도 여기다.

    하위 두 클래스가 ``code`` 를 그대로 물려받으므로
    ``except SrtNetFunnelError`` 는 셋 다 잡는다.
    """

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
    """앱이 NetFunnel 키가 없거나 상했다고 요청을 거절했다 — 새 키면 될 수 있다.

    ``code`` 는 ``NET000001``, 검색 엔드포인트가 ``netfunnelKey`` 를 받아들이지 않을
    때 주는 앱 수준 ``msgCd`` 다.

    **이 라이브러리가 스스로 다시 시도하는 유일한 실패다.** 검색은 키를 새로 받아
    딱 한 번 재시도하고(``client.py:_search_with_retry``), 그래도 이 예외가 오면
    호출자에게 올라온다. 예약은 절대 재시도하지 않는다 — 다시 보낸 예약은 중복
    예약이다.

    srtgo 는 같은 규칙에 메시지 "정상적인 경로로 접근 부탁드립니다"
    (``srtgo/srtgo.py:721``) 로 도달해 ``rail.clear()`` 로 키를 버린다. 그 문자열도,
    ``NET000001`` 자체도, 필드명 ``netfunnelKey`` 조차도 번들에서는 0회다 — 번들의
    NetFunnel 연동은 주석 처리돼 있다. 여기서는 실제 트래픽이 남긴 코드를 쓴다.
    """


class SrtQueueRejectedError(SrtNetFunnelError):
    """대기실이 입장을 거절했다 — 줄을 선 것이 아니라 막힌 것이다.

    지금 다시 시도해 봐야 소용없다. 앱도 이것만은 일반 ``onError`` 와 따로 두어
    ``_showResultChkEnter`` 에서 전용 이벤트를 쏜다
    (``analysis/raw/base/assets/offline/js/common/netfunnel.js``)::

        case NetFunnel.kTsBlock:   ... this.fireEvent(null, this, "onBlock",   ...)
        case NetFunnel.kTsIpBlock: ... this.fireEvent(null, this, "onIpBlock", ...)

    ``kTsBlock=301``, ``kTsIpBlock=302`` (코드표는 ``netfunnel.js:84``). 대기 응답
    (``kContinue`` 201/202)은 이것이 아니다 — 그쪽은 폴링 대상이고
    :func:`~srt_mobile_api.netfunnel.parse_queue_response` 가 토큰으로 돌려준다.

    여기의 IP 차단은 대기열의 것이지 엣지의 것이 아니다. 엣지의 평문 차단은
    :class:`SrtIpBlockedError` 다. 302 에 대해 앱은 ``ipblock_wait_time`` 만큼 쉬고
    ``ipblock_wait_count`` 번까지 다시 시도하지만, 이 라이브러리는 그러지 않는다 —
    차단을 향해 재시도하는 트래픽이 바로 차단을 늘리는 트래픽이다.
    """


# ---------------------------------------------------------------------------
# msgCd -> 예외 대응표
#
# 메시지 문구가 아니라 코드로 가른다. 앱 자신이 그렇게 한다 -- v2.0.41 번들 전체에서
# 서버가 준 문자열로 분기하는 자리는 `resultMap.msgCd == "S111"` (ara1001l.js:1565)
# 하나뿐이고 그것도 코드다. 나머지 분기는 `strResult == "FAIL"` (ara1001l.js:206,
# :234, :1855)이나 `ErrorCode == -1` (:193, :1840)이라 이유를 전혀 구분하지 않는다.
# 앱은 msgTxt 를 부분문자열로 맞춰 보는 일이 없고 그대로 보여 줄 뿐이다.
#
# 그래서 S111 말고는 앱이 주는 이유 분류가 없다. 아래 항목은 전부 이 저장소가 실제
# 응답에서 본 코드를 호출자가 취할 행동에 대응시킨 것이다. 대응이 없는 코드는 코드와
# 원본 응답을 단 SrtAppError 로 남으므로, 표는 그렇게 넓혀 가게 돼 있다.
#
# 일부러 넣지 않은 것: srtgo 는 한국어 부분문자열만으로 네 가지를 더 분류한다
# (srtgo/srtgo.py:736-744) -- "잔여석없음", "사용자가 많아 접속이 원활하지 않습니다",
# "예약대기 접수가 마감되었습니다", "예약대기자한도수초과". 넷 다 번들에서 0회이고
# 알려진 msgCd 가 없으며, 뒤의 둘은 이 라이브러리가 구현하지 않는 예약대기를 말한다.
# 넣으려면 앱이 하지 않는 메시지 매칭을 검증할 수 없는 조건에 대해 추가해야 한다.
# ---------------------------------------------------------------------------

NO_RESULT_CODES = frozenset({"WRG000000", "WRT300005"})
# 직통열차는 없지만, 환승으로 조회 가능합니다. -- 해결책까지 알려 주는 조회 없음이라
# NO_RESULT_CODES 밖에 둔다. 일반 대응은 일반인 채로 두고, 아래에서 더 좁은 항목을
# 따로 받는다.
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
    """``msgCd`` 가 근거를 대 주는 만큼 좁은 :class:`SrtAppError` 를 만들어 돌려준다.

    올리지 않고 **돌려준다.** ``raise`` 와 트레이스백은 호출 지점의 몫으로 남긴다.
    모르는 코드나 코드가 없는 응답은 밋밋한 :class:`SrtAppError` 가 되고, 어느
    경우든 ``code``/``message``/``raw`` 는 그대로 실린다.

    두 코드는 여기서 다루지 않는다. ``NET000001`` 은 :class:`SrtAppError` 가 아닌
    :class:`SrtNetFunnelKeyError` 이고, ``S111`` 은 예약 응답에서만 인증 오류이므로
    (:class:`SrtSessionExpiredError` 참고) 각각 그것을 아는 호출 지점이 처리한다.
    """
    subclass = _APP_ERROR_BY_CODE.get(code or "", SrtAppError)
    return subclass(code, message, raw=raw)
