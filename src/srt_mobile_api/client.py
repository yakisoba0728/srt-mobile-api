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
    :mod:`~srt_mobile_api.models` 의 불변 데이터클래스로 돌려준다.

    **인자 없이 ``SrtClient()`` 로 만들면 바로 동작한다.**
    :class:`~srt_mobile_api.config.SrtConfig` 는 타임아웃·User-Agent·device key 를
    바꿀 때만 넘기며, 정규 SRT 오리진 두 개 말고는 가리키지 못한다.
    ``transport``/``clock``/``sleep`` 은 테스트용 주입점이다.

    조회는 :meth:`login` 뒤에 바로 부르면 된다. 상태를 바꾸는 여섯 메서드
    (:meth:`reserve`, :meth:`reserve_transfer`, :meth:`cancel`,
    :meth:`pay_with_card`, :meth:`refund`, :meth:`register_discount_coupon`)는
    :class:`~srt_mobile_api.consent.MutationConsent` 를 키워드로 **반드시** 받고,
    동의가 없으면 아무것도 만들기 전에
    :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 로 막힌다. 기본
    동의는 ``dry_run=True`` 라서 보낼 폼을 마스킹해 담은
    :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려주고 통신하지 않는다.

    정리는 :meth:`close` 로 한다. ``with`` 문은 지원하지 않는다(``__enter__`` 가
    없다). 쿠키까지 버리려면 :meth:`clear_session` 을 따로 부른다.

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
        """내부 HTTP 커넥션 풀을 닫는다.

        세션 쿠키와 저장된 :class:`~srt_mobile_api.models.SrtSession` 은 지우지 않는다
        — 그것은 :meth:`clear_session` 의 일이다. 서버로는 아무것도 보내지 않는다.

        ``with`` 문은 지원하지 않으므로 직접 부르거나 ``try``/``finally`` 로 감싼다.
        """
        self.http.close()

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        """아이디와 비밀번호로 로그인하고 :class:`~srt_mobile_api.models.SrtSession` 을 돌려준다.

        ``login_id`` 는 이메일·휴대폰번호·회원번호 중 아무거나 된다. 형태를 보고
        ``srchDvCd`` 를 고른다 — 이메일이면 ``"2"``, ``01X`` 로 시작하는 휴대폰이면
        ``"3"``(하이픈은 떼고 보낸다), 그 외에는 회원번호로 보고 ``"1"``.
        ``login_type`` 을 주면 그 값이 이긴다.

        호출하면 먼저 기존 쿠키를 버린다. 응답의 ``userMap.RTNCD`` 가 ``"Y"`` 여야
        성공이고, 그 뒤 ``/main/main.do`` 와 ``/ara/ara0101v.do`` 를 실제로 읽어
        인증됐는지 확인한 다음에야 세션을 저장한다.

        실패는 전부 :class:`~srt_mobile_api.errors.SrtAuthError` 다 — 없는 회원과 틀린
        비밀번호를 서버가 구분해 주지 않는다. IP 차단은 그 하위 클래스인
        :class:`~srt_mobile_api.errors.SrtIpBlockedError`. 어떤 이유로 실패하든 세션은
        다시 비워진다.
        """
        return self.session.login(login_id, password, login_type=login_type)

    def clear_session(self) -> None:
        """쿠키 항아리를 비우고 저장된 세션을 버린다.

        서버로는 아무것도 보내지 않는다. 로그아웃 요청이 아니라 클라이언트 쪽 상태만
        지우는 것이라, 서버 세션은 스스로 만료될 때까지 남아 있다.
        """
        self.session.clear_session()

    def logout(self) -> None:
        """:meth:`clear_session` 의 다른 이름 — 로컬 쿠키와 세션만 버린다.

        서버에 로그아웃 요청을 보내지 않는다. 이름 때문에 서버 세션까지 끊긴다고
        읽히기 쉬워서 적어 둔다.
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
        """로그인 뒤 메인 화면의 HTML 을 파싱 없이 돌려준다.

        ``GET /main/main.do?deviceId=<device_key>``. 반환
        :class:`~srt_mobile_api.models.HtmlPage` 에는 원본 ``raw`` 와 태그를 걷어낸
        ``text`` 뿐이고 구조화된 필드는 없다.

        로그인 세션이 필요하다. 서버가 로그인 페이지를 돌려주면 HTTP 계층이
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 를 내고 저장된 세션도
        같이 비워진다.
        """
        with self._session_guard():
            raw = self.http.get_text("/main/main.do", params={"deviceId": self.config.device_key})
            return parse_html_page(raw, context="main page")

    def get_booking_page(self) -> HtmlPage:
        """승차권 예매 화면(``GET /ara/ara0101v.do``)의 HTML 을 파싱 없이 돌려준다.

        검색·예약 폼이 서버에서 렌더링돼 실려 오는 페이지다. 이 클라이언트는 검색과
        예약 때 이 경로를 Referer 로 쓰고, 여기 박혀 있는 MY SRT 메뉴에서
        :meth:`get_discount_coupons` 와 :meth:`get_public_discounts` 의 경로를 찾았다.

        반환은 파싱되지 않은 :class:`~srt_mobile_api.models.HtmlPage` 다. 로그인 세션이
        필요하고, 미인증 응답은
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 로 올라온다.
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
        """공지사항 응답을 서버가 준 ``dict`` 모양 그대로 돌려준다.

        ``POST /main/noticeList.do`` (``pageId=MB0101000000``). 모양을 바꾸지 않는
        구버전 인터페이스이고, 타입이 붙은 행이 필요하면
        :meth:`get_typed_notice_list` 를 쓴다 — 요청은 완전히 같고 파싱만 다르다.

        공지가 하나도 없으면 ``noticeList`` 가 빈 리스트인 정상 응답이며 예외가 아니다.
        """
        return self._get_notice_list_result().raw

    def get_typed_notice_list(self) -> NoticeListResult:
        """같은 공지 조회를 :class:`~srt_mobile_api.models.NoticeListResult` 로 돌려준다.

        :meth:`get_notice_list` 와 요청은 완전히 같다. 차이는 반환뿐 — 각 행이 불변
        :class:`~srt_mobile_api.models.Notice` 이고, ``SUBJ``/``BODY``/``CREATE_DATE``/
        ``IS_MAIN``/``IS_NOTICE``/``PAGE_ID`` 가 문자열이 아니면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 로 거른다. 서버 응답 전체는
        :attr:`~srt_mobile_api.models.NoticeListResult.raw` 에 남는다.

        공지가 없으면 빈 ``notices`` 가 정상이다.
        """
        return self._get_notice_list_result()

    def get_ticket_list(self, page_no: int = 0) -> HtmlPage:
        """로그인한 계정의 승차권 확인 페이지 HTML 을 파싱 없이 돌려준다.

        ``GET /atc/selectListAtc14017_n.do?pageNo=<page_no>``, 발권이 끝난 승차권을
        보여 주는 화면이다. 예약을 구조화된 행으로 받으려면 :meth:`get_reservations`
        를 쓴다 — 그쪽은 이웃 경로 ``Atc14016`` 을 POST 해 JSON 을 받는 다른 읽기다.

        반환 :class:`~srt_mobile_api.models.HtmlPage` 에는 승차권이 파싱돼 있지 않다.

        로그인이 필요하고, 이 읽기는 응답이 로그인 페이지인지 명시적으로 확인해
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 를 낸다. 만료된 세션이
        빈 승차권 목록으로 읽히는 일을 막기 위한 것이다.
        """
        with self._session_guard():
            raw = self.http.get_text(
                "/atc/selectListAtc14017_n.do", params={"pageNo": str(page_no)}
            )
            return parse_html_page(raw, context="ticket list", require_authenticated=True)

    def get_discount_coupons(self) -> DiscountCouponList:
        """계정이 보유한 할인쿠폰 목록을 읽는다.

        ``GET /apa/selectListApa03020_n.do``, 파라미터 없음. 반환은
        :class:`~srt_mobile_api.models.DiscountCouponList`. 로그인이 필요하다.

        **쿠폰이 하나도 없으면 빈 목록이 정상 반환이다** — 페이지가 "보유한 쿠폰이
        없습니다." 라고 말하는 경우이고 예외가 아니다. 목록도 없고 그 문구도 없으면,
        또는 둘이 동시에 있으면 :class:`~srt_mobile_api.errors.SrtProtocolError` 다.

        **읽기이고 읽기일 뿐이다.** 같은 페이지에 쿠폰 등록 폼이 들어 있지만 등록은
        다른 경로(``POST /arb/selectListArb02A01_n.do``)이고
        :meth:`register_discount_coupon` 의 일이다. 이 경로에는 GET 만 등록돼 있어서
        쿠폰번호와 비밀번호가 조회를 타고 나갈 수 없다.

        경로 근거: v2.0.41 번들에는 ``/apa/`` 라우트가 아예 없고, 서버가 렌더링하는
        MY SRT 메뉴(``/ara/ara0101v.do``)에서 찾았다. 빈 상태는 2026-07-26 실검증,
        채워진 상태는 미검증 — 필드명 근거는
        :class:`~srt_mobile_api.models.DiscountCoupon` 참고.
        """
        with self._session_guard():
            return parse_discount_coupon_page(
                self.http.get_text(
                    COUPON_LIST_PATH,
                    referer=f"{self.config.base_url}/ara/ara0101v.do",
                )
            )

    def get_public_discounts(self) -> PublicDiscountPage:
        """계정이 승인받은 공공할인 자격을 읽는다.

        ``GET /common/ARA/ARA0301V/view.do``, 할인 승차권 페이지, 파라미터 없음.
        반환은 :class:`~srt_mobile_api.models.PublicDiscountPage`. 로그인이 필요하다.

        **자격이 하나도 없는 계정도 정상 반환이다** —
        :attr:`~srt_mobile_api.models.PublicDiscountPage.is_eligible` 가 ``False`` 로
        올 뿐 예외가 아니다. 페이지 자신은 알림을 띄우고 메인으로 튕기지만 이 메서드는
        그러지 않는다. 자격을 가진 계정의 응답은 미검증이다(2026-07-26 실검증은 여덟
        개 ``dataNCheck`` 플래그가 전부 빈 계정 하나뿐).

        **할인 승차권 검색은 하지 않고, 할 수도 없다.** 이 페이지가 곧 그 검색 폼이고,
        검색은 :meth:`search_public_discount_trains` 가 따로 보낸다.

        공공할인의 승객 어휘는 :class:`~srt_mobile_api.models.PassengerCounts` 보다
        넓다 — 청소년(``04``) 아래에는 어느 ``commCode.js`` 에도 없는 ``psgTpCd6`` 이
        있다. :mod:`~srt_mobile_api.discounts` 에 기록만 하고 예약 페이로드에는 잇지
        않았다.
        """
        with self._session_guard():
            return parse_public_discount_page(
                self.http.get_text(
                    PUBLIC_DISCOUNT_PAGE_PATH,
                    referer=f"{self.config.base_url}/ara/ara0101v.do",
                )
            )

    def get_reservations(self, page_no: int = 0) -> SrtReservationListResult:
        """계정의 예약/발권 목록을 구조화된 행으로 읽는다.

        ``POST /atc/selectListAtc14016_n.do``. 반환은
        :class:`~srt_mobile_api.models.SrtReservationListResult`. 로그인이 필요하다.

        **예약을 열거할 수 있는 유일한 읽기다.** PNR 을 잃어버린 홀드로 돌아가는
        길이기도 해서(``scripts/recover_hold.py --list`` 가 이걸 부른다), 파서는 모양이
        예상과 달라도 PNR 만은 건져내도록 쓰여 있다
        (:func:`~srt_mobile_api.parsers.parse_reservation_list_response`).

        :meth:`get_ticket_list` 와 같은 읽기가 아니다. 그쪽은 이웃 경로 ``Atc14017`` 을
        GET 해 HTML 을 주고, 이쪽은 ``Atc14016`` 을 POST 해 행을 준다.

        ``page_no`` 는 ``pageNo`` 로 나가고, 결과의
        :attr:`~srt_mobile_api.models.SrtReservationListResult.total_page_count`
        (``totPageCnt``)가 전체 페이지 수를 말한다.

        **예약이 없으면 빈 결과가 정상이다.** 2026-07-26 실검증에서 서버는
        ``strResult="SUCC"`` / ``IRZ000005`` / "조회할 자료가 없습니다." 를
        ``trainListMap: []`` 와 함께 보냈고, 이 메서드는 빈 결과를 돌려줬다. 채워진
        모양은 미검증이고 행 필드명은 srtgo(``srt.py:1069-1082``) 출처다.
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
        """역 선택 팝업의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0501P/view.do``. 앱이 출발·도착역을 고를 때 여는
        팝업이고, 넘긴 이름·코드 네 개가 현재 선택값으로 박힌 화면이 돌아온다.
        반환 :class:`~srt_mobile_api.models.HtmlPage` 에 역 목록이 파싱돼 있지 않다.

        **역을 고르려고 이 호출을 할 필요는 없다.** 이름과 코드 표는 앱 자신의 것을
        :mod:`~srt_mobile_api.stations` 로 이미 싣고 있다.

        로그인이 필요하고, 미인증 응답은
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 다.
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
        """노선도 방식 역 선택 팝업의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0502P/view.do``, 인자 없음 — 폼은 앱이 처음 열 때 보내는
        고정값으로 채운다. :meth:`get_station_selector` 의 목록형에 대응하는 노선도형
        화면이고, 반환은 똑같이 파싱되지 않은
        :class:`~srt_mobile_api.models.HtmlPage` 다. 역 코드는
        :mod:`~srt_mobile_api.stations` 에서 얻는 편이 낫다.

        로그인이 필요하다.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0502P/view.do",
                station_map_selector_payload(),
                context="station map selector",
            )

    def get_date_selector(self, date: str) -> HtmlPage:
        """날짜 선택 팝업의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0401P/view.do``. ``date`` 는 ``YYYYMMDD`` 여야 하고
        아니면 요청 전에 :class:`ValueError` 다. 반환
        :class:`~srt_mobile_api.models.HtmlPage` 에 예매 가능일이 파싱돼 있지 않다 —
        앱이 달력을 그리는 데 쓰는 원본 화면이다.

        로그인이 필요하다.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0401P/view.do",
                date_selector_payload(date),
                context="date selector",
            )

    def get_passenger_selector(self, passengers: PassengerCounts) -> HtmlPage:
        """승차인원 선택 팝업의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0901P/view.do``. ``passengers`` 의 인원 구성이 그대로
        폼에 실려 나가고, 그 값이 채워진 팝업 화면이 돌아온다. 반환은 파싱되지 않은
        :class:`~srt_mobile_api.models.HtmlPage` 다.

        검색이나 예약과는 무관하다 — :meth:`search_trains` 나 :meth:`reserve` 에 인원을
        넘기는 데 이 호출은 필요 없다.

        로그인이 필요하다.
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
        """좌석 위치·속성 선택 팝업의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0701P/view.do``. 기본값은 앱이 처음 여는 상태와 같다 —
        ``request_seat_attr_code="015"``, ``location_seat_attr_code="000"``,
        ``seat_name="일반/기본"``. 반환
        :class:`~srt_mobile_api.models.HtmlPage` 에 선택 가능한 옵션이 파싱돼 있지 않다.

        실제 좌석을 보고 고르는 것은 :meth:`get_seat_page` 와 :meth:`get_seat_grid` 다.

        로그인이 필요하다.
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
        """열차 종류 선택 화면의 HTML 을 파싱 없이 돌려준다.

        ``POST /common/ARA/ARA0201V/view.do``. 기본값 ``"109"``/``"전체"`` 는
        :class:`~srt_mobile_api.models.TrainSearchQuery` 의 ``train_group_code`` 기본값과
        같은 값이다. 반환 :class:`~srt_mobile_api.models.HtmlPage` 에 선택지가 파싱돼
        있지 않다.

        로그인이 필요하다.
        """
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0201V/view.do",
                train_group_selector_payload(train_group_code, train_group_name),
                context="train group selector",
            )

    def get_mutual_verification(self) -> MutualVerificationResult:
        """상호검증값(``mutMrkVrfCd``)을 발급받는다.

        ``POST /ara/selectListAra10130_n.do``, **본문 없음**. 앱은 이 값을 코레일 연계
        (KTX) 예약 분기에서 네이티브 브리지로 넘기는 데 쓴다(``ara1001l.js:229-241``).
        이 라이브러리의 예약 경로는 쓰지 않으므로, 발급까지가 전부다.

        **로그인이 필요 없다.** 2026-07-26 실검증에서 세션 쿠키 없이도 ``SUCC`` 와 새
        ``mutMrkVrfCd`` 를 돌려줬다 — 이 클라이언트의 다른 읽기와 달리 공개 경로다.

        반환은 :class:`~srt_mobile_api.models.MutualVerificationResult`. ``strResult``
        가 ``"FAIL"`` 이면 :class:`~srt_mobile_api.errors.SrtAppError` 계열로 오르고,
        ``mutMrkVrfCd`` 가 비어 있으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 다. ``msgCd`` 는 정보성이라
        없어도 되고(:attr:`~srt_mobile_api.models.MutualVerificationResult.message_code`
        가 ``None``), 실제 행에는 모델에 없는 ``wctNo``/``uuid``/``cgPsId`` 도 함께
        와서 ``raw`` 로 닿을 수 있다.
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
        """Acquire an ``act_10`` queue key, WAITING if the queue engages.

        Sends ``getTidChkEnter`` (5101) once. A pass (200, or a 300 bypass that
        carries no key) returns immediately, which is what happens at normal
        load and is the only outcome this repository has ever observed live.

        A 201/202 means we are actually in line, and the app's answer to that is
        to poll ``chkEnter`` (5002) until admitted
        (``_showResultChkEnter`` arms ``setTimeout(chkEnterCont, ttl * 1000)``).
        Before this, we simply failed there and the search died of a queue that
        was working as designed.

        The loop is BOUNDED, unlike the app's. The app polls forever behind a
        wait popup a human can close; a library has no such escape hatch, so
        both a poll count (:data:`~srt_mobile_api.netfunnel.QUEUE_POLL_LIMIT`)
        and a wall-clock budget
        (:data:`~srt_mobile_api.netfunnel.QUEUE_WAIT_LIMIT_SECONDS`) cap it, and
        whichever is reached first raises :class:`SrtNetFunnelError` rather than
        waiting on. Each wait is the server's own ``ttl``, clamped to the app's
        1..5s (``TS_MAX_TTL``), so this cannot become a tight retry loop — which
        matters, because tight retries against a queue are exactly the traffic
        shape that earns an IP block.

        Every acquired key is recorded so it can be released with ``setComplete``
        once the guarded request is done; see :meth:`_release_netfunnel_slots`.

        **Live status: the polling path is OFFLINE-TESTED ONLY.** At normal load
        the SRT queue does not engage, so no run of this code has seen a 201,
        and load was deliberately not synthesised to force one.
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
        """Register ``key`` as the slot we hold, retiring ``previous``.

        Kept separate so that acquisition and release stay symmetric no matter
        which path leaves :meth:`_get_act10_key`: whatever this has recorded is
        exactly what :meth:`_release_netfunnel_slots` will send ``setComplete``
        for.

        ``key`` is a ``str`` and never ``None``: every value passed in comes from
        :attr:`~srt_mobile_api.models.NetFunnelToken.key`, which
        :func:`~srt_mobile_api.netfunnel._parse_result_token` builds with
        ``params.get("key", "")``. "No key" is therefore the EMPTY STRING -- what
        a 300 bypass yields -- and the falsiness tests here and in
        :meth:`_get_act10_key` are about that, not about ``None``. ``previous``
        stays optional because the first acquisition has nothing to retire.
        """
        if previous == key:
            return key
        if previous is not None and previous in self._netfunnel_slots:
            self._netfunnel_slots.remove(previous)
        if key:
            self._netfunnel_slots.append(key)
        return key

    def _release_netfunnel_slots(self, referer: str) -> None:
        """Send ``setComplete`` (5004) for every key we still hold. Best effort.

        Without this our place in line is held until it times out, and at peak
        load that is queue pollution we caused. ``TS_AUTO_COMPLETE = true`` in
        the bundle's own config, so the app releases automatically too.

        Deliberately swallows everything. A release is housekeeping that happens
        AFTER the caller's real request has already succeeded or failed on its
        own terms; letting a failed release replace that outcome would mean a
        successful search reported as an error because we could not tidy up. It
        is also unbounded-retry-free by construction: each key is popped before
        it is sent, so a failure drops the key rather than queueing another
        attempt.
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
        # The ceiling half of the 10-person boundary, mirroring the floor
        # group_search_ajax_payload already enforces. ara0101v.js:562-567
        # refuses a non-단체 search of 10 or more with "10명 이상은 단체
        # 예약입니다." and returns, so this is a client-enforced rule in both
        # directions and only one of the two was reproduced.
        #
        # It lives HERE rather than in the payload builder because the builder
        # cannot tell the two flows apart -- search_page_payload hydrates the
        # group flow too, so a cap applied there would refuse the very searches
        # the floor exists to allow. This layer already knows: `group` is the
        # discriminant every entry point passes down, and this is the one place
        # all five of them funnel through.
        #
        # Refused BEFORE _get_act10_key, so a rejected search never takes a
        # place in the queue.
        if not group and query.passengers.total >= GROUP_MIN_PARTY_SIZE:
            raise ValueError(
                f"a personal search is limited to {GROUP_MIN_PARTY_SIZE - 1} "
                f"passengers; {query.passengers.total} is a 단체 search "
                "(ara0101v.js:562-567). Use search_group_trains()."
            )
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        key = self._get_act10_key(referer)
        state = self._hydrate_search(query, key, transfer=transfer)
        # The URL is chosen by grpDv ALONE (ara1001l.js:174-181). 직통 and 환승
        # share it -- the connection type travels in chtnDvCd, not in the path.
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
        """직통 개인 검색 — 한 페이지 분량의 열차 행을 돌려준다.

        ``query`` 의 역 코드, 날짜(``YYYYMMDD``), 시각(``HHMMSS``, **그 시각부터**),
        인원으로 ``POST /ara/selectListAra10007_n.do`` 를 보내고
        :class:`~srt_mobile_api.models.TrainSearchResult` 를 돌려준다. 로그인이 필요하다.

        **결과가 없으면 빈 목록이 아니라 예외다.** 이 서버는 조회 없음을 FAIL 로
        선언하므로 :class:`~srt_mobile_api.errors.SrtNoResultsError` 가 오른다. 직통은
        없지만 환승이 되는 구간이면 그 하위 클래스인
        :class:`~srt_mobile_api.errors.SrtNoDirectTrainError`(``WRD000061``)가 오고,
        같은 ``query`` 를 :meth:`search_transfer_trains` 에 넘기면 된다. 환승 검색을
        대신 보내 주지는 않는다.

        인원이 10명 이상이면 요청 전에 :class:`ValueError` 다 — 앱이 그것을 단체
        예약으로 돌린다(``ara0101v.js:562-567``). :meth:`search_group_trains` 를 쓴다.

        NetFunnel ``act_10`` 대기열을 앱처럼 통과한다: 키를 받고, 대기가 걸리면 정해진
        횟수·시간 안에서만 기다리며, 끝나면 자리를 반납한다. 키가 상해서
        ``NET000001`` 이 오면 한 번만 다시 시도한다.

        다음 페이지는 :meth:`iter_train_search_pages` 다.
        """
        with self._session_guard():
            return self._search_with_retry(query, group=False)

    def search_group_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        """단체(10명 이상) 검색 — 같은 질의를 단체 경로로 보낸다.

        ``POST /ara/selectListAra10082_n.do``. 경로를 가르는 것은 ``grpDv`` 하나이고
        (``ara1001l.js:174-181``), 본문은 ``grpDv="1"`` 과 ``psgNum`` 말고는
        :meth:`search_trains` 와 같다. 반환도 같은
        :class:`~srt_mobile_api.models.TrainSearchResult` 다. 로그인이 필요하다.

        인원이 10명 미만이면 요청 전에 :class:`ValueError` — 앱도 클라이언트에서
        막는다(``ara0101v.js:551-554``).

        **이 라이브러리는 단체 예약은 하지 않는다.** 잔여석과 운임 조회까지가 전부이고,
        단체 예약 경로는 등록조차 돼 있지 않다.

        빈 결과가 예외라는 것과 NetFunnel 처리는 :meth:`search_trains` 와 같다.
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
        """할인 승차권 검색 — 계정이 승인받은 공공할인이 붙는 열차를 찾는다.

        ``POST /ara/selectListAra10131_n.do``. 읽기이며 일반 검색 ajax 와 같은 자격으로
        :data:`~srt_mobile_api.safety.READ_ONLY_ROUTES` 에 자기 23필드 계약과 함께 등록돼
        있다. 반환은 :class:`~srt_mobile_api.models.TrainSearchResult`. 로그인이 필요하다.

        **한 번도 보내 본 적이 없다.** 필드명·값·응답 키는 2026-07-26 에 서버가
        렌더링해 준 페이지에서 읽은 것이고, 이 요청의 응답에서 읽은 것은 하나도 없다 —
        보내려면 승인된 공공할인이 필요한데 여기 계정은 자격이 없다. **요청 모양에는
        근거가 있고 효과에는 없다.**

        ``discount`` 의 ``PBL_DISC_CD`` 는 알려진 값 범위(``01`` 다자녀 … ``06`` 3세대
        동행할인, 그리고 ``07``/``08`` 분기)이고 ``TGT_DTRM_YN`` 은 늘 ``"Y"`` 다.
        ``PBL_DISC_NM`` 은 ajax 폼에 필드 자체가 없어 전송되지 않는다.
        ``PBL_DISC_MG_NO`` 는 서버가 발급하는 승인번호라 여기서 알 수 없고 호출자가
        넘기며 기본값이 ``""`` 다.

        **승객 타입 구성은 전송되지 않는다.** 이 폼은 인원 합계 ``psgNum`` 만 싣고
        ``psgTpCd``/``psgInfoPerPrnb`` 가 아예 없어서, ``query.passengers`` 의 청소년·
        유아는 합계만 바꾼다. 일반 검색 ajax 는 구성을 전부 보낸다.

        ``page_cursor`` 는 ``gdNo`` 이고 첫 페이지는 ``""`` 다. 이 경로의 페이징은
        출발시각을 밀어 올리는 일반 검색과 달리 커서 방식이며, 종료 조건
        (``trainListMap[0].fllwPgExt``)을 본 적이 없어서 자동으로 돌지 않는다.

        NetFunnel ``act_10`` 자리는 앱과 같이 잡았다 반납하지만, 이 경로의 두 폼에는
        ``netfunnelKey`` 필드가 없어 키 자체는 나가지 않는다.

        알 수 없는 할인 코드이거나 다자녀·3세대 동행할인인데 인원이 3명 미만이면
        어떤 I/O 도 하기 전에 :class:`ValueError` 다(페이지 자신의 규칙 ``rsv071``).
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
        """환승 검색 — 짝지어진 :class:`~srt_mobile_api.models.TransferItinerary` 를 돌려준다.

        요청은 :meth:`search_trains` 와 거의 같다. 경로가 같고, 본문 차이는
        ``chtnDvCd`` 가 ``"1"`` 에서 ``"2"`` 로 바뀌는 것뿐이며, 하이드레이션 GET 에
        ``jrnyTpCd="14"``/``jrnyCnt="2"`` 가 더 붙는다(``ara0101v.js:302-303``).
        로그인이 필요하다.

        **별도 메서드인 이유는 요청이 아니라 결과다.** 서버가 주는 행은 한 여정의
        **절반**이고 행 자체에는 그렇다는 표시가 없다 — 평범한
        :class:`~srt_mobile_api.models.TrainSummary` 라서 :meth:`reserve` 에 그대로
        넘어가고, 그러면 환승역까지만 끊긴 승차권이 나온다. 그래서 짝짓기를 거친
        :class:`~srt_mobile_api.models.TransferItinerary` 와 :meth:`reserve_transfer`
        쌍으로 갈라 두었다.

        응답은 2026-07-26 실검증이고 **한 다리에 한 행**이다. 반환
        :class:`~srt_mobile_api.models.TransferSearchResult` 에는 깨끗이 짝지어진
        ``itineraries``, 짝이 맞지 않아 이유와 함께 남겨 둔 ``unpaired``, 그리고 손대지
        않은 원본 검색 결과 ``search`` 가 같이 들어 있다 — 짝짓기는 서버가 아니라 이쪽의
        추론이라서 뒤로 돌아갈 길을 남겼다. 규칙은
        :func:`~srt_mobile_api.parsers.pair_transfer_itineraries` 참고.

        행은 있는데 하나도 짝지어지지 않으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 다. 빈 목록으로 돌려주면 이
        읽기에서 유일하게 조용한 실패가 되기 때문이다.

        페이징은 지원하지 않는다 — 둘째 커서 ``fllwPgExt2`` 가 실검증에서도 ``null``
        이라 용도를 모른다.

        여기 닿는 자연스러운 길은 직통 검색이 ``WRD000061`` 로 답하는 것이다 — 그것이
        :class:`~srt_mobile_api.errors.SrtNoDirectTrainError` 다.
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
        """검색 결과를 페이지 단위로 게으르게 넘기는 제너레이터를 돌려준다.

        첫 페이지는 :meth:`search_trains`(``group=True`` 면
        :meth:`search_group_trains`)와 같은 요청이고, 이어지는 페이지는 직전 페이지
        마지막 열차의 출발시각을 ``dptTm`` 커서로 밀어 올려 같은 경로에 다시 POST
        한다. :class:`~srt_mobile_api.models.TrainSearchResult` 를 한 페이지씩 내놓는다.

        ``max_pages`` 는 양의 정수여야 하고(``bool`` 은 거부한다) 아니면
        :class:`ValueError` 다. 이 검사만은 제너레이터를 돌리기 전, 호출 즉시 일어난다.
        기본 10 페이지에서 멈추며, 그전이라도 서버가 다음 페이지 없음을 말하거나
        페이지가 비면 끝난다.

        커서가 반복되거나 앞으로 나아가지 않으면
        :class:`~srt_mobile_api.errors.SrtProtocolError` 다 — 무한 반복 대신 실패를
        택한 것이다.

        NetFunnel 자리는 **걷기 전체가 끝날 때** 반납된다. 이어지는 페이지가 같은 키를
        다시 쓰기 때문에 첫 페이지에서 놓지 않으며, 도중에 제너레이터를 버려도
        (``GeneratorExit``) 반납된다.

        환승 검색에는 쓸 수 없다 — :meth:`search_transfer_trains` 참고.
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
        """좌석 선택 1단계 — 호차 목록이 담긴 좌석선택 페이지를 읽는다.

        ``POST /arc/selectListArc02012_n.do``. ``train`` 은 검색이 돌려준 완전한
        :class:`~srt_mobile_api.models.TrainSummary` 행이어야 한다. 반환
        :class:`~srt_mobile_api.models.SeatSelectionPage` 는 HTML 에
        :attr:`~srt_mobile_api.models.SeatSelectionPage.cars`(호차 옵션)가 붙은 것이고,
        호차 하나의 좌석 배치는 :meth:`get_seat_grid` 가 이어서 읽는다.

        ``choiceSeatCount`` 는 상수가 아니라 **일행 인원**이다 — 앱은
        ``lfn_getRsv("totPrnb")`` 를 보낸다(``ara1001l.js:1511``). 그래서 ``passengers``
        를 넘기면 거기서 인원을 뽑는다. ``seat_count`` 는 명시적 override 이고 둘 다
        주면 이쪽이 이긴다. 둘 다 없으면 ``"1"``.

        로그인이 필요하다.
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
        """좌석 선택 2단계 — 호차 하나의 좌석배치도를 읽는다.

        ``POST /arc/selectListArc02011_n.do``. :meth:`get_seat_page` 가 "어느 호차에
        자리가 있나" 를 답한다면 이쪽은 "어느 좌석이고, 고를 수 있나" 를 답한다. 반환
        :class:`~srt_mobile_api.models.SeatGrid` 의
        :meth:`~srt_mobile_api.models.SeatGrid.choose` 로
        :class:`~srt_mobile_api.models.SeatDesignation` 을 만들어 :meth:`reserve` 의
        ``designated_seats`` 에 넘길 수 있다.

        ``car_number`` 는 :attr:`~srt_mobile_api.models.SeatSelectionPage.cars` 의
        ``car_number`` 값이다. ``passengers``/``seat_count``/``cabin_class`` 는
        :meth:`get_seat_page` 에 준 것과 같게 준다.

        **열차번호를 다섯 자리로 0 채움해 보낸다** — 그 하나가 좌석배치도와 147바이트
        짜리 경고 껍데기를 가른다
        (:data:`~srt_mobile_api.payloads.SEAT_TRAIN_NUMBER_LENGTH`).

        서버가 거절하면(``"0#<메시지>"``)
        :class:`~srt_mobile_api.errors.SrtSeatUnavailableError` 이지 프로토콜 오류가
        아니다. 로그인이 필요하고, 응답이 로그인 페이지면
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 다.

        2026-07-26 실검증(수서→동탄, 20260812, 315 열차, 25,930바이트에 좌석 셀 74개).
        이 경로도 ``trnScarSeatFrm`` 도 v2.0.41 번들에는 없고 서버가 렌더링하는
        페이지에만 있다.
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
        """열차 하나의 정차역별 시간표를 읽는다.

        ``POST /ara/selectListAra12009_n.do``, 어느 열차인지는 검색 행 ``train`` 이
        말한다. 반환 :class:`~srt_mobile_api.models.TimetablePage` 는 HTML 에 정차역 행
        (:class:`~srt_mobile_api.models.TimetableRow`)이 붙은 것이다.

        **역 이름은 HTML 안에 없다.** 서버는 코드만 내려보내고 WebView 가
        ``getStationNameByCode('0551')`` 로 채운다. 이 파서는 앱과 같은 표를 담은
        :mod:`srt_mobile_api.stations` 로 이름을 해결한다.

        로그인이 필요하다.
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
        """열차 한 다리의 운임·요금 표를 읽는다.

        ``POST /ara/selectListAra13010_n.do``. ``passengers`` 를 생략하면 성인 1명
        (:class:`~srt_mobile_api.models.PassengerCounts` 의 기본값)으로 묻는다. 반환은
        :class:`~srt_mobile_api.models.FarePage`.

        **둘째 다리 표는 읽지 않는다.** 이 페이지는 환승 여정용이라 ``trainPayInfo1``
        (첫 다리)과 ``trainPayInfo22``(둘째 다리) 두 표를 렌더링하는데, 이 요청은 한
        다리만 말할 수 있어 둘째 표는 금액이 ``0원`` 인 자리표시자로 온다. 그것까지
        읽으면 "어른 일반실 → 0" 처럼 돈에 대해 조용히 틀린 답이 나온다.

        로그인이 필요하다.
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
        """The one reservation send path, shared by :meth:`reserve` and :meth:`reserve_transfer`.

        Extracted rather than copied because every safety property of a
        reservation lives here — the consent gate, the session requirement, the
        no-I/O dry run, the single NetFunnel acquisition, the guaranteed slot
        release, the never-retry rule, and the PNR-salvaging parse. A second
        body deserves a second builder, not a second copy of that list; the app
        itself keeps one ``#rsvForm`` for every reservation shape.
        ``build_form`` is called with the NetFunnel key exactly once, and only
        after the key exists, so no form is ever built twice or sent twice. It
        is HANDED the authenticated session rather than left to reach back for
        ``self.session.current`` itself: the session requirement is checked
        here, and a builder that re-read the attribute would be relying on a
        guard in another function that stays true only because
        :meth:`_session_guard` re-raises anything that clears it. Passing the
        object makes the dependency the signature's business.

        ``route`` stays a parameter even though both callers now pass the same
        URL: it keeps each public method's target visible where that method is
        defined, which is the pairing
        :data:`~srt_mobile_api.safety.SRT_MUTATION_ROUTE_CATEGORIES` re-checks at
        the send boundary.
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
        # The booking page is the referer search uses for its own act_10
        # acquisition (_prepare_search), and reserve gates on the same key, so
        # the same referer is used rather than inventing a second one.
        booking_referer = f"{self.config.base_url}/ara/ara0101v.do"
        with self._session_guard():
            key = (
                netfunnel_key
                if netfunnel_key
                else self._get_act10_key(booking_referer)
            )
            # INSIDE the try, not above it. build_form runs every client-side
            # refusal this builder owns -- 국회의원 후급, 코레일 전용역, the seat
            # attr whitelist, the availability requirement, the cabin
            # cross-check -- and any of them raises with a queue slot already
            # acquired two lines up. Outside the try, that slot was never
            # released: the finally below is the only thing that returns it, and
            # the dominant case (a script stopped by a guard) never flushes at
            # all. The sibling paths already do it this way -- _search_once
            # builds inside its guard, _search_public_discount_once builds
            # before acquiring.
            try:
                form = build_form(key, session)
                response = self.http.post_mutation_form(
                    route,
                    form,
                    consent=consent,
                    category="reserve",
                    # The app reserves from the search-result page
                    # (ara1001l.js:1541-1560), which is the referer every other
                    # post-search read here sends. INFERRED from the app flow,
                    # not captured from the wire.
                    referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
                )
            finally:
                # Release the queue slot once the reserve is over. Best effort
                # and exception-swallowing by construction (see
                # _release_netfunnel_slots), which matters most HERE: a hold may
                # already exist on the server by this point, and a failed
                # housekeeping call must never be what the caller sees instead
                # of the PNR. A caller-supplied netfunnel_key was not acquired
                # by us and so is not in _netfunnel_slots to release -- whoever
                # obtained it owns completing it.
                self._release_netfunnel_slots(booking_referer)
            # From here a hold may EXIST on the server. parse_reservation_hold_
            # response is the designed guard: it salvages a minimal hold from a
            # PNR-bearing response rather than letting a strict-validation
            # failure orphan it, and refuses to manufacture one when the server
            # declared a failure.
            hold = parse_reservation_hold_response(response)
            # The form knows how many 여정 it just booked; the response does
            # not say, and the hold is what cancel() will be handed later.
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
        """개인예약(개인 예약 홀드)을 만든다. consent 필수.

        ``POST /arc/selectListArc05013_n.do``. ``require_mutation_consent(consent,
        "reserve")`` 가 첫 관문이라, 기본
        :class:`~srt_mobile_api.consent.MutationConsent`(``allow_reserve=False``)나
        ``None`` 은 폼을 만들기도 전에
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 로 막힌다. 인증
        세션도 필요하고, 그 검사는 ``dry_run`` 분기보다 **앞**이다 — 미리보기도 로그인은
        되어 있어야 한다.

        ``dry_run=True``(기본)면 보낼 폼을 그대로 담은
        :class:`~srt_mobile_api.consent.MutationPreview` 를 돌려주고 **네트워크를 전혀
        쓰지 않는다**(NetFunnel 키도 받지 않는다). ``dry_run=False`` 면 실제로 전송되고,
        성공하면 실계정에 미결제 홀드가 생긴다. 반환
        :class:`~srt_mobile_api.models.SrtReservationHold` 의 ``pnr_no`` 가
        :meth:`cancel` 의 입력이다. **그 홀드는 호출자 책임이다.**

        NetFunnel 은 검색과 같은 ``act_10`` 키 흐름이다(srtgo ``srt.py:987``; ``act_19``
        가 아니다). ``netfunnel_key`` 를 직접 주면 그대로 쓰고 새로 받지 않는다.

        **실패한 예약은 다시 시도하지 않는다** — 재시도는 이중예약이 될 수 있어서, 한
        번의 호출이 만들 수 있는 홀드는 최대 하나다. 응답 파싱이 엉뚱한 필드에서 걸려도
        PNR 만 있으면 취소 가능한 최소 홀드를 건져낸다. PNR 은 보관하라;
        ``scripts/recover_hold.py`` 는 PNR 문자열만으로 홀드를 푼다.

        ``standby`` 는 예약대기(``jobId=1102``)다. 검색 행이 예약대기를 제공하지 않으면
        :class:`ValueError`. 행에서 자동으로 유추하지 않는 것은, 기존 호출자의
        ``reserve(train)`` 이 만석 열차를 만난 순간 말없이 대기 등록으로 바뀌면 안 되기
        때문이다. 번들 근거는 있고(``ara0101v.js:90``, ``ara1001l.js:1445-1448``)
        실검증은 없다. srtgo 가 뒤이어 보내는 SMS·좌석변경 옵션 설정
        (``/ata/selectListAta01135_n.do``)은 번들에 없어 구현하지 않았으므로, 여기서 만든
        대기 등록은 서버 기본값을 그대로 쓴다.

        ``round_trip``(``rtnDv=1``, 왕복)은 **두 번째 요청을 보내지 않는다.** SRT 의
        왕복은 오는열차를 따로 예약하는 구조라, 가는 편과 오는 편을 각각
        ``round_trip=True`` 로 두 번 부른다 — 오는 편 질의는
        :meth:`~srt_mobile_api.models.TrainSearchQuery.for_return_leg` 가 만들어 준다.
        ``jrnyCnt`` 는 두 번 다 ``"1"`` 이고(``"2"`` 는 환승이다), PNR 두 개 다 호출자
        몫이다. 서버가 두 홀드를 엮는지는 미검증이니 독립된 둘로 다뤄라. 코레일 전용역이
        끼거나 회원번호가 ``"11"`` 로 시작하는 국회의원 후급 계정이면 만들기 전에
        거절한다(``ara0101v.js:317-341``). 회원번호는 세션에서 읽으므로 인자가 없다.

        ``designated_seats`` 는 좌석지정(``jobId=1103``)이다. :meth:`get_seat_page` →
        :meth:`get_seat_grid` → :meth:`~srt_mobile_api.models.SeatGrid.choose` 로 만든
        :class:`~srt_mobile_api.models.SeatDesignation` 을 넘긴다. 좌석 수가 인원 수와
        달라도, ``standby``·``round_trip`` 과 섞어도 전송 전에 :class:`ValueError` 다.
        :meth:`reserve_transfer` 에는 아예 없다 — 좌석지정은 환승의 둘째 슬롯을 비운다.

        **근거의 층이 다르다.** 좌석을 읽어 오는 :meth:`get_seat_grid` 는 2026-07-26
        실검증이고, 폼의 좌석 필드(``seatNo1_1..N``, ``scarGridcnt1``, ``scarNo1`` 등,
        ``ara0101v.js:866-882``)와 ``jobId=1103``(``ara1001l.js:1435-1436``)은 번들
        근거이며, **좌석지정 본문이 이 경로로 간다는 것만은 추론**이다 — 앱의 좌석
        콜백은 서버가 렌더링하는 ``fn_submit()`` 으로 끝나고 그 정의는 번들에 없다.

        예약 자체는 2026-07-25 에 한 번 실제로 돌렸다: 예약이 ``SUCC``/``IRR000018`` 로
        PNR 을 돌려줬고 이어서 :meth:`cancel` 이 ``IRG000000`` 으로 풀었다. 확인된 것은
        성인 1명·1여정·일반실·직통 한 건뿐이고, 다인원·다여정·예약대기·좌석지정은
        미검증이다.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            # membership_number is read off the session _submit_reservation
            # hands in, not defaulted and not re-read from self.session.current:
            # that session is the one its own None-check already passed, so the
            # read cannot be the None the check exists to refuse.
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
        """환승 예약 — 두 다리를 **한 요청**으로 예약한다. consent 필수.

        SRT 가 다구간 본문으로 받는 유일한 모양이다. 환승 토글이 ``jrnyTpCd="14"`` 와
        ``jrnyCnt="2"`` 를 같이 세우고(``ara0101v.js:302-303``), ``jrnyCnt="2"`` 는
        v2.0.41 번들에서 다른 데 쓰이지 않는다. :meth:`reserve` 의 ``round_trip`` 은
        정반대다 — 왕복은 1여정짜리 예약을 두 번 하는 것이다.

        경로도 consent 카테고리도 :meth:`reserve` 와 같다
        (``/arc/selectListArc05013_n.do``, ``"reserve"``). 앱이 예약 경로를 가르는 것은
        ``grpDv`` 하나이고 환승은 ``grpDv`` 를 건드리지 않는다(``ara1001l.js:1542-1547``).
        consent 게이트, 인증 세션 요구(``dry_run`` 분기보다 앞), 기본 무통신 미리보기,
        NetFunnel 자리 반납, 무재시도, PNR 건지기까지 :meth:`reserve` 와 똑같은 전송
        경로를 탄다. 한 번의 호출이 만드는 홀드는 여전히 최대 하나다.

        인자가 :class:`~srt_mobile_api.models.TransferItinerary` 인 것은, 열차 두 개를
        따로 받으면 같은 행을 두 번 넣거나 만나지 않는 다리를 넣거나 순서를 뒤집을 수
        있고 그 실패가 전부 조용하기 때문이다 — 그럴듯한 폼과 진짜 홀드가 만들어진다.
        이 타입은 생성 시점에 이음새를 검사한다(앞 다리 도착역 = 뒤 다리 출발역, 도착이
        출발보다 늦지 않을 것).

        ``passengers``·``seat_type``·``window_seat`` 는 두 다리에 한 번에 적용된다
        (``ara0101v.js:769-778``). ``round_trip``·``standby``·단체·좌석지정은 조합되지
        않는다.

        **한 번도 보내 본 적이 없다.** 슬롯 2 의 키 이름 다섯 개(``stlbTrnClsfCd2``,
        ``dptStnConsOrdr2``, ``arvStnConsOrdr2``, ``dptStnRunOrdr2``, ``arvStnRunOrdr2``)
        는 슬롯 1 에서 유추했고, 서버가 렌더링하는 ``#rsvForm`` 은 번들에 없다
        (키별 근거는 :data:`~srt_mobile_api.payloads.TRANSFER_SLOT2_FIELD_EVIDENCE`).
        ``reserveType`` 은 :meth:`reserve` 와 같은 ``"11"`` 로 보내며 ``jrnyTpCd`` 를
        따라가는지는 모른다 — 서버가 본문을 거절하면 여기부터 의심하라.

        취소는 :meth:`cancel` 에 홀드를 그대로 넘기면 된다. 홀드가 자기 여정 수
        (``"2"``)를 기억하므로 ``jrnyCnt`` 가 맞춰진다. PNR 문자열만 들고 있다면
        ``cancel(pnr, journey_count="2", consent=…)`` 로 직접 말해야 한다.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            # The session is unused here: 환승 carries no mbCrdNo field (the
            # 국회의원 후급 check is 왕복's, and 왕복 does not compose with 환승).
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
        """만들어졌지만 결제되지 않은 예약을 취소한다(예약취소). consent 필수.

        ``POST /ard/selectListArd02045_n.do``, 본문은 ``pnrNo``/``jrnyCnt``/
        ``rsvChgTno`` 셋뿐이다. ``require_mutation_consent(consent, "cancel")`` 로
        막히고(기본 :class:`~srt_mobile_api.consent.MutationConsent` 는
        ``allow_cancel=False``), 인증 세션이 필요하며 그 검사는 ``dry_run`` 분기보다
        앞이다.

        ``reservation`` 은 :class:`~srt_mobile_api.models.SrtReservationHold` 이거나 맨
        PNR 문자열이다. 부분 실패에서 회복하는 호출자가 PNR 밖에 못 가진 경우가 있고,
        그 길이 막히면 예약을 풀 수 없다.

        ``journey_count`` 를 생략하면 홀드가 기억하는 여정 수를 쓰고(환승 홀드는
        ``"2"``), 맨 PNR 로 부를 때는 ``"1"`` 이 기본이다. 넘기면 그 값이 이긴다.
        숫자로 정규화되고 **절대 거절되지 않는다** — 0 채움도, 알아볼 수 없는 값도
        기본값으로 떨어질 뿐이다. 폼을 못 만드는 것이 곧 못 푸는 홀드이기 때문이다.

        ``dry_run=True``(기본)면 PNR 을 가린
        :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려주고 통신하지 않는다.
        ``dry_run=False`` 면 전송되고
        :class:`~srt_mobile_api.models.SrtCancelResult` 를 돌려준다.

        2026-07-25 실검증: 실계정의 미결제 홀드 하나가 ``SUCC``/``IRG000000``/
        "정상처리되었습니다" 로 풀렸고 승차권 목록에서도 사라졌다. 1여정·성인 1명 한
        건이라 ``jrnyCnt="1"`` 만 확인된 셈이다. 경로 자체는 v2.0.41 번들에 없지만,
        서버가 렌더링하는 승차권 목록 페이지의 ``cncConfirm()`` 이 같은 경로·같은 세
        필드·같은 응답 봉투를 쓴다.
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
        """할인쿠폰을 계정에 등록한다(할인쿠폰 등록). consent 필수. **전송은 막혀 있다.**

        ``POST /arb/selectListArb02A01_n.do``, 본문은 ``{dscp_no, dscp_pwd}``.
        :meth:`get_discount_coupons` 가 읽는 페이지의 나머지 절반이다 — 그 페이지가
        목록이자 등록 폼이고, 등록하기 버튼의 ``couponReg()`` 가 ``#couponInfo`` 를
        여기로 보내며 ``resultMap[0].RTNCD``/``.MSG`` 를 읽는다.

        consent 카테고리는 다섯 번째인 ``"coupon"`` 이다. 쿠폰 등록은 예약도 결제도
        아니고 소지 크리덴셜을 소진하는 일이라, ``reserve`` 나 ``payment`` 에 얹으면 그
        동의가 말없이 쿠폰까지 쓰게 된다. ``require_mutation_consent(consent, "coupon")``
        과 인증 세션이 필요하고(세션이 이 요청에서 누구 계정인지 말하는 유일한 것이다),
        두 검사 모두 ``dry_run`` 분기보다 앞이다.

        **보낼 수 없다.** ``"coupon"`` 은
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 밖이라
        ``dry_run=False`` 로 불러도 전송 계층이
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 로 거절하고 아무것도
        내보내지 않는다. 열려면 실행이 한 번 필요하고, 실행하려면 쓰지 않은 실물 쿠폰이
        필요하다.

        미리보기는 양쪽을 다 가린다 — ``dscp_no`` 와 ``dscp_pwd`` 모두
        :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS` 에 있다.

        입력 검증은 페이지 자신의 규칙이다 — 번호는 숫자만 최대 10자리, 비밀번호는 최대
        4자, 둘 다 비어 있으면 안 된다.

        **성공은 요청이 접수됐다는 뜻이지 쿠폰이 보인다는 뜻이 아니다.** 페이지 문구도
        그렇게 말한다(쿠폰등록 요청을 완료하였습니다 … 바로 조회 되지 않을 수 있습니다).
        등록 직후 :meth:`get_discount_coupons` 가 아무것도 못 봐도 정상일 수 있다.

        경로·필드명·응답 키는 2026-07-26 의 실제 페이지에서 읽었다. v2.0.41 번들에는
        ``/arb/`` 라우트가 아예 없고, 번들이 뒷받침하는 것은 양쪽 어휘뿐이다
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
        """미결제 PNR 에 카드 결제를 건다(카드결제). consent 필수. **실제로 돈이 나간다.**

        ``POST /ata/selectListAta09036_n.do``, 31개 필드.
        ``require_mutation_consent(consent, "payment")``, 인증 세션, 그리고 세션에
        회원번호(``userMap.MB_CRD_NO``)가 있어야 한다 — 없으면
        :class:`~srt_mobile_api.errors.SrtAuthError` 다. 세 검사 모두 ``dry_run``
        분기보다 앞이다.

        ``reservation`` 은 :meth:`get_reservations` 가 준 행 — 미결제 PNR 을 말해 줄 수
        있는 유일한 읽기다. 금액은 그 행의
        :attr:`~srt_mobile_api.models.SrtReservationSummary.received_amount`
        (``rcvdAmt``, 수납금액)에서만 오고 override 가 없다. ``settlement_date``
        (``stlDmnDt``)는 생략하면 오늘이며, 명시했는데 쓸 수 없는 값이면 조용히
        바꾸지 않고 거절한다. ``passenger_count`` 도 지상 진실을 가진 호출자용
        override 다.

        ``dry_run=True``(기본)면 PAN·PIN·유효기간·생년월일·회원번호·PNR 을 모두 가린
        :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려주고 통신하지 않는다.
        ``dry_run=False`` 면 consent 가 **어떤 카드인지도** 밝혀야 한다
        (:func:`~srt_mobile_api.consent.require_card_kind_claim`: ``fake_card_only`` 와
        ``real_card_acknowledged`` 중 정확히 하나. 둘 다도, 둘 다 아님도 거절이다).
        이 주장은 여기서 한 번, 전송 경계에서 다시 확인된다.

        2026-07-26 실검증: 수서→동탄 2026-08-09 315 열차, 성인 1명 7,500원을 실제
        카드로 결제하고 같은 실행에서 환불했다(``SUCC``/``IRT000000``). 앞서 가짜 카드와
        없는 PNR 로 찔러 본 무료 탐침이 404 나 HTML 오류가 아니라 정상 업무 응답
        (``FAIL``/``WRT100170``)을 줘서, 돈을 쓰기 전에 경로 존재가 확인됐다. 확인된
        것은 1여정·성인 1명·일반실·개인카드·일시불 한 건뿐이다.

        **출처는 이 파일에서 가장 얇다.** 이 경로는 v2.0.41 번들 전체에서 0-hit 이고
        (``Ata09*`` 계열 전부), 앱 자신은 이 길로 결제하지 않는다 — ``#rsvForm`` 을
        ``/ard/selectListArd02017_n.do`` 로 보내고 TransKey 보안 키패드와 RaonSecure
        FIDO 를 거친다. 참조 구현 둘은 한 벌이라(srtgo 가 ryanking13/SRT 의 결제 코드를
        그대로 벤더링) 서로를 뒷받침하지 못한다. 서버가 이 평문 경로를 아직 받아 준다는
        것이 실행으로 확인됐을 뿐이다.
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
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit, matching cancel. stlDmnDt is resolved here
        # rather than in the builder so payloads.py keeps no clock.
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
        # Only on the transmit path: a dry run sends nothing, so requiring the
        # card-kind claim to PREVIEW would buy no safety and would just make
        # previewing harder. post_mutation_form re-checks this itself.
        require_card_kind_claim(consent)
        with self._session_guard():
            # The single send path, so the gate ordering and the refusals stay
            # the transport layer's decision and cannot drift out of sync with
            # it. Since 2026-07-26 this reaches the wire.
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="payment",
            )
            return parse_card_payment_response(response)

    def get_refund_ticket_info(self, pnr_no: str) -> SrtRefundTicketInfo:
        """발권된 승차권의 환불 식별 정보를 읽는다 — 환불 2단계 중 1단계.

        ``POST /atc/getListAtc14087.do``, **본문 없음**. 승차권을 지목하는 것은
        ``Referer`` 로 실려 가는 ``/common/ATC/ATC0201L/view.do?pnrNo=<PNR>`` 이다.
        응답의 ``outDataSets.dsOutput1[0]`` 이
        :class:`~srt_mobile_api.models.SrtRefundTicketInfo` 가 되고, 그대로
        :meth:`refund` 에 넘긴다. 로그인이 필요하다.

        consent 게이트가 아니라 읽기 경로를 탄다 —
        :data:`~srt_mobile_api.safety.READ_ONLY_ROUTES` 에 등록돼 있고, 그 분류는 증명이
        아니라 추론이다(본문이 없고 응답이 순수 식별 정보라는 것이 근거이며, 서버가
        부작용 없다고 말해 준 적은 없다). :meth:`refund` 는 이걸 대신 불러 주지 않는다.

        ``pnr_no`` 는 ASCII 영숫자와 하이픈 1~32자만 받고, 어기면 요청 전에
        :class:`ValueError` 다. 이 엔드포인트가 기대는 ``Referer`` URL 에 그대로
        끼워 넣는 값이라, 다른 문자는 거기에 질의 파라미터를 몰래 붙일 수 있다.

        ``Referer`` 는 이 요청에만 붙는다. 참조 구현은 이걸 세션 헤더로 박아 두고 지우지
        않아서 이후 모든 요청이 PNR 을 들고 다닌다.

        2026-07-26 실검증: 없는 PNR 로도 정상 업무 응답(``WRT300005``, "조회자료가
        없습니다.")이 왔고, 이어진 왕복에서 실제 승차권의 식별 정보를 읽었다. 경로는
        v2.0.41 번들에 없고 참조 구현 하나만 이걸 안다.
        """
        if not isinstance(pnr_no, str) or not pnr_no.strip():
            raise ValueError("refund ticket info requires a non-empty PNR")
        pnr = pnr_no.strip()
        # ASCII-only and length-bounded, via an explicit character class rather
        # than str.isalnum(). isalnum() is UNICODE-aware, so "한글PNR", Arabic-Indic
        # digits and fullwidth letters all satisfied it and then died inside
        # httpx as a bare UnicodeEncodeError — an exception outside this
        # library's taxonomy entirely, raised while building the request. The
        # unbounded form also let a 5,000-character PNR become a 5,058-byte
        # Referer. Same ASCII-class style as safety.NETFUNNEL_KEY_RE.
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
        """발권된 승차권을 환불한다(환불) — 2단계. consent 필수. **실제로 반환된다.**

        ``POST /atc/selectListAtc02063_n.do``, 7개 필드.
        ``require_mutation_consent(consent, "refund")`` 와 인증 세션이 필요하고, 두 검사
        모두 ``dry_run`` 분기보다 앞이다. 성공하면
        :class:`~srt_mobile_api.models.SrtRefundResult` 다.

        ``ticket_info`` 는 :meth:`get_refund_ticket_info` 가 준 것이다. 2단계 본문은
        1단계가 돌려준 식별 정보(발매일·창구·일련번호·반환비밀번호·구매자)가 전부인데,
        **두 단계를 일부러 합치지 않았다.** 이 메서드가 스스로 1단계를 부르지 않으므로
        거절당한 환불은 아무 요청도 남기지 않고, 호출자는 서버가 설명한 적 없는 승차권으로
        2단계 폼을 지어낼 수 없으며, dry run 이 통신을 전혀 하지 않는다.

        ``dry_run=True``(기본)면 반환비밀번호·구매자명·PNR 을 가리고 판매 식별자는 남긴
        :class:`~srt_mobile_api.consent.MutationPreview` 만 돌려준다.

        2026-07-26 실검증: 같은 실행에서 방금 결제한 수서→동탄 승차권이
        ``SUCC``/``IRT200277`` 로 환불됐고, 별도 세션에서 계정에 예약도 승차권도 남지
        않은 것을 확인했다. 1여정·성인 1명 한 건이다.

        출처는 :meth:`pay_with_card` 보다도 얇다 — 참조 구현 **하나**에만 있고
        (ryanking13/SRT 에는 환불이 아예 없다), ``Atc02063`` 은 v2.0.41 번들 전체에서
        0-hit 이며 ``Atc02*`` 계열 자체가 없다.

        필드명 ``tkRetPwd``·``psgNm`` 은 srtgo 출처이고 2026-07-26 실행에서 서버가
        그대로 받았다. 앱 쪽 철자 ``retPwd``/``buyPsNm`` 은 로컬 승차권 캐시
        핸들러의 것이라 이 요청과 무관하다.
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
            # The single send path, so gate ordering and refusals stay the
            # transport layer's decision. Since 2026-07-26 this reaches the wire.
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="refund",
            )
            return parse_refund_response(response)
