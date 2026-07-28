"""실서버 스모크 —— 읽기 경로만 한 번씩 실제로 두드려 보는 도구.

이 모듈의 함수들은 진짜 SRT 서버에 붙는다. 진입점 :func:`run_live_smoke_from_env`
는 환경변수 ``SRT_MOBILE_API_LIVE=1`` 이 없으면 :class:`RuntimeError` 로
멈춘다. 자격증명(``SRT_LOGIN_ID``/``SRT_LOGIN_PASSWORD``)과 여정
(``SRT_TEST_DATE`` 등)도 환경변수로만 받는다 —— 인자로 넘기는 자리가 없다.

**상태를 바꾸지 않는다.** 로그인, 페이지·선택기 조회, 검색, 좌석 페이지,
시각표, 운임까지만 부른다. 예약·취소·결제·환불은 이 스모크에 없다.

결과는 카멜케이스 키를 가진 평평한 ``dict`` 다. 값은 개수·불리언과 서버가 준
오류코드뿐이고, 승차권 내용이나 개인정보는 담기지 않는다. 노선이 매진이어도
실패가 아니다 —— ``seatPageErrorCode`` 에 서버의 거절 코드가 들어갈 뿐이다.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any

from .client import SrtClient
from .config import SrtConfig
from .errors import SrtAppError
from .models import PassengerCounts, SeatSelectionPage, TrainSearchQuery, TrainSummary
from .payloads import (
    TRAIN_GROUP_OPTIONS,
    _general_seat_available,
    _special_seat_available,
    personal_reservation_payload,
)


def live_enabled() -> bool:
    """``SRT_MOBILE_API_LIVE`` 가 정확히 ``"1"`` 인지. 실서버 접속의 스위치다."""
    return os.environ.get("SRT_MOBILE_API_LIVE") == "1"


def read_credentials_from_env() -> tuple[str, str]:
    """``SRT_LOGIN_ID``/``SRT_LOGIN_PASSWORD`` 를 읽어 ``(아이디, 비밀번호)`` 로 준다.

    둘 중 하나라도 비어 있으면 :class:`RuntimeError` 다.
    """
    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        raise RuntimeError("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required for live smoke")
    return login_id, password


def _first_complete_srt_seat_train(
    trains: Sequence[TrainSummary],
) -> TrainSummary | None:
    for train in trains:
        # seat_attr_code is deliberately NOT required here. The app and srtgo
        # both source seatAttCd from the request side (rqSeatAttCd1="015"), and
        # seat_page_payload defaults it rather than reading train.seat_attr_code.
        #
        # CORRECTION, live capture 2026-07-26: this comment used to justify that
        # by claiming "a genuine captured row omits it". It does not -- all 40
        # live rows carried seatAttCd="015", echoing the request. Requiring it
        # would in fact NOT skip every real train. The exclusion stands on the
        # request-side sourcing alone, which is the reason that survives.
        required = (
            train.train_no,
            train.run_date,
            train.departure_date,
            train.departure_time,
            train.departure_station_code,
            train.arrival_station_code,
            train.departure_run_order,
            train.arrival_run_order,
        )
        if train.train_group_code == "300" and all(
            isinstance(value, str) and bool(value) for value in required
        ):
            return train
    return None


def _first_reservable_srt_seat_train(
    trains: Sequence[TrainSummary],
) -> TrainSummary | None:
    """서버가 예약 가능이라 말했고 필드도 다 갖춘 첫 SRT 행. 없으면 ``None``."""
    for train in trains:
        if train_is_reservable(train) and _first_complete_srt_seat_train([train]):
            return train
    return None


def _external_seat_map_handoff_present(page: SeatSelectionPage | None) -> bool:
    if page is None:
        return False
    raw_lower = page.raw.casefold()
    return "korail.com" in raw_lower and "srtjob=seatmap" in raw_lower


SEAT_IDENTIFIER_RE = re.compile(
    r"(?:^|[\s_-])(?:seat|scar)(?:[\s_-]|$)",
    re.IGNORECASE,
)


class _EmbeddedSeatInventoryProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.candidate_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() in {"a", "form", "input", "script", "style"}:
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        identifiers = f"{values.get('id', '')} {values.get('class', '')}"
        has_seat_data_attribute = any(
            name.casefold().startswith("data-") and "seat" in name.casefold()
            for name, _value in attrs
        )
        if has_seat_data_attribute or SEAT_IDENTIFIER_RE.search(identifiers):
            self.candidate_count += 1


def _embedded_seat_inventory_candidate_present(
    page: SeatSelectionPage | None,
) -> bool:
    if page is None:
        return False
    parser = _EmbeddedSeatInventoryProbe()
    parser.feed(page.raw)
    return parser.candidate_count >= 2


def run_live_smoke(
    client: SrtClient,
    *,
    login_id: str,
    password: str,
    query: TrainSearchQuery,
) -> dict[str, Any]:
    """읽기 경로를 순서대로 한 번씩 호출하고 그 결과를 개수·불리언으로 요약한다.

    로그인 → 메인·예매 페이지 → 선택기 여섯 → 공지 → 승차권 페이지 → 개인 검색
    → 좌석 페이지 → 상호확인 → 단체 검색 → 시각표 → 운임 순이다. 단체 검색은
    10명 미만이면 앱이 막으므로 ``query`` 와 무관하게 성인 10명으로 다시 만들어
    보낸다.

    좌석 페이지는 서버가 예약 가능이라고 말한 열차를 우선 고르고, 없으면 필드가
    온전한 첫 SRT 행으로 물러선다. 그 열차마저 매진이면 서버는 좌석 대신 오류
    껍데기를 주는데, 그것은 예외로 새어 나가지 않고 결과의
    ``seatPageErrorCode`` 에 담긴다. 좌석 조회 인원은 검색과 같은 인원이다.

    실패로 끝나는 것은 로그인·검색 같은 앞단계다. ``query`` 노선에 열차가 없으면
    :class:`~srt_mobile_api.errors.SrtNoResultsError` 가 그대로 오른다.
    """
    session = client.login(login_id, password)
    main = client.get_main()
    booking = client.get_booking_page()
    group_name = TRAIN_GROUP_OPTIONS[query.train_group_code][0]
    selectors = (
        client.get_station_selector(
            query.departure_station_name or query.departure_station_code,
            query.arrival_station_name or query.arrival_station_code,
            query.departure_station_code,
            query.arrival_station_code,
        ),
        client.get_station_map_selector(),
        client.get_date_selector(query.departure_date),
        client.get_passenger_selector(query.passengers),
        client.get_seat_option_selector(request_seat_attr_code=query.seat_attr_code),
        client.get_train_group_selector(query.train_group_code, group_name),
    )
    notices = client.get_typed_notice_list()
    tickets = client.get_ticket_list()
    personal = client.search_trains(query)
    # Prefer a train the server currently reports as bookable, falling back to
    # the first completely-described SRT row. A SOLD-OUT train is not answered
    # with a seat map at all: the server returns an error shell, which
    # parse_seat_selection_page now refuses (SrtAppError "error001"). Live
    # capture 2026-07-26 found every train on 수서→부산 매진, so without this
    # preference the smoke reads the error shape on any busy route.
    seat_train = _first_reservable_srt_seat_train(
        personal.trains
    ) or _first_complete_srt_seat_train(personal.trains)
    # The seat page's choiceSeatCount is the party size (ara1001l.js:1511 sends
    # lfn_getRsv("totPrnb")). The smoke searches with query.passengers, so it
    # must read the seat page for the same party rather than silently asking for
    # one seat.
    seat_page = None
    seat_page_error: str | None = None
    if seat_train is not None:
        try:
            seat_page = client.get_seat_page(seat_train, passengers=query.passengers)
        except SrtAppError as exc:
            # Reported, not raised. "Every train on this route is sold out" is
            # the server telling the truth, and it must not read as a broken
            # smoke run -- but it must not read as a successful seat read
            # either, which is what the old marker-only parse produced.
            seat_page_error = exc.code or "UNKNOWN"
    mutual = client.get_mutual_verification()
    # Group search requires >= 10 passengers (the app blocks smaller groups
    # client-side, ara0101v.js:551-554); the individual query above may carry a
    # single passenger, so exercise the group leg with a valid group-sized query.
    group_query = replace(query, passengers=PassengerCounts(adult=10))
    group = client.search_group_trains(group_query)
    timetable = client.get_timetable(personal.trains[0]) if personal.trains else None
    fare = client.get_fare(personal.trains[0], query.passengers) if personal.trains else None
    return {
        "loggedIn": bool(session.user_map),
        "mainLoaded": bool(main.text),
        "bookingLoaded": bool(booking.text),
        "noticeCount": len(notices.notices),
        "ticketPageLoaded": bool(tickets.text),
        "personalTrainCount": len(personal.trains),
        "seatPageLoaded": bool(seat_page and seat_page.text),
        "seatSelectionMarkerPresent": bool(
            seat_page and "좌석선택" in seat_page.text
        ),
        # The car list the seat page actually carries; 0 on a page that brought
        # no inventory. seatPageErrorCode names the server's refusal instead
        # (e.g. "error001" for a sold-out train) so the two are distinguishable.
        "seatCarOptionCount": len(seat_page.cars) if seat_page else 0,
        "seatPageErrorCode": seat_page_error,
        "externalSeatMapHandoffPresent": _external_seat_map_handoff_present(
            seat_page
        ),
        "embeddedSeatInventoryCandidatePresent": (
            _embedded_seat_inventory_candidate_present(seat_page)
        ),
        "mutualVerificationLoaded": bool(mutual.verification_code),
        "groupTrainCount": len(group.trains),
        "timetableRowCount": len(timetable.rows) if timetable else 0,
        "fareItemCount": len(fare.items) if fare else 0,
        "selectorLoadedCount": sum(bool(page.text) for page in selectors),
    }


def read_passenger_counts_from_env() -> PassengerCounts:
    """``SRT_*_COUNT`` 환경변수로 승객 구성을 만든다. 기본은 성인 1명이다."""
    return PassengerCounts(
        adult=int(os.environ.get("SRT_ADULT_COUNT", "1")),
        child=int(os.environ.get("SRT_CHILD_COUNT", "0")),
        senior=int(os.environ.get("SRT_SENIOR_COUNT", "0")),
        disability_1_to_3=int(os.environ.get("SRT_DISABILITY_1_TO_3_COUNT", "0")),
        disability_4_to_6=int(os.environ.get("SRT_DISABILITY_4_TO_6_COUNT", "0")),
    )


def read_query_from_env() -> TrainSearchQuery:
    """환경변수로 여정 질의를 만든다. 기본 노선은 수서(0551) → 부산(0020) 06시다.

    ``SRT_TEST_DATE``(``YYYYMMDD``)만 기본값이 없고 없으면 :class:`RuntimeError`
    다. 나머지는 ``SRT_DEPARTURE_STATION_CODE``·``SRT_ARRIVAL_STATION_CODE``·
    ``SRT_DEPARTURE_TIME``·``SRT_DEPARTURE_STATION_NAME``·
    ``SRT_ARRIVAL_STATION_NAME`` 과 :func:`read_passenger_counts_from_env` 다.

    다른 실서버 도구도 이 함수를 거쳐야 같은 변수와 같은 기본값을 쓴다.
    """
    test_date = os.environ.get("SRT_TEST_DATE")
    if not test_date:
        raise RuntimeError("SRT_TEST_DATE is required for live smoke")
    return TrainSearchQuery(
        departure_station_code=os.environ.get("SRT_DEPARTURE_STATION_CODE", "0551"),
        arrival_station_code=os.environ.get("SRT_ARRIVAL_STATION_CODE", "0020"),
        departure_date=test_date,
        departure_time=os.environ.get("SRT_DEPARTURE_TIME", "060000"),
        passengers=read_passenger_counts_from_env(),
        departure_station_name=os.environ.get("SRT_DEPARTURE_STATION_NAME", "수서"),
        arrival_station_name=os.environ.get("SRT_ARRIVAL_STATION_NAME", "부산"),
    )


def read_device_key_from_env() -> str:
    """``SRT_DEVICE_KEY``, 없으면 ANDROID_ID 모양의 자리채움 값을 준다."""
    return os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF")


def train_is_reservable(train: TrainSummary) -> bool:
    """서버가 이 열차에 앉을 자리가 있다고 말하는지.

    일반실과 특실 중 **하나라도** 예약가능이면 ``True`` 다. 좌석 선택이
    일반실에서 특실로 내려가는 기본 동작과 같은 기준이다(srtgo srt.py:486-490 이
    읽는 것과 같은 잔여석 문자열).

    예약대기(매진이지만 대기를 걸 수 있는 상태)는 여기서 ``False`` 다.
    """
    return _general_seat_available(train) or _special_seat_available(train)


def first_reservable_srt_train(
    trains: Sequence[TrainSummary],
    passengers: PassengerCounts | None = None,
) -> TrainSummary | None:
    """예약 가능하면서 **예약 폼까지 만들어지는** 첫 열차. 없으면 ``None``.

    잔여석이 있다고 표시된 행이라도 예약 폼이 요구하는 필드가 빠져 있을 수
    있다. 그래서 필드 목록을 따로 나열하는 대신
    :func:`~srt_mobile_api.payloads.personal_reservation_payload` 를 실제로
    만들어 보고, :class:`ValueError` 가 나는 행은 건너뛴다. 돌려받은 열차는
    예약 페이로드가 받아들이는 열차다.

    ``passengers`` 를 주지 않으면 성인 1명 기준으로 판단한다.
    """
    for train in trains:
        if not train_is_reservable(train):
            continue
        try:
            personal_reservation_payload(
                train,
                passengers or PassengerCounts(adult=1),
                netfunnel_key="",
            )
        except ValueError:
            continue
        return train
    return None


def run_live_smoke_from_env() -> dict[str, Any]:
    """환경변수만으로 :func:`run_live_smoke` 를 실행한다 —— 실서버 진입점.

    ``SRT_MOBILE_API_LIVE=1`` 이 아니면 아무것도 보내지 않고
    :class:`RuntimeError` 다. 클라이언트는 여기서 만들고 끝나면 반드시 닫는다.
    """
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    query = read_query_from_env()
    client = SrtClient(SrtConfig(device_key=read_device_key_from_env()))
    try:
        return run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
