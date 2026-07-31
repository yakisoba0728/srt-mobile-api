""":class:`SrtClient` — 이 패키지에 하나뿐인 진입점.

폼을 만드는 일은 :mod:`srt_mobile_api.payloads`, HTML 을 값으로 바꾸는 일은
:mod:`srt_mobile_api.parsers` 에 있고 이 모듈은 그 둘을 라우트 하나에 엮습니다.

공개 메서드는 읽기와 상태변경(6개: ``reserve``, ``reserve_transfer``, ``cancel``,
``pay_with_card``, ``refund``, ``register_discount_coupon``) 둘로 나뉩니다. 후자는
:func:`~srt_mobile_api.consent.require_mutation_consent` 로 시작하고,
:mod:`srt_mobile_api.safety` 가 전송 직전에 다시 검사합니다.
"""

from __future__ import annotations

import dataclasses
import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from .config import SrtConfig
from .consent import (
    MutationConsent,
    MutationPreview,
    require_card_kind_claim,
    require_mutation_consent,
)
from .errors import (
    SrtApiError,
    SrtAuthError,
    SrtNetFunnelError,
    SrtProtocolError,
    SrtSessionExpiredError,
)
from .http import SrtHttpClient
from .models import (
    DiscountCouponList,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    NoticeListResult,
    PassengerCounts,
    PublicDiscountPage,
    PublicDiscountSelection,
    SearchPageState,
    SeatDesignation,
    SeatGrid,
    SeatSelectionPage,
    SeatType,
    SrtCancelResult,
    SrtCouponRegistrationRequest,
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
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
    TransferItinerary,
    TransferSearchResult,
)
from .netfunnel import (
    QUEUE_POLL_LIMIT,
    QUEUE_WAIT_LIMIT_SECONDS,
    build_act10_url,
    build_chk_enter_url,
    build_set_complete_url,
    is_queued,
    parse_queue_response,
    parse_set_complete_response,
    queue_wait_seconds,
)
from .parsers import (
    pair_transfer_itineraries,
    parse_card_payment_response,
    parse_coupon_registration_response,
    parse_discount_coupon_page,
    parse_fare_page,
    parse_html_page,
    parse_mutual_verification_response,
    parse_notice_list_response,
    parse_public_discount_page,
    parse_public_discount_search_response,
    parse_refund_response,
    parse_refund_ticket_info_response,
    parse_reservation_hold_response,
    parse_reservation_list_response,
    parse_search_has_following_page,
    parse_search_page_state,
    parse_seat_grid_response,
    parse_seat_selection_page,
    parse_timetable_page,
    parse_train_search_response,
    parse_unpaid_cancel_response,
)
from .payloads import (
    GROUP_MIN_PARTY_SIZE,
    card_payment_payload,
    coupon_registration_payload,
    date_selector_payload,
    fare_payload,
    group_search_ajax_payload,
    passenger_selector_payload,
    personal_reservation_payload,
    public_discount_search_payload,
    refund_payload,
    reservation_list_payload,
    search_ajax_payload,
    search_continuation_payload,
    search_page_payload,
    seat_grid_payload,
    seat_option_selector_payload,
    seat_page_payload,
    station_map_selector_payload,
    station_selector_payload,
    timetable_payload,
    train_group_selector_payload,
    transfer_reservation_payload,
    unpaid_reservation_cancel_payload,
)
from .safety import (
    COUPON_LIST_PATH,
    COUPON_REGISTRATION_PATH,
    PUBLIC_DISCOUNT_PAGE_PATH,
    PUBLIC_DISCOUNT_SEARCH_PATH,
)
from .session import SrtSessionClient


# The PNR shape accepted into the refund step-1 Referer. ASCII only and bounded;
# see SrtClient.get_refund_ticket_info for why str.isalnum() was not enough.
_REFUND_PNR_RE = re.compile(r"[A-Za-z0-9-]{1,32}")


class SrtClient:
    """SRT 모바일 앱(v2.0.41)이 쓰는 HTTP API 를 그대로 호출하는 클라이언트.

    리버스 엔지니어링한 앱 경로에 앱과 같은 헤더·폼으로 요청을 보내고, 응답을
    :mod:`~srt_mobile_api.models` 의 불변 데이터클래스로 돌려줍니다.

    **인자 없이 ``SrtClient()`` 로 만들면 바로 동작합니다.**
    :class:`~srt_mobile_api.config.SrtConfig` 는 타임아웃·User-Agent·device key 를
    바꿀 때만 넘기며, 정규 SRT 오리진 두 개 말고는 가리키지 못합니다.
    ``transport``/``clock``/``sleep`` 은 테스트용 주입점입니다.

    조회는 :meth:`login` 뒤에 바로 부르면 됩니다. 상태를 바꾸는 여섯 메서드
    (:meth:`reserve`, :meth:`reserve_transfer`, :meth:`cancel`,
    :meth:`pay_with_card`, :meth:`refund`, :meth:`register_discount_coupon`)는
    :class:`~srt_mobile_api.consent.MutationConsent` 를 키워드로 **반드시** 받고,
    동의가 없으면 아무것도 만들기 전에
    :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 로 막힙니다. 기본
    동의는 ``dry_run=True`` 라서 보낼 폼을 마스킹해 담은
    :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려주고 통신하지 않습니다.

    정리는 :meth:`close` 로 합니다. ``with`` 문은 지원하지 않으며, 쿠키까지
    버리려면 :meth:`clear_session` 을 따로 부르면 됩니다.

    .. code-block:: python

        from srt_mobile_api import PassengerCounts, SrtClient, TrainSearchQuery

        client = SrtClient()
        client.login("you@example.com", "password")
        try:
            query = TrainSearchQuery(
                departure_station_code="0551",   # 수서
                arrival_station_code="0015",     # 동대구
                departure_date="20260809",       # YYYYMMDD
                departure_time="060000",         # HHMMSS, 이 시각부터
                passengers=PassengerCounts(adult=1),
            )
            for train in client.search_trains(query).trains:
                print(train.train_no, train.departure_time, train.arrival_time)
        finally:
            client.close()
    """

    def __init__(
        self,
        config: SrtConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or SrtConfig()
        self.http = SrtHttpClient(self.config, transport=transport)
        self.session = SrtSessionClient(self.http)
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        # act_10 keys acquired but not yet released with setComplete (5004).
        # A list rather than a single slot because a NetFunnel retry mid-flow
        # can acquire a second key before the first is released, and the point
        # of tracking them is that NONE is left holding a place in line.
        self._netfunnel_slots: list[str] = []

    def close(self) -> None:
        """내부 HTTP 커넥션 풀을 닫습니다.

        세션 쿠키와 저장된 :class:`~srt_mobile_api.models.SrtSession` 은 지우지 않습니다
        — 그것은 :meth:`clear_session` 의 일입니다. 서버로는 아무것도 보내지 않습니다.

        ``with`` 문은 지원하지 않으므로 직접 부르거나 ``try``/``finally`` 로 감쌉니다.
        """
        self.http.close()

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        """아이디와 비밀번호로 로그인하고 :class:`~srt_mobile_api.models.SrtSession` 을 돌려줍니다.

        ``login_id`` 는 이메일·휴대폰번호·회원번호 중 아무거나 됩니다. 형태를 보고
        ``srchDvCd`` 를 고릅니다 — 이메일이면 ``"2"``, ``01X`` 로 시작하는 휴대폰이면
        ``"3"``(하이픈은 떼고 보냅니다), 그 외에는 회원번호로 보고 ``"1"``.
        ``login_type`` 을 주면 그 값이 이깁니다.

        호출하면 먼저 기존 쿠키를 버립니다. 응답의 ``userMap.RTNCD`` 가 ``"Y"`` 여야
        성공이고, 그 뒤 ``/main/main.do`` 와 ``/ara/ara0101v.do`` 를 실제로 읽어
        인증됐는지 확인한 다음에야 세션을 저장합니다.

        실패는 전부 :class:`~srt_mobile_api.errors.SrtAuthError` 입니다 — 없는 회원과
        틀린 비밀번호를 서버가 구분해 주지 않습니다. IP 차단은 그 하위 클래스인
        :class:`~srt_mobile_api.errors.SrtIpBlockedError` 이고, 어떤 이유로 실패하든
        세션은 다시 비워집니다.
        """
        return self.session.login(login_id, password, login_type=login_type)

    def clear_session(self) -> None:
        """쿠키 항아리를 비우고 저장된 세션을 버립니다.

        서버로는 아무것도 보내지 않습니다. 로그아웃 요청이 아니라 클라이언트 쪽 상태만
        지우는 것이라, 서버 세션은 스스로 만료될 때까지 남아 있습니다.
        """
        self.session.clear_session()

    def logout(self) -> None:
        """:meth:`clear_session` 의 다른 이름 — 로컬 쿠키와 세션만 버립니다.

        서버에 로그아웃 요청을 보내지 않습니다. 이름 때문에 서버 세션까지 끊긴다고
        읽히기 쉬워서 적어 둡니다.
        """
        self.clear_session()

    @contextmanager
    def _session_guard(self) -> Iterator[None]:
        try:
            yield
        except SrtSessionExpiredError:
            self.clear_session()
            raise

    def get_main(self) -> HtmlPage:
        """로그인 뒤 메인 화면의 HTML 을 파싱 없이 돌려줍니다.

        ``GET /main/main.do?deviceId=<device_key>``. 반환
        :class:`~srt_mobile_api.models.HtmlPage` 에는 원본 ``raw`` 와 태그를 걷어낸
        ``text`` 뿐이고 구조화된 필드는 없습니다.

        로그인 세션이 필요합니다. 서버가 로그인 페이지를 돌려주면 HTTP 계층이
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 를 내고 저장된 세션도
        같이 비워집니다.
        """
        with self._session_guard():
            raw = self.http.get_text("/main/main.do", params={"deviceId": self.config.device_key})
            return parse_html_page(raw, context="main page")

    def get_booking_page(self) -> HtmlPage:
        """승차권 예매 화면(``GET /ara/ara0101v.do``)의 HTML 을 파싱 없이 돌려줍니다.

        검색·예약 폼이 서버에서 렌더링돼 실려 오는 페이지입니다. 이 클라이언트는 검색과
        예약 때 이 경로를 Referer 로 쓰고, 여기 박혀 있는 MY SRT 메뉴에서
        :meth:`get_discount_coupons` 와 :meth:`get_public_discounts` 의 경로를 찾았습니다.

        반환은 파싱되지 않은 :class:`~srt_mobile_api.models.HtmlPage` 입니다. 로그인 세션이
        필요하고, 미인증 응답은
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 로 올라옵니다.
        """
        with self._session_guard():
            raw = self.http.get_text("/ara/ara0101v.do")
            return parse_html_page(raw, context="booking page")

    def _get_notice_list_result(self) -> NoticeListResult:
        with self._session_guard():
            return parse_notice_list_response(
                self.http.post_form(
                    "/main/noticeList.do",
                    {"pageId": "MB0101000000"},
                    accept="application/json, text/javascript, */*; q=0.01",
                )
            )

    def get_notice_list(self) -> dict[str, Any]:
        """공지사항 응답을 서버가 준 ``dict`` 모양 그대로 돌려줍니다.

        ``POST /main/noticeList.do`` (``pageId=MB0101000000``). 모양을 바꾸지 않는
        구버전 인터페이스이고, 타입이 붙은 행이 필요하면
        :meth:`get_typed_notice_list` 를 씁니다 — 요청은 완전히 같고 파싱만 다릅니다.

        공지가 하나도 없으면 ``noticeList`` 가 빈 리스트인 정상 응답이며 예외가 아닙니다.
        """
        return self._get_notice_list_result().raw

    def get_typed_notice_list(self) -> NoticeListResult:
        """같은 공지 조회를 :class:`~srt_mobile_api.models.NoticeListResult` 로 돌려줍니다.

        :meth:`get_notice_list` 와 요청은 완전히 같습니다. 차이는 반환뿐 — 각 행이 불변
        :class:`~srt_mobile_api.models.Notice` 이고, ``SUBJ``/``BODY``/``CREATE_DATE``/
        ``IS_MAIN``/``IS_NOTICE``/``PAGE_ID`` 가 문자열이 아니면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 로 거릅니다. 서버 응답 전체는
        :attr:`~srt_mobile_api.models.NoticeListResult.raw` 에 남습니다.

        공지가 없으면 빈 ``notices`` 가 정상입니다.
        """
        return self._get_notice_list_result()

    def get_ticket_list(self, page_no: int = 0) -> HtmlPage:
        """로그인한 계정의 승차권 확인 페이지 HTML 을 파싱 없이 돌려줍니다.

        ``GET /atc/selectListAtc14017_n.do?pageNo=<page_no>``, 발권이 끝난 승차권을
        보여 주는 화면입니다. 예약을 구조화된 행으로 받으려면 :meth:`get_reservations`
        를 씁니다 — 그쪽은 이웃 경로 ``Atc14016`` 을 POST 해 JSON 을 받는 다른 읽기입니다.

        반환 :class:`~srt_mobile_api.models.HtmlPage` 에는 승차권이 파싱돼 있지 않습니다.

        로그인이 필요하고, 이 읽기는 응답이 로그인 페이지인지 명시적으로 확인해
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 를 냅니다. 만료된 세션이
        빈 승차권 목록으로 읽히는 일을 막기 위한 것입니다.
        """
        with self._session_guard():
            raw = self.http.get_text(
                "/atc/selectListAtc14017_n.do", params={"pageNo": str(page_no)}
            )
            return parse_html_page(raw, context="ticket list", require_authenticated=True)

    def get_discount_coupons(self) -> DiscountCouponList:
        """계정이 보유한 할인쿠폰 목록을 읽습니다.

        ``GET /apa/selectListApa03020_n.do``, 파라미터 없음. 반환은
        :class:`~srt_mobile_api.models.DiscountCouponList` 이고 로그인이
        필요합니다.

        **쿠폰이 하나도 없으면 빈 목록이 정상 반환입니다** — 페이지가 "보유한 쿠폰이
        없습니다." 라고 말하는 경우입니다. 목록도 없고 그 문구도 없거나 둘이 동시에
        있으면 :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

        같은 페이지에 등록 폼이 있지만 등록은 다른 경로
        (``POST /arb/selectListArb02A01_n.do``)이고
        :meth:`register_discount_coupon` 의 일입니다.

        v2.0.41 번들에는 ``/apa/`` 라우트가 없고 서버가 렌더링하는 MY SRT 메뉴에서
        찾은 경로입니다. 확인된 것은 빈 상태뿐이고 채워진 상태는 미검증입니다 —
        필드명 근거는 :class:`~srt_mobile_api.models.DiscountCoupon` 참고.
        """
        with self._session_guard():
            return parse_discount_coupon_page(
                self.http.get_text(
                    COUPON_LIST_PATH,
                    referer=f"{self.config.base_url}/ara/ara0101v.do",
                )
            )

    def get_public_discounts(self) -> PublicDiscountPage:
        """계정이 승인받은 공공할인 자격을 읽습니다.

        ``GET /common/ARA/ARA0301V/view.do``, 할인 승차권 페이지, 파라미터 없음.
        반환은 :class:`~srt_mobile_api.models.PublicDiscountPage` 이고 로그인이
        필요합니다.

        **자격이 하나도 없는 계정도 정상 반환입니다** —
        :attr:`~srt_mobile_api.models.PublicDiscountPage.is_eligible` 가 ``False``
        로 올 뿐입니다. 자격을 가진 계정의 응답은 미검증입니다.

        검색은 하지 않습니다. 이 페이지가 곧 검색 폼이고, 검색은
        :meth:`search_public_discount_trains` 가 따로 보냅니다.

        공공할인의 승객 어휘는 :class:`~srt_mobile_api.models.PassengerCounts` 보다
        넓습니다 — 청소년(``04``) 아래에는 어느 ``commCode.js`` 에도 없는
        ``psgTpCd6`` 이 있고, :mod:`~srt_mobile_api.discounts` 에 기록만 해
        두었습니다.
        """
        with self._session_guard():
            return parse_public_discount_page(
                self.http.get_text(
                    PUBLIC_DISCOUNT_PAGE_PATH,
                    referer=f"{self.config.base_url}/ara/ara0101v.do",
                )
            )

    def get_reservations(self, page_no: int = 0) -> SrtReservationListResult:
        """계정의 예약/발권 목록을 구조화된 행으로 읽습니다.

        ``POST /atc/selectListAtc14016_n.do``. 반환은
        :class:`~srt_mobile_api.models.SrtReservationListResult` 이고 로그인이
        필요합니다.

        **예약을 열거할 수 있는 유일한 읽기입니다.** PNR 을 잃어버린 홀드로
        돌아가는 길이기도 해서, 파서는 모양이 예상과 달라도 PNR 만은 건져냅니다
        (:func:`~srt_mobile_api.parsers.parse_reservation_list_response`).
        HTML 을 주는 :meth:`get_ticket_list`(``Atc14017`` GET)와는 다른 읽기입니다.

        ``page_no`` 는 ``pageNo`` 로 나가고, 전체 페이지 수는 결과의
        :attr:`~srt_mobile_api.models.SrtReservationListResult.total_page_count`
        (``totPageCnt``)입니다.

        **예약이 없으면 빈 결과가 정상입니다.** 서버는 ``strResult="SUCC"`` /
        ``IRZ000005`` / "조회할 자료가 없습니다." 를 ``trainListMap: []`` 와 함께
        보냅니다. 채워진 모양은 미검증이고 행 필드명은 srtgo(``srt.py:1069-1082``)
        출처입니다.
        """
        with self._session_guard():
            return parse_reservation_list_response(
                self.http.post_form(
                    "/atc/selectListAtc14016_n.do",
                    reservation_list_payload(page_no),
                    accept="application/json, text/javascript, */*; q=0.01",
                    referer=f"{self.config.base_url}/main/main.do",
                )
            )

    def _get_selector_page(
        self,
        path: str,
        payload: dict[str, str],
        *,
        context: str,
    ) -> HtmlPage:
        raw = self.http.post_html_form(
            path,
            payload,
            referer=f"{self.config.base_url}/ara/ara0101v.do",
        )
        return parse_html_page(raw, context=context, require_authenticated=True)

    def get_station_selector(
        self,
        departure_name: str,
        arrival_name: str,
        departure_code: str,
        arrival_code: str,
    ) -> HtmlPage:
        """역 선택 팝업 HTML(``POST /common/ARA/ARA0501P/view.do``).

        역 코드·이름 표는 :mod:`~srt_mobile_api.stations` 에 이미 있으므로 역을
        고르기 위해 이 호출을 할 필요는 없습니다. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0501P/view.do",
                station_selector_payload(
                    departure_name, arrival_name, departure_code, arrival_code
                ),
                context="station selector",
            )

    def get_station_map_selector(self) -> HtmlPage:
        """노선도 방식 역 선택 팝업 HTML(``POST /common/ARA/ARA0502P/view.do``).

        인자 없음 — 고정값. 역 코드는 :mod:`~srt_mobile_api.stations` 에서 얻는 편이
        낫습니다. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0502P/view.do",
                station_map_selector_payload(),
                context="station map selector",
            )

    def get_date_selector(self, date: str) -> HtmlPage:
        """날짜 선택 팝업 HTML(``POST /common/ARA/ARA0401P/view.do``).

        ``date`` 는 ``YYYYMMDD``, 아니면 :class:`ValueError`. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0401P/view.do",
                date_selector_payload(date),
                context="date selector",
            )

    def get_passenger_selector(self, passengers: PassengerCounts) -> HtmlPage:
        """승차인원 선택 팝업 HTML(``POST /common/ARA/ARA0901P/view.do``).

        검색·예약과 무관합니다. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0901P/view.do",
                passenger_selector_payload(passengers),
                context="passenger selector",
            )

    def get_seat_option_selector(
        self,
        *,
        request_seat_attr_code: str = "015",
        location_seat_attr_code: str = "000",
        seat_name: str = "일반/기본",
    ) -> HtmlPage:
        """좌석 위치·속성 선택 팝업 HTML(``POST /common/ARA/ARA0701P/view.do``).

        기본값은 앱의 초기 상태와 동일. 실제 좌석 확인은 :meth:`get_seat_page` /
        :meth:`get_seat_grid`. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0701P/view.do",
                seat_option_selector_payload(
                    request_seat_attr_code,
                    location_seat_attr_code,
                    seat_name,
                ),
                context="seat option selector",
            )

    def get_train_group_selector(
        self,
        train_group_code: SrtTrainGroupCode = "109",
        train_group_name: str = "전체",
    ) -> HtmlPage:
        """열차 종류 선택 팝업 HTML(``POST /common/ARA/ARA0201V/view.do``).

        기본 ``"109"``/``"전체"`` 는 :class:`~srt_mobile_api.models.TrainSearchQuery`
        기본값과 같습니다. 로그인 필요.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0201V/view.do",
                train_group_selector_payload(train_group_code, train_group_name),
                context="train group selector",
            )

    def get_mutual_verification(self) -> MutualVerificationResult:
        """상호검증값(``mutMrkVrfCd``)을 발급받습니다.

        ``POST /ara/selectListAra10130_n.do``, **본문 없음**. 앱은 이 값을 코레일 연계
        (KTX) 예약 분기에서 씁니다(``ara1001l.js:229-241``). 이 라이브러리의 예약
        경로는 쓰지 않으므로 발급까지가 전부입니다.

        **로그인이 필요 없습니다** — 다른 읽기와 달리 공개 경로입니다.

        반환은 :class:`~srt_mobile_api.models.MutualVerificationResult` 입니다.
        ``strResult`` 가 ``"FAIL"`` 이면 :class:`~srt_mobile_api.errors.SrtAppError`
        계열, ``mutMrkVrfCd`` 가 비어 있으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다. ``msgCd`` 는
        정보성이라 없어도 되고, 모델에 없는 ``wctNo``/``uuid``/``cgPsId`` 는
        ``raw`` 로 닿을 수 있습니다.
        """
        with self._session_guard():
            data = self.http.post_form(
                "/ara/selectListAra10130_n.do",
                {},
                accept="application/json, text/javascript, */*; q=0.01",
                referer=(
                    f"{self.config.base_url}"
                    "/ara/selectListAra10007_n.do"
                ),
            )
            return parse_mutual_verification_response(data)

    def _netfunnel_get(self, url: str, referer: str) -> str:
        return self.http.get_text_url(url, referer=referer)

    def _get_act10_key(self, referer: str) -> str:
        """``act_10`` 대기열 키를 받습니다. 줄이 서 있으면 한도 안에서 기다립니다.

        ``getTidChkEnter``(5101)를 한 번 보내고, 통과(200, 또는 키 없는 300 우회)면
        곧바로 돌아옵니다. 201/202 는 줄에 섰다는 뜻이라 ``chkEnter``(5002)를
        폴링합니다.

        **폴링에 한도가 있다는 점이 앱과 다릅니다.** 횟수
        (:data:`~srt_mobile_api.netfunnel.QUEUE_POLL_LIMIT`)와 실시간 예산
        (:data:`~srt_mobile_api.netfunnel.QUEUE_WAIT_LIMIT_SECONDS`) 중 먼저 닿는
        쪽에서 :class:`SrtNetFunnelError` 를 올립니다. 대기 간격은 서버가 준
        ``ttl`` 을 앱과 같이 1~5초로 자른 값이며(``TS_MAX_TTL``), 대기열을 향한
        촘촘한 재시도는 IP 차단을 부릅니다.

        받은 키는 기록해 두었다가 요청이 끝나면 ``setComplete`` 로 반납합니다
        (:meth:`_release_netfunnel_slots`).

        **폴링 경로는 실제로 대기가 걸린 적이 없습니다** — 201 을 받아 본 적이
        없습니다.
        """
        body = self._netfunnel_get(
            build_act10_url(
                self.config.netfunnel_url,
                timestamp_ms=int(self._clock() * 1000),
            ),
            referer,
        )
        token = parse_queue_response(body, action="act_10")
        # Recorded the moment it exists, not once the loop finishes. Both raises
        # below happen with a key already issued to us, and a key recorded after
        # them is a queue slot the server keeps holding for a caller who has
        # given up. Only ever ONE key is registered -- the current one -- because
        # the poll loop supersedes rather than accumulates.
        key = self._hold_netfunnel_key(None, token.key)
        deadline = self._clock() + QUEUE_WAIT_LIMIT_SECONDS
        polls = 0
        while is_queued(token):
            if polls >= QUEUE_POLL_LIMIT or self._clock() >= deadline:
                raise SrtNetFunnelError(
                    token.code,
                    "NetFunnel queue did not admit us within the bounded wait",
                )
            wait = queue_wait_seconds(token)
            self._sleep(wait)
            polls += 1
            # The key to poll with is the one the queue last echoed
            # (chkEnterCont(retval.getValue("key"))); a 201 that omits it leaves
            # the previously held key in place rather than aborting.
            key = self._hold_netfunnel_key(key, token.key or key)
            if not key:
                raise SrtNetFunnelError(
                    token.code,
                    "NetFunnel queued us without ever issuing a key to poll with",
                )
            body = self._netfunnel_get(
                build_chk_enter_url(
                    self.config.netfunnel_url,
                    key=key,
                    timestamp_ms=int(self._clock() * 1000),
                    ttl=wait,
                ),
                referer,
            )
            token = parse_queue_response(body, action="act_10")
            key = self._hold_netfunnel_key(key, token.key or key)
        return key

    def _hold_netfunnel_key(self, previous: str | None, key: str) -> str:
        """잡고 있는 대기열 자리를 ``key`` 로 바꾸고 ``previous`` 는 놓습니다.

        "키 없음" 은 빈 문자열입니다 (300 우회). ``previous`` 만 선택인 것은 첫
        획득에는 놓을 자리가 없기 때문입니다.
        """
        if previous == key:
            return key
        if previous is not None and previous in self._netfunnel_slots:
            self._netfunnel_slots.remove(previous)
        if key:
            self._netfunnel_slots.append(key)
        return key

    def _release_netfunnel_slots(self, referer: str) -> None:
        """잡고 있는 키마다 ``setComplete``(5004)를 보내 자리를 반납합니다.

        모든 예외를 삼킵니다 — 뒷정리 실패가 성공한 요청의 결과를 덮으면 안 됩니다.
        """
        while self._netfunnel_slots:
            key = self._netfunnel_slots.pop()
            try:
                body = self._netfunnel_get(
                    build_set_complete_url(
                        self.config.netfunnel_url,
                        key=key,
                        timestamp_ms=int(self._clock() * 1000),
                    ),
                    referer,
                )
                parse_set_complete_response(body, action="act_10")
            except (SrtApiError, ValueError):
                continue

    def _hydrate_search(
        self,
        query: TrainSearchQuery,
        key: str,
        *,
        transfer: bool = False,
    ) -> SearchPageState:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        html = self.http.get_text(
            "/ara/selectListAra10007_n.do",
            params=search_page_payload(query, key, transfer=transfer),
            referer=referer,
        )
        return parse_search_page_state(html)

    def _prepare_search(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> tuple[str, dict[str, str]]:
        # 10명 이상 개인검색 금지 (ara0101v.js:562-567). 빌더가 아닌 여기서
        # 막는 이유: search_page_payload 는 개인/단체를 구분 못 하므로.
        # _get_act10_key 전에 거절하여 대기열 자리를 낭비하지 않는다.
        if not group and query.passengers.total >= GROUP_MIN_PARTY_SIZE:
            raise ValueError(
                f"a personal search is limited to {GROUP_MIN_PARTY_SIZE - 1} "
                f"passengers; {query.passengers.total} is a 단체 search "
                "(ara0101v.js:562-567). Use search_group_trains()."
            )
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        key = self._get_act10_key(referer)
        state = self._hydrate_search(query, key, transfer=transfer)
        # URL chosen by grpDv (ara1001l.js:174-181); 직통/환승 share it.
        path = "/ara/selectListAra10082_n.do" if group else "/ara/selectListAra10007_n.do"
        payload = (
            group_search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
            if group
            else search_ajax_payload(
                query, key, hydrated_fields=state.hidden_fields, transfer=transfer
            )
        )
        return path, payload

    def _post_search_page(
        self,
        path: str,
        payload: dict[str, str],
    ) -> TrainSearchResult:
        data = self.http.post_form(
            path,
            payload,
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
        )
        return parse_train_search_response(data, request_context=payload)

    def _search_once(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> TrainSearchResult:
        # The slot is released once the guarded request is over, whichever way
        # it went -- a search that raised held a place in line just as much as
        # one that succeeded. This is the app's TS_AUTO_COMPLETE behaviour.
        try:
            path, payload = self._prepare_search(query, group=group, transfer=transfer)
            return self._post_search_page(path, payload)
        finally:
            self._release_netfunnel_slots(
                f"{self.config.base_url}/ara/ara0101v.do"
            )

    def _search_with_retry(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> TrainSearchResult:
        for attempt in range(2):
            try:
                return self._search_once(query, group=group, transfer=transfer)
            except SrtNetFunnelError as exc:
                if exc.code != "NET000001" or attempt == 1:
                    raise
        raise AssertionError("unreachable NetFunnel retry state")

    def search_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        """직통 개인 검색 — 한 페이지 분량의 열차 행을 돌려줍니다.

        ``query`` 의 역 코드, 날짜(``YYYYMMDD``), 시각(``HHMMSS``, **그 시각부터**),
        인원으로 ``POST /ara/selectListAra10007_n.do`` 를 보내고
        :class:`~srt_mobile_api.models.TrainSearchResult` 를 돌려줍니다. 로그인이
        필요합니다.

        **결과가 없으면 빈 목록이 아니라 예외입니다** —
        :class:`~srt_mobile_api.errors.SrtNoResultsError`. 직통은 없지만 환승이 되는
        구간이면 그 하위 클래스인
        :class:`~srt_mobile_api.errors.SrtNoDirectTrainError`(``WRD000061``)가 오고,
        같은 ``query`` 를 :meth:`search_transfer_trains` 에 넘기면 됩니다.

        인원이 10명 이상이면 요청 전에 :class:`ValueError` 입니다
        (``ara0101v.js:562-567``). 그때는 :meth:`search_group_trains` 를 쓰면 됩니다.

        NetFunnel ``act_10`` 대기열은 앱처럼 통과하고, ``NET000001`` 이 오면 한 번만
        다시 시도합니다. 다음 페이지는 :meth:`iter_train_search_pages` 입니다.
        """
        with self._session_guard():
            return self._search_with_retry(query, group=False)

    def search_group_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        """단체(10명 이상) 검색 — 같은 질의를 단체 경로로 보냅니다.

        ``POST /ara/selectListAra10082_n.do``. 경로를 가르는 것은 ``grpDv`` 하나이고
        (``ara1001l.js:174-181``), 본문은 ``grpDv="1"`` 과 ``psgNum`` 말고는
        :meth:`search_trains` 와 같습니다. 반환도 같은
        :class:`~srt_mobile_api.models.TrainSearchResult` 입니다. 로그인이 필요합니다.

        인원이 10명 미만이면 요청 전에 :class:`ValueError` — 앱도 클라이언트에서
        막습니다(``ara0101v.js:551-554``).

        **이 라이브러리는 단체 예약은 하지 않습니다.** 잔여석과 운임 조회까지가 전부이고,
        단체 예약 경로는 등록조차 돼 있지 않습니다.

        빈 결과가 예외라는 것과 NetFunnel 처리는 :meth:`search_trains` 와 같습니다.
        """
        with self._session_guard():
            return self._search_with_retry(query, group=True)

    def search_public_discount_trains(
        self,
        query: TrainSearchQuery,
        discount: PublicDiscountSelection,
        *,
        page_cursor: str = "",
    ) -> TrainSearchResult:
        """할인 승차권 검색 — 계정이 승인받은 공공할인이 붙는 열차를 찾습니다.

        ``POST /ara/selectListAra10131_n.do``. 읽기이며 일반 검색 ajax 와 같은 자격으로
        :data:`~srt_mobile_api.safety.READ_ONLY_ROUTES` 에 자기 23필드 계약과 함께
        등록돼 있습니다. 반환은 :class:`~srt_mobile_api.models.TrainSearchResult`
        이고 로그인이 필요합니다.

        **한 번도 보내 본 적이 없습니다.** 필드명·값·응답 키는 서버가 렌더링해 주는
        할인 승차권 페이지에서 읽은 것이라 **요청 모양에는 근거가 있고 효과에는
        없습니다.**

        ``discount`` 의 ``PBL_DISC_CD`` 는 알려진 값 범위(``01`` 다자녀 … ``06`` 3세대
        동행할인, 그리고 ``07``/``08`` 분기)이고 ``TGT_DTRM_YN`` 은 늘 ``"Y"``
        입니다. ``PBL_DISC_NM`` 은 ajax 폼에 필드가 없어 전송되지 않고,
        ``PBL_DISC_MG_NO`` 는 서버가 발급하는 승인번호라 호출자가 넘깁니다(기본
        ``""``).

        **승객 타입 구성은 전송되지 않습니다.** 이 폼은 인원 합계 ``psgNum`` 만 싣고
        ``psgTpCd``/``psgInfoPerPrnb`` 가 없어서 청소년·유아는 합계만 바꿉니다.

        ``page_cursor`` 는 ``gdNo`` 이고 첫 페이지는 ``""`` 입니다. 종료 조건
        (``trainListMap[0].fllwPgExt``)을 본 적이 없어 자동으로 돌지 않습니다.
        NetFunnel 자리는 잡았다 반납하지만 이 경로의 폼에는 ``netfunnelKey`` 필드가
        없어 키는 나가지 않습니다.

        알 수 없는 할인 코드이거나 다자녀·3세대 동행할인인데 인원이 3명 미만이면
        어떤 I/O 도 하기 전에 :class:`ValueError` 입니다(페이지 규칙 ``rsv071``).
        """
        with self._session_guard():
            return self._search_public_discount_with_retry(
                query, discount, page_cursor=page_cursor
            )

    def _search_public_discount_with_retry(
        self,
        query: TrainSearchQuery,
        discount: PublicDiscountSelection,
        *,
        page_cursor: str,
    ) -> TrainSearchResult:
        # The same single bounded NetFunnel retry the ordinary search gets, and
        # for the same reason: NET000001 means the key was stale, not that the
        # query was wrong.
        for attempt in range(2):
            try:
                return self._search_public_discount_once(
                    query, discount, page_cursor=page_cursor
                )
            except SrtNetFunnelError as exc:
                if exc.code != "NET000001" or attempt == 1:
                    raise
        raise AssertionError("unreachable NetFunnel retry state")

    def _search_public_discount_once(
        self,
        query: TrainSearchQuery,
        discount: PublicDiscountSelection,
        *,
        page_cursor: str,
    ) -> TrainSearchResult:
        referer = f"{self.config.base_url}{PUBLIC_DISCOUNT_PAGE_PATH}"
        # Built BEFORE the queue slot is taken, so a request the page's own rules
        # would refuse never costs a place in line.
        payload = public_discount_search_payload(
            query, discount, page_cursor=page_cursor
        )
        try:
            self._get_act10_key(referer)
            data = self.http.post_form(
                PUBLIC_DISCOUNT_SEARCH_PATH,
                payload,
                accept="application/json, text/javascript, */*; q=0.01",
                referer=referer,
            )
            return parse_public_discount_search_response(
                data, request_context=payload
            )
        finally:
            self._release_netfunnel_slots(referer)

    def search_transfer_trains(self, query: TrainSearchQuery) -> TransferSearchResult:
        """환승 검색 — 짝지어진 :class:`~srt_mobile_api.models.TransferItinerary` 를 돌려줍니다.

        요청은 :meth:`search_trains` 와 거의 같습니다. 경로가 같고, 본문 차이는
        ``chtnDvCd`` 가 ``"1"`` 에서 ``"2"`` 로 바뀌는 것뿐이며, 하이드레이션 GET 에
        ``jrnyTpCd="14"``/``jrnyCnt="2"`` 가 더 붙습니다(``ara0101v.js:302-303``).
        로그인이 필요합니다.

        **별도 메서드인 이유는 결과입니다.** 서버가 주는 행은 한 여정의 **절반**
        인데 표시가 없어서, 그대로 :meth:`reserve` 에 넘기면 환승역까지만 끊긴
        승차권이 나옵니다. 그래서 짝짓기를 거친
        :class:`~srt_mobile_api.models.TransferItinerary` 와 :meth:`reserve_transfer`
        쌍으로 갈라 두었습니다.

        반환 :class:`~srt_mobile_api.models.TransferSearchResult` 에는 짝지어진
        ``itineraries``, 짝이 맞지 않아 이유와 함께 남겨 둔 ``unpaired``, 손대지 않은
        원본 ``search`` 가 함께 들어 있습니다. 규칙은
        :func:`~srt_mobile_api.parsers.pair_transfer_itineraries` 참고.

        행은 있는데 하나도 짝지어지지 않으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다. 페이징은 지원하지
        않습니다 — 둘째 커서 ``fllwPgExt2`` 는 늘 ``null`` 이라 용도를 모릅니다.

        여기 닿는 자연스러운 길은 직통 검색의 ``WRD000061``, 즉
        :class:`~srt_mobile_api.errors.SrtNoDirectTrainError` 입니다.
        """
        with self._session_guard():
            return pair_transfer_itineraries(
                self._search_with_retry(query, group=False, transfer=True)
            )

    def _prepare_first_search_page(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
    ) -> tuple[TrainSearchResult, str, dict[str, str]]:
        for attempt in range(2):
            path, payload = self._prepare_search(query, group=group)
            try:
                return self._post_search_page(path, payload), path, payload
            except SrtNetFunnelError as exc:
                if exc.code != "NET000001" or attempt == 1:
                    raise
        raise AssertionError("unreachable NetFunnel retry state")

    def _iter_train_search_pages(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        max_pages: int,
    ) -> Iterator[TrainSearchResult]:
        # The whole walk is ONE guarded interaction, so the slot is released
        # when the walk ends -- normally, by exception, or by a caller
        # abandoning the generator (GeneratorExit runs this finally too). It is
        # deliberately not released after the first page: continuation pages
        # reuse the same key, and completing it mid-walk would be the app
        # calling setComplete while still on the guarded screen.
        try:
            yield from self._paginate_train_search(
                query, group=group, max_pages=max_pages
            )
        finally:
            self._release_netfunnel_slots(
                f"{self.config.base_url}/ara/ara0101v.do"
            )

    def _paginate_train_search(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        max_pages: int,
    ) -> Iterator[TrainSearchResult]:
        with self._session_guard():
            page, path, payload = self._prepare_first_search_page(query, group=group)
            prior_cursor = payload["dptTm"]
            seen_cursors = {prior_cursor}
            yielded_pages = 0

            while True:
                has_following_page = parse_search_has_following_page(page.raw)
                page_is_empty = not page.trains
                last_departure_time = (
                    None if page_is_empty else page.trains[-1].departure_time
                )
                yield page
                yielded_pages += 1
                if (
                    yielded_pages >= max_pages
                    or not has_following_page
                    or page_is_empty
                ):
                    return

                try:
                    continuation_payload = search_continuation_payload(
                        payload,
                        last_departure_time,
                    )
                except ValueError as exc:
                    raise SrtProtocolError(
                        "SRT paginated search last_departure_time must be six ASCII digits"
                    ) from exc
                cursor = continuation_payload["dptTm"]
                if cursor in seen_cursors:
                    raise SrtProtocolError(
                        "SRT paginated search produced a repeated cursor"
                    )
                if cursor <= prior_cursor:
                    raise SrtProtocolError(
                        "SRT paginated search cursor did not make forward progress"
                    )

                try:
                    next_page = self._post_search_page(path, continuation_payload)
                except SrtNetFunnelError as exc:
                    if exc.code != "NET000001":
                        raise
                    refreshed_path, refreshed_payload = self._prepare_search(
                        query,
                        group=group,
                    )
                    continuation_payload = search_continuation_payload(
                        refreshed_payload,
                        last_departure_time,
                    )
                    next_page = self._post_search_page(
                        refreshed_path,
                        continuation_payload,
                    )
                    path = refreshed_path

                seen_cursors.add(cursor)
                prior_cursor = cursor
                payload = continuation_payload
                page = next_page

    def iter_train_search_pages(
        self,
        query: TrainSearchQuery,
        *,
        group: bool = False,
        max_pages: int = 10,
    ) -> Iterator[TrainSearchResult]:
        """검색 결과를 페이지 단위로 게으르게 넘기는 제너레이터를 돌려줍니다.

        첫 페이지는 :meth:`search_trains`(``group=True`` 면
        :meth:`search_group_trains`)와 같은 요청이고, 이어지는 페이지는 직전 페이지
        마지막 열차의 출발시각을 ``dptTm`` 커서로 밀어 올려 다시 POST 합니다.
        :class:`~srt_mobile_api.models.TrainSearchResult` 를 한 페이지씩 내놓습니다.

        ``max_pages`` 는 양의 정수여야 하고(``bool`` 은 거부) 아니면
        :class:`ValueError` 입니다. 이 검사만은 제너레이터를 돌리기 전 호출 즉시
        일어납니다. 기본 10 페이지에서 멈추며, 그전이라도 서버가 다음 페이지 없음을
        말하거나 페이지가 비면 끝납니다. 커서가 반복되거나 나아가지 않으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

        NetFunnel 자리는 **걷기 전체가 끝날 때** 반납됩니다. 도중에 제너레이터를
        버려도(``GeneratorExit``) 반납됩니다.

        환승 검색에는 쓸 수 없습니다 — :meth:`search_transfer_trains` 참고.
        """
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("max_pages must be a positive non-boolean integer")
        return self._iter_train_search_pages(
            query,
            group=group,
            max_pages=max_pages,
        )

    def get_seat_page(
        self,
        train: TrainSummary,
        cabin_class: str = "1",
        seat_count: str | None = None,
        *,
        passengers: PassengerCounts | None = None,
        seat_attr_code: str = "015",
    ) -> SeatSelectionPage:
        """좌석 선택 1단계 — 호차 목록이 담긴 좌석선택 페이지를 읽습니다.

        ``POST /arc/selectListArc02012_n.do``. ``train`` 은 검색이 돌려준 완전한
        :class:`~srt_mobile_api.models.TrainSummary` 행이어야 합니다. 반환
        :class:`~srt_mobile_api.models.SeatSelectionPage` 는 HTML 에
        :attr:`~srt_mobile_api.models.SeatSelectionPage.cars`(호차 옵션)가 붙은 것이고,
        호차 하나의 좌석 배치는 :meth:`get_seat_grid` 가 이어서 읽습니다.

        ``choiceSeatCount`` 는 상수가 아니라 **일행 인원**입니다 — 앱은
        ``lfn_getRsv("totPrnb")`` 를 보냅니다(``ara1001l.js:1511``). 그래서 ``passengers``
        를 넘기면 거기서 인원을 뽑습니다. ``seat_count`` 는 명시적 override 이고 둘 다
        주면 이쪽이 이깁니다. 둘 다 없으면 ``"1"``.

        로그인이 필요합니다.
        """
        if seat_count is None:
            seat_count = str((passengers or PassengerCounts()).total)
        with self._session_guard():
            raw = self.http.post_html_form(
                "/arc/selectListArc02012_n.do",
                seat_page_payload(
                    train, cabin_class, seat_count, seat_attr_code=seat_attr_code
                ),
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )
            return parse_seat_selection_page(raw)

    def get_seat_grid(
        self,
        train: TrainSummary,
        car_number: str,
        cabin_class: str = "1",
        seat_count: str | None = None,
        *,
        passengers: PassengerCounts | None = None,
        seat_attr_code: str = "015",
    ) -> SeatGrid:
        """좌석 선택 2단계 — 호차 하나의 좌석배치도를 읽습니다.

        ``POST /arc/selectListArc02011_n.do``. :meth:`get_seat_page` 가 "어느 호차에
        자리가 있나" 를 답한다면 이쪽은 "어느 좌석이고, 고를 수 있나" 를 답합니다.
        반환 :class:`~srt_mobile_api.models.SeatGrid` 의
        :meth:`~srt_mobile_api.models.SeatGrid.choose` 로
        :class:`~srt_mobile_api.models.SeatDesignation` 을 만들어 :meth:`reserve` 의
        ``designated_seats`` 에 넘길 수 있습니다.

        ``car_number`` 는 :attr:`~srt_mobile_api.models.SeatSelectionPage.cars` 의
        ``car_number`` 값이고, ``passengers``/``seat_count``/``cabin_class`` 는
        :meth:`get_seat_page` 에 준 것과 같게 주면 됩니다.

        **열차번호를 다섯 자리로 0 채움해 보냅니다** — 그 하나가 좌석배치도와
        147바이트짜리 경고 껍데기를 가릅니다
        (:data:`~srt_mobile_api.payloads.SEAT_TRAIN_NUMBER_LENGTH`).

        서버가 거절하면(``"0#<메시지>"``)
        :class:`~srt_mobile_api.errors.SrtSeatUnavailableError` 이지 프로토콜 오류가
        아닙니다. 로그인이 필요하고, 응답이 로그인 페이지면
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 입니다.
        """
        if seat_count is None:
            seat_count = str((passengers or PassengerCounts()).total)
        with self._session_guard():
            raw = self.http.post_html_form(
                "/arc/selectListArc02011_n.do",
                seat_grid_payload(
                    train,
                    car_number,
                    cabin_class,
                    seat_count,
                    seat_attr_code=seat_attr_code,
                ),
                # The seat page is where this form lives, so it is the page the
                # app would be on. The 2026-07-26 capture established that the
                # server does not care -- the grid came back with and without a
                # Referer -- so this is the app's flow rather than a requirement.
                referer=f"{self.config.base_url}/arc/selectListArc02012_n.do",
            )
            return parse_seat_grid_response(
                raw, car_number=car_number, cabin_class=cabin_class
            )

    def get_timetable(self, train: TrainSummary) -> TimetablePage:
        """열차 하나의 정차역별 시간표를 읽습니다.

        ``POST /ara/selectListAra12009_n.do``, 어느 열차인지는 검색 행 ``train`` 이
        말합니다. 반환 :class:`~srt_mobile_api.models.TimetablePage` 는 HTML 에 정차역 행
        (:class:`~srt_mobile_api.models.TimetableRow`)이 붙은 것입니다.

        **역 이름은 HTML 안에 없습니다.** 서버는 코드만 내려보내고 WebView 가
        ``getStationNameByCode('0551')`` 로 채웁니다. 이 파서는 앱과 같은 표를 담은
        :mod:`srt_mobile_api.stations` 로 이름을 해결합니다.

        로그인이 필요합니다.
        """
        with self._session_guard():
            raw = self.http.post_form(
                "/ara/selectListAra12009_n.do",
                timetable_payload(train),
                accept="text/html, */*; q=0.01",
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )["html"]
            return parse_timetable_page(raw)

    def get_fare(
        self,
        train: TrainSummary,
        passengers: PassengerCounts | None = None,
    ) -> FarePage:
        """열차 한 다리의 운임·요금 표를 읽습니다.

        ``POST /ara/selectListAra13010_n.do``. ``passengers`` 를 생략하면 성인 1명
        (:class:`~srt_mobile_api.models.PassengerCounts` 의 기본값)으로 묻습니다. 반환은
        :class:`~srt_mobile_api.models.FarePage`.

        **둘째 다리 표는 읽지 않습니다.** 이 페이지는 환승 여정용이라 ``trainPayInfo1``
        (첫 다리)과 ``trainPayInfo22``(둘째 다리) 두 표를 렌더링하는데, 이 요청은 한
        다리만 말할 수 있어 둘째 표는 금액이 ``0원`` 인 자리표시자로 옵니다. 그것까지
        읽으면 "어른 일반실 → 0" 처럼 돈에 대해 조용히 틀린 답이 나옵니다.

        로그인이 필요합니다.
        """
        with self._session_guard():
            raw = self.http.post_form(
                "/ara/selectListAra13010_n.do",
                fare_payload(train, passengers or PassengerCounts()),
                accept="text/html, */*; q=0.01",
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )["html"]
            return parse_fare_page(raw)

    def _submit_reservation(
        self,
        route: str,
        build_form: Callable[[str, SrtSession], dict[str, str]],
        *,
        consent: MutationConsent,
        netfunnel_key: str | None,
    ) -> MutationPreview | SrtReservationHold:
        """예약을 보내는 단 하나의 경로. :meth:`reserve` 와
        :meth:`reserve_transfer` 가 함께 씁니다.

        consent 게이트 → 세션 필수 → dry-run 미리보기 → NetFunnel 키 → build_form
        → 전송 → 자리 반납 → PNR 건지기. 재시도 없음. ``build_form`` 은 키가 생긴
        뒤 정확히 한 번 불립니다.
        """
        require_mutation_consent(consent, "reserve")
        session = self.session.current
        if session is None:
            raise SrtAuthError("SRT reservation requires an authenticated session")
        if consent.dry_run:
            # Built inside the dry-run branch with the caller's key (or none):
            # a preview must not acquire anything, so it performs no I/O at all.
            return MutationPreview(
                category="reserve",
                method="POST",
                route=route,
                payload=build_form(netfunnel_key or "", session),
            )
        booking_referer = f"{self.config.base_url}/ara/ara0101v.do"
        with self._session_guard():
            key = (
                netfunnel_key
                if netfunnel_key
                else self._get_act10_key(booking_referer)
            )
            # build_form inside try so a guard failure still releases the slot.
            try:
                form = build_form(key, session)
                response = self.http.post_mutation_form(
                    route,
                    form,
                    consent=consent,
                    category="reserve",
                    # Inferred referer: app reserves from the search-result page.
                    referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
                )
            finally:
                # Best-effort slot release; must never mask the hold/PNR result.
                self._release_netfunnel_slots(booking_referer)
            # parse_reservation_hold_response salvages PNR from malformed
            # responses; refuses to manufacture one when server declared failure.
            hold = parse_reservation_hold_response(response)
            # Attach the journey count the form sent (response doesn't say it).
            sent_journey_count = form.get("jrnyCnt", "1")
            if sent_journey_count != hold.journey_count:
                hold = dataclasses.replace(
                    hold, journey_count=sent_journey_count
                )
            return hold

    def reserve(
        self,
        train: TrainSummary,
        *,
        consent: MutationConsent,
        passengers: PassengerCounts | None = None,
        seat_type: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
        netfunnel_key: str | None = None,
        standby: bool = False,
        round_trip: bool = False,
        designated_seats: SeatDesignation | None = None,
        seat_attr_code: SrtSeatAttrCode | None = None,
    ) -> MutationPreview | SrtReservationHold:
        """열차 한 편에 개인예약 홀드를 만듭니다. consent 게이트.

        ``POST /arc/selectListArc05013_n.do``. 기본 ``dry_run=True`` 면
        :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려주고 네트워크 무사용.
        ``dry_run=False`` 면 실전송 → :class:`~srt_mobile_api.models.SrtReservationHold`.

        재시도 없음(이중예약 방지). 파싱 실패해도 PNR 있으면 최소 홀드 건짐.
        ``standby`` = 예약대기(``jobId=1102``, ara0101v.js:90, ara1001l.js:1445-1448).
        ``round_trip`` = ``rtnDv=1``; 두 번째 요청을 보내지 않으므로 각각 호출.
        ``designated_seats`` = 좌석지정(``jobId=1103``).
        확인된 조합: 성인 1명·1여정·일반실·직통. 나머지 미검증.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            lambda key, session: personal_reservation_payload(
                train,
                passengers or PassengerCounts(),
                seat_type=seat_type,
                netfunnel_key=key,
                window_seat=window_seat,
                standby=standby,
                round_trip=round_trip,
                designated_seats=designated_seats,
                seat_attr_code=seat_attr_code,
                membership_number=session.membership_number,
            ),
            consent=consent,
            netfunnel_key=netfunnel_key,
        )

    def reserve_transfer(
        self,
        itinerary: TransferItinerary,
        *,
        consent: MutationConsent,
        passengers: PassengerCounts | None = None,
        seat_type: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
        netfunnel_key: str | None = None,
        seat_attr_code: SrtSeatAttrCode | None = None,
    ) -> MutationPreview | SrtReservationHold:
        """환승 예약 — 두 다리를 한 요청으로 예약합니다. consent 게이트.

        경로도 consent 카테고리도 :meth:`reserve` 와 같습니다
        (``/arc/selectListArc05013_n.do``, ``"reserve"``). ``jrnyTpCd="14"`` +
        ``jrnyCnt="2"`` (ara0101v.js:302-303). 전송 경로·안전 속성 전부 동일.

        인자가 :class:`~srt_mobile_api.models.TransferItinerary` 인 것은 이음새
        검사를 생성 시점에 하기 위해서입니다. ``round_trip``·``standby``·단체·좌석지정
        조합 불가.

        **2026-07-31 실서버 확인.** 동대구(0015)→목포(0041), 열차 304 + 653, 오송
        환승, 성인 1명으로 ``SUCC``/``IRR000018`` 을 받았습니다(PNR
        ``320260733059548``). 유추였던 슬롯 2 키 5개가 그대로 받아들여졌습니다.
        확인된 것은 **1인·일반실·직통 아님·편도** 한 건입니다.

        **취소는 ``jrnyCnt="2"`` 로 해야 합니다.** 이 예약을 PNR 문자열만으로
        취소하면 :meth:`cancel` 이 ``jrnyCnt="1"`` 을 보내고 서버가
        ``FAIL``/``ERR800052`` 로 거절합니다 — 홀드는 그대로 남습니다. 홀드 객체를
        넘기면 자기 값을 기억하므로 맞고, PNR 만 있으면 ``journey_count="2"`` 를
        직접 줘야 합니다.

        **환승 조회 결과에는 코레일 열차가 섞여 옵니다.** 같은 날 부산→익산 의 환승
        5개 중 3개는 구간 하나 이상이 KTX(``stlbTrnClsfCd="00"``) 또는
        KTX-산천(``"07"``) 이었고, 그런 여정을 넘기면
        :func:`~srt_mobile_api.payloads.personal_reservation_payload` 가
        ``reservation requires an SRT train (service_class_code '17')`` 로 전송 전에
        거절합니다. 예약할 수 있는 것은 양쪽 구간이 다 ``"17"`` 인 여정뿐입니다.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            lambda key, _session: transfer_reservation_payload(
                itinerary,
                passengers or PassengerCounts(),
                seat_type=seat_type,
                netfunnel_key=key,
                window_seat=window_seat,
                seat_attr_code=seat_attr_code,
            ),
            consent=consent,
            netfunnel_key=netfunnel_key,
        )

    def cancel(
        self,
        reservation: SrtReservationHold | str,
        *,
        consent: MutationConsent,
        journey_count: str | None = None,
    ) -> MutationPreview | SrtCancelResult:
        """미결제 예약을 취소합니다. consent 게이트.

        ``POST /ard/selectListArd02045_n.do``, 본문 ``pnrNo``/``jrnyCnt``/``rsvChgTno``.
        ``reservation`` 은 :class:`~srt_mobile_api.models.SrtReservationHold` 또는
        PNR 문자열. ``journey_count`` 생략 시 홀드가 기억하는 값(환승 ``"2"``), 맨
        PNR 이면 ``"1"``. 기본 ``dry_run=True``.
        """
        require_mutation_consent(consent, "cancel")
        if self.session.current is None:
            raise SrtAuthError("SRT cancellation requires an authenticated session")
        route = "/ard/selectListArd02045_n.do"
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit. The builder never refuses over a journey
        # count formatting problem — see unpaid_reservation_cancel_payload.
        form = unpaid_reservation_cancel_payload(
            reservation, journey_count=journey_count
        )
        if consent.dry_run:
            return MutationPreview(
                category="cancel",
                method="POST",
                route=route,
                payload=form,
            )
        with self._session_guard():
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="cancel",
            )
            return parse_unpaid_cancel_response(response)

    def register_discount_coupon(
        self,
        coupon_number: str,
        coupon_password: str,
        *,
        consent: MutationConsent,
    ) -> MutationPreview | SrtCouponRegistrationResult:
        """할인쿠폰을 계정에 등록합니다(할인쿠폰 등록). consent 게이트가 있고, 전송은 막혀 있습니다.

        ``POST /arb/selectListArb02A01_n.do``, 본문은 ``{dscp_no, dscp_pwd}``.
        :meth:`get_discount_coupons` 가 읽는 페이지의 나머지 절반으로, 그 페이지의
        ``couponReg()`` 가 ``#couponInfo`` 를 여기로 보내며
        ``resultMap[0].RTNCD``/``.MSG`` 를 읽습니다.

        consent 카테고리는 다섯 번째인 ``"coupon"`` 입니다. 쿠폰 등록은 소지
        크리덴셜을 소진하는 일이라 ``reserve`` 나 ``payment`` 에 얹지 않았습니다.
        ``require_mutation_consent(consent, "coupon")`` 과 인증 세션이 필요하고, 두
        검사 모두 ``dry_run`` 분기보다 앞입니다.

        **보낼 수 없습니다.** ``"coupon"`` 은
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 밖이라
        ``dry_run=False`` 로 불러도 전송 계층이
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 로 거절합니다.

        미리보기는 ``dscp_no`` 와 ``dscp_pwd`` 를 모두 가립니다
        (:data:`~srt_mobile_api.redaction.SENSITIVE_KEYS`). 입력 검증은 페이지 자신의
        규칙으로, 번호는 숫자만 최대 10자리, 비밀번호는 최대 4자이고 둘 다 비어 있으면
        안 됩니다.

        **성공은 요청이 접수됐다는 뜻이지 쿠폰이 보인다는 뜻이 아닙니다**(쿠폰등록
        요청을 완료하였습니다 … 바로 조회 되지 않을 수 있습니다). 등록 직후
        :meth:`get_discount_coupons` 가 아무것도 못 봐도 정상일 수 있습니다.

        경로·필드명·응답 키는 서버가 렌더링하는 실제 페이지에서 읽었습니다. v2.0.41
        번들에는 ``/arb/`` 라우트가 없고, 번들이 뒷받침하는 것은 어휘뿐입니다
        (``js/common/messages.js:111-113``, ``sub/main.html:475`` 의 ``DSCP_YN``).
        """
        require_mutation_consent(consent, "coupon")
        if self.session.current is None:
            raise SrtAuthError(
                "SRT coupon registration requires an authenticated session"
            )
        # Built before the dry-run branch so a preview validates exactly what a
        # send would transmit -- and, here, so a malformed coupon is rejected by
        # the same builder whether or not anything could ever be sent.
        form = coupon_registration_payload(
            SrtCouponRegistrationRequest(
                coupon_number=coupon_number,
                coupon_password=coupon_password,
            )
        )
        if consent.dry_run:
            return MutationPreview(
                category="coupon",
                method="POST",
                route=COUPON_REGISTRATION_PATH,
                payload=form,
            )
        with self._session_guard():
            response = self.http.post_mutation_form(
                COUPON_REGISTRATION_PATH,
                form,
                consent=consent,
                category="coupon",
                referer=f"{self.config.base_url}{COUPON_LIST_PATH}",
            )
            return parse_coupon_registration_response(response)

    def pay_with_card(
        self,
        reservation: SrtReservationSummary,
        card: SrtPaymentCard,
        *,
        consent: MutationConsent,
        passenger_count: str | None = None,
        settlement_date: str | None = None,
    ) -> MutationPreview | SrtPaymentResult:
        """미결제 PNR 을 카드로 결제합니다. consent 게이트.

        ``POST /ata/selectListAta09036_n.do``, 31개 필드. 세션에 회원번호 필수.
        ``reservation`` 은 :meth:`get_reservations` 행. 금액은 ``rcvdAmt`` 에서만.
        기본 ``dry_run=True`` → 민감정보 가린 미리보기. ``dry_run=False`` 면
        ``require_card_kind_claim`` 추가 필요.

        확인된 조합: 1여정·성인 1명·일반실·개인카드·일시불(``SUCC``/``IRT000000``).
        ``Ata09*`` 전체가 v2.0.41 번들 0-hit. 출처가 얇은 경로입니다.
        """
        require_mutation_consent(consent, "payment")
        session = self.session.current
        if session is None:
            raise SrtAuthError("SRT card payment requires an authenticated session")
        membership_number = session.membership_number
        if not membership_number:
            raise SrtAuthError(
                "SRT card payment requires the account's membership number "
                "(userMap.MB_CRD_NO); the session carried none, which is how "
                "the app itself spells 'not logged in'"
            )
        route = "/ata/selectListAta09036_n.do"
        # Form built before dry-run branch so preview validates the same way.
        form = card_payment_payload(
            reservation,
            card,
            membership_number=membership_number,
            # `is None`, not `or`: an explicitly supplied but unusable value
            # must be REFUSED by the builder, not silently replaced with today.
            # Everywhere else on this path an unusable input raises rather than
            # being substituted (see payloads._payment_amount), and a payment
            # settled under a date the caller did not choose is the same class
            # of quiet wrongness.
            settlement_date=(
                time.strftime("%Y%m%d") if settlement_date is None else settlement_date
            ),
            passenger_count=passenger_count,
        )
        if consent.dry_run:
            return MutationPreview(
                category="payment",
                method="POST",
                route=route,
                payload=form,
            )
        # Only on transmit path: dry run needs no card-kind claim to preview.
        require_card_kind_claim(consent)
        with self._session_guard():
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="payment",
            )
            return parse_card_payment_response(response)

    def get_refund_ticket_info(self, pnr_no: str) -> SrtRefundTicketInfo:
        """발권된 승차권의 환불 식별 정보를 읽습니다 — 환불 2단계 중 1단계.

        ``POST /atc/getListAtc14087.do``, **본문 없음**. 승차권을 지목하는 것은
        ``Referer`` 로 실려 가는 ``/common/ATC/ATC0201L/view.do?pnrNo=<PNR>``
        입니다. 응답의 ``outDataSets.dsOutput1[0]`` 이
        :class:`~srt_mobile_api.models.SrtRefundTicketInfo` 가 되고, 그대로
        :meth:`refund` 에 넘기면 됩니다. 로그인이 필요합니다.

        consent 게이트가 아니라 읽기 경로를 탑니다
        (:data:`~srt_mobile_api.safety.READ_ONLY_ROUTES`). 그 분류는 증명이 아니라
        추론입니다 — 서버가 부작용 없다고 말해 준 적은 없습니다.

        ``pnr_no`` 는 ASCII 영숫자와 하이픈 1~32자만 받고, 어기면 요청 전에
        :class:`ValueError` 입니다. ``Referer`` URL 에 그대로 끼워 넣는 값이라 다른
        문자는 질의 파라미터를 몰래 붙일 수 있습니다. 이 ``Referer`` 는 이 요청에만
        붙습니다.

        없는 PNR 도 오류가 아니라 정상 업무 응답(``WRT300005``, "조회자료가
        없습니다.")으로 돌아옵니다. 경로는 v2.0.41 번들에 없고 참조 구현 하나만 이걸
        압니다.
        """
        if not isinstance(pnr_no, str) or not pnr_no.strip():
            raise ValueError("refund ticket info requires a non-empty PNR")
        pnr = pnr_no.strip()
        # ASCII-only, length-bounded: goes into Referer URL verbatim.
        if _REFUND_PNR_RE.fullmatch(pnr) is None:
            raise ValueError(
                "refund ticket info PNR must be 1-32 ASCII alphanumerics or "
                "hyphens; it is interpolated into the Referer URL this endpoint "
                "gates on"
            )
        with self._session_guard():
            return parse_refund_ticket_info_response(
                self.http.post_form(
                    "/atc/getListAtc14087.do",
                    # No body. The reference implementation POSTs bare, and the
                    # Referer is what identifies the ticket.
                    None,
                    accept="application/json, text/javascript, */*; q=0.01",
                    referer=(
                        f"{self.config.base_url}"
                        f"/common/ATC/ATC0201L/view.do?pnrNo={pnr}"
                    ),
                )
            )

    def refund(
        self,
        ticket_info: SrtRefundTicketInfo,
        *,
        consent: MutationConsent,
    ) -> MutationPreview | SrtRefundResult:
        """발권까지 끝난 승차권을 환불합니다 — 2단계 흐름의 둘째. consent 게이트가 있습니다.

        ``POST /atc/selectListAtc02063_n.do``, 7개 필드.
        ``require_mutation_consent(consent, "refund")`` 와 인증 세션이 필요하고, 두
        검사 모두 ``dry_run`` 분기보다 앞입니다. 성공하면
        :class:`~srt_mobile_api.models.SrtRefundResult` 입니다.

        ``ticket_info`` 는 :meth:`get_refund_ticket_info` 가 준 것입니다. **두 단계를
        일부러 합치지 않았습니다** — 이 메서드가 스스로 1단계를 부르지 않으므로
        거절당한 환불은 아무 요청도 남기지 않고, dry run 이 통신을 전혀 하지
        않습니다.

        ``dry_run=True``(기본)면 반환비밀번호·구매자명·PNR 을 가리고 판매 식별자는
        남긴 :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려줍니다.

        확인된 것은 1여정·성인 1명 한 건이고(``SUCC``/``IRT200277``), 성공 뒤 계정에는
        예약도 승차권도 남지 않습니다.

        출처는 :meth:`pay_with_card` 보다도 얇습니다 — 참조 구현 **하나**에만 있고
        ``Atc02063`` 은 v2.0.41 번들에서 0-hit 입니다. 필드명 ``tkRetPwd``·``psgNm``
        은 srtgo 철자이고 서버가 그대로 받습니다. 앱 쪽 철자 ``retPwd``/``buyPsNm``
        은 로컬 승차권 캐시 핸들러의 것이라 이 요청과 무관합니다.
        """
        require_mutation_consent(consent, "refund")
        if self.session.current is None:
            raise SrtAuthError("SRT refund requires an authenticated session")
        route = "/atc/selectListAtc02063_n.do"
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit, matching cancel and pay_with_card.
        form = refund_payload(ticket_info)
        if consent.dry_run:
            return MutationPreview(
                category="refund",
                method="POST",
                route=route,
                payload=form,
            )
        with self._session_guard():
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="refund",
            )
            return parse_refund_response(response)
