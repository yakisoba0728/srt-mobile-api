from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


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
