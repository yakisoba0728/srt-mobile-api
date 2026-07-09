# SRT Python Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first installable `srt-mobile-api` Python package with login and safe read/query APIs.

**Architecture:** The package uses a thin `httpx` transport wrapper, dataclass models, extracted payload builders, defensive parsers, and an `SrtClient` facade. NetFunnel support is limited to `act_10` for search. Reservation, ARD, payment, refund, cancellation, and native bridge flows are not implemented as public methods or stubs.

**Tech Stack:** Python 3.11+, `httpx`, standard-library `dataclasses`, `pytest`.

## Global Constraints

- Distribution package name: `srt-mobile-api`.
- Python import package: `srt_mobile_api`.
- Runtime dependency: `httpx`.
- Test dependency: `pytest`.
- Package layout: `src/srt_mobile_api/`.
- MVP includes login and safe read/query APIs only.
- Reservation, payment, refund, cancellation, and payment-detail entry flows are not implemented in this version.
- Dangerous endpoints must not appear as public stub methods in this version.
- Default tests must be offline and non-destructive.
- Live smoke must require `SRT_MOBILE_API_LIVE=1` and credentials from environment variables.
- Live smoke must only perform login and read/query calls.
- Live smoke must never call reservation, payment, refund, cancellation, ARD, ATA, or native bridge endpoints.
- Live smoke must not persist raw responses inside the repository.
- Runtime defaults: base host `https://app.srail.or.kr`, NetFunnel host `https://nf.letskorail.com:443`, user-agent suffix `SRT-APP-Android V.2.0.41`, and form encoding `application/x-www-form-urlencoded; charset=UTF-8`.
- `dsOutput0` must normalize correctly when it is either an object or a list.
- Group search must have a separate request builder. It must not be implemented by changing only the endpoint URL.
- NetFunnel `act_19` is out of scope for this MVP.

---

## File Structure

Create:

```text
pyproject.toml
src/srt_mobile_api/__init__.py
src/srt_mobile_api/client.py
src/srt_mobile_api/config.py
src/srt_mobile_api/errors.py
src/srt_mobile_api/http.py
src/srt_mobile_api/live.py
src/srt_mobile_api/models.py
src/srt_mobile_api/netfunnel.py
src/srt_mobile_api/payloads.py
src/srt_mobile_api/parsers.py
src/srt_mobile_api/redaction.py
src/srt_mobile_api/safety.py
src/srt_mobile_api/session.py
tests/conftest.py
tests/fixtures/fare.html
tests/fixtures/group_search_success.json
tests/fixtures/login_failure.json
tests/fixtures/login_success.json
tests/fixtures/netfunnel_act10.js
tests/fixtures/notice_list.json
tests/fixtures/search_empty.json
tests/fixtures/search_netfunnel_failure.json
tests/fixtures/search_success.json
tests/fixtures/ticket_list.html
tests/fixtures/timetable.html
tests/test_client_read_apis.py
tests/test_http.py
tests/test_live.py
tests/test_models.py
tests/test_netfunnel_payloads_parsers.py
tests/test_redaction_safety.py
tests/test_session.py
```

Do not create modules or methods for excluded destructive domains.

---

### Task 1: Package Scaffold And Metadata

**Files:**
- Create: `pyproject.toml`
- Create: `src/srt_mobile_api/__init__.py`
- Create: `src/srt_mobile_api/client.py`
- Create: `src/srt_mobile_api/config.py`
- Create: `src/srt_mobile_api/errors.py`
- Create: `src/srt_mobile_api/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `SrtConfig`, exported package symbols, base exception classes, and initial dataclasses used by later tasks.

- [ ] **Step 1: Write failing metadata/import tests**

Create `tests/test_models.py`:

```python
from dataclasses import is_dataclass

import srt_mobile_api
from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtApiError, SrtAuthError, SrtProtocolError
from srt_mobile_api.models import PassengerCounts, SrtSession, TrainSearchQuery, TrainSearchResult, TrainSummary


def test_public_exports_are_available():
    assert srt_mobile_api.SrtConfig is SrtConfig
    assert issubclass(SrtAuthError, SrtApiError)
    assert issubclass(SrtProtocolError, SrtApiError)


def test_core_models_are_dataclasses():
    assert is_dataclass(SrtConfig)
    assert is_dataclass(SrtSession)
    assert is_dataclass(PassengerCounts)
    assert is_dataclass(TrainSearchQuery)
    assert is_dataclass(TrainSummary)
    assert is_dataclass(TrainSearchResult)


def test_config_defaults_match_design():
    config = SrtConfig()
    assert config.base_url == "https://app.srail.or.kr"
    assert config.netfunnel_url == "https://nf.letskorail.com:443"
    assert "SRT-APP-Android V.2.0.41" in config.user_agent
    assert config.device_key == "0123456789ABCDEF"
    assert config.live_env_var == "SRT_MOBILE_API_LIVE"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'srt_mobile_api'`.

- [ ] **Step 3: Add package metadata and initial code**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "srt-mobile-api"
version = "0.1.0"
description = "Python client for documented SRT Android app read APIs"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.27,<1",
]

[project.optional-dependencies]
test = [
  "pytest>=8,<10",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
addopts = "-ra"
testpaths = ["tests"]
markers = [
  "live: tests that call live SRT services and require explicit opt-in",
]
```

Create `src/srt_mobile_api/errors.py`:

```python
class SrtApiError(Exception):
    """Base error for SRT client failures."""


class SrtTransportError(SrtApiError):
    """HTTP transport failed before an app-level response was parsed."""


class SrtProtocolError(SrtApiError):
    """The server response did not match the documented protocol."""


class SrtAuthError(SrtApiError):
    """Login or session authentication failed."""


class SrtAppError(SrtApiError):
    """The server returned an app-level failure response."""

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{code or 'UNKNOWN'}: {message or ''}".strip())


class SrtNetFunnelError(SrtApiError):
    """NetFunnel token parsing or acquisition failed."""
```

Create `src/srt_mobile_api/config.py`:

```python
from dataclasses import dataclass


DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Version/4.0 Chrome/126.0.0.0 Mobile Safari/537.36 "
    "SRT-APP-Android V.2.0.41"
)


@dataclass(frozen=True)
class SrtConfig:
    base_url: str = "https://app.srail.or.kr"
    netfunnel_url: str = "https://nf.letskorail.com:443"
    user_agent: str = DEFAULT_UA
    device_key: str = "0123456789ABCDEF"
    timeout: float = 20.0
    live_env_var: str = "SRT_MOBILE_API_LIVE"
```

Create `src/srt_mobile_api/models.py`:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SrtSession:
    login_id: str | None = None
    user_map: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PassengerCounts:
    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0
    infant: int = 0

    @property
    def total(self) -> int:
        return self.adult + self.child + self.senior + self.disability_1_to_3 + self.disability_4_to_6 + self.infant


@dataclass(frozen=True)
class NetFunnelToken:
    action: str
    key: str
    raw_type: str
    code: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainSearchQuery:
    departure_station_code: str
    arrival_station_code: str
    departure_date: str
    departure_time: str = "060000"
    passengers: PassengerCounts = field(default_factory=PassengerCounts)
    train_group_code: str = "900"
    seat_attr_code: str = "015"


@dataclass(frozen=True)
class TrainSummary:
    train_no: str
    train_group_code: str | None = None
    service_class_code: str | None = None
    run_date: str | None = None
    departure_date: str | None = None
    departure_time: str | None = None
    arrival_date: str | None = None
    arrival_time: str | None = None
    departure_station_code: str | None = None
    arrival_station_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainSearchResult:
    trains: list[TrainSummary]
    result: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HtmlPage:
    text: str
    raw: str
```

Create `src/srt_mobile_api/client.py`:

```python
from .config import SrtConfig


class SrtClient:
    def __init__(self, config: SrtConfig | None = None) -> None:
        self.config = config or SrtConfig()
```

Create `src/srt_mobile_api/__init__.py`:

```python
from .client import SrtClient
from .config import SrtConfig
from .errors import SrtApiError, SrtAuthError, SrtProtocolError
from .models import PassengerCounts, SrtSession, TrainSearchQuery, TrainSearchResult, TrainSummary

__all__ = [
    "PassengerCounts",
    "SrtApiError",
    "SrtAuthError",
    "SrtClient",
    "SrtConfig",
    "SrtProtocolError",
    "SrtSession",
    "TrainSearchQuery",
    "TrainSearchResult",
    "TrainSummary",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/srt_mobile_api tests/test_models.py
git commit -m "feat: scaffold srt python package"
```

---

### Task 2: HTTP, Parsers, Redaction, And Safety Core

**Files:**
- Create: `src/srt_mobile_api/http.py`
- Create: `src/srt_mobile_api/parsers.py`
- Create: `src/srt_mobile_api/redaction.py`
- Create: `src/srt_mobile_api/safety.py`
- Create: `tests/conftest.py`
- Test: `tests/test_http.py`
- Test: `tests/test_redaction_safety.py`

**Interfaces:**
- Consumes: `SrtConfig`, `SrtAppError`, `SrtProtocolError`.
- Produces: `SrtHttpClient`, `normalize_result_row()`, `extract_text()`, `redact_mapping()`, `EXCLUDED_API_DOMAINS`.

- [ ] **Step 1: Write failing tests**

Create `tests/conftest.py`:

```python
import json
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_json_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def load_text_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")
```

Create `tests/test_http.py`:

```python
import httpx

from srt_mobile_api import SrtConfig
from srt_mobile_api.http import SrtHttpClient
from srt_mobile_api.parsers import extract_text, normalize_result_row


def test_post_form_adds_ajax_headers_and_form_encoding():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    result = client.post_form("/example.do", {"a": "b"}, accept="application/json", referer="https://app.srail.or.kr/main/main.do")

    assert result["ok"] is True
    assert captured["headers"]["origin"] == "https://app.srail.or.kr"
    assert captured["headers"]["x-requested-with"] == "XMLHttpRequest"
    assert captured["headers"]["content-type"] == "application/x-www-form-urlencoded; charset=UTF-8"
    assert captured["body"] == "a=b"


def test_normalize_result_row_accepts_list_and_object():
    assert normalize_result_row({"outDataSets": {"dsOutput0": [{"msgCd": "A"}]}})["msgCd"] == "A"
    assert normalize_result_row({"outDataSets": {"dsOutput0": {"msgCd": "B"}}})["msgCd"] == "B"
    assert normalize_result_row({"resultMap": [{"msgCd": "C"}]})["msgCd"] == "C"


def test_extract_text_collapses_html_text():
    assert extract_text("<html><body><h1>열차조회</h1><p>  test </p></body></html>") == "열차조회 test"
```

Create `tests/test_redaction_safety.py`:

```python
from srt_mobile_api.redaction import redact_mapping, redact_text
from srt_mobile_api.safety import EXCLUDED_API_DOMAINS


def test_redact_mapping_masks_sensitive_values():
    data = {
        "srchDvNm": "login-id",
        "hmpgPwdCphd": "password",
        "netfunnelKey": "NF",
        "pnrNo": "123456789012",
        "safe": "value",
    }
    redacted = redact_mapping(data)
    assert redacted["srchDvNm"] == "[REDACTED]"
    assert redacted["hmpgPwdCphd"] == "[REDACTED]"
    assert redacted["netfunnelKey"] == "[REDACTED]"
    assert redacted["pnrNo"] == "[REDACTED]"
    assert redacted["safe"] == "value"


def test_redact_text_masks_card_like_values():
    assert "411111" not in redact_text("card 4111-1111-1111-1111")


def test_safety_excludes_dangerous_domains_without_stub_apis():
    assert "reservation" in EXCLUDED_API_DOMAINS
    assert "netfunnel-act-19" in EXCLUDED_API_DOMAINS
    assert "ard-payment-entry" in EXCLUDED_API_DOMAINS
    assert "payment" in EXCLUDED_API_DOMAINS
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_http.py tests/test_redaction_safety.py -q`

Expected: FAIL because modules are missing.

- [ ] **Step 3: Implement HTTP, parsers, redaction, and safety**

Create `src/srt_mobile_api/http.py`:

```python
from typing import Any, Mapping

import httpx

from .config import SrtConfig
from .errors import SrtTransportError


class SrtHttpClient:
    def __init__(self, config: SrtConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            transport=transport,
        )

    @property
    def cookies(self) -> httpx.Cookies:
        return self._client.cookies

    def close(self) -> None:
        self._client.close()

    def get_text(self, path: str, params: Mapping[str, Any] | None = None, *, referer: str | None = None) -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.get(path, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return response.text

    def get_json(self, path: str, params: Mapping[str, Any] | None = None, *, referer: str | None = None) -> dict[str, Any]:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.get(path, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return response.json()

    def post_form(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        *,
        accept: str = "*/*",
        referer: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": accept,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.config.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.post(path, data=dict(data or {}), headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        try:
            return response.json()
        except ValueError:
            return {"html": response.text}
```

Create `src/srt_mobile_api/parsers.py`:

```python
from html.parser import HTMLParser
from typing import Any
import re


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
```

Create `src/srt_mobile_api/redaction.py`:

```python
from collections.abc import Mapping
import re
from typing import Any

SENSITIVE_KEYS = {
    "srchDvNm",
    "hmpgPwdCphd",
    "password",
    "Cookie",
    "Set-Cookie",
    "netfunnelKey",
    "key",
    "pnrNo",
}

CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def redact_text(value: str) -> str:
    return CARD_RE.sub("[REDACTED_CARD]", value)


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key in SENSITIVE_KEYS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = value
    return redacted
```

Create `src/srt_mobile_api/safety.py`:

```python
EXCLUDED_API_DOMAINS = frozenset(
    {
        "reservation",
        "netfunnel-act-19",
        "ard-payment-entry",
        "payment",
        "refund",
        "cancellation",
        "ata-detail",
        "native-bridge",
        "external-seatmap",
    }
)

SAFETY_STATEMENTS = (
    "No user credentials, cookies, NetFunnel keys, raw response bodies, or payment tokens are stored here.",
    "Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or card-shaped values in the repository.",
    "Library rule: do not implement real card approval in the core client.",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_http.py tests/test_redaction_safety.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srt_mobile_api tests/conftest.py tests/test_http.py tests/test_redaction_safety.py
git commit -m "feat: add srt http and safety core"
```

---

### Task 3: NetFunnel, Payload Builders, And Train Parsers

**Files:**
- Create: `src/srt_mobile_api/netfunnel.py`
- Create: `src/srt_mobile_api/payloads.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/models.py`
- Create: `tests/fixtures/group_search_success.json`
- Create: `tests/fixtures/netfunnel_act10.js`
- Create: `tests/fixtures/search_empty.json`
- Create: `tests/fixtures/search_netfunnel_failure.json`
- Create: `tests/fixtures/search_success.json`
- Test: `tests/test_netfunnel_payloads_parsers.py`

**Interfaces:**
- Consumes: `TrainSearchQuery`, `PassengerCounts`, `TrainSummary`, `TrainSearchResult`.
- Produces: `parse_netfunnel_response()`, `search_page_payload()`, `search_ajax_payload()`, `group_search_ajax_payload()`, `parse_train_search_response()`.

- [ ] **Step 1: Write failing tests**

Create `tests/fixtures/netfunnel_act10.js`:

```text
NetFunnel.gControl.result='NetFunnel.gRtype=5101;5101:key=ABC123&nwait=0&nnext=0';
```

Create `tests/fixtures/search_success.json`:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"IRG000000","strResult":"SUCC","qryCnqeCnt":"1"}],"dsOutput1":[{"trnNo":"303","trnGpCd":"300","stlbTrnClsfCd":"17","runDt":"20260710","dptDt":"20260710","dptTm":"060000","arvDt":"20260710","arvTm":"083000","dptRsStnCd":"0551","arvRsStnCd":"0020"}]}}
```

Create `tests/fixtures/group_search_success.json`:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":{"msgCd":"IRG000000","strResult":"SUCC","qryCnqeCnt":"1"},"dsOutput1":[{"trnNo":"301","trnGpCd":"300","stlbTrnClsfCd":"17","runDt":"20260710","dptDt":"20260710","dptTm":"053000","arvDt":"20260710","arvTm":"080000","dptRsStnCd":"0551","arvRsStnCd":"0020"}]}}
```

Create `tests/fixtures/search_empty.json`:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"IRG000000","strResult":"SUCC","qryCnqeCnt":"0"}],"dsOutput1":[]}}
```

Create `tests/fixtures/search_netfunnel_failure.json`:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"NET000001","strResult":"FAIL","msgTxt":"NetFunnel key required"}],"dsOutput1":[]}}
```

Create `tests/test_netfunnel_payloads_parsers.py`:

```python
from srt_mobile_api.models import PassengerCounts, TrainSearchQuery
from srt_mobile_api.netfunnel import parse_netfunnel_response
from srt_mobile_api.parsers import parse_train_search_response
from srt_mobile_api.payloads import group_search_ajax_payload, search_ajax_payload, search_page_payload


def test_parse_netfunnel_response_extracts_key(load_text_fixture):
    token = parse_netfunnel_response(load_text_fixture("netfunnel_act10.js"), action="act_10")
    assert token.action == "act_10"
    assert token.code == "5101"
    assert token.key == "ABC123"


def test_search_payloads_include_expected_keys():
    query = TrainSearchQuery("0551", "0020", "20260710", passengers=PassengerCounts(adult=1))
    page_payload = search_page_payload(query, "수서", "부산", "NF")
    ajax_payload = search_ajax_payload(query, "NF")
    group_payload = group_search_ajax_payload(query, "NF")

    assert page_payload["dptRsStnCd1"] == "0551"
    assert page_payload["arvRsStnCdNm1"] == "부산"
    assert ajax_payload["netfunnelKey"] == "NF"
    assert ajax_payload["psgNum"] == "1"
    assert group_payload["psgNum"] == "10"
    assert group_payload["grpDv"] == "1"


def test_parse_train_search_response_normalizes_list_and_object_result(load_json_fixture):
    result = parse_train_search_response(load_json_fixture("search_success.json"))
    group = parse_train_search_response(load_json_fixture("group_search_success.json"))
    empty = parse_train_search_response(load_json_fixture("search_empty.json"))

    assert result.result["msgCd"] == "IRG000000"
    assert result.trains[0].train_no == "303"
    assert group.trains[0].train_no == "301"
    assert empty.trains == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_netfunnel_payloads_parsers.py -q`

Expected: FAIL because modules/functions are missing.

- [ ] **Step 3: Implement NetFunnel, payloads, and train parser**

Create `src/srt_mobile_api/netfunnel.py`:

```python
import re

from .errors import SrtNetFunnelError
from .models import NetFunnelToken


def parse_netfunnel_response(body: str, *, action: str) -> NetFunnelToken:
    match = re.search(r"'([^']*(?:5101|5002):[^']*)'", body)
    if not match:
        match = re.search(r'"([^"]*(?:5101|5002):[^"]*)"', body)
    if not match:
        raise SrtNetFunnelError("NetFunnel response did not include a result token")
    value = match.group(1)
    token_part = value.rsplit(";", 1)[-1]
    parts = token_part.split(":", 2)
    raw_type = parts[0] if parts else ""
    if len(parts) == 2:
        code = raw_type
        param_text = parts[1]
    elif len(parts) >= 3:
        code = parts[1]
        param_text = parts[2]
    else:
        code = ""
        param_text = ""
    params: dict[str, str] = {}
    for item in param_text.split("&"):
        if "=" in item:
            key, val = item.split("=", 1)
            params[key] = val
    return NetFunnelToken(action=action, key=params.get("key", ""), raw_type=raw_type, code=code, params=params)
```

Create `src/srt_mobile_api/payloads.py`:

```python
from .models import PassengerCounts, TrainSearchQuery, TrainSummary


def search_page_payload(query: TrainSearchQuery, depart_name: str, arrive_name: str, netfunnel_key: str) -> dict[str, str]:
    payload = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": "05",
        "stndFlg": "N",
        "jrnySqno1": "001",
        "trnGpCd1": query.train_group_code,
        "trnGpNm1": "전체",
        "dptRsStnCd1": query.departure_station_code,
        "dptRsStnCdNm1": depart_name,
        "arvRsStnCd1": query.arrival_station_code,
        "arvRsStnCdNm1": arrive_name,
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "totPrnb": str(query.passengers.total),
        "totPrnbNm": f"{query.passengers.total}명",
        "psgGridcnt": str(query.passengers.total),
        "psgTpCd1": "1",
        "psgInfoPerPrnb1": str(query.passengers.adult),
        "seatAttCd": query.seat_attr_code,
        "netfunnelKey": netfunnel_key,
        "adjStnScdlOfrFlg": "N",
    }
    for key in ["jrnySqno2", "trnGpCd2", "trnGpNm2", "arvDt1", "arvTm1", "pnrNo", "JRNYLIST_KEY"]:
        payload.setdefault(key, "")
    for leg in (1, 2):
        for idx in range(1, 10):
            payload[f"seatNo{leg}_{idx}"] = ""
    return payload


def search_ajax_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    return {
        "chtnDvCd": "1",
        "dptDt": query.departure_date,
        "dptTm": query.departure_time,
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "dptRsStnCd": query.departure_station_code,
        "arvRsStnCd": query.arrival_station_code,
        "stlbTrnClsfCd": "05",
        "trnGpCd": query.train_group_code,
        "trnNo": "",
        "psgNum": str(query.passengers.total),
        "seatAttCd": query.seat_attr_code,
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


def group_search_ajax_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    payload = search_ajax_payload(query, netfunnel_key)
    payload["grpDv"] = "1"
    payload["psgNum"] = str(max(query.passengers.total, 10))
    return payload
```

Modify `src/srt_mobile_api/parsers.py`:

```python
from .models import TrainSearchResult, TrainSummary


def parse_train_search_response(data: dict[str, Any]) -> TrainSearchResult:
    result = normalize_result_row(data)
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_netfunnel_payloads_parsers.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/srt_mobile_api tests/fixtures tests/test_netfunnel_payloads_parsers.py
git commit -m "feat: add srt payload and parser core"
```

---

### Task 4: Login Session Support

**Files:**
- Create: `src/srt_mobile_api/session.py`
- Modify: `src/srt_mobile_api/client.py`
- Create: `tests/fixtures/login_success.json`
- Create: `tests/fixtures/login_failure.json`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `SrtHttpClient`, `SrtSession`.
- Produces: `SrtSessionClient.login()`, `SrtClient.login()`, `SrtClient.logout()`, `SrtClient.clear_session()`.

- [ ] **Step 1: Write failing session tests**

Create `tests/fixtures/login_success.json`:

```json
{"userMap":{"RTNCD":"Y","MSG":"로그인 성공","CUST_NM":"TEST"}}
```

Create `tests/fixtures/login_failure.json`:

```json
{"userMap":{"RTNCD":"N","MSG":"로그인 실패"}}
```

Create `tests/test_session.py`:

```python
import httpx

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtAuthError


def test_login_flow_posts_expected_fields(load_json_fixture):
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.method, request.url.path, request.content.decode()))
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        if request.url.path == "/main/main.do":
            return httpx.Response(200, text="<html>main</html>")
        if request.url.path == "/ara/ara0101v.do":
            return httpx.Response(200, text="<html>booking</html>")
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    session = client.login("login-id", "pw")

    assert session.login_id == "login-id"
    login_body = captured[1][2]
    assert "srchDvCd=3" in login_body
    assert "srchDvNm=login-id" in login_body
    assert "hmpgPwdCphd=pw" in login_body


def test_login_failure_raises_auth_error(load_json_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, json=load_json_fixture("login_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    try:
        client.login("login-id", "pw")
    except SrtAuthError as exc:
        assert "로그인 실패" in str(exc)
    else:
        raise AssertionError("SrtAuthError was not raised")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -q`

Expected: FAIL because login/session implementation is missing.

- [ ] **Step 3: Implement session and facade wiring**

Create `src/srt_mobile_api/session.py`:

```python
from .errors import SrtAuthError, SrtProtocolError
from .http import SrtHttpClient
from .models import SrtSession


class SrtSessionClient:
    def __init__(self, http: SrtHttpClient) -> None:
        self.http = http
        self.current: SrtSession | None = None

    def login(self, login_id: str, password: str, *, login_type: str = "3") -> SrtSession:
        self.http.get_text("/login/login.do")
        response = self.http.post_form(
            "/apb/selectListApb01080_n.do",
            {
                "srchDvCd": login_type,
                "srchDvNm": login_id,
                "check": "",
                "auto": "",
                "login_referer": "",
                "hmpgPwdCphd": password,
                "deviceKey": self.http.config.device_key,
                "page": "",
                "customerYn": "",
                "ciUptYn": "",
                "dupInfoVal": "",
            },
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.http.config.base_url}/login/login.do",
        )
        user_map = response.get("userMap")
        if not isinstance(user_map, dict):
            raise SrtProtocolError("SRT login response missing userMap")
        if user_map.get("RTNCD") != "Y":
            raise SrtAuthError(str(user_map.get("MSG") or "SRT login failed"))
        self.http.get_text("/main/main.do", params={"deviceId": self.http.config.device_key})
        self.http.get_text("/ara/ara0101v.do")
        self.current = SrtSession(login_id=login_id, user_map=user_map)
        return self.current

    def clear_session(self) -> None:
        self.http.cookies.clear()
        self.current = None
```

Modify `src/srt_mobile_api/client.py`:

```python
import httpx

from .config import SrtConfig
from .http import SrtHttpClient
from .models import SrtSession
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -q`

Expected: PASS.

- [ ] **Step 5: Run existing tests**

Run: `pytest tests/test_models.py tests/test_http.py tests/test_redaction_safety.py tests/test_netfunnel_payloads_parsers.py tests/test_session.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/srt_mobile_api tests/fixtures/login_success.json tests/fixtures/login_failure.json tests/test_session.py
git commit -m "feat: add srt login session support"
```

---

### Task 5: Read-Only Facade APIs

**Files:**
- Modify: `src/srt_mobile_api/client.py`
- Modify: `src/srt_mobile_api/http.py`
- Create: `tests/fixtures/fare.html`
- Create: `tests/fixtures/notice_list.json`
- Create: `tests/fixtures/ticket_list.html`
- Create: `tests/fixtures/timetable.html`
- Test: `tests/test_client_read_apis.py`

**Interfaces:**
- Consumes: `SrtClient`, payload builders, parsers, `TrainSearchQuery`, `TrainSummary`.
- Produces: public read methods from the approved SRT design.

- [ ] **Step 1: Write failing read API tests**

Create `tests/fixtures/notice_list.json`:

```json
{"noticeList":[{"title":"공지"}]}
```

Create `tests/fixtures/ticket_list.html`:

```html
<html><body><h1>승차권</h1><p>조회자료가 없습니다.</p></body></html>
```

Create `tests/fixtures/timetable.html`:

```html
<html><body><table><tr><td>수서</td><td>06:00</td></tr><tr><td>부산</td><td>08:30</td></tr></table></body></html>
```

Create `tests/fixtures/fare.html`:

```html
<html><body><table><tr><td>어른 일반실</td><td>51,900원</td></tr></table></body></html>
```

Create `tests/test_client_read_apis.py`:

```python
import httpx

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.models import TrainSearchQuery, TrainSummary


def test_read_pages_and_notice(load_json_fixture, load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/main/main.do":
            return httpx.Response(200, text="<html>main</html>")
        if request.url.path == "/ara/ara0101v.do":
            return httpx.Response(200, text="<html>booking</html>")
        if request.url.path == "/main/noticeList.do":
            return httpx.Response(200, json=load_json_fixture("notice_list.json"))
        if request.url.path == "/atc/selectListAtc14017_n.do":
            return httpx.Response(200, text=load_text_fixture("ticket_list.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    assert "main" in client.get_main().raw
    assert "booking" in client.get_booking_page().raw
    assert client.get_notice_list()["noticeList"][0]["title"] == "공지"
    assert "승차권" in client.get_ticket_list().text


def test_search_uses_act10_and_search_endpoint(load_json_fixture, load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text=load_text_fixture("netfunnel_act10.js"))
        if request.url.path == "/ara/selectListAra10007_n.do" and request.method == "POST":
            return httpx.Response(200, json=load_json_fixture("search_success.json"))
        if request.url.path == "/ara/selectListAra10082_n.do":
            return httpx.Response(200, json=load_json_fixture("group_search_success.json"))
        if request.url.path == "/ara/selectListAra10007_n.do":
            return httpx.Response(200, text="<html>searchForm</html>")
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    query = TrainSearchQuery("0551", "0020", "20260710")
    result = client.search_trains(query)
    group = client.search_group_trains(query)
    assert result.trains[0].train_no == "303"
    assert group.trains[0].train_no == "301"


def test_timetable_and_fare(load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ara/selectListAra12009_n.do":
            return httpx.Response(200, text=load_text_fixture("timetable.html"))
        if request.url.path == "/ara/selectListAra13010_n.do":
            return httpx.Response(200, text=load_text_fixture("fare.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    train = TrainSummary(train_no="303", train_group_code="300", service_class_code="17", run_date="20260710", departure_date="20260710", departure_time="060000", departure_station_code="0551", arrival_station_code="0020")
    assert "06:00" in client.get_timetable(train).text
    assert "51,900원" in client.get_fare(train).text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_client_read_apis.py -q`

Expected: FAIL because facade read methods are missing.

- [ ] **Step 3: Implement read-only facade methods**

Modify `src/srt_mobile_api/http.py` to allow absolute NetFunnel URL requests:

```python
    def get_text_url(self, url: str, *, referer: str | None = None) -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return response.text
```

Modify `src/srt_mobile_api/client.py`:

```python
import time

from .models import HtmlPage, PassengerCounts, TrainSearchQuery, TrainSearchResult, TrainSummary
from .netfunnel import parse_netfunnel_response
from .parsers import extract_text, parse_train_search_response
from .payloads import group_search_ajax_payload, search_ajax_payload, search_page_payload

    def get_main(self) -> HtmlPage:
        raw = self.http.get_text("/main/main.do", params={"deviceId": self.config.device_key})
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_booking_page(self) -> HtmlPage:
        raw = self.http.get_text("/ara/ara0101v.do")
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_notice_list(self) -> dict:
        return self.http.post_form("/main/noticeList.do", {"pageId": "MB0101000000"}, accept="application/json, text/javascript, */*; q=0.01")

    def get_ticket_list(self, page_no: int = 0) -> HtmlPage:
        raw = self.http.get_text("/atc/selectListAtc14017_n.do", params={"pageNo": str(page_no)})
        return HtmlPage(text=extract_text(raw), raw=raw)

    def _get_act10_key(self, referer: str) -> str:
        stamp = int(time.time() * 1000)
        url = f"{self.config.netfunnel_url}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true&{stamp}"
        body = self.http.get_text_url(url, referer=referer)
        return parse_netfunnel_response(body, action="act_10").key

    def search_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        key = self._get_act10_key(f"{self.config.base_url}/ara/ara0101v.do")
        page_params = search_page_payload(query, query.departure_station_code, query.arrival_station_code, key)
        self.http.get_text("/ara/selectListAra10007_n.do", params=page_params, referer=f"{self.config.base_url}/ara/ara0101v.do")
        data = self.http.post_form(
            "/ara/selectListAra10007_n.do",
            search_ajax_payload(query, key),
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
        )
        return parse_train_search_response(data)

    def search_group_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        key = self._get_act10_key(f"{self.config.base_url}/ara/selectListAra10007_n.do")
        data = self.http.post_form(
            "/ara/selectListAra10082_n.do",
            group_search_ajax_payload(query, key),
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
        )
        return parse_train_search_response(data)

    def get_timetable(self, train: TrainSummary) -> HtmlPage:
        raw = self.http.post_form(
            "/ara/selectListAra12009_n.do",
            {"stnCourseNm": "", "trnSort": "SRT" if train.service_class_code == "17" else train.service_class_code or "", "runDt": train.run_date or train.departure_date or "", "trnNo": train.train_no.zfill(5)},
            accept="text/html, */*; q=0.01",
        )["html"]
        return HtmlPage(text=extract_text(raw), raw=raw)

    def get_fare(self, train: TrainSummary, passengers: PassengerCounts | None = None) -> HtmlPage:
        passengers = passengers or PassengerCounts()
        raw = self.http.post_form(
            "/ara/selectListAra13010_n.do",
            {"stnCourseNm": "", "trnSort": "SRT" if train.service_class_code == "17" else train.service_class_code or "", "runDt": train.run_date or train.departure_date or "", "trnNo": train.train_no.zfill(5), "chtnDvCd": "1", "dptRsStnCd1": train.departure_station_code or "", "arvRsStnCd1": train.arrival_station_code or "", "runDt1": train.run_date or train.departure_date or "", "trnNo1": train.train_no.zfill(5), "psgTpCd1": "1", "psgInfoPerPrnb1": str(passengers.adult)},
            accept="text/html, */*; q=0.01",
        )["html"]
        return HtmlPage(text=extract_text(raw), raw=raw)
```

- [ ] **Step 4: Run read API tests**

Run: `pytest tests/test_client_read_apis.py -q`

Expected: PASS.

- [ ] **Step 5: Run all tests**

Run: `pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/srt_mobile_api tests/fixtures tests/test_client_read_apis.py
git commit -m "feat: add srt read api facade"
```

---

### Task 6: Live Smoke Boundary And Documentation

**Files:**
- Create: `src/srt_mobile_api/live.py`
- Create: `tests/test_live.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: `SrtClient`, `SrtConfig`.
- Produces: `run_live_smoke_from_env()` and user-facing docs for safe live execution.

- [ ] **Step 1: Write failing live boundary tests**

Create `tests/test_live.py`:

```python
from srt_mobile_api.live import live_enabled, read_credentials_from_env


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SRT_MOBILE_API_LIVE", raising=False)
    assert live_enabled() is False


def test_live_enabled_only_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    assert live_enabled() is True


def test_credentials_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("SRT_LOGIN_ID", "member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", "pw")
    assert read_credentials_from_env() == ("member", "pw")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_live.py -q`

Expected: FAIL because `live.py` is missing.

- [ ] **Step 3: Implement live boundary**

Create `src/srt_mobile_api/live.py`:

```python
from __future__ import annotations

import os
from typing import Any

from .client import SrtClient
from .config import SrtConfig


def live_enabled() -> bool:
    return os.environ.get("SRT_MOBILE_API_LIVE") == "1"


def read_credentials_from_env() -> tuple[str, str]:
    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        raise RuntimeError("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required for live smoke")
    return login_id, password


def run_live_smoke_from_env() -> dict[str, Any]:
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    client = SrtClient(SrtConfig())
    try:
        session = client.login(login_id, password)
        notice = client.get_notice_list()
        tickets = client.get_ticket_list()
        return {
            "loggedIn": bool(session.user_map),
            "noticeCount": len(notice.get("noticeList") or []),
            "ticketTextPrefix": tickets.text[:80],
        }
    finally:
        client.close()
```

Modify `README.md` by adding:

```markdown
## Python Package MVP

This repository now contains an installable Python client package under `src/srt_mobile_api`.

Default tests are offline:

```bash
pip install -e ".[test]"
pytest
```

Live smoke is opt-in and limited to login plus read/query calls:

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
python -c "from srt_mobile_api.live import run_live_smoke_from_env; print(run_live_smoke_from_env())"
```

Reservation, payment, refund, cancellation, ARD, ATA, and native bridge flows are not implemented in this package version.
```

- [ ] **Step 4: Run live boundary tests**

Run: `pytest tests/test_live.py -q`

Expected: PASS.

- [ ] **Step 5: Run full verification**

Run:

```bash
pytest -q
python -c "from srt_mobile_api import SrtClient, SrtConfig; print(SrtClient(SrtConfig()).config.base_url)"
```

Expected: all tests PASS and command prints `https://app.srail.or.kr`.

- [ ] **Step 6: Commit**

```bash
git add README.md src/srt_mobile_api/live.py tests/test_live.py
git commit -m "feat: add srt live smoke boundary"
```
