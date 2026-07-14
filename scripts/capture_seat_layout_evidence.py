#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path

from srt_mobile_api import SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.live import (
    _first_complete_srt_seat_train,
    read_credentials_from_env,
)


MAX_ITEMS = 64
MAX_STRING = 64
MAX_ELEMENTS = 10_000
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
SENSITIVE_NAME_RE = re.compile(r"\d{6}|@|://")
STATUS_VALUES = {
    "success",
    "no_complete_train",
    "login_failed",
    "search_failed",
    "seat_page_failed",
    "unsafe_report",
}

_SEAT_IDENTIFIER_RE = re.compile(
    r"(?:^|[\s_-])(?:seat|scar)(?:[\s_-]|$)",
    re.IGNORECASE,
)
_NON_INVENTORY_TAGS = frozenset({"a", "form", "input", "script", "style"})
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_URL_RE = re.compile(r"(?i)\b(?:https?|wss?)://")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_AUTH_COOKIE_RE = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie)\b"
)
_LONG_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_=-])[A-Za-z0-9_=-]{32,}(?![A-Za-z0-9_=-])"
)
_PAGE_KEYS = (
    "marker_present",
    "external_handoff_candidate",
    "embedded_inventory_candidate",
    "script_present",
    "form_present",
    "tag_names",
    "attribute_names",
    "input_names",
    "structural_class_tokens",
    "element_count",
    "candidate_element_count",
)


def _safe_structural_name(value: str) -> bool:
    return (
        len(value) <= MAX_STRING
        and SAFE_NAME_RE.fullmatch(value) is not None
        and SENSITIVE_NAME_RE.search(value) is None
    )


def _external_handoff_value(value: str) -> bool:
    folded = value.casefold()
    return "srtjob=seatmap" in folded or (
        "://" in folded
        and any(marker in folded for marker in ("seatmap", "seat-map"))
    )


class _SeatLayoutEvidenceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.marker_present = False
        self.external_handoff_candidate = False
        self.script_present = False
        self.form_present = False
        self.tag_names: set[str] = set()
        self.attribute_names: set[str] = set()
        self.input_names: set[str] = set()
        self.structural_class_tokens: set[str] = set()
        self.element_count = 0
        self.candidate_element_count = 0
        self._suppressed_text_depth = 0

    @staticmethod
    def _add_bounded(items: set[str], value: str) -> None:
        if len(items) < MAX_ITEMS:
            items.add(value)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.casefold()
        self.element_count = min(self.element_count + 1, MAX_ELEMENTS)
        if _safe_structural_name(tag_name):
            self._add_bounded(self.tag_names, tag_name)
        if tag_name == "script":
            self.script_present = True
            self._suppressed_text_depth += 1
        elif tag_name == "style":
            self._suppressed_text_depth += 1
        if tag_name == "form":
            self.form_present = True

        candidate = False
        for raw_name, raw_value in attrs:
            name = raw_name.casefold()
            if _safe_structural_name(name):
                self._add_bounded(self.attribute_names, name)
            if raw_value is None:
                continue
            if _external_handoff_value(raw_value):
                self.external_handoff_candidate = True
            if tag_name == "input" and name == "name":
                if _safe_structural_name(raw_value):
                    self._add_bounded(self.input_names, raw_value)
            elif name == "class":
                for token in raw_value.split():
                    if _safe_structural_name(token):
                        self._add_bounded(self.structural_class_tokens, token)
                if _SEAT_IDENTIFIER_RE.search(raw_value):
                    candidate = True
            elif name == "id" and _SEAT_IDENTIFIER_RE.search(raw_value):
                candidate = True
            if name.startswith("data-") and "seat" in name:
                candidate = True

        if candidate and tag_name not in _NON_INVENTORY_TAGS:
            self.candidate_element_count = min(
                self.candidate_element_count + 1,
                MAX_ELEMENTS,
            )

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self._suppressed_text_depth:
            self._suppressed_text_depth -= 1

    def handle_data(self, data: str) -> None:
        if _external_handoff_value(data):
            self.external_handoff_candidate = True
        if not self._suppressed_text_depth and "좌석선택" in data:
            self.marker_present = True

    def evidence(self) -> dict[str, object]:
        result: dict[str, object] = {
            "marker_present": self.marker_present,
            "external_handoff_candidate": self.external_handoff_candidate,
            "embedded_inventory_candidate": self.candidate_element_count >= 2,
            "script_present": self.script_present,
            "form_present": self.form_present,
            "tag_names": sorted(self.tag_names),
            "attribute_names": sorted(self.attribute_names),
            "input_names": sorted(self.input_names),
            "structural_class_tokens": sorted(self.structural_class_tokens),
            "element_count": self.element_count,
            "candidate_element_count": self.candidate_element_count,
        }
        assert tuple(result) == _PAGE_KEYS
        return result


def collect_page_evidence(raw: str) -> dict[str, object]:
    collector = _SeatLayoutEvidenceCollector()
    collector.feed(raw)
    collector.close()
    return collector.evidence()


def _result(
    status: str,
    calls: dict[str, int],
    page: dict[str, object] | None = None,
) -> dict[str, object]:
    if status not in STATUS_VALUES:
        raise ValueError("unsupported evidence status")
    if status != "success":
        page = None
    if page is None:
        sufficiency = "unavailable"
    elif page["embedded_inventory_candidate"]:
        sufficiency = "stable_embedded_candidate"
    elif page["external_handoff_candidate"] or page["script_present"]:
        sufficiency = "external_or_script_backed"
    else:
        sufficiency = "no_inventory_candidate"
    return {
        "schema_version": 1,
        "status": status,
        "calls": dict(calls),
        "page": page,
        "sufficiency": sufficiency,
    }


def run_bounded_evidence(
    client: SrtClient,
    *,
    login_id: str,
    password: str,
    query: TrainSearchQuery,
) -> dict[str, object]:
    calls = {"login": 0, "search": 0, "seat_page": 0}
    try:
        calls["login"] = 1
        client.login(login_id, password)
    except Exception:
        return _result("login_failed", calls)

    try:
        calls["search"] = 1
        search_result = client.search_trains(query)
        train = _first_complete_srt_seat_train(search_result.trains)
    except Exception:
        return _result("search_failed", calls)
    if train is None:
        return _result("no_complete_train", calls)

    seat_page = None
    raw = None
    try:
        calls["seat_page"] = 1
        seat_page = client.get_seat_page(train)
        raw = seat_page.raw
        page = collect_page_evidence(raw)
    except Exception:
        return _result("seat_page_failed", calls)
    finally:
        raw = None
        seat_page = None
    return _result("success", calls, page)


def report_is_safe(serialized: str, secrets: tuple[str, ...]) -> bool:
    if any(secret and secret in serialized for secret in secrets):
        return False
    return not any(
        pattern.search(serialized)
        for pattern in (
            _AUTH_COOKIE_RE,
            _CARD_RE,
            _URL_RE,
            _EMAIL_RE,
            _LONG_TOKEN_RE,
        )
    )


def _safe_calls(report: object) -> dict[str, int]:
    if not isinstance(report, dict):
        return {"login": 0, "search": 0, "seat_page": 0}
    source = report.get("calls")
    if not isinstance(source, dict):
        return {"login": 0, "search": 0, "seat_page": 0}
    return {
        name: 1 if source.get(name) == 1 else 0
        for name in ("login", "search", "seat_page")
    }


def _write_atomic(output: Path, serialized: str, *, force: bool) -> bool:
    temporary: Path | None = None
    try:
        if output.exists() and not force:
            return False
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        if force:
            os.replace(temporary, output)
            temporary = None
        else:
            os.link(temporary, output)
            temporary.unlink()
            temporary = None
        return True
    except Exception:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture bounded structural SRT seat-layout evidence"
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    output: Path = args.output

    if os.environ.get("SRT_MOBILE_API_LIVE") != "1":
        return 2
    if not output.parent.is_dir() or output.is_dir():
        return 2
    if output.exists() and not args.force:
        return 2
    test_date = os.environ.get("SRT_TEST_DATE")
    if not test_date:
        return 2

    device_key = os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF")
    try:
        login_id, password = read_credentials_from_env()
        config = SrtConfig(device_key=device_key)
        query = TrainSearchQuery(
            departure_station_code=os.environ.get(
                "SRT_DEPARTURE_STATION_CODE",
                "0551",
            ),
            arrival_station_code=os.environ.get(
                "SRT_ARRIVAL_STATION_CODE",
                "0020",
            ),
            departure_date=test_date,
            departure_time=os.environ.get("SRT_DEPARTURE_TIME", "060000"),
            departure_station_name=os.environ.get(
                "SRT_DEPARTURE_STATION_NAME",
                "수서",
            ),
            arrival_station_name=os.environ.get(
                "SRT_ARRIVAL_STATION_NAME",
                "부산",
            ),
        )
    except Exception:
        return 2

    try:
        client = SrtClient(config)
    except Exception:
        return 2
    report: dict[str, object] | None = None
    failed = False
    try:
        report = run_bounded_evidence(
            client,
            login_id=login_id,
            password=password,
            query=query,
        )
    except Exception:
        failed = True
    finally:
        try:
            client.close()
        except Exception:
            failed = True
    if failed or report is None:
        return 1

    try:
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    except Exception:
        return 1
    secrets = (login_id, password, device_key)
    if not report_is_safe(serialized, secrets):
        report = _result("unsafe_report", _safe_calls(report))
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
        if not report_is_safe(serialized, ()):
            return 1
    return 0 if _write_atomic(output, serialized, force=args.force) else 1


if __name__ == "__main__":
    raise SystemExit(main())
