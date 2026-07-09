from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from .errors import SrtAppError
from .models import TrainSearchResult, TrainSummary


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)


def extract_text(html: str, *, limit: int | None = None) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    return text if limit is None else text[:limit]


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


def parse_train_search_response(data: dict[str, Any]) -> TrainSearchResult:
    result = normalize_result_row(data)
    result_code = str(result.get("msgCd") or "")
    result_status = str(result.get("strResult") or "")
    if result and result_status and result_status != "SUCC":
        raise SrtAppError(result_code or None, str(result.get("msgTxt") or "") or None, raw=data)
    out = data.get("outDataSets") or {}
    rows = out.get("dsOutput1") if isinstance(out, dict) else []
    trains = []
    for row in rows or []:
        if isinstance(row, dict):
            trains.append(
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
                    raw=row,
                )
            )
    return TrainSearchResult(trains=trains, result=result, raw=data)
