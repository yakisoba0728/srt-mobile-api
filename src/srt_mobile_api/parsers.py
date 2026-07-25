from __future__ import annotations

import re
from collections.abc import Mapping
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from .config import APP_ORIGIN
from .errors import SrtAppError, SrtNetFunnelError, SrtProtocolError, SrtSessionExpiredError
from .models import (
    FareItem,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    Notice,
    NoticeListResult,
    ReservationAttemptResult,
    ReservationRecord,
    ReservationTrain,
    SearchPageState,
    SeatCarOption,
    SeatSelectionPage,
    SrtCancelResult,
    SrtReservationHold,
    SrtReservationListResult,
    SrtReservationSummary,
    TimetablePage,
    TimetableRow,
    TrainSearchMetadata,
    TrainSearchResult,
    TrainSummary,
)
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
    _HIDDEN_TAGS = {"script", "style"}
    _VOID_TAGS = {
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
            self._form_stack.append(_is_login_form_action(values.get("action", ""), base_url=self.base_url))
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
    parser = _LoginFormParser(base_url=base_url)
    parser.feed(html)
    return parser.found


# The message key the server puts in the "you are not signed in" alert. Captured
# live on 2026-07-26: an authenticated read issued with no session cookie
# (/atc/selectListAtc14017_n.do) answered HTTP 200 with the ORDINARY page shell
# -- header, footer, every menu form -- and an inline script that pops the alert
# and leaves:
#
#     //console.log("로그인페이지로 이동");
#     srtAlertBoxDivShow("알림", Sr.msgs.login020, null, "mvLoginPage()");
#     ...
#     function mvLoginPage() { location.href = "/login/login.do?page=menu"; }
#
# There is no <form action=".../apb/selectListApb01080_n.do">, no hmpgPwdCphd
# input, no redirect and no error status -- so is_login_form() above, which is
# specifically a REAL login FORM detector, correctly says False, and every
# expiry guard keyed on it silently passed the page through as content.
LOGIN_REDIRECT_MESSAGE_KEY = "Sr.msgs.login020"
# mvLoginPage() is DEFINED on ordinary authenticated pages too (the ticket list
# carries the definition whether or not it is called), so the discriminator is
# the message key, not the function name. Across the 2026-07-26 capture the key
# appears in exactly two places: the login page itself, and this expired
# response. It is 0-hit in every authenticated read -- main, booking page, all
# six selectors, the search hydration page, the seat page, the timetable, the
# fare page and the AUTHENTICATED ticket list.
_LOGIN_REDIRECT_CALL = "srtAlertBoxDivShow"


class _LoginRedirectParser(HTMLParser):
    """Detect the server's "sign in again" answer to an authenticated read.

    Looks for the alert INSIDE a ``<script>`` element rather than anywhere in
    the byte stream, so the same token appearing in visible copy — or in an
    attribute — cannot be mistaken for the server's instruction to re-login.
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
    """Whether the server answered an authenticated read with "sign in again"."""
    parser = _LoginRedirectParser()
    parser.feed(html)
    return parser.found


def is_unauthenticated_page(html: str, *, base_url: str = APP_ORIGIN) -> bool:
    """Whether ``html`` is the server refusing an authenticated read.

    The union of the two shapes the real server actually uses: the login FORM
    (:func:`is_login_form`) and the login-REDIRECT page
    (:func:`is_login_redirect_page`). Every expiry guard goes through here so
    both are caught in one place; keying a guard on ``is_login_form`` alone is
    what let an expired session read as an empty ticket list.
    """
    return is_login_form(html, base_url=base_url) or is_login_redirect_page(html)


def extract_text(html: str, *, limit: int | None = None) -> str:
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
    """The 호차 options, plus any page-level error alert the server attached.

    Both come from the same pass because they are the two halves of one
    question: did this page bring a seat map, or did it bring a refusal?
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
    """Parse the 좌석선택 page, refusing the server's error shell.

    **Live-captured 2026-07-26, on two trains that differ only in availability.**

    For a train with seats free, POST /arc/selectListArc02012_n.do returns the
    real page: a ``<select id="selectScarNo">`` listing each 호차 with the seats
    it has left (``<option value='7'> 7호차 (2석) </option>``), and a hidden
    ``trnScarSeatFrm`` carrying the identity for the follow-up seat-grid read.

    For a SOLD-OUT train the server returns a shell instead: the same ``<h1>``
    heading, no car select, no options, no form, and one script at the very end::

        <script>
        srtAlertBoxDivShow("알림", Sr.msgs.error001, null, "historyBack();");
        </script>

    The old check was for the visible marker "좌석선택" alone. That marker is the
    page HEADING, so it is present on both — the error shell passed, and a caller
    got a ``SeatSelectionPage`` for a page whose only content was "error, go
    back". The capture logged it as a successful read of 38506 bytes.

    So a declared failure now raises :class:`SrtAppError`, matching how every
    other parser here treats a server-declared failure, and the car list is
    returned as data instead of being left in ``raw`` for the caller to scrape.
    The seat GRID is deliberately not parsed: it is not in this response. The
    real page leaves ``<div id="trnScarSeatInfo">`` empty and loads the grid
    separately once a car is picked.
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
        raise SrtAppError(
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


def parse_notice_list_response(data: dict[str, Any]) -> NoticeListResult:
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
    """``_TableParser`` plus the station code each row's inline script carries.

    The station name is not in the markup at all; the code that produces it is,
    in a ``<script>`` INSIDE the ``<tr>``. So the code has to be collected with
    row affinity — a document-order list of codes matched positionally against
    rows would drift the moment the server emits a row without one.
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
    """Parse the 열차 시간표 page, resolving each stop's name from its code.

    **This app is a WebView shell, and the timetable is where that shows.** The
    station name is NOT in the HTML. Captured live on 2026-07-26, a stop row is::

        <tr class="ac">
            <td id="stationNm_1">
            <td style="border-left: 2px solid #999;">
                <img id="stationNow_1" class="hidden" ...>
            </td>
            <script>$("#stationNm_1").html( getStationNameByCode('0551') );</script>
            <td>-</td>
            <td>10:00</td>
        </tr>

    The name cell is empty (and unclosed); the WebView fills it in from the
    CODE, using the same static lookup table we already ship as
    :mod:`srt_mobile_api.stations`.

    Reading "the first non-time cell" as the station name therefore never found
    one. On the real 수서→부산 timetable it produced ``'-'`` for the origin and
    the terminus — the arrival/departure placeholder dash, mistaken for a name —
    and ``''`` for all five intermediate stops. Seven rows, zero station names,
    two of them actively wrong. Both captured routes behaved identically.

    So the code is read from the row's own script and resolved through
    ``station_name_by_code``, exactly as the app does, and kept on
    :class:`~srt_mobile_api.models.TimetableRow.station_code` as well — it is
    real data the response carries that was previously dropped entirely. The old
    cell heuristic remains as the fallback for a row with no such script, minus
    the placeholder dashes it used to mistake for names.
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
    """Parse the 운임·요금 page for the ONE journey leg we asked about.

    **Live-captured 2026-07-26, and the reason this reads one table and not
    all of them.** The real page is built for a TRANSFER itinerary: it renders
    ``<div id="trainPayInfo1">`` for the first leg and
    ``<div id="trainPayInfo22">`` for a second, each with its own fare table.
    Our request can only ever describe one leg -- :func:`fare_payload` hard-codes
    ``runDt2=""``/``trnNo2=""``/``dptRsStnCd2=""``/``arvRsStnCd2=""`` -- so the
    second block comes back as an unpopulated placeholder: its title shows ``..``
    for the date and ``[]`` for the station course, and the page hides it on load
    with ``$("#trainPayInfo22").hide();``.

    Its six rows are not empty, though. They repeat the same labels with
    placeholder amounts::

        어른 특실 -        어른 일반실 0원
        어린이 특실 -      어린이 일반실 0원
        경로 특실 -        경로 일반실 0원

    Reading every table therefore produced twelve items, of which three were
    ``0원`` fares carrying labels IDENTICAL to real ones. A caller building
    ``{item.label: item.amount}`` got ``어른 일반실 → 0`` instead of ``51900``:
    a silently wrong answer about money, reproduced on two unrelated routes
    (수서→부산 and 수서→천안아산) in the same capture.

    So only the first fare-bearing table is read. The page's own ``hide()``
    calls are deliberately NOT used as the signal: the same script also contains
    ``$("#trainPayInfo1").hide();`` inside ``selectTransferTrain()``, so
    collecting hide() calls textually would suppress the REAL table too.
    "The first table with data rows" needs no JavaScript reasoning and matches
    what we requested.
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


def normalize_result_row(data: dict[str, Any]) -> dict[str, Any]:
    out = data.get("outDataSets") or {}
    if isinstance(out, dict) and "dsOutput0" in out:
        return _first_row(out.get("dsOutput0"))
    return _first_row(data.get("resultMap"))


def parse_mutual_verification_response(
    data: dict[str, Any],
) -> MutualVerificationResult:
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
    # The app never reads msgCd for Ara10130 -- fn_searchMutMrkVrfCd only checks
    # dsOutput0.strResult == "FAIL" then reads dsOutput0.mutMrkVrfCd (ara1001l.js:234-241).
    # Treat msgCd as informational/optional; gate solely on strResult (+ a present
    # mutMrkVrfCd). Keeping it optional is still right, and the live response is
    # why the reasoning behind it is restated rather than the old one repeated.
    #
    # CORRECTION, live capture 2026-07-26. The old comment added that "the
    # documented dsOutput0 schema is {strResult, msgTxt, mutMrkVrfCd} with no
    # msgCd". The real row has SEVEN keys and msgCd is one of them:
    #
    #   {"msgCd":"IRZ000008", "wctNo":"<counter>", "strResult":"SUCC",
    #    "msgTxt":"정상적으로 처리 되었습니다.", "mutMrkVrfCd":"<30 chars>",
    #    "uuid":"APP...", "cgPsId":"korail"}
    #
    # So optional-and-usually-present, not optional-because-absent. wctNo, uuid
    # and cgPsId are not modelled and stay reachable through
    # MutualVerificationResult.raw.
    #
    # The same capture also showed this route answering SUCC with a fresh
    # mutMrkVrfCd when called with NO session cookie at all: Ara10130 is public,
    # unlike every other read behind SrtClient's session guard.
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
        raise SrtAppError(
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
    """Parse an already-obtained reservation-attempt response without issuing a request."""
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
    # POLARITY: only an explicit "FAIL" is a failure, exactly as the app.
    # ara1001l.js:1562 is `if (resultMap.strResult == "FAIL")` -- it alerts and
    # returns there, and ANY other value falls straight through to :1577/:1609,
    # which read reservListMap[0].pnrNo and proceed with a created reservation.
    # So a third status value means "the hold exists"; treating it as failure
    # would raise SrtAppError for a reservation that IS on the server. Worse, it
    # would also make _declares_a_declared_failure below refuse the PNR salvage,
    # producing precisely the orphaned hold this subsystem exists to prevent.
    # This is the same fix already applied to the search parser for the same
    # reason (parse_train_search_response, `if status == "FAIL"`), and the app
    # is consistent about it: ara1001l.js:206, :234 and :1855 are all == "FAIL".
    #
    # The DECLARED outcome is classified before any strict optional-field read.
    # A server that says FAIL is authoritative about the outcome whether or not
    # msgCd/msgTxt happen to be well formed, and callers distinguish "the
    # reservation was rejected" from "the response was malformed" purely by
    # exception type. Reading the optional fields strictly first meant a FAIL
    # that was ALSO slightly malformed (no msgCd, an int msgCd, no msgTxt) came
    # out as SrtProtocolError, which sent it into
    # parse_reservation_hold_response's salvage branch and manufactured a hold
    # for a reservation that was never created.
    declared_code = result_row.get("msgCd")
    declared_message = result_row.get("msgTxt")
    code_hint = declared_code if isinstance(declared_code, str) else ""
    message_hint = declared_message if isinstance(declared_message, str) else ""
    declared_failure = status == "FAIL"
    if declared_failure and code_hint == "S111":
        # Bundled JS treats FAIL + msgCd "S111" as a session-expiry / re-login
        # signal (ara1001l.js:1562-1571; cross-validation-2026-07-21.md §2),
        # not a generic business error.
        raise SrtSessionExpiredError(
            message_hint or "SRT reservation attempt session expired",
            raw=data,
        )
    # WRP011002 (passenger-count error) stays an independent failure signal
    # rather than being folded into the status test: it was observed live
    # alongside strResult=FAIL (srt-app-api-library-spec-2026-07-09.md §runtime
    # probes), so it never contradicts the polarity above, and keeping it means
    # a server that reports the rejection only in msgCd is still not read as a
    # hold.
    if code_hint == "WRP011002" or declared_failure:
        raise SrtAppError(code_hint, message_hint or status, raw=data)

    # Only a DECLARED SUCCESS reaches the strict reads: there the fields are
    # load-bearing, a malformed one means we cannot trust the parse, and the
    # hold parser's salvage path is the designed answer.
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
    """Salvage the cancelable identity from a response strict parsing rejected.

    Returns ``None`` when no usable ``reservListMap[0].pnrNo`` is present, i.e.
    when there is no hold to lose. Every other field is taken only if it is
    already a string, so one malformed optional value cannot cost us the PNR.
    The PNR is stripped, matching what the cancel builder puts on the wire, so a
    caller reading ``hold.pnr_no`` — to log it, or to hand it back later as a
    bare PNR string — gets the identity itself and not padding around it.
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
    """True when the payload itself declares ``strResult == "FAIL"``.

    Read straight off the raw payload, deliberately duplicating the check
    :func:`parse_reservation_attempt_response` already performs. It is the
    second layer of the guarantee that a declared failure is never salvaged
    into a hold: if that parser's ordering ever regresses so a malformed FAIL
    surfaces as :class:`SrtProtocolError` again, this still refuses to
    manufacture a hold for a reservation the server says does not exist.

    The test is ``== "FAIL"``, not ``!= "SUCC"``, and the distinction is
    load-bearing here rather than cosmetic. The app fails a reservation only on
    an explicit FAIL (``ara1001l.js:1562``) and otherwise reads
    ``reservListMap[0].pnrNo`` as a created reservation (:1577/:1609), so a
    third status value means a hold probably EXISTS — the one case where
    suppressing the salvage is most damaging. Absent status likewise means "not
    declared", which is a malformed response rather than a declared failure —
    that too is precisely what the salvage path exists for.
    """
    if not isinstance(data, dict):
        return False
    row = normalize_result_row(data)
    return row.get("strResult") == "FAIL"


def parse_reservation_hold_response(data: dict[str, Any]) -> SrtReservationHold:
    """Parse a reserve response into a minimal cancelable hold.

    Reuses :func:`parse_reservation_attempt_response` for the full success
    gating (resultMap strResult/msgCd, S111 session-expiry, app-error wrappers)
    and validated container shapes, then keeps only the identity srtgo keeps
    from a live reserve (``reservListMap[0].pnrNo``, srt.py:1006).

    A live reserve may already have created a real hold on the server by the
    time we parse, so this must NEVER discard the identity needed to cancel it.
    Strict parsing raises :class:`SrtProtocolError` on any malformed field,
    including one we do not need (a missing ``trainListMap`` seat number, say),
    which would orphan an existing hold. When that happens and the response
    still carries a PNR, fall back to a minimal hold built from
    ``reservListMap[0]`` so the caller can still cancel; with no PNR there is no
    hold to lose, so the original error is re-raised. A business FAIL
    (:class:`SrtAppError`) and a session expiry
    (:class:`SrtSessionExpiredError`) are NOT salvaged: those mean the
    reservation was rejected, not that a hold exists behind a parse failure.
    Telling a caller a reservation exists when it does not is as damaging as
    losing one that does — they stop trying to recover — so that exclusion is
    enforced twice: by the declared-status classification inside
    :func:`parse_reservation_attempt_response`, and again by
    :func:`_declares_a_declared_failure` on the raw payload here.
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


def parse_unpaid_cancel_response(data: dict[str, Any]) -> SrtCancelResult:
    """Parse the response of an unpaid-reservation cancel (예약취소).

    **Provenance — live-verified once, on 2026-07-25.** That
    ``/ard/selectListArd02045_n.do`` answers with the standard ``resultMap``
    envelope, successful on ``strResult == "SUCC"``, originally came solely from
    srtgo's live runs (``docs/analysis/ref-srtgo_plus.md`` §7.1); the route is
    0-hit across all 21,673 files of our v2.0.41 offline decompile
    (``docs/analysis/cross-validation-2026-07-21.md``). One operator-run round
    trip has since seen a real response: ``SUCC`` / ``IRG000000`` /
    ``정상처리되었습니다`` for a single-journey unpaid hold. That is ONE observed
    envelope, not a schema, so this parser keeps reusing the shared envelope
    handling (:func:`normalize_result_row`, which accepts both the ``resultMap``
    and ``outDataSets.dsOutput0`` spellings, plus the ``ERROR_CODE``/
    ``ERROR_MSG`` wrapper check) instead of hard-asserting the container layout
    that one response happened to use.

    A business failure is RETURNED, not raised: ``SrtCancelResult.succeeded`` is
    ``False`` and the server's ``msgCd``/``msgTxt`` are preserved. Raising there
    would push the "did my hold get released?" answer into an exception path,
    which is how holds get orphaned. Only a malformed envelope
    (:class:`SrtProtocolError`) or an app-level ``ERROR_CODE`` rejection
    (:class:`SrtAppError`) raises. ``msgCd`` is optional, matching the app's own
    habit of gating purely on ``strResult`` (see
    :func:`parse_mutual_verification_response`) and srtgo, which never reads a
    cancel ``msgCd``; refusing a response over a field nobody reads would hide a
    real cancellation outcome.
    """
    if not isinstance(data, dict) or not data:
        raise SrtProtocolError(
            "SRT cancel response must be a non-empty JSON object",
            raw=data,
        )
    _validate_error_code_wrapper(data, context="cancel")
    row = normalize_result_row(data)
    if not row:
        raise SrtProtocolError(
            "SRT cancel response must contain a resultMap result row",
            raw=data,
        )
    status = row.get("strResult")
    if not isinstance(status, str) or not status:
        raise SrtProtocolError(
            "SRT cancel resultMap strResult must be a non-empty string",
            raw=data,
        )
    code = row.get("msgCd", "")
    message = row.get("msgTxt", "")
    if not isinstance(code, str) or not isinstance(message, str):
        raise SrtProtocolError(
            "SRT cancel resultMap msgCd and msgTxt must be strings",
            raw=data,
        )
    return SrtCancelResult(
        status=status,
        message_code=code,
        message=message,
        raw=data,
    )


def _reservation_list_container(
    data: dict[str, Any],
    name: str,
) -> list[dict[str, Any]]:
    """One of the two parallel row containers, normalised to a list of objects.

    ``null`` is accepted as "empty" because this very response uses it: the
    2026-07-26 probe carried ``"rsListMap": null`` alongside
    ``"trainListMap": []``, i.e. the server spells absence both ways within a
    single body. Anything else present but not a list is a genuine surprise and
    raises.
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


def _reservation_list_optional_string(
    row: dict[str, Any],
    key: str,
) -> str | None:
    """A row field, or ``None`` when absent — never an exception.

    Deliberately more forgiving than :func:`_optional_row_string`, which raises
    on a present non-string. The non-empty row shape here has never been
    observed by this repository (see
    :class:`~srt_mobile_api.models.SrtReservationSummary`), so a field arriving
    as a number instead of a string is a live-shape unknown rather than a
    protocol violation — and raising over one cosmetic field would cost the
    caller the PNRs of every reservation in the list, which is the one outcome
    this read exists to prevent. An unexpected type is dropped from the typed
    field and stays readable through ``raw_train`` / ``raw_pay``.
    """
    value = row.get(key)
    return value if isinstance(value, str) else None


def _reservation_list_count(
    row: dict[str, Any],
    key: str,
    *,
    raw: Any,
) -> int | None:
    """``rowCnt`` / ``totPageCnt``, which arrive as JSON integers.

    Both were integers (``0``) in the observed empty response. A digit string is
    also accepted, because the neighbouring SRT reads mix the two spellings
    freely and a count is not worth failing a list over. ``bool`` is rejected
    outright: ``True`` is an ``int`` in Python and would silently become 1.
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
    """Parse the 예약/발권 목록 response of ``/atc/selectListAtc14016_n.do``.

    **Live-verified for the EMPTY case only, on 2026-07-26.** A POST of
    ``pageNo=0`` on an account with no reservations answered, in full::

        {"payListMap": [],
         "rsListMap": null,
         "rsMap": [{"msgCd": "WRT300005", "strResult": "FAIL",
                    "msgTxt": "조회자료가 없습니다."}],
         "resultMap": [{"msgCd": "IRZ000005", "wctNo": "...", "strResult": "SUCC",
                        "msgTxt": "조회할 자료가 없습니다.", "uuid": "...",
                        "cgPsId": "korail", "totPageCnt": 0, "rowCnt": 0}],
         "commandMap": {"pageNo": "0"},
         "trainListMap": []}

    Three things in that response drive this parser.

    1. **Empty here is an empty ARRAY, not a FAIL.** The train search answers an
       empty result with ``strResult=FAIL`` / ``WRG000000``; this endpoint does
       not. It reports ``SUCC`` and sends ``[]``. So an empty list must come
       back as an empty list — raising :class:`SrtAppError` for "you have no
       reservations" would make the recovery path useless exactly when someone
       is checking whether a hold survived.

    2. **``rsMap`` says FAIL on that same successful response.** It is a second,
       narrower envelope (``WRT300005`` "조회자료가 없습니다."), and it is
       present precisely BECAUSE the list is empty. Gating on "any FAIL
       anywhere" — or on ``rsMap`` — would classify the verified empty response
       as an error. This parser reads ``resultMap`` and only ``resultMap``,
       which is also what srtgo does (``SRTResponseData`` prefers ``resultMap``
       when present). ``rsMap`` stays available through ``raw``.

    3. **``rsListMap`` is ``null`` while ``trainListMap`` is ``[]``**, so
       ``null`` and ``[]`` both mean empty in this response — see
       :func:`_reservation_list_container`.

    The NON-EMPTY shape remains UNVERIFIED by this repository. The two-parallel-
    container layout (``trainListMap[i]`` zipped with ``payListMap[i]``) and
    every row field name come from srtgo's live runs; the containers exist in
    the verified response, the row fields do not. Rows are therefore built as
    permissively as is compatible with never inventing a reservation: a row is
    kept when it has a non-empty ``pnrNo`` (checked in ``trainListMap[i]`` first,
    then in the paired ``payListMap[i]``, so a swapped layout still yields the
    identity), and if NO row in a non-empty container carries one,
    :class:`SrtProtocolError` is raised with the whole response attached rather
    than a silently empty list being returned — "you have no reservations" is
    too dangerous a thing to say by accident.

    The two containers are zipped by index up to the shorter one, but iterated
    over ``trainListMap`` in full, so an asymmetric response still surfaces
    every PNR it carries instead of truncating the tail away.
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
        # Gated on == "FAIL" rather than != "SUCC", matching the app's own habit
        # everywhere else in this file: an unrecognised third status is not a
        # declared failure, and treating it as one would hide a list that exists.
        raise SrtAppError(code or None, message or status, raw=data)

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


def _required_row_string(
    row: dict[str, Any],
    key: str,
    *,
    context: str,
) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise SrtProtocolError(f"SRT {context} {key} must be a string")
    return value


def _row_field_is_absent(row: dict[str, Any], key: str) -> bool:
    """Whether an OPTIONAL row field is missing, counting JSON null as missing.

    **The server really does send nulls here, and it is not an anomaly.** Every
    one of the 30 personal ``dsOutput1`` rows in the 2026-07-26 live capture
    carried ``"fresRsvPsbCdNm": null``, and ``dsOutput0`` carried
    ``"fllwPgExt2": null`` in every successful search. So ``null`` is this API's
    ordinary spelling of "this row has no such value" — the app agrees, since it
    reads ``item.X`` straight into the DOM and cannot tell null from absent.

    It matters because the optional readers below raised
    :class:`SrtProtocolError` for any present non-string, and that exception is
    not scoped to the field: it aborts the ENTIRE search. We happen not to read
    ``fresRsvPsbCdNm``, so the bomb has not gone off — but the fields we DO read
    optionally live in the same rows, filled by the same server, and the day one
    of them (say ``rsvWaitPsbCd`` on a train with no waitlist) comes back null,
    every search on the route stops returning trains at all rather than one
    train losing one attribute.

    A present non-string that is NOT null still raises. A number or an object
    where a string belongs is a genuine protocol surprise; null is documented
    behaviour we have observed.
    """
    return key not in row or row[key] is None


def _optional_row_string(
    row: dict[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        if _row_field_is_absent(row, key):
            continue
        value = row[key]
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
    """``msgTxt`` as a string, treating JSON null as the empty default.

    Same reasoning as :func:`_row_field_is_absent`, applied to the metadata
    container that demonstrably carries nulls (``fllwPgExt2`` is null in every
    successful search of the 2026-07-26 capture). ``msgTxt`` already defaults to
    ``""`` when absent, so a null -- the server's other spelling of absent --
    yielding anything but that default would be inconsistent, and raising over a
    human-readable message would discard a whole page of trains.
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
        raise SrtNetFunnelError(code, message or "NetFunnel key required", raw=data)
    # The app classifies a search purely on dsOutput0.strResult (== "FAIL" fails, anything
    # else succeeds) and never inspects msgCd (ara1001l.js:206); srtgo agrees (srt.py:391-401).
    # msgCd is kept as informational metadata (and drives the NET000001 NetFunnel-retry signal
    # above) but is NOT required to equal "IRG000000".
    if status == "FAIL":
        raise SrtAppError(code or None, message or status or None, raw=data)
    metadata = _parse_search_metadata(result)
    rows = out.get("dsOutput1")
    if not isinstance(rows, list):
        raise SrtProtocolError("SRT search response missing dsOutput1 list")
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
                raw=row,
            )
        )
    return TrainSearchResult(
        trains=trains,
        result=result,
        raw=data,
        metadata=metadata,
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
