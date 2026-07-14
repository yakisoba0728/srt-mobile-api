#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from srt_mobile_api import SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.config import APP_ORIGIN
from srt_mobile_api.live import (
    _first_complete_srt_seat_train,
    read_credentials_from_env,
)


MAX_ITEMS = 64
MAX_STRING = 64
MAX_ELEMENTS = 10_000
MAX_PATH = 160
MAX_SCRIPT_CHARS = 16_384
MAX_JSON_DEPTH = 5
MAX_JSON_NODES = 256
MAX_JSON_ARRAY_ITEMS = 64
_APP_ORIGIN_PARTS = urlsplit(APP_ORIGIN)
_APP_ORIGIN_PORT = _APP_ORIGIN_PARTS.port or 443
SAFE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
SENSITIVE_NAME_RE = re.compile(r"\d{6}|@|://")
SENSITIVE_STRUCTURAL_RE = re.compile(
    r"(?i)(?:authorization|cookie|credential|email|member|passw|secret|session|token)"
)
LONG_STRUCTURAL_TOKEN_RE = re.compile(r"[A-Za-z0-9_=-]{32,}")
STATUS_VALUES = {
    "success",
    "no_complete_train",
    "login_failed",
    "search_failed",
    "seat_page_failed",
    "unsafe_report",
}

_NON_INVENTORY_TAGS = frozenset(
    {"a", "form", "iframe", "input", "script", "style"}
)
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_URL_RE = re.compile(r"(?i)\b(?:https?|wss?)://")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_AUTH_COOKIE_RE = re.compile(
    r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie)\b"
)
_LONG_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_=-])[A-Za-z0-9_=-]{32,}(?![A-Za-z0-9_=-])"
)
_DIGEST_VALUE_RE = re.compile(r'("sha256"\s*:\s*")[0-9a-f]{64}(")')
_SAFE_LONG_LITERALS = frozenset(
    {
        "embedded_dom_inventory_candidate",
        "embedded_json_inventory_candidate",
        "inline_script_inventory_candidate",
        "same_origin_script_inventory_reference",
    }
)
_PAYLOAD_RE = re.compile(r"\b(?:body|data)\s*:\s*\{(?P<body>[^{}]{0,4096})\}")
_OBJECT_KEY_RE = re.compile(
    r"(?:^|[,\s])(?:['\"])?(?P<name>[A-Za-z][A-Za-z0-9_-]{0,63})(?:['\"])?\s*:"
)
_RESPONSE_PATH_RE = re.compile(
    r"\b(?:data|response|result)(?:\s*\?*\.\s*[A-Za-z][A-Za-z0-9_-]{0,31}){1,4}"
)
_DYNAMIC_MARKER_RE = re.compile(
    r"(?i)(?:seat|scar|car|coach)[_-]?(?:\d|[A-Z]{1,4}\d)"
)
_LETTER_FIRST_COORDINATE_RE = re.compile(r"(?i)[A-Z]{1,4}\d{1,4}[A-Z]?\Z")
_DIGIT_FIRST_COORDINATE_RE = re.compile(r"(?i)\d{1,4}[A-Z]{1,4}\Z")
_STATIC_PATH_SUFFIXES = (".do", ".js", ".mjs")
_METHOD_RE = re.compile(
    r"\b(?:method|type)\s*:\s*['\"](?P<method>GET|POST|PUT|PATCH|DELETE|HEAD)['\"]",
    re.IGNORECASE,
)
_XHR_METHOD_RE = re.compile(
    r"\.open\s*\(\s*['\"](?P<method>GET|POST|PUT|PATCH|DELETE|HEAD)['\"]",
    re.IGNORECASE,
)
_PAGE_KEYS = (
    "marker_present",
    "element_count",
    "inventory_marker_element_count",
    "structural_names",
    "source_categories",
    "scripts",
    "forms",
    "iframes",
    "embedded_json",
    "external_handoff_candidate",
)


def _safe_structural_name(value: str) -> bool:
    return (
        len(value) <= MAX_STRING
        and SAFE_NAME_RE.fullmatch(value) is not None
        and SENSITIVE_NAME_RE.search(value) is None
        and SENSITIVE_STRUCTURAL_RE.search(value) is None
        and LONG_STRUCTURAL_TOKEN_RE.search(value) is None
    )


def _inventory_name(value: str) -> bool:
    value = value[:MAX_PATH]
    folded = value.casefold()
    if any(marker in folded for marker in ("seat", "scar", "coach")):
        return True
    if re.search(r"(?:^|[-_])cars?(?:[-_]|$)", folded):
        return True
    return re.search(
        r"car(?:No|List|Rows|Items|Code|Info|Map|[0-9])",
        value,
    ) is not None


def _dynamic_value_name(value: str) -> bool:
    return (
        value.isdigit()
        or _DYNAMIC_MARKER_RE.search(value) is not None
        or _LETTER_FIRST_COORDINATE_RE.fullmatch(value) is not None
        or _DIGIT_FIRST_COORDINATE_RE.fullmatch(value) is not None
    )


def _safe_same_origin_path(path: str) -> str | None:
    if not path:
        path = "/"
    if (
        len(path) > MAX_PATH
        or not path.startswith("/")
        or "//" in path
        or re.fullmatch(r"/[A-Za-z0-9._~/-]*", path) is None
    ):
        return None
    if not path.casefold().endswith(_STATIC_PATH_SUFFIXES):
        return None
    segments = [segment for segment in path.split("/") if segment]
    stems = [*segments[:-1], segments[-1].rsplit(".", 1)[0]]
    if any(
        segment in {".", ".."}
        or len(segment) > 31
        or SENSITIVE_NAME_RE.search(segment)
        or SENSITIVE_STRUCTURAL_RE.search(segment)
        or LONG_STRUCTURAL_TOKEN_RE.search(segment)
        for segment in segments
    ) or any(_dynamic_value_name(stem) for stem in stems):
        return None
    return path


def _classify_target(value: str | None) -> tuple[str, str | None]:
    if value is None:
        return "self", None
    if len(value) > 2_048:
        return "unresolved", None
    target = value.strip()
    if not target or target.startswith(("#", "?")):
        return "self", None
    try:
        parsed = urlsplit(urljoin(f"{APP_ORIGIN}/", target))
        port = parsed.port
    except ValueError:
        return "unresolved", None
    if parsed.scheme.casefold() not in {"http", "https"} or parsed.hostname is None:
        return "unresolved", None
    same_origin = (
        parsed.scheme.casefold() == _APP_ORIGIN_PARTS.scheme.casefold()
        and parsed.hostname.casefold() == _APP_ORIGIN_PARTS.hostname.casefold()
        and (port if port is not None else _APP_ORIGIN_PORT) == _APP_ORIGIN_PORT
        and parsed.username is None
        and parsed.password is None
    )
    if not same_origin:
        return "cross_origin", None
    return "same_origin", _safe_same_origin_path(parsed.path)


def _script_type(value: str | None) -> str:
    folded = (value or "")[:128].split(";", 1)[0].strip().casefold()
    if folded == "module":
        return "module"
    if folded == "application/json" or folded.endswith("+json"):
        return "application_json"
    if folded in {"", "application/javascript", "text/javascript"}:
        return "classic"
    return "other"


def _external_handoff_value(value: str) -> bool:
    folded = value[:2_048].casefold()
    return "srtjob=seatmap" in folded or (
        "://" in folded
        and any(marker in folded for marker in ("seatmap", "seat-map"))
    )


def _scan_javascript(code: str) -> tuple[str, list[str]]:
    masked = ["\n" if char == "\n" else " " for char in code]
    literals: list[str] = []
    methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
    index = 0
    while index < len(code):
        if code.startswith("//", index):
            newline = code.find("\n", index + 2)
            if newline < 0:
                break
            masked[newline] = "\n"
            index = newline + 1
            continue
        if code.startswith("/*", index):
            end = code.find("*/", index + 2)
            if end < 0:
                break
            for offset in range(index, end + 2):
                if code[offset] == "\n":
                    masked[offset] = "\n"
            index = end + 2
            continue

        quote = code[index]
        if quote in {"`", "/"}:
            break
        if quote in {'"', "'"}:
            end = index + 1
            while end < len(code):
                if code[end] == "\\":
                    end += 2
                    continue
                if code[end] == quote:
                    break
                end += 1
            if end >= len(code):
                break
            value = code[index + 1 : end]
            if len(value) <= 512 and len(literals) < MAX_ITEMS:
                literals.append(value)
            following = end + 1
            while following < len(code) and code[following].isspace():
                following += 1
            preserve = (
                following < len(code) and code[following] == ":"
            ) or value.upper() in methods
            masked[index] = quote
            masked[end] = quote
            if preserve:
                masked[index + 1 : end] = code[index + 1 : end]
            index = end + 1
            continue

        masked[index] = code[index]
        index += 1
    return "".join(masked), literals


class _SeatLayoutEvidenceCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.marker_present = False
        self.external_handoff_candidate = False
        self.tag_names: set[str] = set()
        self.attribute_names: set[str] = set()
        self.input_names: set[str] = set()
        self.class_tokens: set[str] = set()
        self.inventory_names: set[str] = set()
        self.source_categories: set[str] = set()
        self.element_count = 0
        self.inventory_marker_element_count = 0
        self.script_count = 0
        self.inline_script_count = 0
        self.same_origin_script_count = 0
        self.cross_origin_script_count = 0
        self.script_items: list[dict[str, object]] = []
        self.form_count = 0
        self.same_origin_form_count = 0
        self.cross_origin_form_count = 0
        self.self_form_count = 0
        self.form_items: list[dict[str, object]] = []
        self.iframe_count = 0
        self.same_origin_iframe_count = 0
        self.cross_origin_iframe_count = 0
        self.unresolved_iframe_count = 0
        self.same_origin_iframe_paths: set[str] = set()
        self.json_count = 0
        self.valid_json_count = 0
        self.invalid_json_count = 0
        self.json_items: list[dict[str, object]] = []
        self._style_depth = 0
        self._current_script: dict[str, object] | None = None
        self._form_stack: list[dict[str, object] | None] = []
        self._form_overflow_depth = 0

    @staticmethod
    def _add_bounded(items: set[str], value: str) -> None:
        if len(items) < MAX_ITEMS:
            items.add(value)

    @staticmethod
    def _increment(value: int) -> int:
        return min(value + 1, MAX_ELEMENTS)

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        return {name.casefold(): value for name, value in attrs[:MAX_ITEMS]}

    def _add_script_item(self, item: dict[str, object]) -> None:
        if len(self.script_items) < MAX_ITEMS:
            self.script_items.append(item)

    @staticmethod
    def _empty_script_item(
        *,
        kind: str,
        script_type: str,
        async_present: bool,
        defer_present: bool,
        path: str | None,
    ) -> dict[str, object]:
        return {
            "kind": kind,
            "type": script_type,
            "async": async_present,
            "defer": defer_present,
            "path": path,
            "length": 0,
            "truncated": False,
            "sha256": None,
            "ajax_primitives": [],
            "http_methods": [],
            "route_paths": [],
            "cross_origin_route_count": 0,
            "payload_keys": [],
            "response_paths": [],
            "inventory_names": [],
        }

    def _start_script(self, attrs: dict[str, str | None]) -> None:
        self.script_count = self._increment(self.script_count)
        script_type = _script_type(attrs.get("type"))
        async_present = "async" in attrs
        defer_present = "defer" in attrs
        src = attrs.get("src")
        if src is not None:
            target, path = _classify_target(src)
            if target == "cross_origin":
                self.cross_origin_script_count = self._increment(
                    self.cross_origin_script_count
                )
                self.source_categories.add("cross_origin_script_reference")
            elif target == "same_origin":
                self.same_origin_script_count = self._increment(
                    self.same_origin_script_count
                )
                self.source_categories.add("same_origin_script_reference")
                if path is not None:
                    item = self._empty_script_item(
                        kind="same_origin_external",
                        script_type=script_type,
                        async_present=async_present,
                        defer_present=defer_present,
                        path=path,
                    )
                    self._add_script_item(item)
                    if _inventory_name(path):
                        self.source_categories.add(
                            "same_origin_script_inventory_reference"
                        )
                    else:
                        self.source_categories.add("generic_script")
            else:
                self.source_categories.add("generic_script")
            self._current_script = {
                "external": True,
                "buffer": "",
                "length": 0,
            }
            return

        self.inline_script_count = self._increment(self.inline_script_count)
        self._current_script = {
            "external": False,
            "type": script_type,
            "async": async_present,
            "defer": defer_present,
            "buffer": "",
            "length": 0,
        }

    def _append_script_data(self, data: str) -> None:
        state = self._current_script
        if state is None:
            return
        state["length"] = min(
            int(state["length"]) + len(data),
            MAX_SCRIPT_CHARS + 1,
        )
        remaining = MAX_SCRIPT_CHARS - len(str(state["buffer"]))
        if remaining > 0:
            state["buffer"] = f"{state['buffer']}{data[:remaining]}"

    def _analyze_inline_script(
        self,
        code: str,
        *,
        script_type: str,
        async_present: bool,
        defer_present: bool,
        length: int,
        sha256: str,
    ) -> None:
        structural_code, literals = _scan_javascript(code)
        ajax_primitives: set[str] = set()
        for name, pattern in (
            ("fetch", r"\bfetch\s*\("),
            ("jquery_ajax", r"\$\.ajax\s*\("),
            ("jquery_get", r"\$\.get\s*\("),
            ("jquery_post", r"\$\.post\s*\("),
            ("xml_http_request", r"\bXMLHttpRequest\b"),
        ):
            if re.search(pattern, structural_code):
                ajax_primitives.add(name)

        methods = {
            match.group("method").upper()
            for pattern in (_METHOD_RE, _XHR_METHOD_RE)
            for match in pattern.finditer(structural_code)
        }
        route_paths: set[str] = set()
        cross_origin_route_count = 0
        for value in literals:
            if _external_handoff_value(value):
                self.external_handoff_candidate = True
            if not (
                value.startswith(("/", "./", "../", "http://", "https://", "//"))
                or ".do" in value.casefold()
            ):
                continue
            target, path = _classify_target(value)
            if target == "same_origin" and path is not None:
                if len(route_paths) < MAX_ITEMS:
                    route_paths.add(path)
            elif target == "cross_origin":
                cross_origin_route_count = min(
                    cross_origin_route_count + 1,
                    MAX_ITEMS,
                )

        payload_keys: set[str] = set()
        for payload in _PAYLOAD_RE.finditer(structural_code):
            for match in _OBJECT_KEY_RE.finditer(payload.group("body")):
                name = match.group("name")
                if (
                    _safe_structural_name(name)
                    and not _dynamic_value_name(name)
                    and len(payload_keys) < MAX_ITEMS
                ):
                    payload_keys.add(name)

        response_paths: set[str] = set()
        for match in _RESPONSE_PATH_RE.finditer(structural_code):
            path = re.sub(r"\s*\?*\.\s*", ".", match.group(0))
            segments = path.split(".")
            if (
                len(path) <= MAX_STRING
                and all(_safe_structural_name(segment) for segment in segments)
                and all(not _dynamic_value_name(segment) for segment in segments)
                and len(response_paths) < MAX_ITEMS
            ):
                response_paths.add(path)

        inventory_names: set[str] = set()
        for name in payload_keys:
            if _inventory_name(name):
                inventory_names.add(name)
        for path in response_paths:
            for segment in path.split("."):
                if len(inventory_names) >= MAX_ITEMS:
                    break
                if _inventory_name(segment) and _safe_structural_name(segment):
                    inventory_names.add(segment)

        item = self._empty_script_item(
            kind="inline",
            script_type=script_type,
            async_present=async_present,
            defer_present=defer_present,
            path=None,
        )
        item.update(
            {
                "length": min(length, MAX_SCRIPT_CHARS),
                "truncated": length > MAX_SCRIPT_CHARS,
                "sha256": sha256,
                "ajax_primitives": sorted(ajax_primitives),
                "http_methods": sorted(methods),
                "route_paths": sorted(route_paths),
                "cross_origin_route_count": cross_origin_route_count,
                "payload_keys": sorted(payload_keys),
                "response_paths": sorted(response_paths),
                "inventory_names": sorted(inventory_names),
            }
        )
        self._add_script_item(item)

        has_inventory_contract = bool(inventory_names) and bool(
            route_paths or payload_keys or response_paths
        )
        if ajax_primitives:
            self.source_categories.add(
                "inline_ajax_inventory_contract"
                if has_inventory_contract
                else "inline_ajax_contract"
            )
        if len(inventory_names) >= 2:
            self.source_categories.add("inline_script_inventory_candidate")
        if not ajax_primitives and len(inventory_names) < 2:
            self.source_categories.add("generic_script")
        if cross_origin_route_count:
            self.source_categories.add("cross_origin_ajax_target")

    @staticmethod
    def _json_type(value: object) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return "other"

    def _summarize_json(self, value: object) -> dict[str, object]:
        key_types: set[str] = set()
        array_cardinalities: dict[str, dict[str, object]] = {}
        inventory_names: set[str] = set()
        nodes = 0
        max_depth = 0
        truncated = False

        def visit(current: object, path: str, depth: int) -> None:
            nonlocal nodes, max_depth, truncated
            if nodes >= MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
                truncated = True
                return
            nodes += 1
            max_depth = max(max_depth, min(depth, MAX_JSON_DEPTH))
            if isinstance(current, dict):
                if len(current) > MAX_ITEMS:
                    truncated = True
                for index, (raw_key, child) in enumerate(current.items()):
                    if index >= MAX_ITEMS:
                        break
                    if (
                        not isinstance(raw_key, str)
                        or not _safe_structural_name(raw_key)
                        or _dynamic_value_name(raw_key)
                    ):
                        continue
                    child_path = f"{path}.{raw_key}" if path else raw_key
                    if len(child_path) > MAX_STRING:
                        truncated = True
                        continue
                    if len(key_types) < MAX_ITEMS:
                        key_types.add(f"{child_path}:{self._json_type(child)}")
                    if _inventory_name(raw_key) and len(inventory_names) < MAX_ITEMS:
                        inventory_names.add(raw_key)
                    visit(child, child_path, depth + 1)
            elif isinstance(current, list):
                array_path = path or "$"
                if len(array_cardinalities) < MAX_ITEMS:
                    array_cardinalities[array_path] = {
                        "path": array_path,
                        "count": min(len(current), MAX_JSON_ARRAY_ITEMS),
                        "truncated": len(current) > MAX_JSON_ARRAY_ITEMS,
                    }
                if len(current) > MAX_JSON_ARRAY_ITEMS:
                    truncated = True
                child_path = f"{path}[]" if path else "$[]"
                for child in current[:MAX_JSON_ARRAY_ITEMS]:
                    visit(child, child_path, depth + 1)

        visit(value, "", 0)
        return {
            "root_type": self._json_type(value),
            "key_types": sorted(key_types),
            "array_cardinalities": [
                array_cardinalities[path] for path in sorted(array_cardinalities)
            ],
            "inventory_names": sorted(inventory_names),
            "max_depth": max_depth,
            "truncated": truncated,
        }

    def _finish_script(self) -> None:
        state = self._current_script
        if state is None:
            return
        self._current_script = None
        if bool(state["external"]):
            return
        code = str(state["buffer"])
        script_type = str(state["type"])
        length = int(state["length"])
        sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if script_type == "application_json":
            item = self._empty_script_item(
                kind="inline",
                script_type=script_type,
                async_present=bool(state["async"]),
                defer_present=bool(state["defer"]),
                path=None,
            )
            item.update(
                {
                    "length": min(length, MAX_SCRIPT_CHARS),
                    "truncated": length > MAX_SCRIPT_CHARS,
                    "sha256": sha256,
                }
            )
            self._add_script_item(item)
            self.json_count = self._increment(self.json_count)
            if length > MAX_SCRIPT_CHARS:
                self.invalid_json_count = self._increment(self.invalid_json_count)
                return
            try:
                parsed = json.loads(code)
            except (TypeError, ValueError):
                self.invalid_json_count = self._increment(self.invalid_json_count)
                return
            self.valid_json_count = self._increment(self.valid_json_count)
            summary = self._summarize_json(parsed)
            if len(self.json_items) < MAX_ITEMS:
                self.json_items.append(summary)
            if len(summary["inventory_names"]) >= 2 and summary[
                "array_cardinalities"
            ]:
                self.source_categories.add("embedded_json_inventory_candidate")
            return
        self._analyze_inline_script(
            code,
            script_type=script_type,
            async_present=bool(state["async"]),
            defer_present=bool(state["defer"]),
            length=length,
            sha256=sha256,
        )

    def _start_form(self, attrs: dict[str, str | None]) -> None:
        self.form_count = self._increment(self.form_count)
        method_value = (attrs.get("method") or "get")[:16].strip().upper()
        method = method_value if method_value in {"GET", "POST"} else "OTHER"
        target, path = _classify_target(attrs.get("action"))
        item: dict[str, object] | None = None
        if target == "cross_origin":
            self.cross_origin_form_count = self._increment(
                self.cross_origin_form_count
            )
            self.source_categories.add("cross_origin_form_reference")
        else:
            if target == "same_origin":
                self.same_origin_form_count = self._increment(
                    self.same_origin_form_count
                )
                self.source_categories.add("same_origin_form_reference")
            else:
                self.self_form_count = self._increment(self.self_form_count)
                target = "self"
                path = None
            if len(self.form_items) < MAX_ITEMS:
                item = {
                    "method": method,
                    "target": target,
                    "path": path,
                    "input_names": set(),
                    "inventory_names": set(),
                }
                self.form_items.append(item)
        if len(self._form_stack) < MAX_ITEMS:
            self._form_stack.append(item)
        else:
            self._form_overflow_depth = min(
                self._form_overflow_depth + 1,
                MAX_ELEMENTS,
            )

    def _start_iframe(self, attrs: dict[str, str | None]) -> None:
        self.iframe_count = self._increment(self.iframe_count)
        target, path = _classify_target(attrs.get("src"))
        if target == "cross_origin":
            self.cross_origin_iframe_count = self._increment(
                self.cross_origin_iframe_count
            )
            self.source_categories.add("cross_origin_iframe_reference")
        elif target == "same_origin":
            self.same_origin_iframe_count = self._increment(
                self.same_origin_iframe_count
            )
            self.source_categories.add("same_origin_iframe_reference")
            if path is not None and len(self.same_origin_iframe_paths) < MAX_ITEMS:
                self.same_origin_iframe_paths.add(path)
        else:
            self.unresolved_iframe_count = self._increment(
                self.unresolved_iframe_count
            )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag_name = tag.casefold()
        self.element_count = self._increment(self.element_count)
        if _safe_structural_name(tag_name):
            self._add_bounded(self.tag_names, tag_name)
        attr_map = self._attrs(attrs)
        if tag_name == "script":
            self._start_script(attr_map)
        elif tag_name == "style":
            self._style_depth += 1
        elif tag_name == "form":
            self._start_form(attr_map)
        elif tag_name == "iframe":
            self._start_iframe(attr_map)

        inventory_marker = _inventory_name(tag_name)
        for raw_name, raw_value in attrs:
            name = raw_name.casefold()
            if _safe_structural_name(name):
                self._add_bounded(self.attribute_names, name)
                if _inventory_name(name):
                    self._add_bounded(self.inventory_names, name)
            if raw_value is None:
                continue
            if _external_handoff_value(raw_value):
                self.external_handoff_candidate = True
            if tag_name == "input" and name == "name":
                if _safe_structural_name(raw_value):
                    self._add_bounded(self.input_names, raw_value)
                    if _inventory_name(raw_value):
                        self._add_bounded(self.inventory_names, raw_value)
                    if (
                        not self._form_overflow_depth
                        and self._form_stack
                        and self._form_stack[-1] is not None
                    ):
                        form = self._form_stack[-1]
                        if len(form["input_names"]) < MAX_ITEMS:
                            form["input_names"].add(raw_value)
                        if (
                            _inventory_name(raw_value)
                            and len(form["inventory_names"]) < MAX_ITEMS
                        ):
                            form["inventory_names"].add(raw_value)
            elif name == "class":
                for index, match in enumerate(re.finditer(r"\S+", raw_value)):
                    if index >= MAX_ITEMS:
                        break
                    token = match.group(0)
                    if _inventory_name(token):
                        inventory_marker = True
                    elif _safe_structural_name(token):
                        self._add_bounded(self.class_tokens, token)
            elif name == "id" and _inventory_name(raw_value):
                inventory_marker = True
            if name.startswith("data-") and _inventory_name(name):
                inventory_marker = True

        if inventory_marker and tag_name not in _NON_INVENTORY_TAGS:
            self.inventory_marker_element_count = self._increment(
                self.inventory_marker_element_count
            )

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name == "script":
            self._finish_script()
        elif tag_name == "style" and self._style_depth:
            self._style_depth -= 1
        elif tag_name == "form":
            if self._form_overflow_depth:
                self._form_overflow_depth -= 1
            elif self._form_stack:
                self._form_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._current_script is not None:
            self._append_script_data(data)
        else:
            if _external_handoff_value(data):
                self.external_handoff_candidate = True
            if not self._style_depth and "좌석선택" in data:
                self.marker_present = True

    def evidence(self) -> dict[str, object]:
        self._finish_script()
        if self.inventory_marker_element_count >= 2:
            self.source_categories.add("embedded_dom_inventory_candidate")
        if self.external_handoff_candidate:
            self.source_categories.add("external_seat_map_handoff")
        form_items: list[dict[str, object]] = []
        for item in self.form_items:
            form_items.append(
                {
                    "method": item["method"],
                    "target": item["target"],
                    "path": item["path"],
                    "input_names": sorted(item["input_names"]),
                    "inventory_names": sorted(item["inventory_names"]),
                }
            )
        result: dict[str, object] = {
            "marker_present": self.marker_present,
            "element_count": self.element_count,
            "inventory_marker_element_count": self.inventory_marker_element_count,
            "structural_names": {
                "tag_names": sorted(self.tag_names),
                "attribute_names": sorted(self.attribute_names),
                "input_names": sorted(self.input_names),
                "class_tokens": sorted(self.class_tokens),
                "inventory_names": sorted(self.inventory_names),
            },
            "source_categories": sorted(self.source_categories),
            "scripts": {
                "count": self.script_count,
                "inline_count": self.inline_script_count,
                "same_origin_count": self.same_origin_script_count,
                "cross_origin_count": self.cross_origin_script_count,
                "items": self.script_items,
            },
            "forms": {
                "count": self.form_count,
                "same_origin_count": self.same_origin_form_count,
                "cross_origin_count": self.cross_origin_form_count,
                "self_count": self.self_form_count,
                "items": form_items,
            },
            "iframes": {
                "count": self.iframe_count,
                "same_origin_count": self.same_origin_iframe_count,
                "cross_origin_count": self.cross_origin_iframe_count,
                "unresolved_count": self.unresolved_iframe_count,
                "same_origin_paths": sorted(self.same_origin_iframe_paths),
            },
            "embedded_json": {
                "count": self.json_count,
                "valid_count": self.valid_json_count,
                "invalid_count": self.invalid_json_count,
                "items": self.json_items,
            },
            "external_handoff_candidate": self.external_handoff_candidate,
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
    else:
        categories = set(page["source_categories"])
        if categories.intersection(
            {
                "embedded_dom_inventory_candidate",
                "embedded_json_inventory_candidate",
                "inline_ajax_inventory_contract",
                "inline_script_inventory_candidate",
            }
        ):
            sufficiency = "inventory_source_candidate"
        elif "same_origin_script_inventory_reference" in categories:
            sufficiency = "inventory_source_reference"
        elif "external_seat_map_handoff" in categories:
            sufficiency = "external_handoff_only"
        else:
            sufficiency = "no_inventory_source"
    return {
        "schema_version": 2,
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
    scan_value = _DIGEST_VALUE_RE.sub(r'\1[DIGEST]\2', serialized)
    for literal in _SAFE_LONG_LITERALS:
        scan_value = scan_value.replace(json.dumps(literal), '"[CATEGORY]"')
    return not any(
        pattern.search(scan_value)
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
