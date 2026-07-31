"""서버 응답을 읽어 모델로 바꾸는 곳 —— HTML 과 JSON 양쪽 다.

:mod:`~srt_mobile_api.payloads` 가 내보내는 쪽이면 이쪽은 받는 쪽입니다.

HTML 에서 요소를 찾는 일은 정규식이 아니라 표준 :mod:`html.parser` 로 합니다.
정규식은 마크업이 아니라 **스크립트 안의 값**을 읽을 때만 씁니다 —— 공공할인
승인 플래그(``var dataNCheck="…";``)와 시각표 행의 역 코드가 그렇습니다.

**이 모듈의 판단 기준 세 가지.**

* *서버가 실패라고 말하면 실패입니다.* HTTP 200 에 정상 페이지 모양이어도
  ``strResult``/``ErrorCode``/경고창 스크립트가 실패를 선언하면
  :class:`~srt_mobile_api.errors.SrtAppError` 계열로 올립니다.
  :func:`~srt_mobile_api.errors.classify_app_error` 가 ``msgCd`` 로 하위 클래스를
  고릅니다.
* *모르는 것은 추측하지 않습니다.* 알아볼 수 없는 봉투나 빠진 필수 필드는
  :class:`~srt_mobile_api.errors.SrtProtocolError` 이고, 원문은 예외의 ``raw``
  에 남습니다.
* *비어 있음은 실패가 아닙니다.* 다만 "없음" 을 빈 배열로 말하는지 FAIL 로
  말하는지는 경로마다 다릅니다 —— 검색은 FAIL, 예약 목록은 빈 배열이며 각 파서
  docstring 에 적어 두었습니다.

세션이 끊긴 응답은 어느 파서에 들어가든
:class:`~srt_mobile_api.errors.SrtSessionExpiredError` 로 바뀝니다. 서버가 HTTP
200 에 로그인 안내 페이지를 실어 보내므로 :func:`is_unauthenticated_page` 가 그
두 모양을 한곳에서 판별합니다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import urljoin, urlsplit

from .config import APP_ORIGIN
from .discounts import public_discount_name
from .errors import (
    SrtAppError,
    SrtNetFunnelKeyError,
    SrtProtocolError,
    SrtSeatUnavailableError,
    SrtSessionExpiredError,
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
    PublicDiscountEntitlement,
    PublicDiscountPage,
    ReservationAttemptResult,
    ReservationRecord,
    ReservationTrain,
    SearchPageState,
    SeatCarOption,
    SeatGrid,
    SeatGridSeat,
    SeatSelectionPage,
    SrtCancelResult,
    SrtCouponRegistrationResult,
    SrtPaymentResult,
    SrtRefundResult,
    SrtRefundTicketInfo,
    SrtReservationHold,
    SrtReservationListResult,
    SrtReservationSummary,
    TimetablePage,
    TimetableRow,
    TrainSearchMetadata,
    TrainSearchResult,
    TrainSummary,
    TransferItinerary,
    TransferSearchResult,
    UnpairedTransferGroup,
)
from .redaction import redact_mapping
from .stations import station_name_by_code


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)


class _SeatPageMarkerParser(HTMLParser):
    _HIDDEN_TAGS: ClassVar[set[str]] = {"script", "style"}
    _VOID_TAGS: ClassVar[set[str]] = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.has_element = False
        self.found_marker = False
        self._hidden_depth = 0
        self._visible_elements: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._HIDDEN_TAGS:
            self._hidden_depth += 1
            return
        if self._hidden_depth:
            return
        self.has_element = True
        if normalized_tag not in self._VOID_TAGS:
            self._visible_elements.append(normalized_tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._hidden_depth and tag.casefold() not in self._HIDDEN_TAGS:
            self.has_element = True

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth and self._visible_elements and "좌석선택" in data:
            self.found_marker = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._HIDDEN_TAGS:
            if self._hidden_depth:
                self._hidden_depth -= 1
            return
        if self._hidden_depth or normalized_tag not in self._visible_elements:
            return
        matching_index = len(self._visible_elements) - 1 - self._visible_elements[::-1].index(
            normalized_tag
        )
        del self._visible_elements[matching_index:]


LOGIN_FORM_ACTION_PATH = "/apb/selectListApb01080_n.do"


def _is_login_form_action(action: str, *, base_url: str) -> bool:
    if not action:
        return False
    parsed = urlsplit(urljoin(f"{base_url}/", action))
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "app.srail.or.kr"
        and port in {None, 443}
        and parsed.username is None
        and parsed.password is None
        and parsed.path == LOGIN_FORM_ACTION_PATH
    )


class _LoginFormParser(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.found = False
        self._form_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        if tag.casefold() == "form":
            self._form_stack.append(
                _is_login_form_action(values.get("action", ""), base_url=self.base_url)
            )
        elif (
            tag.casefold() == "input"
            and any(self._form_stack)
            and values.get("name") == "hmpgPwdCphd"
        ):
            self.found = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "form" and self._form_stack:
            self._form_stack.pop()


def is_login_form(html: str, *, base_url: str = APP_ORIGIN) -> bool:
    """``html`` 에 진짜 로그인 폼이 들어 있는지.

    ``action`` 이 이 서버의 로그인 API(``/apb/selectListApb01080_n.do``)를
    가리키는 ``<form>`` 안에 비밀번호 입력칸(``hmpgPwdCphd``)이 있어야 합니다.
    남의 출처를 가리키는 폼은 세지 않습니다.
    """
    parser = _LoginFormParser(base_url=base_url)
    parser.feed(html)
    return parser.found


# Live 2026-07-26: expired session returns HTTP 200 with normal page shell
# and an inline script: srtAlertBoxDivShow("알림", Sr.msgs.login020, ...).
# No login form, no redirect, no error status — so is_login_form() misses it.
LOGIN_REDIRECT_MESSAGE_KEY = "Sr.msgs.login020"
# The discriminator is the message key, not mvLoginPage() (which is defined on
# ordinary authenticated pages too).
_LOGIN_REDIRECT_CALL = "srtAlertBoxDivShow"


class _LoginRedirectParser(HTMLParser):
    """인증이 필요한 읽기에 서버가 "다시 로그인하라" 고 답한 페이지를 가려냅니다.

    경고창 호출을 ``<script>`` 요소 **안에서만** 찾습니다. 같은 글자가 본문이나
    속성에 있다고 로그인 안내로 오해하지 않기 위해서입니다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.found = False
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "script":
            self._in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if (
            self._in_script
            and LOGIN_REDIRECT_MESSAGE_KEY in data
            and _LOGIN_REDIRECT_CALL in data
        ):
            self.found = True


def is_login_redirect_page(html: str) -> bool:
    """서버가 "다시 로그인하라" 안내 페이지로 답했는지.

    HTTP 200 에 평소와 같은 껍데기를 씌우고 스크립트로 경고창만 띄우는 응답입니다.
    로그인 **폼**은 들어 있지 않으므로 :func:`is_login_form` 으로는 보이지 않습니다.
    """
    parser = _LoginRedirectParser()
    parser.feed(html)
    return parser.found


def is_unauthenticated_page(html: str, *, base_url: str = APP_ORIGIN) -> bool:
    """``html`` 이 인증을 거절하는 응답인지 —— 세션 만료 판정의 유일한 관문.

    서버가 실제로 쓰는 두 모양을 합집합으로 봅니다: 로그인 **폼**
    (:func:`is_login_form`)과 로그인 **안내** 페이지
    (:func:`is_login_redirect_page`). 만료 검사는 전부 이 함수를 지납니다 ——
    폼만 보면 만료된 세션이 "빈 승차권 목록" 으로 읽힙니다.
    """
    return is_login_form(html, base_url=base_url) or is_login_redirect_page(html)


def extract_text(html: str, *, limit: int | None = None) -> str:
    """태그를 걷어 낸 텍스트. 공백은 한 칸으로 접습니다.

    ``<script>``·``<style>`` 안의 내용도 **함께 섞여 나옵니다**. 사람이 읽는
    본문만 남기는 함수가 아니라, 페이지에 어떤 문구가 있는지 확인하는 용도입니다.
    ``limit`` 을 주면 그 길이로 자릅니다.
    """
    parser = _TextExtractor()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return text if limit is None else text[:limit]


def parse_html_page(
    html: str,
    *,
    context: str,
    require_authenticated: bool = False,
) -> HtmlPage:
    """HTML 응답을 :class:`~srt_mobile_api.models.HtmlPage` 로 감쌉니다.

    ``text`` 는 :func:`extract_text` 의 결과이고 ``raw`` 는 원문 그대로입니다. 이
    페이지의 내용을 구조화하지는 않습니다.

    빈 본문은 :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    ``require_authenticated=True`` 면 로그인 요구 응답을
    :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 로 올립니다 —— 만료된
    세션이 "내용 없는 페이지" 로 읽히지 않게 하는 검사이므로, 로그인이 필요한
    읽기에는 켜야 합니다.

    ``context`` 는 예외 메시지에 들어가는 짧은 이름입니다("ticket list" 처럼).
    """
    if not html.strip():
        raise SrtProtocolError(f"SRT {context} returned an empty HTML body")
    if require_authenticated and is_unauthenticated_page(html):
        raise SrtSessionExpiredError(
            f"SRT {context} returned the sign-in page", raw=html
        )
    return HtmlPage(text=extract_text(html), raw=html)


SEAT_CAR_SELECT_ID = "selectScarNo"
_ALERT_CALL_PREFIX = "srtAlertBoxDivShow("
_MESSAGE_KEY_RE = re.compile(r"Sr\.msgs\.(?P<key>\w+)")
_SEAT_COUNT_RE = re.compile(r"\((?P<count>\d+)\s*석\)")


class _SeatCarOptionParser(HTMLParser):
    """호차 목록과 페이지 전체를 덮는 오류 경고를 한 번에 읽습니다.

    둘을 같이 읽는 이유는 하나의 질문이기 때문입니다 —— 이 페이지는 좌석을 가져
    왔는가, 거절을 가져왔는가.

    경고는 스크립트 **전체**가 경고창 호출로 시작할 때만 오류로 봅니다. 정상
    좌석 페이지도 같은 함수를 언급하지만 그것은 함수 본문 안이라 스크립트가
    호출로 시작하지 않습니다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.cars: list[SeatCarOption] = []
        self.error_message_key: str | None = None
        self._in_target_select = False
        self._option_value: str | None = None
        self._option_parts: list[str] = []
        self._in_script = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        values = {key.casefold(): value or "" for key, value in attrs}
        if name == "script":
            self._in_script = True
            self._script_parts = []
        elif name == "select" and values.get("id") == SEAT_CAR_SELECT_ID:
            self._in_target_select = True
        elif name == "option" and self._in_target_select:
            self._option_value = values.get("value", "")
            self._option_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)
        elif self._option_value is not None:
            self._option_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name == "script":
            self._in_script = False
            self._classify_script("".join(self._script_parts))
            self._script_parts = []
        elif name == "option" and self._option_value is not None:
            self._append_car()
        elif name == "select" and self._in_target_select:
            if self._option_value is not None:
                self._append_car()
            self._in_target_select = False

    def _append_car(self) -> None:
        label = re.sub(r"\s+", " ", " ".join(self._option_parts)).strip()
        value = (self._option_value or "").strip()
        self._option_value = None
        self._option_parts = []
        if not value and not label:
            return
        match = _SEAT_COUNT_RE.search(label)
        self.cars.append(
            SeatCarOption(
                car_number=value,
                label=label,
                available_seat_count=int(match.group("count")) if match else None,
            )
        )

    def _classify_script(self, text: str) -> None:
        # A page-level refusal is a script whose WHOLE content is the alert
        # call. A genuine seat page also mentions srtAlertBoxDivShow, but only
        # ever inside a function body (Sr.msgs.rsv045 in
        # showSelectTrainScarList(), Sr.msgs.rsv046 in the seat-count handler),
        # so those scripts never start with the call. That distinction needs no
        # JavaScript scope analysis, which is why it is the one used.
        stripped = text.strip()
        if self.error_message_key is None and stripped.startswith(_ALERT_CALL_PREFIX):
            match = _MESSAGE_KEY_RE.search(stripped)
            self.error_message_key = match.group("key") if match else "UNKNOWN"


def parse_seat_selection_page(html: str) -> SeatSelectionPage:
    """좌석선택 페이지를 읽어 호차 목록을 뽑습니다. 매진 페이지는 거절합니다.

    ``POST /arc/selectListArc02012_n.do`` 의 응답입니다. 자리가 있는 열차면
    ``<select id="selectScarNo">`` 에 호차별 잔여석이 실려 옵니다
    (``<option value='7'> 7호차 (2석) </option>``). 그 괄호 안 숫자가
    :attr:`~srt_mobile_api.models.SeatCarOption.available_seat_count` 이고,
    없으면 ``None`` 입니다.

    **매진 열차에는 서버가 껍데기를 줍니다.** 제목은 같고, 호차 select 도 폼도
    없이 끝에 경고창 스크립트 하나만 붙습니다::

        srtAlertBoxDivShow("알림", Sr.msgs.error001, null, "historyBack();");

    이때는 :class:`~srt_mobile_api.errors.SrtSeatUnavailableError` 이고 ``code``
    는 그 경고 키(``error001``)입니다 —— 이 경로는 HTML 이라 ``msgCd`` 가 없고,
    제목 문구는 두 경우 모두 있어 문구만으로는 구분되지 않습니다.

    **좌석배치도는 여기 없습니다.** 실제 페이지도 ``<div id="trnScarSeatInfo">``
    를 비워 두고 호차를 고른 뒤 따로 불러옵니다 ——
    :func:`parse_seat_grid_response` 입니다.

    로그인이 필요하고, 페이지 표지가 없으면
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    """
    page = parse_html_page(
        html,
        context="seat selection page",
        require_authenticated=True,
    )
    marker_parser = _SeatPageMarkerParser()
    marker_parser.feed(html)
    if not marker_parser.has_element or not marker_parser.found_marker:
        raise SrtProtocolError(
            "SRT seat selection page did not contain the required marker"
        )
    car_parser = _SeatCarOptionParser()
    car_parser.feed(html)
    car_parser.close()
    if car_parser.error_message_key is not None and not car_parser.cars:
        # SrtSeatUnavailableError, a SrtAppError subclass, so an existing
        # `except SrtAppError` around get_seat_page keeps its meaning. `code`
        # stays the messages.js alert KEY (error001), which is all this HTML
        # response carries -- there is no msgCd on this route.
        raise SrtSeatUnavailableError(
            car_parser.error_message_key,
            "SRT seat selection page returned an error instead of a seat map "
            "(no car is selectable; the train is typically sold out)",
            raw=html,
        )
    return SeatSelectionPage(
        text=page.text,
        raw=page.raw,
        cars=tuple(car_parser.cars),
    )


# choiceSeatNo(<internal seat number>, <printed label>, <'Y' | 'N'>) -- the
# onclick of every cell in the 좌석배치도, live-captured 2026-07-26. Single or
# double quotes are both accepted because this is server-rendered markup and
# neither the page nor the bundle promises which it emits.
_SEAT_CHOICE_CALL_RE = re.compile(
    r"""choiceSeatNo\(\s*['"](?P<number>[^'"]*)['"]\s*,"""
    r"""\s*['"](?P<label>[^'"]*)['"]\s*,"""
    r"""\s*['"](?P<selectable>[^'"]*)['"]\s*\)"""
)
# class="seatChoice015Y" -- 좌석속성코드 plus the same Y/N flag the onclick
# carries. Codes 000, 015, 021 and 028 were all present in the captured car.
_SEAT_CLASS_RE = re.compile(r"seatChoice(?P<attribute>[0-9]{3})(?P<selectable>[YN])")
# The grid's error envelope, in the page's own words:
#     args = args.trim(); tmp = args.split("#");
#     if (tmp[0] == "0") alert(tmp[1]); else render(args);
_SEAT_GRID_REFUSAL_MARKER = "0"


class _SeatGridParser(HTMLParser):
    """좌석배치도의 ``choiceSeatNo`` 칸을 문서 순서대로 모읍니다.

    태그 이름이나 class 가 아니라 **onclick** 을 보고 좌석을 찾습니다. 내부
    좌석번호와 표시용 좌석명이 함께 나오고 선택가능 Y/N 이 확정되는 곳이
    거기뿐이기 때문입니다. class 에서는 좌석속성코드만 읽으며, 없어도 됩니다
    (그때는 빈 문자열).
    """

    def __init__(self) -> None:
        super().__init__()
        self.seats: list[SeatGridSeat] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        call = _SEAT_CHOICE_CALL_RE.search(values.get("onclick", ""))
        if call is None:
            return
        class_match = _SEAT_CLASS_RE.search(values.get("class", ""))
        self.seats.append(
            SeatGridSeat(
                internal_seat_number=call.group("number").strip(),
                printed_seat_label=call.group("label").strip(),
                seat_attribute_code=(
                    class_match.group("attribute") if class_match else ""
                ),
                selectable=call.group("selectable").strip().upper() == "Y",
            )
        )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def parse_seat_grid_response(
    html: str, *, car_number: str = "", cabin_class: str = ""
) -> SeatGrid:
    """호차 하나의 좌석배치도 조각(``/arc/selectListArc02011_n.do``)을 읽습니다.

    응답은 페이지가 아니라 HTML **조각**이라 페이지 표지를 요구하지 않습니다.

    **``#`` 봉투는 파싱 실패가 아니라 서버의 거절입니다.** 페이지 자신의 처리가
    ``tmp = args.trim().split("#"); if (tmp[0] == "0") alert(tmp[1]);`` 이므로,
    첫 조각이 정확히 ``"0"`` 인 본문은 배치도가 아니라 메시지입니다. 이때
    :class:`~srt_mobile_api.errors.SrtSeatUnavailableError` 를 내고 ``code`` 는
    봉투의 표시자 ``"0"`` 입니다 —— 이 경로에는 ``msgCd`` 가 없습니다.

    **그 메시지를 원인 진단으로 읽지 않는 편이 좋습니다.** 확인된 거절 하나
    ("출발 20분 전부터 좌석이 자동배정됩니다…")는 시간 규칙이 아니라 이쪽이 보낸
    ``trnNo`` 가 다섯 자리로 채워지지 않아 나온 것이었습니다
    (:data:`~srt_mobile_api.payloads.SEAT_TRAIN_NUMBER_LENGTH`).

    ``car_number`` 와 ``cabin_class`` 는 호출자가 요청한 값을 그대로 새깁니다.
    조각 자체는 자기가 몇 호차인지 말하지 않습니다.

    좌석 칸이 하나도 없으면 :class:`~srt_mobile_api.errors.SrtProtocolError`
    입니다 —— 거절이었다면 서버가 ``"0#…"`` 이라고 말했을 것이기 때문입니다.
    """
    if not html.strip():
        raise SrtProtocolError("SRT seat grid returned an empty body")
    stripped = html.strip()
    marker, separator, message = stripped.partition("#")
    if separator and marker.strip() == _SEAT_GRID_REFUSAL_MARKER:
        raise SrtSeatUnavailableError(
            _SEAT_GRID_REFUSAL_MARKER,
            message.strip() or "SRT seat grid was refused without a message",
            raw=html,
        )
    if is_unauthenticated_page(html):
        raise SrtSessionExpiredError("SRT seat grid returned the sign-in page", raw=html)
    parser = _SeatGridParser()
    parser.feed(html)
    parser.close()
    if not parser.seats:
        # Not a refusal (the server would have said "0#..."), and not a grid
        # either. Refusing to return an empty SeatGrid keeps "no seats" from
        # being indistinguishable from "a shape we do not understand".
        raise SrtProtocolError(
            "SRT seat grid contained no choiceSeatNo seat cells", raw=html
        )
    return SeatGrid(
        text=extract_text(html),
        raw=html,
        car_number=car_number,
        cabin_class=cabin_class,
        seats=tuple(parser.seats),
    )


# The 할인쿠폰 page's own markup vocabulary, taken from the live page
# (2026-07-26). `coupList` is the list CONTAINER and is rendered whether or not
# the account holds anything, which is what makes it usable as the page's
# identity marker; `coup-box` is one coupon.
COUPON_LIST_CLASS = "coupList"
_COUPON_BOX_CLASS = "coup-box"
# Six spans, keyed by class. Read from the page's own commented-out template --
# see models.DiscountCoupon for why that is the best evidence available and for
# why every value stays display text.
_COUPON_SPAN_FIELDS = {
    "num": "coupon_number",
    "type": "discount_kind",
    "rate": "discount_rate",
    "date": "validity",
    "boarding": "basis",
    "useCnt": "remaining_uses",
}
COUPON_EMPTY_MARKER = "보유한 쿠폰이 없습니다"


class _DiscountCouponParser(HTMLParser):
    """할인쿠폰 페이지의 ``coup-box`` 를 모으고, 목록 자체가 있는지도 기록합니다.

    **주석 안의 마크업은 마크업으로 읽히지 않습니다.** 이 페이지에서는 그것이
    안전장치입니다 —— 실제 페이지의 ``ul.coupList`` 안에는 그럴듯한 쿠폰번호와
    할인율이 박힌 디자인 템플릿 두 개가 주석으로 들어 있습니다.
    :class:`~html.parser.HTMLParser` 는 주석을 통째로 한 덩어리로 넘기고 그
    안에서는 시작 태그를 만들지 않으므로 템플릿이 쿠폰이 되지 않습니다. 같은
    페이지를 정규식으로 긁으면 없는 쿠폰 두 장이 생깁니다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.has_coupon_list = False
        self.coupons: list[DiscountCoupon] = []
        self._in_box = False
        self._fields: dict[str, str] = {}
        self._span_field: str | None = None
        self._span_parts: list[str] = []

    def _flush(self) -> None:
        if self._fields:
            self.coupons.append(DiscountCoupon(**self._fields))
        self._fields = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        values = {key.casefold(): value or "" for key, value in attrs}
        classes = values.get("class", "").split()
        if name == "ul" and COUPON_LIST_CLASS in classes:
            self.has_coupon_list = True
        if name == "div" and _COUPON_BOX_CLASS in classes:
            # A new box ends the previous one without needing to match depth,
            # which keeps this immune to the page's nested left/right halves.
            self._flush()
            self._in_box = True
        elif self._in_box and name == "span":
            self._span_field = next(
                (
                    _COUPON_SPAN_FIELDS[name_]
                    for name_ in classes
                    if name_ in _COUPON_SPAN_FIELDS
                ),
                None,
            )
            self._span_parts = []

    def handle_data(self, data: str) -> None:
        if self._span_field is not None:
            self._span_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name == "span" and self._span_field is not None:
            self._fields[self._span_field] = " ".join("".join(self._span_parts).split())
            self._span_field = None
        elif name == "ul" and self._in_box:
            self._flush()
            self._in_box = False

    def close(self) -> None:
        super().close()
        self._flush()


def parse_discount_coupon_page(html: str) -> DiscountCouponList:
    """할인쿠폰 조회/등록 페이지(``/apa/selectListApa03020_n.do``)를 읽습니다.

    쿠폰이 없는 계정은 ``ul.coupList`` 가 비어 있고 ``보유한 쿠폰이 없습니다.``
    안내가 붙습니다. 그 상태가 확인된 유일한 상태이고, 쿠폰을 가진 계정의 응답은
    미검증입니다 —— 필드명 근거는
    :class:`~srt_mobile_api.models.DiscountCoupon` 참고.

    **"없다" 와 "이 페이지를 못 읽었다" 를 섞지 않습니다.** 페이지가 둘 중 하나를
    말하도록 요구하며, 다음 세 경우는 모두
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

    * ``ul.coupList`` 가 아예 없는 경우 —— 쿠폰 페이지가 아닙니다.
    * 쿠폰도 없고 "없습니다" 문구도 없는 경우.
    * 쿠폰이 있는데 "없습니다" 문구도 있는 경우.

    **등록 폼은 건드리지 않습니다.** 같은 페이지의 ``dscp_no``/``dscp_pwd`` 는
    자격증명이고 이 파서의 결과는 가려지지 않으므로 읽지 않습니다. 등록은 다른
    경로(``/arb/selectListArb02A01_n.do``)이고
    :meth:`~srt_mobile_api.client.SrtClient.register_discount_coupon` 의 일입니다.
    """
    page = parse_html_page(
        html,
        context="discount coupon page",
        require_authenticated=True,
    )
    parser = _DiscountCouponParser()
    parser.feed(html)
    parser.close()
    if not parser.has_coupon_list:
        raise SrtProtocolError(
            "SRT discount coupon page did not contain the coupon list",
            raw=html,
        )
    says_empty = COUPON_EMPTY_MARKER in page.text
    if parser.coupons and says_empty:
        raise SrtProtocolError(
            "SRT discount coupon page both listed coupons and said it held none",
            raw=html,
        )
    if not parser.coupons and not says_empty:
        raise SrtProtocolError(
            "SRT discount coupon page listed no coupons and did not say it held "
            "none",
            raw=html,
        )
    return DiscountCouponList(
        text=page.text,
        raw=html,
        coupons=tuple(parser.coupons),
    )


# Anchored on `var` to match only DECLARATIONS (not client-side reassignments).
_PUBLIC_DISCOUNT_FLAG_RE = re.compile(
    r'var\s+data([1-8])Check\s*=\s*"([^"]*)"\s*;'
)
_PUBLIC_DISCOUNT_APPROVED = "Y"
PUBLIC_DISCOUNT_SLOT_COUNT = 8
# The hidden input that identifies this page. Present whether or not the account
# holds anything, and 0-hit in the v2.0.41 bundle.
PUBLIC_DISCOUNT_FIELD = "PBL_DISC_CD"


class _PublicDiscountMarkerParser(HTMLParser):
    """페이지 고유의 ``PBL_DISC_CD`` 입력을 보면 참이 됩니다 —— 페이지 신원 확인."""

    def __init__(self) -> None:
        super().__init__()
        self.found_marker = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "input":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        if values.get("name") == PUBLIC_DISCOUNT_FIELD:
            self.found_marker = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def parse_public_discount_page(html: str) -> PublicDiscountPage:
    """할인 승차권 페이지(``/common/ARA/ARA0301V/view.do``)의 공공할인 자격을 읽습니다.

    자격은 서버가 렌더링하는 여덟 개의 ``var dataNCheck="…";`` 선언에 들어
    있고, 슬롯 1~8 이 곧 공공할인코드 ``01``~``08`` 입니다. 값이 ``"Y"`` 면 승인,
    아니면 미승인입니다.

    **아무 자격도 없는 계정도 정상 반환입니다** —— "가진 것이 없다" 가 질문에
    대한 답입니다. 확인된 것은 여덟 플래그가 전부 빈 계정 하나뿐입니다.

    거절하는 경우는 둘이고, 모양이 달라진 페이지가 "자격 없음" 으로 둔갑하지
    않게 하기 위한 것입니다. 둘 다
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

    * ``PBL_DISC_CD`` 입력이 없는 경우 —— 이 페이지가 아닙니다.
    * 플래그 선언이 여덟이 아니거나 같은 슬롯이 중복되는 경우 —— 코드와 슬롯의
      대응이 여덟 칸 배치에 기대고 있기 때문입니다.

    ``""``·``"Y"`` 가 아닌 값은 거절하지 않고 미승인으로 봅니다. 페이지 자신도
    ``== "Y"`` 와 ``!= "Y"`` 로만 검사합니다.
    """
    page = parse_html_page(
        html,
        context="public discount page",
        require_authenticated=True,
    )
    marker_parser = _PublicDiscountMarkerParser()
    marker_parser.feed(html)
    marker_parser.close()
    if not marker_parser.found_marker:
        raise SrtProtocolError(
            "SRT public discount page did not contain the PBL_DISC_CD field",
            raw=html,
        )
    matches = _PUBLIC_DISCOUNT_FLAG_RE.findall(html)
    flags = dict(matches)
    if len(flags) != PUBLIC_DISCOUNT_SLOT_COUNT or len(matches) != len(flags):
        raise SrtProtocolError(
            "SRT public discount page did not declare exactly eight "
            f"공공할인 approval flags (saw {len(matches)})",
            raw=html,
        )
    entitlements = tuple(
        PublicDiscountEntitlement(
            code=code,
            name=public_discount_name(code),
            approved=flags[str(slot)].strip() == _PUBLIC_DISCOUNT_APPROVED,
        )
        for slot in range(1, PUBLIC_DISCOUNT_SLOT_COUNT + 1)
        for code in (f"{slot:02d}",)
    )
    return PublicDiscountPage(
        text=page.text,
        raw=html,
        entitlements=entitlements,
    )


def parse_notice_list_response(data: dict[str, Any]) -> NoticeListResult:
    """공지 목록 JSON 을 :class:`~srt_mobile_api.models.NoticeListResult` 로 만듭니다.

    봉투는 ``ErrorCode``/``ErrorMsg`` 입니다 —— ``""`` 나 ``"0"`` 이 아니면
    :class:`~srt_mobile_api.errors.SrtAppError` 입니다. 공지가 없는 것은 빈
    ``noticeList`` 이고 정상입니다.

    행 검사는 엄격합니다. 여섯 문자열 필드(``IS_MAIN``·``PAGE_ID``·``BODY``·
    ``CREATE_DATE``·``IS_NOTICE``·``SUBJ``)와 정수 ``POST_NO`` 중 하나라도
    타입이 어긋나면 :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다
    —— ``POST_NO`` 는 ``bool`` 도 거절합니다.
    """
    if not isinstance(data, dict):
        raise SrtProtocolError("SRT notice response must be a JSON object", raw=data)
    error_code = data.get("ErrorCode", "")
    error_message = data.get("ErrorMsg", "")
    if not isinstance(error_code, str):
        raise SrtProtocolError("SRT notice ErrorCode must be a string", raw=data)
    if not isinstance(error_message, str):
        raise SrtProtocolError("SRT notice ErrorMsg must be a string", raw=data)
    if error_code not in {"", "0"}:
        raise SrtAppError(error_code, error_message, raw=data)
    rows = data.get("noticeList")
    if not isinstance(rows, list):
        raise SrtProtocolError("SRT notice response missing noticeList", raw=data)
    notices: list[Notice] = []
    string_fields = (
        "IS_MAIN",
        "PAGE_ID",
        "BODY",
        "CREATE_DATE",
        "IS_NOTICE",
        "SUBJ",
    )
    for row in rows:
        if not isinstance(row, dict):
            raise SrtProtocolError("SRT notice row must be an object", raw=data)
        for key in string_fields:
            if not isinstance(row.get(key), str):
                raise SrtProtocolError(
                    f"SRT notice row {key} must be a string",
                    raw=data,
                )
        if type(row.get("POST_NO")) is not int:
            raise SrtProtocolError(
                "SRT notice row POST_NO must be an integer",
                raw=data,
            )
        notices.append(
            Notice(
                is_main=row["IS_MAIN"],
                page_id=row["PAGE_ID"],
                body=row["BODY"],
                post_no=row["POST_NO"],
                create_date=row["CREATE_DATE"],
                is_notice=row["IS_NOTICE"],
                subject=row["SUBJ"],
                raw=row,
            )
        )
    return NoticeListResult(notices=tuple(notices), raw=data)


class _InputParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = {name: value or "" for name, value in attrs}
        name = values.get("name")
        if name:
            self.fields[name] = values.get("value", "")


def parse_search_page_state(html: str) -> SearchPageState:
    page = parse_html_page(html, context="search hydration", require_authenticated=True)
    parser = _InputParser()
    parser.feed(html)
    if not parser.fields:
        raise SrtProtocolError("SRT search hydration page did not contain named inputs")
    return SearchPageState(hidden_fields=parser.fields, raw=page.raw)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.data_rows: list[list[str]] = []
        # data_rows grouped by the <table> they came from, in document order,
        # with the empty groups dropped. The fare page renders one table per
        # journey leg and only the first is ever populated -- see
        # parse_fare_page.
        self.data_row_tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None
        self._row_has_data_cell = False
        self._table_data_rows: list[list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "table":
            self._close_table()
            self._table_data_rows = []
        elif tag.lower() == "tr":
            self._row = []
            self._row_has_data_cell = False
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []
            if tag.lower() == "td":
                self._row_has_data_cell = True

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(re.sub(r"\s+", " ", " ".join(self._cell_parts)).strip())
            self._cell_parts = None
        elif tag.lower() == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
                if self._row_has_data_cell:
                    self.data_rows.append(self._row)
                    if self._table_data_rows is not None:
                        self._table_data_rows.append(self._row)
            self._row = None
        elif tag.lower() == "table":
            self._close_table()

    def _close_table(self) -> None:
        if self._table_data_rows:
            self.data_row_tables.append(self._table_data_rows)
        self._table_data_rows = None

    def close(self) -> None:
        super().close()
        self._close_table()


TIME_RE = re.compile(r"\b\d{2}:\d{2}\b")
FARE_RE = re.compile(r"(\d{1,3}(?:,\d{3})*)\s*원")
# The call the timetable page uses to fill in a stop's name client-side. Live
# capture, 2026-07-26 -- see parse_timetable_page.
STATION_NAME_CALL_RE = re.compile(
    r"getStationNameByCode\(\s*['\"](?P<code>[0-9]+)['\"]\s*\)"
)
# A cell holding only this is a "no time here" placeholder (the origin has no
# arrival time, the terminus no departure time), not a station name.
_TIMETABLE_PLACEHOLDER_CELLS = frozenset({"-", "–", "—", ""})


class _TimetableTableParser(_TableParser):
    """표 파서에 더해, 각 행의 인라인 스크립트가 실은 역 코드를 함께 모읍니다.

    역 이름은 마크업에 없습니다. ``<tr>`` **안**의 ``<script>`` 가 코드로부터
    이름을 채웁니다. 그래서 코드는 행에 붙여서 모읍니다 —— 문서 순서로 코드만
    늘어놓고 나중에 행과 짝지으면, 스크립트 없는 행이 하나만 나와도 전체가
    밀립니다.
    """

    def __init__(self) -> None:
        super().__init__()
        self.row_station_codes: list[str] = []
        self._row_script_parts: list[str] | None = None
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row_script_parts = []
        elif tag.lower() == "script":
            self._in_script = True
        super().handle_starttag(tag, attrs)

    def handle_data(self, data: str) -> None:
        if self._in_script:
            if self._row_script_parts is not None:
                self._row_script_parts.append(data)
            return
        super().handle_data(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script":
            self._in_script = False
            return
        row_had_cells = self._row is not None and any(self._row or ())
        super().handle_endtag(tag)
        if tag.lower() == "tr":
            script_text = " ".join(self._row_script_parts or ())
            self._row_script_parts = None
            if row_had_cells:
                match = STATION_NAME_CALL_RE.search(script_text)
                self.row_station_codes.append(match.group("code") if match else "")


def parse_timetable_page(html: str) -> TimetablePage:
    """열차 시간표 페이지를 읽습니다. 정차역 이름은 코드에서 되살립니다.

    **역 이름은 HTML 에 없습니다.** 이름 칸은 비워진 채로 오고 행 안의 스크립트가
    코드로 채웁니다::

        <tr class="ac">
            <td id="stationNm_1">
            ...
            <script>$("#stationNm_1").html( getStationNameByCode('0551') );</script>
            <td>-</td>
            <td>10:00</td>
        </tr>

    그래서 코드를 읽어 :func:`~srt_mobile_api.stations.station_name_by_code` 로
    이름을 만듭니다(앱이 쓰는 것과 같은 표). 코드 자체도
    :attr:`~srt_mobile_api.models.TimetableRow.station_code` 에 남습니다.

    스크립트가 없는 행에서는 셀에서 이름을 찾는 옛 방식으로 물러섭니다. 시각도
    자리채움 대시(``-``)도 아닌 첫 셀입니다 —— 출발역에는 도착시각이, 종착역에는
    출발시각이 없어 그 자리에 대시가 오기 때문입니다.

    시각이 하나도 없는 행은 버립니다. 표에서 아무 행도 못 얻으면 페이지 전체
    텍스트에서 시각을 긁어 한 행으로 만들고, 그마저 없으면
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    """
    page = parse_html_page(html, context="timetable")
    table = _TimetableTableParser()
    table.feed(html)
    table.close()
    rows: list[TimetableRow] = []
    for index, cells in enumerate(table.rows):
        raw_text = " ".join(cells)
        times = tuple(TIME_RE.findall(raw_text))
        if not times:
            continue
        code = (
            table.row_station_codes[index]
            if index < len(table.row_station_codes)
            else ""
        )
        station = station_name_by_code(code) if code else ""
        if not station:
            station = next(
                (
                    cell.strip()
                    for cell in cells
                    if cell.strip() not in _TIMETABLE_PLACEHOLDER_CELLS
                    and not TIME_RE.fullmatch(cell.strip())
                ),
                "",
            )
        rows.append(
            TimetableRow(
                station_name=station,
                times=times,
                raw_text=raw_text,
                station_code=code,
            )
        )
    if not rows:
        times = tuple(TIME_RE.findall(page.text))
        if not times:
            raise SrtProtocolError("SRT timetable page did not contain timetable rows or times")
        rows.append(TimetableRow(station_name="", times=times, raw_text=page.text))
    return TimetablePage(text=page.text, raw=page.raw, rows=tuple(rows))


def parse_fare_page(html: str) -> FarePage:
    """운임·요금 페이지에서 **우리가 물어본 한 구간**의 운임만 읽습니다.

    페이지 자체는 환승 여정용이라 구간마다 운임표를 하나씩 렌더링하지만
    (``trainPayInfo1``, ``trainPayInfo22``), 이쪽 요청은 한 구간만 말할 수
    있습니다 —— :func:`~srt_mobile_api.payloads.fare_payload` 가 둘째 구간 필드를
    빈 값으로 고정합니다.

    **감춰진 둘째 표도 비어 있지는 않습니다.** 같은 이름표에 금액만 ``0원`` 인
    행이 들어 있습니다::

        어른 특실 -        어른 일반실 0원

    표를 전부 읽으면 ``{이름표: 금액}`` 을 만든 호출자가 ``어른 일반실`` 을
    0원으로 읽게 되므로, 데이터 행이 있는 **첫 표**만 읽습니다. 페이지의
    ``hide()`` 호출은 신호로 쓰지 않습니다 —— 진짜 표를 감추는 ``hide()`` 도 다른
    분기에 있기 때문입니다.

    :attr:`~srt_mobile_api.models.FarePage.items` 는 금액이 읽힌 항목만이고,
    ``-`` 처럼 금액이 없는 칸까지 포함한 전체는
    :attr:`~srt_mobile_api.models.FarePage.semantic_items` 에 있습니다(그쪽은
    ``amount`` 가 ``None`` 이고 원문이 ``status`` 에 남습니다).

    의미 있는 행이 하나도 없으면 :class:`~srt_mobile_api.errors.SrtProtocolError`
    입니다.
    """
    page = parse_html_page(html, context="fare")
    table = _TableParser()
    table.feed(html)
    table.close()
    leg_rows = table.data_row_tables[0] if table.data_row_tables else table.data_rows
    items: list[FareItem] = []
    for cells in leg_rows:
        semantic_cells = [cell.strip() for cell in cells if cell.strip()]
        if len(semantic_cells) < 2:
            continue
        label = " ".join(semantic_cells[:-1])
        amount_text = semantic_cells[-1]
        match = FARE_RE.search(amount_text)
        raw_amount = match.group(0) if match else amount_text
        amount = int(match.group(1).replace(",", "")) if match else None
        items.append(
            FareItem(
                label=label,
                amount=amount,
                raw_amount=raw_amount,
                available=amount is not None,
                status=None if amount is not None else amount_text,
            )
        )
    if not items:
        raise SrtProtocolError("SRT fare page did not contain semantic fare rows")
    semantic_items = tuple(items)
    available_items = tuple(item for item in semantic_items if item.available)
    return FarePage(
        text=page.text,
        raw=page.raw,
        items=available_items,
        semantic_items=semantic_items,
    )


def _first_row(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        first = value[0] if value else {}
        return first if isinstance(first, dict) else {}
    if isinstance(value, dict):
        return value
    return {}


def _declares_status(row: dict[str, Any]) -> bool:
    status = row.get("strResult")
    return isinstance(status, str) and bool(status)


def normalize_result_row(data: dict[str, Any]) -> dict[str, Any]:
    """두 봉투 중 실제로 결과 행이 든 쪽을 고릅니다.

    ``outDataSets.dsOutput0`` 를 우선하되 비어 있으면 ``resultMap`` 으로 물러섭니다.
    **양쪽이 다 상태를 말하고 서로 어긋나면 실패 쪽을 믿습니다** — 안전한 쪽으로
    닫는 선택입니다. 상태 선언이 없는 행은 그대로 돌려줍니다.
    """
    out = data.get("outDataSets") or {}
    primary: dict[str, Any] = {}
    if isinstance(out, dict):
        primary = _first_row(out.get("dsOutput0"))
    fallback = _first_row(data.get("resultMap"))

    if not _declares_status(primary):
        return primary or fallback
    if not _declares_status(fallback):
        return primary
    if primary.get("strResult") == fallback.get("strResult"):
        return primary
    return fallback if fallback.get("strResult") != "SUCC" else primary


def parse_mutual_verification_response(
    data: dict[str, Any],
) -> MutualVerificationResult:
    """상호확인코드(``mutMrkVrfCd``) 발급 응답을 읽습니다.

    ``ErrorCode`` 봉투를 먼저 보고, 안쪽 ``dsOutput0`` 행에서 ``strResult`` 와
    ``mutMrkVrfCd`` 를 읽습니다. ``FAIL`` 이면
    :func:`~srt_mobile_api.errors.classify_app_error` 로 분류해 올리고, 성공인데
    코드가 비어 있으면 :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

    ``msgCd`` 는 있어도 되고 없어도 됩니다 —— 앱도 이 경로에서는 ``strResult`` 만
    보고 ``mutMrkVrfCd`` 를 읽습니다(``ara1001l.js:234-241``). 모델에 없는
    ``wctNo``·``uuid``·``cgPsId`` 는
    :attr:`~srt_mobile_api.models.MutualVerificationResult.raw` 로 볼 수 있습니다.

    이 경로는 로그인 없이도 코드를 내줍니다 —— 이 라이브러리의 다른 읽기와 다른
    점입니다.
    """
    if not isinstance(data, dict):
        raise SrtProtocolError(
            "SRT mutual verification response must be a JSON object"
        )
    wrapper_code = data.get("ErrorCode", "")
    wrapper_message = data.get("ErrorMsg", "")
    if not isinstance(wrapper_code, str):
        raise SrtProtocolError(
            "SRT mutual verification ErrorCode must be a string"
        )
    if not isinstance(wrapper_message, str):
        raise SrtProtocolError(
            "SRT mutual verification ErrorMsg must be a string"
        )
    if wrapper_code not in {"", "0"}:
        raise SrtAppError(
            wrapper_code,
            "SRT mutual verification request failed",
            raw=data,
        )

    datasets = data.get("outDataSets")
    if not isinstance(datasets, dict):
        raise SrtProtocolError(
            "SRT mutual verification response missing outDataSets"
        )
    value = datasets.get("dsOutput0")
    if isinstance(value, list):
        if len(value) != 1 or not isinstance(value[0], dict):
            raise SrtProtocolError(
                "SRT mutual verification dsOutput0 must contain one object"
            )
        row = value[0]
    elif isinstance(value, dict):
        row = value
    else:
        raise SrtProtocolError(
            "SRT mutual verification response missing dsOutput0 object"
        )

    code = row.get("msgCd")
    status = row.get("strResult")
    message = row.get("msgTxt", "")
    verification_code = row.get("mutMrkVrfCd")
    # App gates on strResult only, not msgCd (ara1001l.js:234-241).
    # Live 2026-07-26: row has 7 keys including msgCd "IRZ000008", wctNo, uuid,
    # cgPsId. Route answers SUCC without a session cookie — it's public.
    message_code = code if isinstance(code, str) else None
    if not isinstance(status, str):
        raise SrtProtocolError(
            "SRT mutual verification strResult must be a string"
        )
    if not isinstance(message, str):
        raise SrtProtocolError(
            "SRT mutual verification message must be a string"
        )
    if status == "FAIL":
        raise classify_app_error(
            message_code,
            "SRT mutual verification failed",
            raw=data,
        )
    if not isinstance(verification_code, str) or not verification_code.strip():
        raise SrtProtocolError(
            "SRT mutual verification mutMrkVrfCd must be a non-empty string"
        )
    return MutualVerificationResult(
        message_code=message_code,
        status=status,
        message=message,
        verification_code=verification_code,
        raw=data,
    )


def _reservation_attempt_row(
    data: dict[str, Any],
    container_name: str,
) -> dict[str, Any]:
    value = data.get(container_name)
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], dict)
        or not value[0]
    ):
        raise SrtProtocolError(
            f"SRT reservation attempt {container_name} must contain exactly one object",
            raw=data,
        )
    return value[0]


def _reservation_attempt_string(
    row: dict[str, Any],
    key: str,
    *,
    container_name: str,
    raw: dict[str, Any],
    allow_empty: bool = False,
) -> str:
    value = row.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        requirement = "a string" if allow_empty else "a non-empty string"
        raise SrtProtocolError(
            f"SRT reservation attempt {container_name} {key} must be {requirement}",
            raw=raw,
        )
    return value


def _validate_error_code_wrapper(
    data: dict[str, Any],
    *,
    context: str = "reservation attempt",
) -> None:
    code_present = "ERROR_CODE" in data
    message_present = "ERROR_MSG" in data
    if code_present != message_present:
        raise SrtProtocolError(
            f"SRT {context} ERROR_CODE/ERROR_MSG wrapper pair is partial",
            raw=data,
        )
    if not code_present:
        return
    code = data["ERROR_CODE"]
    message = data["ERROR_MSG"]
    if not isinstance(code, str) or not isinstance(message, str):
        raise SrtProtocolError(
            f"SRT {context} ERROR_CODE and ERROR_MSG must be strings",
            raw=data,
        )
    if code not in {"", "0"}:
        raise SrtAppError(code, message or f"SRT {context} rejected", raw=data)


def parse_reservation_attempt_response(
    data: dict[str, Any],
) -> ReservationAttemptResult:
    """이미 받아 둔 예약 시도 응답을 요청 없이 해석합니다.

    ``resultMap``·``reservListMap``·``trainListMap``·``commandMap`` 네 봉투를
    읽어 :class:`~srt_mobile_api.models.ReservationAttemptResult` 로 만듭니다.

    **``strResult`` 가 정확히 ``"FAIL"`` 일 때만 실패입니다.** 앱도 그렇게
    판정하고(``ara1001l.js:1562``), 다른 값은 통과시켜 PNR 을 읽습니다. 제3의
    값을 실패로 뒤집으면 서버에 실제로 잡혀 있는 예약이 예외로 사라집니다.

    실패의 갈래는 셋입니다.

    * ``msgCd`` 가 ``S111`` 이면
      :class:`~srt_mobile_api.errors.SrtSessionExpiredError` —— 앱이 이것을
      재로그인 신호로 다룹니다.
    * ``msgCd`` 가 ``WRP011002``(인원 오류)이면 ``strResult`` 와 무관하게
      실패입니다.
    * 그 밖의 FAIL 은 :func:`~srt_mobile_api.errors.classify_app_error` 가
      코드에 맞는 예외를 고릅니다.

    **선언된 실패를 먼저 판정하고, 엄격한 필드 검사는 성공일 때만 합니다.**
    순서를 뒤집으면 "실패했는데 응답도 조금 어긋난" 경우가
    :class:`~srt_mobile_api.errors.SrtProtocolError` 로 나가고, 그것을
    :func:`parse_reservation_hold_response` 의 구제 분기가 받아 존재하지 않는
    예약을 만들어 냅니다.

    성공 경로에서는 PNR·좌석 등 필드가 전부 문자열이어야 하며, 하나라도
    어긋나면 :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    ``ERROR_CODE``/``ERROR_MSG`` 바깥 봉투는 둘 다 있거나 둘 다 없어야 합니다.
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT reservation attempt response must be a non-empty JSON object",
            raw=data,
        )
    _validate_error_code_wrapper(data)

    result_row = _reservation_attempt_row(data, "resultMap")
    status = _reservation_attempt_string(
        result_row,
        "strResult",
        container_name="resultMap",
        raw=data,
    )
    # Only == "FAIL" is failure (ara1001l.js:1562). A third value means a hold
    # exists (:1577/:1609 read pnrNo). Failure is classified BEFORE strict field
    # reads so a malformed FAIL doesn't become SrtProtocolError → false salvage.
    declared_code = result_row.get("msgCd")
    declared_message = result_row.get("msgTxt")
    code_hint = declared_code if isinstance(declared_code, str) else ""
    message_hint = declared_message if isinstance(declared_message, str) else ""
    declared_failure = status == "FAIL"
    if declared_failure and code_hint == "S111":
        # S111 = re-login signal (ara1001l.js:1562-1571).
        raise SrtSessionExpiredError(
            message_hint or "SRT reservation attempt session expired",
            raw=data,
        )
    # WRP011002 (passenger-count) fails regardless of strResult (live-observed).
    if code_hint == "WRP011002" or declared_failure:
        raise classify_app_error(code_hint, message_hint or status, raw=data)

    # Success path: strict field reads (salvage handles malformed cases).
    code = _reservation_attempt_string(
        result_row,
        "msgCd",
        container_name="resultMap",
        raw=data,
    )
    message = _reservation_attempt_string(
        result_row,
        "msgTxt",
        container_name="resultMap",
        raw=data,
        allow_empty=True,
    )
    total_received_amount = _reservation_attempt_string(
        result_row,
        "totRcvdAmt",
        container_name="resultMap",
        raw=data,
    )
    temporary_job_sequence = _reservation_attempt_string(
        result_row,
        "tmpJobSqno1",
        container_name="resultMap",
        raw=data,
    )
    reservation_row = _reservation_attempt_row(data, "reservListMap")
    train_row = _reservation_attempt_row(data, "trainListMap")
    command_row = _reservation_attempt_row(data, "commandMap")

    reservation_values = {
        key: _reservation_attempt_string(
            reservation_row,
            key,
            container_name="reservListMap",
            raw=data,
        )
        for key in (
            "pnrNo",
            "JRNYLIST_KEY",
            "arvDt",
            "arvRsStnCd",
            "arvTm",
            "dlayAcptFlg",
            "dptDt",
            "dptRsStnCd",
            "dptTm",
            "lumpStlTgtNo",
            "proyStlTgtFlg",
            "stlbTrnClsfCd",
            "totSeatNum",
            "trnGpCd",
            "trnNo",
        )
    }
    reservation = ReservationRecord(
        pnr_number=reservation_values["pnrNo"],
        journey_list_key=reservation_values["JRNYLIST_KEY"],
        arrival_date=reservation_values["arvDt"],
        arrival_station_code=reservation_values["arvRsStnCd"],
        arrival_time=reservation_values["arvTm"],
        delay_acceptance_flag=reservation_values["dlayAcptFlg"],
        departure_date=reservation_values["dptDt"],
        departure_station_code=reservation_values["dptRsStnCd"],
        departure_time=reservation_values["dptTm"],
        lump_settlement_target_number=reservation_values["lumpStlTgtNo"],
        provisional_settlement_target_flag=reservation_values["proyStlTgtFlg"],
        service_class_code=reservation_values["stlbTrnClsfCd"],
        total_seat_count=reservation_values["totSeatNum"],
        train_group_code=reservation_values["trnGpCd"],
        train_number=reservation_values["trnNo"],
        raw=reservation_row,
    )
    train = ReservationTrain(
        seat_number=_reservation_attempt_string(
            train_row,
            "seatNo",
            container_name="trainListMap",
            raw=data,
        ),
        car_number=_reservation_attempt_string(
            train_row,
            "scarNo",
            container_name="trainListMap",
            raw=data,
        ),
        raw=train_row,
    )
    return ReservationAttemptResult(
        message_code=code,
        status=status,
        total_received_amount=total_received_amount,
        reservation=reservation,
        train=train,
        message=message,
        temporary_job_sequence=temporary_job_sequence,
        command=dict(command_row),
        raw=data,
    )


def _minimal_hold_from_raw(data: Any) -> SrtReservationHold | None:
    """엄격한 파싱이 거절한 응답에서 취소에 필요한 PNR 만 건져 냅니다.

    ``reservListMap[0].pnrNo`` 가 없으면 ``None``. 나머지 필드는 문자열일 때만 가져
    오고, 부수적 필드 하나가 망가졌다고 PNR 을 통째로 잃지 않습니다.
    """
    if not isinstance(data, dict):
        return None
    row = _first_row(data.get("reservListMap"))
    pnr = row.get("pnrNo")
    if not isinstance(pnr, str) or not pnr.strip():
        return None
    journey_list_key = row.get("JRNYLIST_KEY")
    total_seat_count = row.get("totSeatNum")
    return SrtReservationHold(
        pnr_no=pnr.strip(),
        journey_list_key=(
            journey_list_key if isinstance(journey_list_key, str) else ""
        ),
        total_seat_count=(
            total_seat_count if isinstance(total_seat_count, str) else ""
        ),
        raw=data,
    )


def _declares_a_declared_failure(data: Any) -> bool:
    """응답 자신이 ``strResult == "FAIL"`` 이라고 선언했는지.

    구제 경로가 선언된 실패를 "예약이 있다" 로 둔갑시키지 않게 하는 두 번째 층.
    ``== "FAIL"`` (not ``!= "SUCC"``) — 제3의 값은 예약이 생긴 쪽이므로
    (ara1001l.js:1562, :1577/:1609).
    """
    if not isinstance(data, dict):
        return False
    row = normalize_result_row(data)
    return row.get("strResult") == "FAIL"


def parse_reservation_hold_response(data: dict[str, Any]) -> SrtReservationHold:
    """예약 응답에서 취소 가능한 최소 신원(PNR·여정키·좌석수)만 남깁니다.

    :func:`parse_reservation_attempt_response` 의 성공 판정을 거치고, 실패하면
    PNR 이 있는 한 최소 홀드로 구제합니다. 업무 실패와 세션 만료는 구제하지 않습니다.
    """
    try:
        result = parse_reservation_attempt_response(data)
    except SrtProtocolError:
        if _declares_a_declared_failure(data):
            raise
        hold = _minimal_hold_from_raw(data)
        if hold is None:
            raise
        return hold
    return SrtReservationHold(
        pnr_no=result.reservation.pnr_number,
        journey_list_key=result.reservation.journey_list_key,
        total_seat_count=result.reservation.total_seat_count,
        raw=data,
    )


def _parse_result_envelope(
    data: dict[str, Any],
    *,
    context: str,
    container_description: str = "resultMap",
) -> tuple[str, str, str]:
    """공통 SUCC/FAIL 봉투를 ``(strResult, msgCd, msgTxt)`` 로 읽습니다.

    취소·카드결제·환불이 쓰는 공통 로직. :func:`normalize_result_row` 로 두 담는
    방식을 모두 받습니다. ``msgCd``/``msgTxt`` 는 없어도 됩니다. **성패 판정은
    호출자 몫입니다.**
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            f"SRT {context} response must be a non-empty JSON object",
            raw=data,
        )
    _validate_error_code_wrapper(data, context=context)
    row = normalize_result_row(data)
    if not row:
        raise SrtProtocolError(
            f"SRT {context} response must contain a {container_description} "
            "result row",
            raw=data,
        )
    status = row.get("strResult")
    if not isinstance(status, str) or not status:
        raise SrtProtocolError(
            f"SRT {context} strResult must be a non-empty string",
            raw=data,
        )
    code = row.get("msgCd", "")
    message = row.get("msgTxt", "")
    if not isinstance(code, str) or not isinstance(message, str):
        raise SrtProtocolError(
            f"SRT {context} msgCd and msgTxt must be strings",
            raw=data,
        )
    return status, code, message


def parse_unpaid_cancel_response(data: dict[str, Any]) -> SrtCancelResult:
    """미결제 예약취소(``/ard/selectListArd02045_n.do``) 응답을 읽습니다.

    표준 ``resultMap`` 봉투이고 ``strResult == "SUCC"`` 가 성공입니다. 확인된
    응답은 단일 여정 미결제 예약 하나뿐입니다(``SUCC`` / ``IRG000000`` /
    ``정상처리되었습니다``). 하나의 응답은 스키마가 아니므로 컨테이너 배치를
    못박지 않고 공통 봉투 처리(:func:`_parse_result_envelope`)를 그대로 씁니다.

    **업무 실패는 던지지 않고 돌려줍니다.**
    :attr:`~srt_mobile_api.models.SrtCancelResult.succeeded` 가 ``False`` 이고
    서버의 ``msgCd``/``msgTxt`` 가 그대로 남습니다. "내 예약이 풀렸나" 라는 질문의
    답을 예외 경로로 밀어 넣으면 취소하지 못한 예약이 방치됩니다.

    예외가 되는 것은 어긋난 봉투(:class:`~srt_mobile_api.errors.SrtProtocolError`)
    와 ``ERROR_CODE`` 거절(:class:`~srt_mobile_api.errors.SrtAppError`) 뿐입니다.
    """
    status, code, message = _parse_result_envelope(data, context="cancel")
    return SrtCancelResult(
        status=status,
        message_code=code,
        message=message,
        raw=data,
    )


def parse_coupon_registration_response(
    data: dict[str, Any],
) -> SrtCouponRegistrationResult:
    """할인쿠폰 등록(``/arb/selectListArb02A01_n.do``) 응답을 읽습니다.

    **이 응답은 한 번도 본 적이 없습니다.** 근거는 쿠폰 페이지 자신의 성공 처리
    코드뿐입니다::

        var msg   = args.resultMap[0].MSG;
        var rtncd = args.resultMap[0].RTNCD;
        if(rtncd == "N"){ srtAlertBoxDivShow("알림", msg, null); }
        else            { srtAlertBoxDivShow("알림", Sr.msgs.mysrt008, ...); }

    그래서 **공통 봉투 처리를 쓰지 않습니다.** 취소·결제·환불이 공유하는
    :func:`_parse_result_envelope` 는 ``strResult``/``msgCd``/``msgTxt`` 를 읽는데,
    이 경로는 대문자 ``RTNCD``/``MSG`` 로 답하고 ``strResult`` 가 아예 없습니다.

    **``RTNCD`` 는 비어 있으면 안 됩니다** —— 페이지보다 엄격한 유일한 지점입니다.
    페이지는 ``"N"`` 만 실패로 보므로 코드가 없으면 성공으로 읽히는데, "내 쿠폰이
    쓰였나" 는 틀리면 안 되는 방향입니다. 말하지 않는 응답은
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.

    선언된 실패는 던지지 않고 돌려줍니다. ``RTNCD="N"`` 과 서버의 ``MSG`` 는
    비밀번호가 틀렸는지 이미 쓴 쿠폰인지를 말해 주는 답입니다.
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT coupon registration response must be a non-empty JSON object",
            raw=data,
        )
    _validate_error_code_wrapper(data, context="coupon registration")
    row = _first_row(data.get("resultMap"))
    if not row:
        raise SrtProtocolError(
            "SRT coupon registration response must contain a resultMap result row",
            raw=data,
        )
    status = row.get("RTNCD")
    if not isinstance(status, str) or not status:
        raise SrtProtocolError(
            "SRT coupon registration RTNCD must be a non-empty string",
            raw=data,
        )
    message = row.get("MSG")
    return SrtCouponRegistrationResult(
        status=status,
        message=message if isinstance(message, str) else "",
        raw=data,
    )


def parse_card_payment_response(data: dict[str, Any]) -> SrtPaymentResult:
    """카드결제 응답을 읽습니다. **결제만 봉투가 다릅니다.**

    이 라이브러리가 다루는 다른 상태 변경은 모두 ``resultMap`` 에 답하는데, 결제는
    ``outDataSets.dsOutput0[0]`` 에 답하고 거기서 ``strResult`` 와 ``msgTxt`` 를
    읽습니다. :func:`normalize_result_row` 가 두 방식을 모두 받으므로 결제가
    ``resultMap`` 으로 답하더라도 읽힙니다.

    확인된 응답은 성공 ``SUCC``/``IRT000000``(실제 청구 1건)과 실패
    ``FAIL``/``WRT100170``(가짜 카드·없는 PNR) 두 갈래입니다.

    **알 수 없는 상태값을 성공으로 넘겨짚지 않습니다.**
    :class:`~srt_mobile_api.models.SrtPaymentResult` 의 ``succeeded`` 와 ``failed``
    는 서로의 부정이 아니라 둘 다 ``False`` 일 수 있습니다.

    **업무 실패는 던지지 않고 돌려줍니다.** "내 카드가 청구됐나" 는 예외 처리 없이
    읽을 수 있어야 합니다. 예외가 되는 것은 어긋난 봉투
    (:class:`~srt_mobile_api.errors.SrtProtocolError`)와 ``ERROR_CODE`` 거절
    (:class:`~srt_mobile_api.errors.SrtAppError`) 뿐입니다. ``msgCd`` 는 없어도
    됩니다.
    """
    status, code, message = _parse_result_envelope(
        data,
        context="card payment",
        container_description="outDataSets.dsOutput0 (or resultMap)",
    )
    return SrtPaymentResult(
        status=status,
        message_code=code,
        message=message,
        raw=data,
    )


def parse_refund_ticket_info_response(
    data: dict[str, Any],
) -> SrtRefundTicketInfo:
    """환불 1단계 — 발권된 승차권의 신원을 읽습니다.

    ``/atc/getListAtc14087.do``. 알맹이는 ``outDataSets.dsOutput1[0]`` (다른
    읽기의 ``dsOutput0`` 이 아님). 성공 조건은 ``ErrorCode == "0"`` && ``ErrorMsg
    == ""``. **이 파서의 예외만 ``raw`` 가 가려져 있습니다** — 응답에
    ``ogtkRetPwd`` 와 구매자명이 실려 오기 때문입니다.
    """
    # Redacted raw: ogtkRetPwd (refund credential) + buyer name in the response.
    # Structure survives redaction so shape issues are still diagnosable.
    safe_raw = redact_mapping(data) if isinstance(data, dict) else data
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT refund ticket info response must be a non-empty JSON object",
            raw=safe_raw,
        )
    code = data.get("ErrorCode")
    message = data.get("ErrorMsg")
    if not isinstance(code, str) or not isinstance(message, str):
        raise SrtProtocolError(
            "SRT refund ticket info ErrorCode and ErrorMsg must be strings",
            raw=safe_raw,
        )
    if code != "0" or message != "":
        raise SrtAppError(
            code,
            message or "SRT refund ticket info request failed",
            raw=safe_raw,
        )
    datasets = data.get("outDataSets")
    if not isinstance(datasets, dict):
        raise SrtProtocolError(
            "SRT refund ticket info response missing outDataSets",
            raw=safe_raw,
        )
    row = _first_row(datasets.get("dsOutput1"))
    if not row:
        # LIVE 2026-07-26: the wrapper can succeed (`ErrorCode "0"`,
        # `ErrorMsg ""`) while the lookup itself failed, and the server then
        # puts a business row in `dsOutput0` instead of the payload in
        # `dsOutput1`. Probing an unissued PNR returned
        # `{"msgCd": "WRT300005", "strResult": "FAIL",
        #   "msgTxt": "조회자료가 없습니다."}` there.
        #
        # That is "no such ticket", not a malformed response, so it must not
        # surface as a protocol error: a caller checking whether a PNR is
        # refundable would be unable to tell a missing ticket from a broken
        # server. Classify it from the server's own code and let the taxonomy
        # decide, exactly as every other read does.
        failure = _first_row(datasets.get("dsOutput0"))
        if failure:
            code = failure.get("msgCd") or ""
            message = failure.get("msgTxt") or ""
            raise classify_app_error(
                str(code),
                str(message),
                raw=safe_raw,
            )
        raise SrtProtocolError(
            "SRT refund ticket info response missing dsOutput1 payload",
            raw=safe_raw,
        )

    def _text(name: str) -> str:
        value = row.get(name, "")
        if value is None:
            return ""
        if not isinstance(value, str):
            raise SrtProtocolError(
                f"SRT refund ticket info {name} must be a string",
                raw=safe_raw,
            )
        return value

    pnr_no = _text("pnrNo")
    if not pnr_no.strip():
        raise SrtProtocolError(
            "SRT refund ticket info response carried no PNR",
            raw=safe_raw,
        )
    return SrtRefundTicketInfo(
        pnr_no=pnr_no,
        sale_date=_text("ogtkSaleDt"),
        sale_window_number=_text("ogtkSaleWctNo"),
        sale_sequence_number=_text("ogtkSaleSqno"),
        return_password=_text("ogtkRetPwd"),
        buyer_name=_text("buyPsNm"),
        raw=data,
    )


def parse_refund_response(data: dict[str, Any]) -> SrtRefundResult:
    """환불 2단계 —— 평범한 ``resultMap`` SUCC/FAIL 봉투를 읽습니다.

    ``/atc/selectListAtc02063_n.do`` 의 응답입니다. 봉투는 취소와 같습니다. 바로 앞
    단계인 카드결제가 ``outDataSets.dsOutput0`` 에 답하는 것과 대비됩니다 ——
    두 파서 모두 :func:`_parse_result_envelope` 를 지나 어느 쪽 봉투든 받습니다.

    확인된 성공 응답은 ``SUCC``/``IRT200277`` 입니다.

    **업무 실패는 던지지 않고 돌려줍니다.** "내 승차권이 환불됐나" 는 예외 처리
    없이 읽을 수 있어야 합니다. 어긋난 봉투와 ``ERROR_CODE`` 거절만 예외입니다.
    """
    status, code, message = _parse_result_envelope(data, context="refund")
    return SrtRefundResult(
        status=status,
        message_code=code,
        message=message,
        raw=data,
    )


def _reservation_list_container(
    data: dict[str, Any],
    name: str,
) -> list[dict[str, Any]]:
    """나란히 오는 두 행 컨테이너 중 하나를 객체 목록으로 다듬습니다.

    ``null`` 도 "비었음" 으로 받습니다. 이 응답 자신이 한 본문 안에서 없음을 두
    가지로 쓰기 때문입니다 —— ``"rsListMap": null`` 옆에 ``"trainListMap": []``.
    그 밖에 리스트가 아닌 값이나 객체가 아닌 행은
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    """
    value = data.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise SrtProtocolError(
            f"SRT reservation list {name} must be a list",
            raw=data,
        )
    rows: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            raise SrtProtocolError(
                f"SRT reservation list {name} contained a non-object row",
                raw=data,
            )
        rows.append(row)
    return rows


#: Fixed-width identifier columns that need zero-padding when arriving as JSON
#: numbers (e.g. 06:30 departure arrives as 63000, must be "063000" for the
#: 6-digit card_payment_payload check). Membership: width is fixed by protocol
#: AND downstream requires exact width. trnNo fails (variable width), seatNum/
#: rcvdAmt fail (no width requirement downstream).
_ZERO_PADDED_RESERVATION_COLUMNS = {
    "dptTm": 6,
    "arvTm": 6,
    "iseLmtTm": 6,
    "dptRsStnCd": 4,
    "arvRsStnCd": 4,
}


def _reservation_list_optional_string(
    row: dict[str, Any],
    key: str,
) -> str | None:
    """행의 필드를 문자열로 읽습니다. 없으면 ``None``.

    숫자도 문자열로 바꿉니다 — JSON 숫자로 오는 필드(``rcvdAmt``, ``jrnyCnt``)가
    있기 때문입니다. :data:`_ZERO_PADDED_RESERVATION_COLUMNS` 에 있는 열은 앞의
    0 을 복원합니다 (06:30 → ``63000`` → ``"063000"``). ``bool`` 과 컨테이너는
    버립니다.
    """
    value = row.get(key)
    if isinstance(value, str):
        return value
    width = _ZERO_PADDED_RESERVATION_COLUMNS.get(key)
    # bool is an int subclass; a flag is not an identifier or an amount.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value).zfill(width) if width else str(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
        return text.zfill(width) if width else text
    return None


def _reservation_list_count(
    row: dict[str, Any],
    key: str,
    *,
    raw: Any,
) -> int | None:
    """``rowCnt``·``totPageCnt`` 처럼 JSON 정수로 오는 개수를 읽습니다.

    숫자로 된 문자열도 받습니다 —— 이웃한 읽기들이 두 표기를 섞어 쓰고, 개수
    하나 때문에 목록 전체를 실패시킬 이유가 없습니다. 키가 없거나 ``null`` 이면
    ``None`` 입니다.

    ``bool`` 은 거절합니다. 파이썬에서 ``True`` 는 ``int`` 라 그냥 두면 1 이 됩니다.
    """
    if key not in row or row[key] is None:
        return None
    value = row[key]
    if type(value) is int:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise SrtProtocolError(
        f"SRT reservation list {key} must be an integer",
        raw=raw,
    )


def parse_reservation_list_response(
    data: dict[str, Any],
) -> SrtReservationListResult:
    """예약/발권 목록(``/atc/selectListAtc14016_n.do``) 응답을 읽습니다.

    "없음" 은 FAIL 이 아니라 빈 배열입니다 — 서버는 ``SUCC`` + ``IRZ000005`` +
    빈 ``trainListMap`` 으로 답합니다. ``rsMap`` 의 ``WRT300005`` 는 무시하고
    ``resultMap`` 만 읽습니다.

    행은 ``trainListMap`` 과 ``payListMap`` 을 인덱스로 짝지어 만듭니다.
    ``pnrNo`` 없는 행은 버리되, 행이 있는데 하나도 읽히지 않으면
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT reservation list response must be a non-empty JSON object",
            raw=data,
        )
    _validate_error_code_wrapper(data, context="reservation list")
    result_row = _first_row(data.get("resultMap"))
    if not result_row:
        raise SrtProtocolError(
            "SRT reservation list response must contain a resultMap result row",
            raw=data,
        )
    status = result_row.get("strResult")
    if not isinstance(status, str) or not status:
        raise SrtProtocolError(
            "SRT reservation list resultMap strResult must be a non-empty string",
            raw=data,
        )
    code = result_row.get("msgCd", "")
    message = result_row.get("msgTxt", "")
    if not isinstance(code, str) or not isinstance(message, str):
        raise SrtProtocolError(
            "SRT reservation list resultMap msgCd and msgTxt must be strings",
            raw=data,
        )
    if status == "FAIL":
        # == "FAIL" only, same polarity as the rest of this file
        # (ara1001l.js:206, :234, :1562). rsMap's FAIL is ignored above.
        raise classify_app_error(code or None, message or status, raw=data)

    train_rows = _reservation_list_container(data, "trainListMap")
    pay_rows = _reservation_list_container(data, "payListMap")
    reservations: list[SrtReservationSummary] = []
    for index, train_row in enumerate(train_rows):
        pay_row = pay_rows[index] if index < len(pay_rows) else {}
        pnr = _reservation_list_optional_string(
            train_row, "pnrNo"
        ) or _reservation_list_optional_string(pay_row, "pnrNo")
        if pnr is None or not pnr.strip():
            continue
        reservations.append(
            SrtReservationSummary(
                pnr_no=pnr.strip(),
                received_amount=_reservation_list_optional_string(
                    train_row, "rcvdAmt"
                ),
                ticket_special_number=_reservation_list_optional_string(
                    train_row, "tkSpecNum"
                ),
                seat_number=_reservation_list_optional_string(
                    train_row, "seatNum"
                ),
                service_class_code=_reservation_list_optional_string(
                    pay_row, "stlbTrnClsfCd"
                ),
                train_no=_reservation_list_optional_string(pay_row, "trnNo"),
                departure_date=_reservation_list_optional_string(pay_row, "dptDt"),
                departure_time=_reservation_list_optional_string(pay_row, "dptTm"),
                departure_station_code=_reservation_list_optional_string(
                    pay_row, "dptRsStnCd"
                ),
                arrival_time=_reservation_list_optional_string(pay_row, "arvTm"),
                arrival_station_code=_reservation_list_optional_string(
                    pay_row, "arvRsStnCd"
                ),
                payment_limit_date=_reservation_list_optional_string(
                    pay_row, "iseLmtDt"
                ),
                payment_limit_time=_reservation_list_optional_string(
                    pay_row, "iseLmtTm"
                ),
                settlement_flag=_reservation_list_optional_string(
                    pay_row, "stlFlg"
                ),
                raw_train=train_row,
                raw_pay=pay_row,
            )
        )
    if train_rows and not reservations:
        raise SrtProtocolError(
            "SRT reservation list carried rows but no pnrNo could be read from "
            "any of them; the full response is attached so the PNR is not lost",
            raw=data,
        )
    return SrtReservationListResult(
        reservations=tuple(reservations),
        status=status,
        message_code=code,
        message=message,
        row_count=_reservation_list_count(result_row, "rowCnt", raw=data),
        total_page_count=_reservation_list_count(
            result_row, "totPageCnt", raw=data
        ),
        raw=data,
    )


SEARCH_WRAPPER_PAIRS = (
    ("ErrorCode", "ErrorMsg"),
    ("ERROR_CODE", "ERROR_MSG"),
)


def _normalize_search_wrapper(data: dict[str, Any]) -> tuple[str, str]:
    complete_pairs: list[tuple[str, str]] = []
    for code_key, message_key in SEARCH_WRAPPER_PAIRS:
        code_present = code_key in data
        message_present = message_key in data
        if code_present != message_present:
            raise SrtProtocolError(
                f"SRT search response {code_key}/{message_key} wrapper pair is partial",
                raw=data,
            )
        if code_present:
            complete_pairs.append((code_key, message_key))
    if len(complete_pairs) != 1:
        raise SrtProtocolError(
            "SRT search response must contain exactly one observed wrapper pair",
            raw=data,
        )
    code_key, message_key = complete_pairs[0]
    code = data[code_key]
    message = data[message_key]
    if not isinstance(code, str):
        raise SrtProtocolError(
            f"SRT search response {code_key} must be a string",
            raw=data,
        )
    if not isinstance(message, str):
        raise SrtProtocolError(
            f"SRT search response {message_key} must be a string",
            raw=data,
        )
    return code, message


#: Search-row fixed-width columns — same criterion as reservation list.
#: Downstream requirements (all in payloads.py, exact-length checks):
#:   dptTm/arvTm → length=6, dptDt/arvDt/runDt → length=8,
#:   dptRsStnCd/arvRsStnCd → length=4, seatAttCd → length=3.
#: Absent: trnNo (variable width, payloads.py already zfill(5)s it).
_ZERO_PADDED_SEARCH_ROW_COLUMNS = {
    "dptTm": 6,
    "arvTm": 6,
    "dptDt": 8,
    "arvDt": 8,
    "runDt": 8,
    "dptRsStnCd": 4,
    "arvRsStnCd": 4,
    "seatAttCd": 3,
    "stlbTrnClsfCd": 2,
}


def _row_scalar(value: Any, key: str) -> str | None:
    """검색 행의 값 하나. 문자열이면 그대로, 등록된 고정폭 키의 숫자면 0-패딩,
    그 밖은 ``None``. ``bool`` 제외.
    """
    if value is None or isinstance(value, str):
        return value
    width = _ZERO_PADDED_SEARCH_ROW_COLUMNS.get(key)
    if width is not None and type(value) is int:
        return str(value).zfill(width)
    return None


def _required_row_string(
    row: dict[str, Any],
    key: str,
    *,
    context: str,
) -> str:
    value = _row_scalar(row.get(key), key)
    if not isinstance(value, str):
        raise SrtProtocolError(f"SRT {context} {key} must be a string")
    return value


def _row_field_is_absent(row: dict[str, Any], key: str) -> bool:
    """선택 필드가 없는지. JSON ``null`` 도 없는 것으로 셉니다.

    서버가 실제로 ``null`` 을 보냅니다 (``fresRsvPsbCdNm``, ``fllwPgExt2``). ``null``
    을 없음으로 보지 않으면 선택 필드의 타입 검사가 검색 전체를 무너뜨립니다.
    ``null`` 이 아닌 이상한 타입은 여전히 예외입니다.
    """
    return key not in row or row[key] is None


def _optional_row_string(
    row: dict[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        if _row_field_is_absent(row, key):
            continue
        value = _row_scalar(row[key], key)
        if not isinstance(value, str):
            raise SrtProtocolError(
                f"SRT search train row {key} must be a string"
            )
        return value
    return None


def _optional_row_nonnegative_int(
    row: dict[str, Any],
    *keys: str,
) -> int | None:
    for key in keys:
        if _row_field_is_absent(row, key):
            continue
        value = row[key]
        return _nonnegative_int(value, context=f"search train row {key}")
    return None


def _optional_row_string_tuple(
    row: dict[str, Any],
    *keys: str,
) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        if _row_field_is_absent(row, key):
            continue
        value = row[key]
        if not isinstance(value, str):
            raise SrtProtocolError(
                f"SRT search train row {key} must be a string"
            )
        values.append(value)
    return tuple(values)


def _nonnegative_int(value: Any, *, context: str) -> int:
    if type(value) is int and value >= 0:
        return value
    if (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
    ):
        try:
            return int(value)
        except ValueError as exc:
            raise SrtProtocolError(
                f"SRT {context} exceeds the supported integer size"
            ) from exc
    raise SrtProtocolError(
        f"SRT {context} must be a non-negative integer or ASCII integer string"
    )


def _station_name(
    row: dict[str, Any],
    *,
    row_key: str,
    context: Mapping[str, str] | None,
    context_code_key: str,
    context_key: str,
    station_code: str | None,
) -> str | None:
    row_name = _optional_row_string(row, row_key)
    if row_name is not None and row_name.strip():
        return row_name.strip()
    if context is None:
        return None
    normalized_station_code = (
        station_code.strip() if isinstance(station_code, str) else ""
    )
    context_code = context.get(context_code_key)
    if (
        not normalized_station_code
        or not isinstance(context_code, str)
        or context_code.strip() != normalized_station_code
    ):
        return None
    context_name = context.get(context_key)
    if not isinstance(context_name, str) or not context_name.strip():
        return None
    normalized = context_name.strip()
    if normalized == normalized_station_code:
        return None
    return normalized


def _optional_message(result: dict[str, Any]) -> str:
    """``msgTxt`` 를 문자열로 읽습니다. ``null`` 은 없는 것과 같이 ``""`` 입니다.

    :func:`_row_field_is_absent` 와 같은 이유입니다. 이 메타 컨테이너에는 실제로
    ``null`` 이 실려 옵니다. 사람이 읽는 메시지 하나 때문에 예외를 내면 열차 한
    페이지가 통째로 버려집니다. 문자열도 ``null`` 도 아닌 값은 여전히 예외입니다.
    """
    message = result.get("msgTxt")
    if message is None:
        return ""
    if not isinstance(message, str):
        raise SrtProtocolError("SRT search metadata msgTxt must be a string")
    return message


def _parse_search_metadata(result: dict[str, Any]) -> TrainSearchMetadata:
    code = _required_row_string(result, "msgCd", context="search metadata")
    status = _required_row_string(result, "strResult", context="search metadata")
    message = _optional_message(result)
    raw_query_count = result.get("qryCnqeCnt")
    query_count = _nonnegative_int(
        raw_query_count,
        context="search metadata qryCnqeCnt",
    )
    raw_following = result.get("fllwPgExt")
    if raw_following is None:
        has_following_page = None
    elif isinstance(raw_following, str) and raw_following in {"Y", "N"}:
        has_following_page = raw_following == "Y"
    else:
        raise SrtProtocolError(
            "SRT search metadata fllwPgExt must be exactly Y or N"
        )
    return TrainSearchMetadata(
        message_code=code,
        status=status,
        query_count=query_count,
        has_following_page=has_following_page,
        message=message,
        raw=result,
    )


def parse_train_search_response(
    data: dict[str, Any],
    request_context: Mapping[str, str] | None = None,
) -> TrainSearchResult:
    """열차 검색 응답을 :class:`~srt_mobile_api.models.TrainSearchResult` 로 만듭니다.

    메타데이터는 ``outDataSets.dsOutput0``, 열차 행은 ``dsOutput1``. 개인·단체·
    환승이 모두 이 모양입니다. 결과 없음은 빈 목록이 아니라 ``strResult=FAIL`` +
    ``WRG000000`` → :class:`~srt_mobile_api.errors.SrtNoResultsError`.
    ``NET000001`` → :class:`~srt_mobile_api.errors.SrtNetFunnelKeyError`.

    성패는 ``strResult`` 로만 가릅니다(ara1001l.js:206). ``request_context`` 는
    응답 행에 역 이름이 없을 때 코드 일치 시 채워 넣는 용도입니다.
    """
    if not isinstance(data, dict):
        raise SrtProtocolError(
            "SRT search response must be a JSON object",
            raw=data,
        )
    wrapper_code, wrapper_message = _normalize_search_wrapper(data)
    if wrapper_code not in {"", "0"}:
        raise SrtAppError(wrapper_code, wrapper_message, raw=data)
    out = data.get("outDataSets")
    if not isinstance(out, dict):
        raise SrtProtocolError("SRT search response missing outDataSets")
    result = _first_row(out.get("dsOutput0"))
    if not result:
        raise SrtProtocolError("SRT search response missing dsOutput0 result metadata")
    code = _required_row_string(result, "msgCd", context="search metadata")
    status = _required_row_string(result, "strResult", context="search metadata")
    message = _optional_message(result)
    if code == "NET000001":
        raise SrtNetFunnelKeyError(code, message or "NetFunnel key required", raw=data)
    # == "FAIL" only (ara1001l.js:206); empty window lands here as WRG000000.
    if status == "FAIL":
        raise classify_app_error(code or None, message or status or None, raw=data)
    metadata = _parse_search_metadata(result)
    rows = out.get("dsOutput1")
    if not isinstance(rows, list):
        raise SrtProtocolError("SRT search response missing dsOutput1 list")
    return TrainSearchResult(
        trains=_parse_search_train_rows(rows, request_context),
        result=result,
        raw=data,
        metadata=metadata,
    )


def _parse_search_train_rows(
    rows: list[Any],
    request_context: Mapping[str, str] | None = None,
) -> list[TrainSummary]:
    """검색 행 목록을 :class:`~srt_mobile_api.models.TrainSummary` 로 바꿉니다.

    일반 검색(``dsOutput1``)과 할인 검색(``trainListMap``)이 같은 열을 쓰므로 한
    함수로 처리합니다. ``trnNo`` 필수, 나머지는 ``None`` 허용.
    """
    trains: list[TrainSummary] = []
    for row in rows:
        if not isinstance(row, dict):
            raise SrtProtocolError(
                "SRT search response contained a non-object train row"
            )
        train_no = _required_row_string(row, "trnNo", context="search train row")
        if not train_no:
            raise SrtProtocolError(
                "SRT search response contained a train without trnNo"
            )
        departure_station_code = _optional_row_string(row, "dptRsStnCd")
        arrival_station_code = _optional_row_string(row, "arvRsStnCd")
        trains.append(
            TrainSummary(
                train_no=train_no,
                train_group_code=_optional_row_string(row, "trnGpCd"),
                service_class_code=_optional_row_string(row, "stlbTrnClsfCd"),
                train_class_code=_optional_row_string(row, "trnClsfCd"),
                run_date=_optional_row_string(row, "runDt"),
                departure_date=_optional_row_string(row, "dptDt"),
                departure_time=_optional_row_string(row, "dptTm"),
                arrival_date=_optional_row_string(row, "arvDt"),
                arrival_time=_optional_row_string(row, "arvTm"),
                departure_station_code=departure_station_code,
                arrival_station_code=arrival_station_code,
                departure_station_name=_station_name(
                    row,
                    row_key="dptRsStnNm",
                    context=request_context,
                    context_code_key="dptRsStnCd1",
                    context_key="dptRsStnCdNm1",
                    station_code=departure_station_code,
                ),
                arrival_station_name=_station_name(
                    row,
                    row_key="arvRsStnNm",
                    context=request_context,
                    context_code_key="arvRsStnCd1",
                    context_key="arvRsStnCdNm1",
                    station_code=arrival_station_code,
                ),
                departure_run_order=_optional_row_string(row, "dptStnRunOrdr"),
                arrival_run_order=_optional_row_string(row, "arvStnRunOrdr"),
                seat_attr_code=_optional_row_string(row, "seatAttCd"),
                run_time=_optional_row_string(row, "runTm", "trnRunTm"),
                train_run_order=_optional_row_nonnegative_int(
                    row,
                    "trnRunOrdr",
                    "trnOrdrNo",
                ),
                departure_consist_order=_optional_row_string(
                    row,
                    "dptStnConsOrdr",
                ),
                arrival_consist_order=_optional_row_string(
                    row,
                    "arvStnConsOrdr",
                ),
                current_delay=_optional_row_nonnegative_int(
                    row,
                    "ocurDlayTnum",
                    "curDlayTm",
                    "dptDlayTm",
                ),
                expected_delay=_optional_row_string(
                    row,
                    "expnDptDlayTnum",
                    "expDlayTm",
                    "arvDlayTm",
                ),
                general_seat_availability=_optional_row_string(
                    row,
                    "gnrmRsvPsbStr",
                ),
                special_seat_availability=_optional_row_string(
                    row,
                    "sprmRsvPsbStr",
                ),
                reservation_wait_availability=_optional_row_string(
                    row,
                    "rsvWaitPsbCd",
                    "rsvWaitPsbStr",
                ),
                standing_availability=_optional_row_string(
                    row,
                    "stmpRsvPsbFlgCd",
                    "stndFlg",
                ),
                general_seat_availability_name=_optional_row_string(
                    row,
                    "gnrmRsvPsbCdNm",
                ),
                special_seat_availability_name=_optional_row_string(
                    row,
                    "sprmRsvPsbCdNm",
                ),
                reservation_wait_availability_name=_optional_row_string(
                    row,
                    "rsvWaitPsbCdNm",
                ),
                standing_availability_name=_optional_row_string(
                    row,
                    "stndRsvPsbCdNm",
                ),
                received_amount=_optional_row_string(row, "rcvdAmt"),
                discount_rate=_optional_row_string(row, "trainDiscGenRt"),
                received_fare=_optional_row_string(row, "rcvdFare"),
                train_composition_codes=_optional_row_string_tuple(
                    row,
                    "trnCpsCd1",
                    "trnCpsCd2",
                    "trnCpsCd3",
                    "trnCpsCd4",
                    "trnCpsCd5",
                ),
                # 할인 승차권 검색 전용 (0-hit in bundle, absent from ordinary rows).
                general_class_discount_rate=_optional_row_string(
                    row,
                    "gnrmBkclDcntRt",
                ),
                special_class_discount_rate=_optional_row_string(
                    row,
                    "sprmBkclDcntRt",
                ),
                raw=row,
            )
        )
    return trains


def parse_public_discount_search_response(
    data: dict[str, Any],
    request_context: Mapping[str, str] | None = None,
) -> TrainSearchResult:
    """할인 승차권 검색(``/ara/selectListAra10131_n.do``) 응답을 읽습니다.

    **이 응답은 한 번도 본 적이 없습니다.** 이 검색을 보내려면 승인된 공공할인
    자격이 필요합니다. 아래 내용은 전부 서버가 렌더링해 주는 조회결과 페이지의 처리
    코드에서 읽은 것입니다::

        var resultMap = data.resultMap[0];
        if(resultMap.strResult == "FAIL"){ ...stop paging... }
        else{
            var trainListMap = data.trainListMap;
            if (trainListMap[0].fllwPgExt != 'Y') { ...last page... }
            $("#gdNo").val(data.dsCmdMap.gdNo);
        }

    **담는 그릇은 일반 검색과 다르고 행은 같습니다.** 일반 검색은 ``ErrorCode``
    봉투 안의 ``outDataSets.dsOutput0``/``dsOutput1`` 로 답하는데 이쪽은
    ``resultMap`` 과 ``trainListMap`` 입니다. 행의 열 이름은 같아서
    :func:`_parse_search_train_rows` 를 그대로 씁니다.

    **열 두 개가 새로 붙습니다.** ``gnrmBkclDcntRt``·``sprmBkclDcntRt`` —— 일반실과
    특실의 공공할인율(정수 퍼센트)이고 이 검색의 목적입니다. 페이지는 1 미만을 "이
    열차에는 할인 없음" 으로 다룹니다. 결과에서는
    :attr:`~srt_mobile_api.models.TrainSummary.general_class_discount_rate` 과
    ``special_class_discount_rate`` 로 나옵니다.

    **페이지 넘김은 시각이 아니라 커서입니다.** 다음 요청에 실을 값은
    ``dsCmdMap.gdNo`` 이고, 다음 페이지 유무는 ``trainListMap[0].fllwPgExt`` ——
    메타 행이 아니라 **첫 행**에 실립니다. 둘 다
    :class:`~srt_mobile_api.models.TrainSearchMetadata` 로 옮기지 않았고 원문은
    :attr:`~srt_mobile_api.models.TrainSearchResult.raw` 에 있습니다. 이 함수의
    반환은 ``metadata`` 가 ``None`` 입니다.

    ``strResult == "FAIL"`` 은 일반 검색과 같이 올라가고 빈 결과는
    :class:`~srt_mobile_api.errors.SrtNoResultsError` 입니다. 자격 없는 계정에
    서버가 무엇을 답하는지는 알 수 없어 거절과 빈 결과가 구분되지 않습니다.
    ``msgCd`` 는 없어도 됩니다 —— 페이지도 읽지 않습니다.
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT public discount search response must be a non-empty JSON object",
            raw=data,
        )
    # Kept even though the page never checks it: every other JSON route on this
    # server may carry the wrapper, and validating it costs nothing when absent.
    _validate_error_code_wrapper(data, context="public discount search")
    result = _first_row(data.get("resultMap"))
    if not result:
        raise SrtProtocolError(
            "SRT public discount search response missing resultMap result row",
            raw=data,
        )
    status = _required_row_string(
        result, "strResult", context="public discount search metadata"
    )
    # msgCd is OPTIONAL here, unlike the ordinary search which requires it. The
    # page reads strResult and nothing else on this route, and refusing a
    # response over a field its own client never looks at would turn a real
    # search outcome into a parse error.
    code = _optional_row_string(result, "msgCd") or ""
    message = _optional_message(result)
    if code == "NET000001":
        raise SrtNetFunnelKeyError(code, message or "NetFunnel key required", raw=data)
    if status == "FAIL":
        raise classify_app_error(code or None, message or status or None, raw=data)
    rows = data.get("trainListMap")
    if not isinstance(rows, list):
        raise SrtProtocolError(
            "SRT public discount search response missing trainListMap list",
            raw=data,
        )
    return TrainSearchResult(
        trains=_parse_search_train_rows(rows, request_context),
        result=result,
        raw=data,
        metadata=None,
    )


def parse_search_has_following_page(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        raise SrtProtocolError("SRT paginated search response must be a JSON object")
    out = data.get("outDataSets")
    if not isinstance(out, dict):
        raise SrtProtocolError("SRT paginated search response missing outDataSets")
    metadata = out.get("dsOutput0")
    if isinstance(metadata, list):
        if not metadata or not isinstance(metadata[0], dict):
            raise SrtProtocolError(
                "SRT paginated search response missing dsOutput0 object"
            )
        result = metadata[0]
    elif isinstance(metadata, dict):
        result = metadata
    else:
        raise SrtProtocolError(
            "SRT paginated search response missing dsOutput0 object"
        )
    flag = result.get("fllwPgExt")
    if not isinstance(flag, str) or flag not in {"Y", "N"}:
        raise SrtProtocolError(
            "SRT paginated search response fllwPgExt must be exactly Y or N"
        )
    return flag == "Y"


# The 환승 search row column that identifies WHICH itinerary a leg belongs to.
# Live-confirmed 2026-07-26 on 동대구(0015) -> 광주송정(0036): 10 rows came back,
# every one with chtnDvCd="2", and the legs of one itinerary shared a trnOrdrNo
# (1 -> trains 382 + 411, 2 -> trains 14 + 475, 3 -> trains 316 + 655).
#
# The same column is 열차순서번호 on a DIRECT row, where it is just a position in
# the list, so the name does not change -- only what it groups.
TRANSFER_ITINERARY_COLUMN = "trnOrdrNo"

# Exactly how many rows one 환승 itinerary is made of. Not a tunable: jrnyCnt="2"
# is the only journey count 환승 has (ara0101v.js:302-303), the reservation form
# carries exactly two 여정 slots, and the app's own refusal to book a partial one
# is phrased for two ("선행 및 후행", messages.js:217).
TRANSFER_LEGS_PER_ITINERARY = 2


def _itinerary_key(train: TrainSummary) -> str:
    """이 구간이 속한 여정 번호. 알 수 없으면 ``""`` 입니다.

    ``trnOrdrNo`` 를 **원본 행에서 먼저** 읽고, 없을 때만 타입이 붙은
    :attr:`~srt_mobile_api.models.TrainSummary.train_run_order` 를 봅니다. 순서가
    중요합니다 —— 그 속성은 ``trnRunOrdr`` 를 ``trnOrdrNo`` 보다 먼저 받으므로,
    둘 다 실린 행을 그쪽부터 보면 엉뚱한 기준으로 묶입니다.
    """
    raw = train.raw
    if isinstance(raw, dict):
        value = raw.get(TRANSFER_ITINERARY_COLUMN)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    if train.train_run_order is not None:
        return str(train.train_run_order)
    return ""


def _order_transfer_legs(
    rows: tuple[TrainSummary, ...],
) -> tuple[TransferItinerary | None, str]:
    """두 구간의 선행/후행을 역 연결로 가립니다. ``(여정, "")`` 또는 ``(None, 이유)``.

    두 방향을 모두 :class:`~srt_mobile_api.models.TransferItinerary` 에 넣어 보고
    성립하는 방향이 정확히 하나여야 합니다. 0 이면 여정이 아니고, 2 면 모호합니다.
    """
    first, second = rows
    candidates: list[TransferItinerary] = []
    failures: list[str] = []
    for leading, following in ((first, second), (second, first)):
        try:
            candidates.append(
                TransferItinerary(first_leg=leading, second_leg=following)
            )
        except ValueError as exc:
            failures.append(str(exc))
    if len(candidates) == 1:
        return candidates[0], ""
    if not candidates:
        return None, "; ".join(dict.fromkeys(failures))
    return (
        None,
        "both leg orders read as a valid itinerary, so which one is 선행 is "
        "ambiguous",
    )


def pair_transfer_itineraries(result: TrainSearchResult) -> TransferSearchResult:
    """환승 검색의 낱개 행을 ``trnOrdrNo`` 기준으로 두 구간짜리 여정으로 묶습니다.

    서버는 한 구간짜리 행을 평평하게 보내므로 묶는 일은 이쪽이 합니다. 원본은
    :attr:`~srt_mobile_api.models.TransferSearchResult.search` 에 그대로 남습니다.

    규칙: ``trnOrdrNo`` 가 같은 행이 한 여정이고, 정확히
    :data:`TRANSFER_LEGS_PER_ITINERARY` 행이어야 합니다. 맞지 않는 묶음은
    ``unpaired`` 에 이유와 함께 남깁니다. 행이 왔는데 하나도 묶이지 않으면
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다.
    """
    groups: dict[str, list[TrainSummary]] = {}
    for row in result.trains:
        groups.setdefault(_itinerary_key(row), []).append(row)

    itineraries: list[TransferItinerary] = []
    unpaired: list[UnpairedTransferGroup] = []
    for key, rows in groups.items():
        frozen = tuple(rows)
        if not key:
            unpaired.append(
                UnpairedTransferGroup(
                    itinerary_no="",
                    rows=frozen,
                    reason=(
                        f"row carries no {TRANSFER_ITINERARY_COLUMN}, so which "
                        "itinerary it belongs to is unknown"
                    ),
                )
            )
            continue
        if len(frozen) != TRANSFER_LEGS_PER_ITINERARY:
            unpaired.append(
                UnpairedTransferGroup(
                    itinerary_no=key,
                    rows=frozen,
                    reason=(
                        f"{TRANSFER_ITINERARY_COLUMN}={key} returned "
                        f"{len(frozen)} rows; a 환승 itinerary is exactly "
                        f"{TRANSFER_LEGS_PER_ITINERARY}"
                    ),
                )
            )
            continue
        itinerary, reason = _order_transfer_legs(frozen)
        if itinerary is None:
            unpaired.append(
                UnpairedTransferGroup(
                    itinerary_no=key, rows=frozen, reason=reason
                )
            )
            continue
        itineraries.append(itinerary)

    if result.trains and not itineraries:
        raise SrtProtocolError(
            "SRT transfer search returned rows but none of them paired into an "
            f"itinerary by {TRANSFER_ITINERARY_COLUMN}: "
            + "; ".join(group.reason for group in unpaired),
            raw=result.raw,
        )
    return TransferSearchResult(
        itineraries=tuple(itineraries),
        unpaired=tuple(unpaired),
        search=result,
    )
