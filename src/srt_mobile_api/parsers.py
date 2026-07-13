from __future__ import annotations

import re
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
    SearchPageState,
    TimetablePage,
    TimetableRow,
    TrainSearchResult,
    TrainSummary,
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)


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
    if require_authenticated and is_login_form(html):
        raise SrtSessionExpiredError(f"SRT {context} returned the login form", raw=html)
    return HtmlPage(text=extract_text(html), raw=html)


def parse_notice_list_response(data: dict[str, Any]) -> dict[str, Any]:
    error_code = str(data.get("ErrorCode") or "")
    if error_code not in {"", "0"}:
        raise SrtAppError(error_code, str(data.get("ErrorMsg") or ""), raw=data)
    notices = data.get("noticeList")
    if not isinstance(notices, list):
        raise SrtProtocolError("SRT notice response missing noticeList")
    return data


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
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []

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
            self._row = None


TIME_RE = re.compile(r"\b\d{2}:\d{2}\b")
FARE_RE = re.compile(r"(\d{1,3}(?:,\d{3})*)\s*원")


def parse_timetable_page(html: str) -> TimetablePage:
    page = parse_html_page(html, context="timetable")
    table = _TableParser()
    table.feed(html)
    rows: list[TimetableRow] = []
    for cells in table.rows:
        raw_text = " ".join(cells)
        times = tuple(TIME_RE.findall(raw_text))
        if times:
            station = next((cell for cell in cells if not TIME_RE.fullmatch(cell)), "")
            rows.append(TimetableRow(station_name=station, times=times, raw_text=raw_text))
    if not rows:
        times = tuple(TIME_RE.findall(page.text))
        if not times:
            raise SrtProtocolError("SRT timetable page did not contain timetable rows or times")
        rows.append(TimetableRow(station_name="", times=times, raw_text=page.text))
    return TimetablePage(text=page.text, raw=page.raw, rows=tuple(rows))


def parse_fare_page(html: str) -> FarePage:
    page = parse_html_page(html, context="fare")
    table = _TableParser()
    table.feed(html)
    items: list[FareItem] = []
    for cells in table.rows:
        raw_text = " ".join(cells)
        match = FARE_RE.search(raw_text)
        if match:
            raw_amount = match.group(0)
            label = raw_text.replace(raw_amount, "").strip()
            items.append(
                FareItem(
                    label=label,
                    amount=int(match.group(1).replace(",", "")),
                    raw_amount=raw_amount,
                )
            )
    if not items:
        raise SrtProtocolError("SRT fare page did not contain a fare amount")
    return FarePage(text=page.text, raw=page.raw, items=tuple(items))


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
    if not isinstance(code, str) or not isinstance(status, str):
        raise SrtProtocolError(
            "SRT mutual verification code and status must be strings"
        )
    if not isinstance(message, str):
        raise SrtProtocolError(
            "SRT mutual verification message must be a string"
        )
    if code != "IRZ000008" or status != "SUCC":
        raise SrtAppError(
            code or None,
            "SRT mutual verification failed",
            raw=data,
        )
    if not isinstance(verification_code, str) or not verification_code.strip():
        raise SrtProtocolError(
            "SRT mutual verification mutMrkVrfCd must be a non-empty string"
        )
    return MutualVerificationResult(
        message_code=code,
        status=status,
        message=message,
        verification_code=verification_code,
        raw=data,
    )


def parse_train_search_response(data: dict[str, Any]) -> TrainSearchResult:
    wrapper_code_value = data.get("ErrorCode", "")
    if not isinstance(wrapper_code_value, str):
        raise SrtProtocolError("SRT search response ErrorCode must be a string")
    wrapper_message_value = data.get("ErrorMsg", "")
    if not isinstance(wrapper_message_value, str):
        raise SrtProtocolError("SRT search response ErrorMsg must be a string")
    wrapper_code = wrapper_code_value
    if wrapper_code not in {"", "0"}:
        raise SrtAppError(wrapper_code, wrapper_message_value, raw=data)
    out = data.get("outDataSets")
    if not isinstance(out, dict):
        raise SrtProtocolError("SRT search response missing outDataSets")
    result = _first_row(out.get("dsOutput0"))
    if not result:
        raise SrtProtocolError("SRT search response missing dsOutput0 result metadata")
    code = str(result.get("msgCd") or "")
    status = str(result.get("strResult") or "")
    message = str(result.get("msgTxt") or "")
    if code == "NET000001":
        raise SrtNetFunnelError(code, message or "NetFunnel key required", raw=data)
    if code != "IRG000000" or status != "SUCC":
        raise SrtAppError(code or None, message or status or None, raw=data)
    rows = out.get("dsOutput1")
    if not isinstance(rows, list):
        raise SrtProtocolError("SRT search response missing dsOutput1 list")
    trains = [
        TrainSummary(
            train_no=str(row.get("trnNo") or ""),
            train_group_code=row.get("trnGpCd"),
            service_class_code=row.get("stlbTrnClsfCd"),
            run_date=row.get("runDt"),
            departure_date=row.get("dptDt"),
            departure_time=row.get("dptTm"),
            arrival_date=row.get("arvDt"),
            arrival_time=row.get("arvTm"),
            departure_station_code=row.get("dptRsStnCd"),
            arrival_station_code=row.get("arvRsStnCd"),
            departure_station_name=row.get("dptRsStnNm"),
            arrival_station_name=row.get("arvRsStnNm"),
            raw=row,
        )
        for row in rows
        if isinstance(row, dict)
    ]
    if len(trains) != len(rows):
        raise SrtProtocolError("SRT search response contained a non-object train row")
    if any(not train.train_no for train in trains):
        raise SrtProtocolError("SRT search response contained a train without trnNo")
    return TrainSearchResult(trains=trains, result=result, raw=data)
