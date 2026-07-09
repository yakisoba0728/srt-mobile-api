#!/usr/bin/env python3
"""Smoke-test SRT mobile app API endpoints.

This runner intentionally excludes payment APIs and does not submit a valid
reservation payload. Credentials are read only from environment variables:

  SRT_LOGIN_ID
  SRT_LOGIN_PASSWORD

The output directory contains a machine-readable summary. Raw response bodies
are not saved unless --keep-raw is passed.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


APP_BASE = "https://app.srail.or.kr"
NETFUNNEL_BASE = "https://nf.letskorail.com:443"
DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36 "
    "SRT-APP-Android V.2.0.41"
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self.parts.append(data)

    def text(self, limit: int = 400) -> str:
        value = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
        return value[:limit]


@dataclass
class HttpResult:
    method: str
    url: str
    status: int
    content_type: str
    size: int
    body: bytes

    def text(self) -> str:
        charset = "utf-8"
        match = re.search(r"charset=([^;]+)", self.content_type, re.I)
        if match:
            charset = match.group(1).strip()
        return self.body.decode(charset, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


class SrtSmokeClient:
    def __init__(self, out_dir: Path, keep_raw: bool, user_agent: str, device_key: str, insecure_tls: bool) -> None:
        self.out_dir = out_dir
        self.keep_raw = keep_raw
        self.user_agent = user_agent
        self.device_key = device_key
        self.cookie_jar = http.cookiejar.MozillaCookieJar(str(out_dir / "cookies.txt"))
        self.ssl_context = ssl._create_unverified_context() if insecure_tls else ssl.create_default_context()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.ssl_context),
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
        )
        self.summary: dict[str, Any] = {
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "appBase": APP_BASE,
            "netfunnelBase": NETFUNNEL_BASE,
            "steps": [],
        }

    def request(
        self,
        name: str,
        method: str,
        url: str,
        *,
        data: dict[str, str] | None = None,
        accept: str = "*/*",
        referer: str | None = None,
        raw_name: str | None = None,
    ) -> HttpResult:
        encoded: bytes | None = None
        headers = {
            "User-Agent": self.user_agent,
            "Accept": accept,
        }
        if referer:
            headers["Referer"] = referer
        if data is not None:
            encoded = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
            headers["Origin"] = APP_BASE
            headers["X-Requested-With"] = "XMLHttpRequest"
        request = urllib.request.Request(url, data=encoded, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=20) as response:
                body = response.read()
                result = HttpResult(
                    method=method,
                    url=url,
                    status=response.status,
                    content_type=response.headers.get("Content-Type", ""),
                    size=len(body),
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read()
            result = HttpResult(
                method=method,
                url=url,
                status=exc.code,
                content_type=exc.headers.get("Content-Type", ""),
                size=len(body),
                body=body,
            )
        if self.keep_raw and raw_name:
            (self.out_dir / raw_name).write_bytes(result.body)
        self.summary["steps"].append(
            {
                "name": name,
                "method": method,
                "url": url.split("?", 1)[0],
                "status": result.status,
                "contentType": result.content_type,
                "size": result.size,
            }
        )
        return result

    def get_json_result(self, result: HttpResult) -> tuple[dict[str, Any], dict[str, Any]]:
        data = result.json()
        out = data.get("outDataSets") or {}
        result_row = (out.get("dsOutput0") or data.get("resultMap") or [{}])[0]
        return data, result_row

    def save(self) -> None:
        if self.keep_raw:
            self.cookie_jar.save(ignore_discard=True, ignore_expires=True)
        (self.out_dir / "summary.json").write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def tomorrow_yyyymmdd() -> str:
    return (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")


def parse_netfunnel_response(body: str) -> dict[str, Any]:
    match = re.search(r"'([^']*(?:5101|5002):[^']*)'", body)
    if not match:
        match = re.search(r'"([^"]*(?:5101|5002):[^"]*)"', body)
    if not match:
        raise RuntimeError("NetFunnel response did not include a result token")
    value = match.group(1)
    parts = value.split(":", 2)
    parsed: dict[str, Any] = {
        "rawType": parts[0] if len(parts) > 0 else "",
        "code": parts[1] if len(parts) > 1 else "",
        "params": {},
    }
    if len(parts) > 2:
        for item in parts[2].split("&"):
            if "=" in item:
                key, val = item.split("=", 1)
                parsed["params"][key] = val
    return parsed


def search_page_payload(test_date: str, depart_cd: str, depart_nm: str, arrive_cd: str, arrive_nm: str, netfunnel_key: str) -> dict[str, str]:
    payload = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": "05",
        "stndFlg": "N",
        "jrnySqno1": "001",
        "jrnySqno2": "",
        "trnGpCd1": "900",
        "trnGpCd2": "",
        "trnGpNm1": "전체",
        "trnGpNm2": "",
        "dptRsStnCd1": depart_cd,
        "dptRsStnCd2": "",
        "dptRsStnCdNm1": depart_nm,
        "dptRsStnCdNm2": "",
        "arvRsStnCd1": arrive_cd,
        "arvRsStnCd2": "",
        "arvRsStnCdNm1": arrive_nm,
        "arvRsStnCdNm2": "",
        "dptDt1": test_date,
        "dptTm1": "060000",
        "dptTm2": "",
        "arvDt1": "",
        "arvTm1": "",
        "dptDtTmNm1": test_date,
        "dptDtTmName1": "06시이후",
        "back_dptDt1": test_date,
        "back_dptTm1": "060000",
        "back_dptDtTmNm1": test_date,
        "back_dptDtTmName1": "06시이후",
        "totPrnb": "1",
        "totPrnbNm": "1명",
        "psgGridcnt": "1",
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": "1",
        "psgTpCd2": "",
        "psgInfoPerPrnb2": "0",
        "psgTpCd3": "",
        "psgInfoPerPrnb3": "0",
        "psgTpCd4": "",
        "psgInfoPerPrnb4": "0",
        "psgTpCd5": "",
        "psgInfoPerPrnb5": "0",
        "infantCnt": "0",
        "psgTpCd6": "",
        "psgInfoPerPrnb6": "0",
        "smkSeatAttCd1": "000",
        "dirSeatAttCd1": "009",
        "locSeatAttCd1": "000",
        "rqSeatAttCd1": "015",
        "etcSeatAttCd1": "000",
        "seatAttNm1": "일반/기본",
        "smkSeatAttCd2": "000",
        "dirSeatAttCd2": "009",
        "locSeatAttCd2": "000",
        "rqSeatAttCd2": "015",
        "etcSeatAttCd2": "000",
        "seatAttNm2": "일반/기본",
        "seatAttCd": "015",
        "dptTm": "000000",
        "trnGpCd": "900",
        "netfunnelKey": netfunnel_key,
        "adjStnScdlOfrFlg": "N",
    }
    for key in [
        "go_baseDsXml",
        "go_seatDsXml",
        "trnNo1",
        "trnNo2",
        "runDt1",
        "runDt2",
        "scarNo1",
        "scarNo2",
        "psrmClCd1",
        "psrmClCd2",
        "dptStnConsOrdr1",
        "dptStnConsOrdr2",
        "arvStnConsOrdr1",
        "arvStnConsOrdr2",
        "dptStnRunOrdr1",
        "dptStnRunOrdr2",
        "arvStnRunOrdr1",
        "arvStnRunOrdr2",
        "choiceSeatCount",
        "pnrNo",
        "jrnySqno",
        "JRNYLIST_KEY",
        "arvDt",
        "arvRsStnCd",
        "arvTm",
        "dlayAcptFlg",
        "dptDt",
        "dptRsStnCd",
        "lumpStlTgtNo",
        "proyStlTgtFlg",
        "stlbTrnClsfCd",
        "totSeatNum",
        "trnNo",
        "rcvdAmt",
        "tmpJobSqno1",
        "tmpJobSqno2",
        "dcntKndCd",
    ]:
        payload.setdefault(key, "")
    for leg in (1, 2):
        for idx in range(1, 10):
            payload[f"seatNo{leg}_{idx}"] = ""
    return payload


def search_ajax_payload(test_date: str, depart_cd: str, arrive_cd: str, netfunnel_key: str, psg_num: str = "1") -> dict[str, str]:
    return {
        "chtnDvCd": "1",
        "dptDt": test_date,
        "dptTm": "060000",
        "dptDt1": test_date,
        "dptTm1": "060000",
        "dptRsStnCd": depart_cd,
        "arvRsStnCd": arrive_cd,
        "stlbTrnClsfCd": "05",
        "trnGpCd": "900",
        "trnNo": "",
        "psgNum": psg_num,
        "seatAttCd": "015",
        "arriveTime": "N",
        "tkDptDt": "",
        "tkDptTm": "",
        "tkTrnNo": "",
        "tkTripChgFlg": "",
        "dlayTnumAplFlg": "Y",
        "netfunnelKey": netfunnel_key,
        "disability": "N",
        "adjStnScdlOfrFlg": "N",
    }


def pick_srt_train(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in rows:
        if str(row.get("trnGpCd")) == "300":
            return row
    return rows[0] if rows else {}


def safe_train(row: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "trnNo",
        "trnGpCd",
        "stlbTrnClsfCd",
        "runDt",
        "dptDt",
        "arvDt",
        "dptTm",
        "arvTm",
        "dptRsStnCd",
        "arvRsStnCd",
        "dptStnConsOrdr",
        "arvStnConsOrdr",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "seatAttCd",
        "gnrmRsvPsbCdNm",
        "gnrmRsvPsbStr",
        "sprmRsvPsbCdNm",
        "sprmRsvPsbStr",
        "gnrmRsvPsbImg",
        "sprmRsvPsbImg",
    ]
    return {key: row.get(key) for key in keys if key in row}


def safe_result_row(row: dict[str, Any]) -> dict[str, Any]:
    allowed = ["msgCd", "strResult", "msgTxt", "qryCnqeCnt", "fllwPgExt", "seandYo"]
    return {key: row.get(key) for key in allowed if key in row}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=os.environ.get("SRT_TEST_DATE") or tomorrow_yyyymmdd(), help="YYYYMMDD departure date")
    parser.add_argument("--depart-code", default="0551")
    parser.add_argument("--depart-name", default="수서")
    parser.add_argument("--arrive-code", default="0020")
    parser.add_argument("--arrive-name", default="부산")
    parser.add_argument("--device-key", default=os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF"))
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--keep-raw", action="store_true")
    parser.add_argument("--insecure-tls", action="store_true", help="Disable TLS certificate verification when the local Python CA store is unavailable")
    args = parser.parse_args()

    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        print("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else Path(tempfile.mkdtemp(prefix="srt_app_api_smoke_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)
    client = SrtSmokeClient(
        out_dir=out_dir,
        keep_raw=args.keep_raw,
        user_agent=DEFAULT_UA,
        device_key=args.device_key,
        insecure_tls=args.insecure_tls,
    )
    client.summary["query"] = {
        "date": args.date,
        "departCode": args.depart_code,
        "departName": args.depart_name,
        "arriveCode": args.arrive_code,
        "arriveName": args.arrive_name,
    }

    client.request("login_page", "GET", f"{APP_BASE}/login/login.do", raw_name="login_page.html")
    login = client.request(
        "login_api",
        "POST",
        f"{APP_BASE}/apb/selectListApb01080_n.do",
        data={
            "srchDvCd": "3",
            "srchDvNm": login_id,
            "check": "",
            "auto": "",
            "login_referer": "",
            "hmpgPwdCphd": password,
            "deviceKey": args.device_key,
            "page": "",
            "customerYn": "",
            "ciUptYn": "",
            "dupInfoVal": "",
        },
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{APP_BASE}/login/login.do",
        raw_name="login_raw.json",
    )
    login_json = login.json()
    user_map = login_json.get("userMap") or {}
    client.summary["login"] = {"RTNCD": user_map.get("RTNCD"), "MSG": user_map.get("MSG")}
    if user_map.get("RTNCD") != "Y":
        client.save()
        print(json.dumps({"outDir": str(out_dir), "login": client.summary["login"]}, ensure_ascii=False))
        return 1

    client.request("main_page", "GET", f"{APP_BASE}/main/main.do?deviceId={urllib.parse.quote(args.device_key)}", raw_name="main.html")
    client.request("booking_page", "GET", f"{APP_BASE}/ara/ara0101v.do", raw_name="ara0101v.html")

    nf_search = client.request(
        "netfunnel_act10",
        "GET",
        f"{NETFUNNEL_BASE}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true&{int(time.time() * 1000)}",
        referer=f"{APP_BASE}/ara/ara0101v.do",
        raw_name="netfunnel_act10.txt",
    )
    nf10 = parse_netfunnel_response(nf_search.text())
    key10 = nf10["params"].get("key", "")
    client.summary["netfunnelAct10"] = {"code": nf10["code"], "keyLength": len(key10)}

    search_page_params = search_page_payload(args.date, args.depart_code, args.depart_name, args.arrive_code, args.arrive_name, key10)
    query = urllib.parse.urlencode(search_page_params)
    page = client.request(
        "train_search_page",
        "GET",
        f"{APP_BASE}/ara/selectListAra10007_n.do?{query}",
        referer=f"{APP_BASE}/ara/ara0101v.do",
        raw_name="train_search_page.html",
    )
    client.summary["searchPage"] = {
        "containsSeatSearchForm": "seatSearchForm" in page.text(),
    }

    search = client.request(
        "train_search_ajax",
        "POST",
        f"{APP_BASE}/ara/selectListAra10007_n.do",
        data=search_ajax_payload(args.date, args.depart_code, args.arrive_code, key10),
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="train_search_ajax.json",
    )
    search_json, search_result = client.get_json_result(search)
    rows = (search_json.get("outDataSets") or {}).get("dsOutput1") or []
    selected = pick_srt_train(rows)
    safe_selected = safe_train(selected)
    client.summary["trainSearch"] = {
        "result": safe_result_row(search_result),
        "rowCount": len(rows),
        "selectedTrain": safe_selected,
    }

    nf_group = client.request(
        "netfunnel_act10_group",
        "GET",
        f"{NETFUNNEL_BASE}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true&{int(time.time() * 1000)}",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="netfunnel_act10_group.txt",
    )
    key10_group = parse_netfunnel_response(nf_group.text())["params"].get("key", "")
    group = client.request(
        "group_train_search_ajax",
        "POST",
        f"{APP_BASE}/ara/selectListAra10082_n.do",
        data=search_ajax_payload(args.date, args.depart_code, args.arrive_code, key10_group, psg_num="10"),
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="group_train_search_ajax.json",
    )
    group_json, group_result = client.get_json_result(group)
    group_rows = (group_json.get("outDataSets") or {}).get("dsOutput1") or []
    client.summary["groupTrainSearch"] = {"result": safe_result_row(group_result), "rowCount": len(group_rows)}

    train_no = str(safe_selected.get("trnNo") or "").zfill(5)
    train_date = str(safe_selected.get("dptDt") or args.date)
    train_sort = "SRT" if str(safe_selected.get("stlbTrnClsfCd")) == "17" else str(safe_selected.get("stlbTrnClsfCd") or "")
    timetable = client.request(
        "timetable",
        "POST",
        f"{APP_BASE}/ara/selectListAra12009_n.do",
        data={"stnCourseNm": f"{args.depart_name}-{args.arrive_name}", "trnSort": train_sort, "runDt": train_date, "trnNo": train_no},
        accept="text/html, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="timetable.html",
    )
    timetable_text_parser = TextExtractor()
    timetable_text_parser.feed(timetable.text())
    client.summary["timetable"] = {
        "textPrefix": timetable_text_parser.text(500),
        "times": re.findall(r"\b\d{2}:\d{2}\b", timetable_text_parser.text(2000))[:20],
    }

    fare = client.request(
        "fare",
        "POST",
        f"{APP_BASE}/ara/selectListAra13010_n.do",
        data={
            "stnCourseNm": f"{args.depart_name}-{args.arrive_name}",
            "trnSort": train_sort,
            "runDt": train_date,
            "trnNo": train_no,
            "chtnDvCd": "1",
            "dptRsStnCd1": args.depart_code,
            "arvRsStnCd1": args.arrive_code,
            "runDt1": train_date,
            "trnNo1": train_no,
            "psgTpCd1": "1",
            "psgInfoPerPrnb1": "1",
            "psgTpCd2": "",
            "psgInfoPerPrnb2": "0",
            "psgTpCd3": "",
            "psgInfoPerPrnb3": "0",
            "psgTpCd4": "",
            "psgInfoPerPrnb4": "0",
            "psgTpCd5": "",
            "psgInfoPerPrnb5": "0",
            "psgTpCd6": "",
            "psgInfoPerPrnb6": "0",
            "dptRsStnCd2": "",
            "arvRsStnCd2": "",
            "runDt2": "",
            "trnNo2": "",
        },
        accept="text/html, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="fare.html",
    )
    fare_text_parser = TextExtractor()
    fare_text_parser.feed(fare.text())
    fare_text = fare_text_parser.text(2000)
    client.summary["fare"] = {
        "textPrefix": fare_text[:500],
        "amounts": re.findall(r"\d{1,3}(?:,\d{3})+\s*원", fare_text)[:10],
    }

    popup_calls = [
        ("popup_station", "/common/ARA/ARA0501P/view.do", {"reqCode": "1", "sDptStnNm": args.depart_name, "sArvStnNm": args.arrive_name, "sDptStnCd": args.depart_code, "sArvStnCd": args.arrive_code, "chk_rtrp": "false", "sNowSel": "1", "page": "ARA0101", "boolRtrp": "false"}),
        ("popup_map", "/common/ARA/ARA0502P/view.do", {"reqCode": "2", "chk_rtrp": "false", "sNowSel": "1", "page": "ARA0101", "boolRtrp": "false"}),
        ("popup_date", "/common/ARA/ARA0403P/view.do", {"reqCode": "3", "selectDay": "", "selectDt": args.date, "selectTime": "06"}),
        ("popup_passenger", "/common/ARA/ARA0901P/view.do", {"reqCode": "6", "isOrg": "2", "passenger1": "1", "passenger2": "0", "passenger3": "0", "passenger4": "0", "passenger5": "0", "passenger6": "0", "totalPessnger": "1"}),
        ("popup_seat", "/common/ARA/ARA0701P/view.do", {"reqCode": "5", "rqSeatAttCd": "015", "locSeatAttCd": "000", "seatAttNm": "일반/기본"}),
        ("popup_train_group", "/common/ARA/ARA0201V/view.do", {"reqCode": "7", "trnGpCd": "109", "trnGpCdNm": "전체"}),
    ]
    client.summary["popups"] = {}
    for name, path, payload in popup_calls:
        result = client.request(name, "POST", f"{APP_BASE}{path}", data=payload, accept="text/html, */*; q=0.01", referer=f"{APP_BASE}/ara/ara0101v.do", raw_name=f"{name}.html")
        parser2 = TextExtractor()
        parser2.feed(result.text())
        client.summary["popups"][name] = {"status": result.status, "textPrefix": parser2.text(180)}

    seat = client.request(
        "seat_selection_app_page",
        "POST",
        f"{APP_BASE}/arc/selectListArc02012_n.do",
        data={
            "reqCode": "9",
            "runDt": str(safe_selected.get("runDt") or args.date),
            "dptDt": train_date,
            "trnNo": train_no,
            "dptTm": str(safe_selected.get("dptTm") or "060000"),
            "trnGpCd": "300",
            "dptRsStnCd": args.depart_code,
            "arvRsStnCd": args.arrive_code,
            "psrmClCd": "1",
            "seatAttCd": "015",
            "dptStnRunOrdr": str(safe_selected.get("dptStnRunOrdr") or "000001"),
            "arvStnRunOrdr": str(safe_selected.get("arvStnRunOrdr") or ""),
            "choiceSeatCount": "1",
        },
        accept="text/html, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="seat_selection.html",
    )
    seat_parser = TextExtractor()
    seat_parser.feed(seat.text())
    client.summary["seatSelection"] = {"textPrefix": seat_parser.text(300)}

    notice = client.request(
        "notice_list",
        "POST",
        f"{APP_BASE}/main/noticeList.do",
        data={"pageId": "MB0101000000"},
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{APP_BASE}/main/main.do",
        raw_name="notice_list.json",
    )
    notice_json = notice.json()
    client.summary["noticeList"] = {"count": len(notice_json.get("noticeList") or [])}

    mutual = client.request(
        "mutual_verify",
        "POST",
        f"{APP_BASE}/ara/selectListAra10130_n.do",
        data={},
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="mutual_verify.json",
    )
    _, mutual_row = client.get_json_result(mutual)
    client.summary["mutualVerify"] = {
        "msgCd": mutual_row.get("msgCd"),
        "strResult": mutual_row.get("strResult"),
        "hasMutualCode": bool(mutual_row.get("mutMrkVrfCd")),
    }

    nf_resv = client.request(
        "netfunnel_act19_reservation_negative",
        "GET",
        f"{NETFUNNEL_BASE}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_19&js=true&{int(time.time() * 1000)}",
        referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
        raw_name="netfunnel_act19.txt",
    )
    key19 = parse_netfunnel_response(nf_resv.text())["params"].get("key", "")
    invalid_base = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
        "rtnDv": "0",
        "trnGpCd1": "300",
        "trnNo1": "",
        "runDt1": "",
        "dptDt1": "",
        "dptTm1": "",
        "dptRsStnCd1": "",
        "arvRsStnCd1": "",
        "psrmClCd1": "1",
        "psgGridcnt": "1",
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": "0",
        "netfunnelKey": key19,
    }
    client.summary["reservationNegative"] = {}
    for name, path, group_flag in [
        ("personal", "/arc/selectListArc05013_n.do", "0"),
        ("group", "/arc/selectListArc06014_n.do", "1"),
    ]:
        payload = dict(invalid_base)
        payload["grpDv"] = group_flag
        result = client.request(
            f"reservation_negative_{name}",
            "POST",
            f"{APP_BASE}{path}",
            data=payload,
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{APP_BASE}/ara/selectListAra10007_n.do",
            raw_name=f"reservation_negative_{name}.json",
        )
        body_text = result.text()
        parsed: Any
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            parsed = {"rawPrefix": body_text[:200]}
        client.summary["reservationNegative"][name] = parsed

    before_ticket = client.request("ticket_list", "GET", f"{APP_BASE}/atc/selectListAtc14017_n.do?pageNo=0", raw_name="ticket_list.html")
    after_ticket = client.request("ticket_list_after_negative", "GET", f"{APP_BASE}/atc/selectListAtc14017_n.do?pageNo=0", raw_name="ticket_list_after_negative.html")
    client.summary["ticketListCheck"] = {
        "beforeSize": before_ticket.size,
        "afterSize": after_ticket.size,
        "sameBody": before_ticket.body == after_ticket.body,
    }

    client.summary["excluded"] = [
        "/ard/selectListArd02017_n.do",
        "/ard/selectListArd02018_n.do",
    ]
    client.save()
    print(json.dumps({"outDir": str(out_dir), "summary": client.summary}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
