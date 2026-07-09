from __future__ import annotations

import time

import httpx

from .config import SrtConfig
from .http import SrtHttpClient
from .models import HtmlPage, PassengerCounts, SrtSession, TrainSearchQuery, TrainSearchResult, TrainSummary
from .netfunnel import parse_netfunnel_response
from .parsers import extract_text, parse_train_search_response
from .payloads import group_search_ajax_payload, search_ajax_payload, search_page_payload
from .session import SrtSessionClient


class SrtClient:
    def __init__(self, config: SrtConfig | None = None, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config or SrtConfig()
        self.http = SrtHttpClient(self.config, transport=transport)
        self.session = SrtSessionClient(self.http)

    def close(self) -> None:
        self.http.close()

    def login(self, login_id: str, password: str, *, login_type: str = "3") -> SrtSession:
        return self.session.login(login_id, password, login_type=login_type)

    def clear_session(self) -> None:
        self.session.clear_session()

    def logout(self) -> None:
        self.clear_session()

    def get_main(self) -> HtmlPage:
        raw = self.http.get_text("/main/main.do", params={"deviceId": self.config.device_key})
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_booking_page(self) -> HtmlPage:
        raw = self.http.get_text("/ara/ara0101v.do")
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_notice_list(self) -> dict:
        return self.http.post_form(
            "/main/noticeList.do",
            {"pageId": "MB0101000000"},
            accept="application/json, text/javascript, */*; q=0.01",
        )

    def get_ticket_list(self, page_no: int = 0) -> HtmlPage:
        raw = self.http.get_text("/atc/selectListAtc14017_n.do", params={"pageNo": str(page_no)})
        return HtmlPage(text=extract_text(raw), raw=raw)

    def _get_act10_key(self, referer: str) -> str:
        stamp = int(time.time() * 1000)
        url = (
            f"{self.config.netfunnel_url}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
            f"&sid=service_1&aid=act_10&js=true&{stamp}"
        )
        body = self.http.get_text_url(url, referer=referer)
        return parse_netfunnel_response(body, action="act_10").key

    def search_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        key = self._get_act10_key(referer)
        page_params = search_page_payload(
            query,
            query.departure_station_code,
            query.arrival_station_code,
            key,
        )
        self.http.get_text(
            "/ara/selectListAra10007_n.do",
            params=page_params,
            referer=referer,
        )
        data = self.http.post_form(
            "/ara/selectListAra10007_n.do",
            search_ajax_payload(query, key),
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
        )
        return parse_train_search_response(data)

    def search_group_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        referer = f"{self.config.base_url}/ara/selectListAra10007_n.do"
        key = self._get_act10_key(referer)
        data = self.http.post_form(
            "/ara/selectListAra10082_n.do",
            group_search_ajax_payload(query, key),
            accept="application/json, text/javascript, */*; q=0.01",
            referer=referer,
        )
        return parse_train_search_response(data)

    def get_timetable(self, train: TrainSummary) -> HtmlPage:
        raw = self.http.post_form(
            "/ara/selectListAra12009_n.do",
            {
                "stnCourseNm": "",
                "trnSort": "SRT" if train.service_class_code == "17" else train.service_class_code or "",
                "runDt": train.run_date or train.departure_date or "",
                "trnNo": train.train_no.zfill(5),
            },
            accept="text/html, */*; q=0.01",
        )["html"]
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_fare(self, train: TrainSummary, passengers: PassengerCounts | None = None) -> HtmlPage:
        passengers = passengers or PassengerCounts()
        raw = self.http.post_form(
            "/ara/selectListAra13010_n.do",
            {
                "stnCourseNm": "",
                "trnSort": "SRT" if train.service_class_code == "17" else train.service_class_code or "",
                "runDt": train.run_date or train.departure_date or "",
                "trnNo": train.train_no.zfill(5),
                "chtnDvCd": "1",
                "dptRsStnCd1": train.departure_station_code or "",
                "arvRsStnCd1": train.arrival_station_code or "",
                "runDt1": train.run_date or train.departure_date or "",
                "trnNo1": train.train_no.zfill(5),
                "psgTpCd1": "1",
                "psgInfoPerPrnb1": str(passengers.adult),
            },
            accept="text/html, */*; q=0.01",
        )["html"]
        return HtmlPage(text=extract_text(raw), raw=raw)
