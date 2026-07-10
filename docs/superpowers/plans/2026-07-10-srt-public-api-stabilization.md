# SRT Public API Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every currently exposed SRT read-only client method match the observed WebView and live-server contracts without adding new endpoint methods.

**Architecture:** Keep `SrtClient` as the facade, route every app and NetFunnel request through an exact read-only policy, and keep login/search state per client instance. Preserve existing `raw` and `text` access while adding strict JSON contracts, hydrated search forms, one bounded NetFunnel retry, and `HtmlPage`-compatible structured timetable/fare results.

**Tech Stack:** Python 3.11+, `httpx>=0.27,<1`, frozen dataclasses, the standard-library `HTMLParser`, `pytest>=8,<10`, setuptools.

## Global Constraints

- Work from the current working tree and do not revert files changed by another worker.
- Stage and commit only the paths named by the current task.
- Keep Python support at `>=3.11` and add no runtime dependency.
- Do not add seat selection, selector popup, reservation, `act_19`, payment, cancellation, refund, ATA, ARD, native bridge, or external seat-map endpoint methods.
- Keep existing public method names and ordinary calling forms.
- Keep existing `raw` and `text` access; specialized page models must subclass `HtmlPage`.
- Default tests must be offline and must use `httpx.MockTransport`.
- Live credentials come only from shell environment loaded from ignored `.local-live-smoke.env`.
- A failed or malformed JSON envelope must never become an empty successful train result.
- Only `NET000001` is retried, with one fresh `act_10` key and a complete repeated search flow.
- Do not invent an undocumented SRT session-expiry JSON code. Classify only a redirect to the login path or a returned login form as expired.
- Preserve every named input from the hydrated search page. If duplicate names appear, the final occurrence wins in the mapping, matching the current dict-based payload API.
- Passenger type codes are explicit protocol constants: adult `1`, child `5`, senior `4`, disability grades 1-3 `2`, disability grades 4-6 `3`, infant `6`. Preserve a non-empty hydrated code and use these constants for positive caller counts.
- Unsafe low-level requests raise `SrtProtocolError` before network I/O.
- Follow TDD: add one focused failing test, confirm the expected failure, implement the minimum behavior, rerun the focused test, then run the affected suite.

---

## File Structure

Files created by this plan:

- `tests/fixtures/search_page.html`: hydrated form with known and unknown inputs.
- `tests/test_safety.py`: exact app/NetFunnel route and bypass tests.
- `tests/test_smoke_script.py`: static and mock verification that the legacy runner is read-only.
- `tests/test_public_contract.py`: final public surface gate.
- `tests/test_live_service.py`: explicitly opted-in live read-only gate.

Existing files modified by this plan:

- `src/srt_mobile_api/__init__.py`: export completed errors and result models.
- `src/srt_mobile_api/client.py`: orchestrate transactional search and structured detail results.
- `src/srt_mobile_api/config.py`: validate immutable host/device settings.
- `src/srt_mobile_api/errors.py`: expose transport, protocol, app, auth, expiry, and NetFunnel errors.
- `src/srt_mobile_api/http.py`: unify request sending, route checks, redirects, and framing.
- `src/srt_mobile_api/live.py`: run every current safe read without raw output.
- `src/srt_mobile_api/models.py`: validate inputs and add hydrated/structured result models.
- `src/srt_mobile_api/netfunnel.py`: build and parse exact `act_10` requests.
- `src/srt_mobile_api/parsers.py`: validate pages/search JSON and parse timetable/fare tables.
- `src/srt_mobile_api/payloads.py`: preserve hydrated fields and build exact search/detail forms.
- `src/srt_mobile_api/redaction.py`: recursively redact values, URLs, and dataclasses.
- `src/srt_mobile_api/safety.py`: define and enforce method/host/path read-only routes.
- `src/srt_mobile_api/session.py`: make login a commit/rollback transaction.
- `scripts/srt_app_api_smoke.py`: become a thin wrapper over the safe library helper.
- `tests/test_client_read_apis.py`, `tests/test_http.py`, `tests/test_live.py`, `tests/test_models.py`, `tests/test_netfunnel_payloads_parsers.py`, `tests/test_redaction_safety.py`, `tests/test_session.py`: lock corrected contracts.
- `.gitignore` and `README.md`: protect local credentials and document safe execution.

---

### Task 1: Core Error, Configuration, And Input Model Contracts

**Files:**
- Modify: `src/srt_mobile_api/config.py`
- Modify: `src/srt_mobile_api/errors.py`
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/__init__.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: current frozen configuration and dataclass request/result models.
- Produces: `SrtSessionExpiredError`, field-carrying `SrtNetFunnelError`, validated `SrtConfig`/`PassengerCounts`/`TrainSearchQuery`, optional station names, and safe model representations.

- [ ] **Step 1: Add failing hierarchy and input validation tests**

```python
import pytest

from srt_mobile_api.errors import SrtAuthError, SrtNetFunnelError, SrtSessionExpiredError
from srt_mobile_api.models import PassengerCounts, TrainSearchQuery


def test_completed_error_hierarchy_is_public():
    assert issubclass(SrtSessionExpiredError, SrtAuthError)
    error = SrtNetFunnelError("NET000001", "refresh required")
    assert error.code == "NET000001"
    assert error.message == "refresh required"


def test_passenger_counts_reject_empty_or_negative_totals():
    with pytest.raises(ValueError):
        PassengerCounts(adult=0)
    with pytest.raises(ValueError):
        PassengerCounts(adult=-1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"departure_station_code": "", "arrival_station_code": "0020", "departure_date": "20260710"},
        {"departure_station_code": "0551", "arrival_station_code": "", "departure_date": "20260710"},
        {"departure_station_code": "0551", "arrival_station_code": "0020", "departure_date": "2026-07-10"},
        {
            "departure_station_code": "0551",
            "arrival_station_code": "0020",
            "departure_date": "20260710",
            "departure_time": "60000",
        },
        {
            "departure_station_code": "0551",
            "arrival_station_code": "0020",
            "departure_date": "20260710",
            "train_group_code": "unknown",
        },
    ],
)
def test_search_query_rejects_invalid_contract(kwargs):
    with pytest.raises(ValueError):
        TrainSearchQuery(**kwargs)
```

- [ ] **Step 2: Run the focused model tests**

Run: `pytest tests/test_models.py -q`

Expected: FAIL because the expiry error and validation hooks do not exist.

- [ ] **Step 3: Implement validated configuration and caller inputs**

Add:

```python
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SrtConfig:
    base_url: str = "https://app.srail.or.kr"
    netfunnel_url: str = "https://nf.letskorail.com:443"
    user_agent: str = DEFAULT_UA
    device_key: str = "0123456789ABCDEF"
    timeout: float = 20.0
    live_env_var: str = "SRT_MOBILE_API_LIVE"

    def __post_init__(self) -> None:
        for name in ("base_url", "netfunnel_url"):
            parsed = urlsplit(getattr(self, name))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"{name} must be an absolute HTTP URL")
        if not self.device_key:
            raise ValueError("device_key must not be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
```

Add model validation while preserving field order and defaults:

```python
@dataclass(frozen=True)
class PassengerCounts:
    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0
    infant: int = 0

    def __post_init__(self) -> None:
        values = (
            self.adult,
            self.child,
            self.senior,
            self.disability_1_to_3,
            self.disability_4_to_6,
            self.infant,
        )
        if any(not isinstance(value, int) or value < 0 for value in values):
            raise ValueError("passenger counts must be non-negative integers")
        if sum(values) < 1:
            raise ValueError("at least one passenger is required")

    @property
    def total(self) -> int:
        return (
            self.adult
            + self.child
            + self.senior
            + self.disability_1_to_3
            + self.disability_4_to_6
            + self.infant
        )


@dataclass(frozen=True)
class TrainSearchQuery:
    departure_station_code: str
    arrival_station_code: str
    departure_date: str
    departure_time: str = "060000"
    passengers: PassengerCounts = field(default_factory=PassengerCounts)
    train_group_code: str = "900"
    seat_attr_code: str = "015"
    departure_station_name: str | None = None
    arrival_station_name: str | None = None

    def __post_init__(self) -> None:
        if not self.departure_station_code.strip() or not self.arrival_station_code.strip():
            raise ValueError("departure and arrival station codes are required")
        if len(self.departure_date) != 8 or not self.departure_date.isdigit():
            raise ValueError("departure_date must use YYYYMMDD")
        if len(self.departure_time) != 6 or not self.departure_time.isdigit():
            raise ValueError("departure_time must use HHMMSS")
        if self.train_group_code not in {"300", "900", "109"}:
            raise ValueError("train_group_code must be one of 300, 900, or 109")
```

- [ ] **Step 4: Implement completed error objects and exports**

Keep the existing base classes and use:

```python
class SrtSessionExpiredError(SrtAuthError):
    def __init__(self, message: str = "SRT session expired", *, raw: object | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class SrtNetFunnelError(SrtApiError):
    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        raw: object | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{code or 'NETFUNNEL'}: {message or 'NetFunnel request failed'}")
```

Export `SrtAppError`, `SrtTransportError`, `SrtNetFunnelError`, and `SrtSessionExpiredError` from `__init__.py` without removing current exports.

- [ ] **Step 5: Exclude secrets/raw payloads from model repr**

Apply these exact field definitions to their owning models:

```python
class SrtSession:
    login_id: str | None = field(default=None, repr=False)
    user_map: dict[str, Any] = field(default_factory=dict, repr=False)


class NetFunnelToken:
    key: str = field(repr=False)
    params: dict[str, str] = field(default_factory=dict, repr=False)


class TrainSummary:
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class TrainSearchResult:
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


class HtmlPage:
    raw: str = field(repr=False)
```

Add `departure_station_name` and `arrival_station_name` to `TrainSummary` before its `raw` field.

- [ ] **Step 6: Run model tests**

Run: `pytest tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 7: Commit only Task 1 files**

```bash
git add src/srt_mobile_api/config.py src/srt_mobile_api/errors.py src/srt_mobile_api/models.py src/srt_mobile_api/__init__.py tests/test_models.py
git commit -m "fix: validate srt core contracts"
```

---

### Task 2: Recursive Redaction And Secret-Safe Exceptions

**Files:**
- Modify: `src/srt_mobile_api/redaction.py`
- Modify: `src/srt_mobile_api/errors.py`
- Test: `tests/test_redaction_safety.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: Task 1 model and error fields.
- Produces: `redact_value(value, *, key=None) -> Any`, `redact_url(value: str) -> str`, recursive `redact_mapping`, and sanitized exception strings.

- [ ] **Step 1: Add failing recursive, URL, model, and exception tests**

```python
from srt_mobile_api.errors import SrtAppError, SrtNetFunnelError
from srt_mobile_api.models import NetFunnelToken, SrtSession
from srt_mobile_api.redaction import redact_mapping, redact_url


def test_recursive_redaction_is_case_insensitive():
    redacted = redact_mapping(
        {
            "outer": [
                {
                    "HMPGPWDCphd": "password-secret",
                    "url": "https://host/path?netfunnelKey=key-secret&safe=1",
                }
            ]
        }
    )
    assert redacted["outer"][0]["HMPGPWDCphd"] == "[REDACTED]"
    assert "key-secret" not in redacted["outer"][0]["url"]
    assert "safe=1" in redacted["outer"][0]["url"]


def test_secrets_do_not_appear_in_model_or_exception_repr():
    token = NetFunnelToken("act_10", "key-secret", "5101", "5101")
    session = SrtSession("login-secret", {"cookie": "cookie-secret"})
    app_error = SrtAppError("ERR", "card 4111-1111-1111-1111")
    net_error = SrtNetFunnelError("NET000001", "https://host/path?netfunnelKey=key-secret")
    assert "key-secret" not in repr(token)
    assert "login-secret" not in repr(session)
    assert "4111" not in str(app_error)
    assert "key-secret" not in str(net_error)
```

- [ ] **Step 2: Run redaction tests**

Run: `pytest tests/test_redaction_safety.py tests/test_models.py -q`

Expected: FAIL because redaction is shallow and exception messages are unsanitized.

- [ ] **Step 3: Implement recursive value and URL redaction**

Replace `redaction.py` with:

```python
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEYS = frozenset(
    key.casefold()
    for key in {
        "srchDvNm",
        "hmpgPwdCphd",
        "password",
        "cookie",
        "set-cookie",
        "JSESSIONID",
        "netfunnelKey",
        "key",
        "pnrNo",
    }
)
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
SESSION_RE = re.compile(r"(?i)(JSESSIONID=)[^&;\s]+")


def redact_text(value: str) -> str:
    return SESSION_RE.sub(r"\1[REDACTED]", CARD_RE.sub("[REDACTED_CARD]", value))


def redact_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return redact_text(value)
    query = [
        (name, "[REDACTED]" if name.casefold() in SENSITIVE_KEYS else redact_text(item))
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.casefold() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {name: redact_value(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: redact_value(getattr(value, field.name), key=field.name) for field in fields(value)}
    if isinstance(value, str):
        return redact_url(value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {name: redact_value(item, key=str(name)) for name, item in data.items()}
```

- [ ] **Step 4: Sanitize application and NetFunnel exception messages**

Import `redact_text` and `redact_url` in `errors.py`. Build `SrtAppError` messages with `redact_text(message or "")` and `SrtNetFunnelError` messages with `redact_url(message or "NetFunnel request failed")`.

- [ ] **Step 5: Run focused tests**

Run: `pytest tests/test_redaction_safety.py tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 6: Commit only Task 2 files**

```bash
git add src/srt_mobile_api/redaction.py src/srt_mobile_api/errors.py tests/test_redaction_safety.py tests/test_models.py
git commit -m "fix: redact srt secrets recursively"
```

---

### Task 3: Exact Read-Only Route Policy And Unified HTTP Transport

**Files:**
- Modify: `src/srt_mobile_api/safety.py`
- Modify: `src/srt_mobile_api/http.py`
- Modify: `tests/test_http.py`
- Create: `tests/test_safety.py`

**Interfaces:**
- Consumes: `SrtConfig` and Task 1/2 errors.
- Produces: `ReadOnlyRoute`, `READ_ONLY_ROUTES`, `assert_read_only_request(method: str, url: httpx.URL, config: SrtConfig) -> None`, and `SrtHttpClient._request(method: str, url: str, *, params: Mapping[str, Any] | None = None, data: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None) -> httpx.Response`.

- [ ] **Step 1: Add failing app-route, NetFunnel, and bypass tests**

```python
import httpx
import pytest

from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtProtocolError
from srt_mobile_api.safety import assert_read_only_request


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/login/login.do"),
        ("POST", "/apb/selectListApb01080_n.do"),
        ("GET", "/main/main.do"),
        ("GET", "/ara/ara0101v.do"),
        ("POST", "/main/noticeList.do"),
        ("GET", "/atc/selectListAtc14017_n.do"),
        ("GET", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10082_n.do"),
        ("POST", "/ara/selectListAra12009_n.do"),
        ("POST", "/ara/selectListAra13010_n.do"),
    ],
)
def test_current_app_routes_are_allowed(method, path):
    config = SrtConfig()
    assert_read_only_request(method, httpx.URL(config.base_url + path), config)


def test_only_exact_act10_netfunnel_url_is_allowed():
    config = SrtConfig()
    allowed = httpx.URL(
        config.netfunnel_url
        + "/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        + "&sid=service_1&aid=act_10&js=true&1712345678901"
    )
    assert_read_only_request("GET", allowed, config)
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            "GET",
            httpx.URL(config.netfunnel_url + "/ts.wseq?opcode=5101&sid=service_1&aid=act_19&js=true"),
            config,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/main/main.do",
        "https://app.srail.or.kr/arc/selectListArc05013_n.do",
        "https://app.srail.or.kr/ard/selectListArd02017_n.do",
        "https://app.srail.or.kr/%61rc/selectListArc05013_n.do",
    ],
)
def test_off_host_and_mutation_routes_are_rejected(url):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request("POST", httpx.URL(url), SrtConfig())
```

- [ ] **Step 2: Add a zero-I/O HTTP safety test**

```python
def test_http_rejects_unknown_route_before_transport():
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"ok": True})

    client = SrtHttpClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtProtocolError):
        client.post_form("/arc/selectListArc05013_n.do", {})
    assert called is False
```

Update current `/example.do` HTTP tests to use registered routes such as `/main/noticeList.do` for JSON POST and `/main/main.do` for GET.

- [ ] **Step 3: Run HTTP and safety tests**

Run: `pytest tests/test_http.py tests/test_safety.py -q`

Expected: FAIL because all four HTTP helpers currently bypass safety.

- [ ] **Step 4: Define method/host/path route metadata**

Replace descriptive-only safety with:

```python
from dataclasses import dataclass
from urllib.parse import unquote

import httpx

from .config import SrtConfig
from .errors import SrtProtocolError


@dataclass(frozen=True)
class ReadOnlyRoute:
    method: str
    host_kind: str
    path: str


READ_ONLY_ROUTES = frozenset(
    {
        ReadOnlyRoute("GET", "app", "/login/login.do"),
        ReadOnlyRoute("POST", "app", "/apb/selectListApb01080_n.do"),
        ReadOnlyRoute("GET", "app", "/main/main.do"),
        ReadOnlyRoute("GET", "app", "/ara/ara0101v.do"),
        ReadOnlyRoute("POST", "app", "/main/noticeList.do"),
        ReadOnlyRoute("GET", "app", "/atc/selectListAtc14017_n.do"),
        ReadOnlyRoute("GET", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10082_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra12009_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra13010_n.do"),
        ReadOnlyRoute("GET", "netfunnel", "/ts.wseq"),
    }
)


def _same_origin(left: httpx.URL, right: httpx.URL) -> bool:
    return (
        left.scheme,
        left.host,
        left.port or (443 if left.scheme == "https" else 80),
    ) == (
        right.scheme,
        right.host,
        right.port or (443 if right.scheme == "https" else 80),
    )


def assert_read_only_request(method: str, url: httpx.URL, config: SrtConfig) -> None:
    app = httpx.URL(config.base_url)
    netfunnel = httpx.URL(config.netfunnel_url)
    host_kind = "app" if _same_origin(url, app) else "netfunnel" if _same_origin(url, netfunnel) else ""
    path = unquote(url.path)
    route = ReadOnlyRoute(method.upper(), host_kind, path)
    if route not in READ_ONLY_ROUTES:
        raise SrtProtocolError(f"SRT request route is not allowed: {method.upper()} {path}")
    if host_kind == "netfunnel":
        params = dict(url.params.multi_items())
        timestamp_keys = [name for name, value in url.params.multi_items() if name.isdigit() and value == ""]
        required = {
            "opcode": "5101",
            "nfid": "0",
            "prefix": "NetFunnel.gRtype=5101;",
            "sid": "service_1",
            "aid": "act_10",
            "js": "true",
        }
        allowed_names = set(required) | set(timestamp_keys)
        actual_names = {name for name, _value in url.params.multi_items()}
        if (
            any(params.get(name) != value for name, value in required.items())
            or len(timestamp_keys) != 1
            or actual_names != allowed_names
        ):
            raise SrtProtocolError("SRT NetFunnel request is not the registered act_10 contract")
```

- [ ] **Step 5: Route every HTTP helper through one request method**

Implement:

```python
def _request(
    self,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    data: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    request = self._client.build_request(method, url, params=params, data=data, headers=headers)
    assert_read_only_request(method, request.url, self.config)
    try:
        response = self._client.send(request)
    except httpx.HTTPError as exc:
        raise SrtTransportError(f"SRT transport failed for {method.upper()} {request.url.path}") from exc
    if response.is_redirect:
        location = response.headers.get("location", "")
        if "/login/" in location:
            raise SrtSessionExpiredError("SRT session redirected to login")
        raise SrtTransportError(f"SRT HTTP {response.status_code} redirect for {method.upper()} {request.url.path}")
    if response.is_error:
        raise SrtTransportError(f"SRT HTTP {response.status_code} for {method.upper()} {request.url.path}")
    return response
```

Refactor `get_text`, `get_json`, `get_text_url`, and `post_form` to construct their existing headers and call `_request`. Keep their public/internal signatures and JSON-object validation unchanged.

- [ ] **Step 6: Run HTTP and safety tests**

Run: `pytest tests/test_http.py tests/test_safety.py -q`

Expected: PASS and all rejected requests leave the mock transport uncalled.

- [ ] **Step 7: Commit only Task 3 files**

```bash
git add src/srt_mobile_api/safety.py src/srt_mobile_api/http.py tests/test_http.py tests/test_safety.py
git commit -m "fix: enforce srt read only transport"
```

---

### Task 4: Transactional Login And Basic Read Page Contracts

**Files:**
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/session.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `tests/test_session.py`
- Modify: `tests/test_client_read_apis.py`

**Interfaces:**
- Consumes: Task 3 HTTP client and Task 1 session/expiry errors.
- Produces: `parse_html_page(html, *, context, require_authenticated=False) -> HtmlPage`, `parse_notice_list_response(data) -> dict`, and login commit/rollback behavior.

- [ ] **Step 1: Add failing page and notice parser tests**

```python
def test_html_page_rejects_empty_and_login_form_for_authenticated_context():
    with pytest.raises(SrtProtocolError):
        parse_html_page("", context="ticket list")
    with pytest.raises(SrtSessionExpiredError):
        parse_html_page(
            '<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>',
            context="ticket list",
            require_authenticated=True,
        )


def test_notice_requires_notice_list():
    with pytest.raises(SrtProtocolError):
        parse_notice_list_response({})
    with pytest.raises(SrtAppError):
        parse_notice_list_response({"ErrorCode": "NOTICE_ERR", "ErrorMsg": "notice failed"})
    assert parse_notice_list_response({"noticeList": []}) == {"noticeList": []}
```

- [ ] **Step 2: Add a parameterized login rollback test**

```python
@pytest.mark.parametrize(
    "failure_path",
    [
        "/login/login.do",
        "/apb/selectListApb01080_n.do",
        "/main/main.do",
        "/ara/ara0101v.do",
    ],
)
def test_login_rolls_back_cookie_and_current_on_every_step(failure_path, load_json_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failure_path:
            return httpx.Response(503, text="failed")
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        if request.url.path == "/apb/selectListApb01080_n.do":
            return httpx.Response(
                200,
                json=load_json_fixture("login_success.json"),
                headers={"Set-Cookie": "JSESSIONID=new-cookie; Path=/"},
            )
        return httpx.Response(200, text="<html>ok</html>")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.http.cookies.set("JSESSIONID", "old-cookie")
    with pytest.raises(SrtApiError):
        client.login("login-id", "pw")
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies
```

- [ ] **Step 3: Run focused session and parser tests**

Run: `pytest tests/test_session.py tests/test_client_read_apis.py -q`

Expected: FAIL because hydration exceptions leave cookies and page content is not validated.

- [ ] **Step 4: Implement basic page and notice validation**

Add:

```python
def parse_html_page(
    html: str,
    *,
    context: str,
    require_authenticated: bool = False,
) -> HtmlPage:
    if not html.strip():
        raise SrtProtocolError(f"SRT {context} returned an empty HTML body")
    if require_authenticated and "hmpgPwdCphd" in html and "selectListApb01080_n.do" in html:
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
```

- [ ] **Step 5: Make login atomic through final booking hydration**

Replace `SrtSessionClient.login` with:

```python
def login(self, login_id: str, password: str, *, login_type: str = "3") -> SrtSession:
    self.clear_session()
    try:
        parse_html_page(self.http.get_text("/login/login.do"), context="login page")
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
        parse_html_page(
            self.http.get_text("/main/main.do", params={"deviceId": self.http.config.device_key}),
            context="main page",
            require_authenticated=True,
        )
        parse_html_page(
            self.http.get_text("/ara/ara0101v.do"),
            context="booking page",
            require_authenticated=True,
        )
        self.current = SrtSession(login_id=login_id, user_map=user_map)
        return self.current
    except Exception:
        self.clear_session()
        raise
```

- [ ] **Step 6: Use page parsers in every basic read method**

Use `parse_html_page` for `get_main`, `get_booking_page`, and `get_ticket_list`; set `require_authenticated=True` for ticket list. Use `parse_notice_list_response` around `get_notice_list`. Preserve the existing return types (`HtmlPage` and `dict`) and exact request paths.

- [ ] **Step 7: Run session and basic read tests**

Run: `pytest tests/test_session.py tests/test_client_read_apis.py -q`

Expected: PASS.

- [ ] **Step 8: Commit only Task 4 files**

```bash
git add src/srt_mobile_api/parsers.py src/srt_mobile_api/session.py src/srt_mobile_api/client.py tests/test_session.py tests/test_client_read_apis.py
git commit -m "fix: make srt login transactional"
```

---

### Task 5: Exact Act10 Contract And Hydrated Search Payloads

**Files:**
- Modify: `src/srt_mobile_api/netfunnel.py`
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/payloads.py`
- Modify: `src/srt_mobile_api/client.py`
- Create: `tests/fixtures/search_page.html`
- Modify: `tests/test_netfunnel_payloads_parsers.py`
- Modify: `tests/test_client_read_apis.py`

**Interfaces:**
- Consumes: Task 3 safe absolute URL support and validated `TrainSearchQuery`.
- Produces: `build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str`, `SearchPageState`, `parse_search_page_state(html: str) -> SearchPageState`, train-group/passenger constants, and hydrated search builders.

- [ ] **Step 1: Add a hydrated search fixture**

Create:

```html
<html><body><form id="seatSearchForm">
<input type="hidden" name="serverNonce" value="nonce-1">
<input type="hidden" name="dptRsStnCdNm1" value="수서">
<input type="hidden" name="arvRsStnCdNm1" value="부산">
<input type="hidden" name="psgTpCd1" value="1">
<input type="hidden" name="unknownField" value="keep-me">
</form></body></html>
```

- [ ] **Step 2: Add failing deterministic NetFunnel and hydration tests**

```python
def test_build_act10_url_is_deterministic():
    url = build_act10_url("https://nf.letskorail.com:443", timestamp_ms=1712345678901)
    assert "aid=act_10" in url
    assert "sid=service_1" in url
    assert url.endswith("&1712345678901")


def test_search_page_state_preserves_unknown_and_station_name_fields(load_text_fixture):
    state = parse_search_page_state(load_text_fixture("search_page.html"))
    assert state.hidden_fields["serverNonce"] == "nonce-1"
    assert state.hidden_fields["unknownField"] == "keep-me"
    assert state.hidden_fields["dptRsStnCdNm1"] == "수서"


def test_hydrated_ajax_payload_overlays_only_caller_fields(load_text_fixture):
    state = parse_search_page_state(load_text_fixture("search_page.html"))
    query = TrainSearchQuery("0551", "0020", "20260710", train_group_code="300")
    payload = search_ajax_payload(query, "NF", hydrated_fields=state.hidden_fields)
    assert payload["serverNonce"] == "nonce-1"
    assert payload["unknownField"] == "keep-me"
    assert payload["dptRsStnCdNm1"] == "수서"
    assert payload["stlbTrnClsfCd"] == "17"
    assert payload["trnGpCd"] == "300"
```

- [ ] **Step 3: Run focused NetFunnel and payload tests**

Run: `pytest tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py -q`

Expected: FAIL because no search-page model/parser exists and current hydration is discarded.

- [ ] **Step 4: Implement exact act10 URL construction**

Add:

```python
def build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str:
    return (
        f"{netfunnel_url.rstrip('/')}/ts.wseq"
        "?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        f"&sid=service_1&aid=act_10&js=true&{timestamp_ms}"
    )
```

Keep `parse_netfunnel_response(body, action="act_10")`, but raise `SrtNetFunnelError(None, "NetFunnel response did not include a result token", raw=body)` for a missing token and `SrtNetFunnelError(None, "NetFunnel response did not include a non-empty key parameter", raw=body)` for a missing key.

- [ ] **Step 5: Add search-page state and input parsing**

Add to models:

```python
@dataclass(frozen=True)
class SearchPageState:
    hidden_fields: dict[str, str] = field(default_factory=dict)
    raw: str = field(default="", repr=False)
```

Add to parsers:

```python
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
```

- [ ] **Step 6: Implement train-group and passenger field helpers**

Replace payload builders around these constants:

```python
TRAIN_GROUP_OPTIONS = {
    "300": ("SRT", "17"),
    "900": ("KTX+SRT", "00"),
    "109": ("전체", "05"),
}
PASSENGER_SLOTS = (
    ("adult", "1"),
    ("child", "5"),
    ("senior", "4"),
    ("disability_1_to_3", "2"),
    ("disability_4_to_6", "3"),
    ("infant", "6"),
)


def _passenger_fields(
    passengers: PassengerCounts,
    hydrated_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    hydrated_fields = hydrated_fields or {}
    fields: dict[str, str] = {}
    for index, (attribute, type_code) in enumerate(PASSENGER_SLOTS, start=1):
        count = getattr(passengers, attribute)
        hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")
        fields[f"psgTpCd{index}"] = (hydrated_code or type_code) if count else ""
        fields[f"psgInfoPerPrnb{index}"] = str(count)
    fields["infantCnt"] = str(passengers.infant)
    return fields
```

Implement the complete seed page payload:

```python
def search_page_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": service_class,
        "stndFlg": "N",
        "jrnySqno1": "001",
        "jrnySqno2": "",
        "trnGpCd1": query.train_group_code,
        "trnGpCd2": "",
        "trnGpNm1": group_name,
        "trnGpNm2": "",
        "dptRsStnCd1": query.departure_station_code,
        "dptRsStnCd2": "",
        "dptRsStnCdNm1": query.departure_station_name or query.departure_station_code,
        "dptRsStnCdNm2": "",
        "arvRsStnCd1": query.arrival_station_code,
        "arvRsStnCd2": "",
        "arvRsStnCdNm1": query.arrival_station_name or query.arrival_station_code,
        "arvRsStnCdNm2": "",
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "dptTm2": "",
        "arvDt1": "",
        "arvTm1": "",
        "totPrnb": str(query.passengers.total),
        "totPrnbNm": f"{query.passengers.total}명",
        "psgGridcnt": str(query.passengers.total),
        "smkSeatAttCd1": "000",
        "dirSeatAttCd1": "009",
        "locSeatAttCd1": "000",
        "rqSeatAttCd1": query.seat_attr_code,
        "etcSeatAttCd1": "000",
        "seatAttNm1": "일반/기본",
        "seatAttCd": query.seat_attr_code,
        "netfunnelKey": netfunnel_key,
        "adjStnScdlOfrFlg": "N",
        "pnrNo": "",
        "JRNYLIST_KEY": "",
    }
    payload.update(_passenger_fields(query.passengers))
    for leg in (1, 2):
        for index in range(1, 10):
            payload[f"seatNo{leg}_{index}"] = ""
    return payload
```

Implement:

```python
def search_ajax_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    hydrated_fields: dict[str, str],
) -> dict[str, str]:
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = dict(hydrated_fields)
    payload.update(
        {
            "chtnDvCd": "1",
            "dptDt": query.departure_date,
            "dptTm": query.departure_time,
            "dptDt1": query.departure_date,
            "dptTm1": query.departure_time,
            "dptRsStnCd": query.departure_station_code,
            "arvRsStnCd": query.arrival_station_code,
            "stlbTrnClsfCd": service_class,
            "trnGpCd": query.train_group_code,
            "trnGpNm1": group_name,
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
    )
    payload.update(_passenger_fields(query.passengers, hydrated_fields))
    return payload


def group_search_ajax_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    hydrated_fields: dict[str, str],
) -> dict[str, str]:
    payload = search_ajax_payload(query, netfunnel_key, hydrated_fields=hydrated_fields)
    payload["grpDv"] = "1"
    payload["psgNum"] = str(max(query.passengers.total, 10))
    return payload
```

- [ ] **Step 7: Hydrate and retain state in the client**

Extend the constructor compatibly:

```python
def __init__(
    self,
    config: SrtConfig | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], float] | None = None,
) -> None:
    self.config = config or SrtConfig()
    self.http = SrtHttpClient(self.config, transport=transport)
    self.session = SrtSessionClient(self.http)
    self._clock = clock or time.time
```

Use `build_act10_url(self.config.netfunnel_url, timestamp_ms=int(self._clock() * 1000))` in `_get_act10_key`. Add:

```python
def _hydrate_search(self, query: TrainSearchQuery, key: str) -> SearchPageState:
    referer = f"{self.config.base_url}/ara/ara0101v.do"
    html = self.http.get_text(
        "/ara/selectListAra10007_n.do",
        params=search_page_payload(query, key),
        referer=referer,
    )
    return parse_search_page_state(html)
```

Pass `state.hidden_fields` to personal and group AJAX payload builders.

- [ ] **Step 8: Run hydration and NetFunnel tests**

Run: `pytest tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py -q`

Expected: PASS.

- [ ] **Step 9: Commit only Task 5 files**

```bash
git add src/srt_mobile_api/netfunnel.py src/srt_mobile_api/models.py src/srt_mobile_api/parsers.py src/srt_mobile_api/payloads.py src/srt_mobile_api/client.py tests/fixtures/search_page.html tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py
git commit -m "fix: preserve srt search hydration"
```

---

### Task 6: Strict Search Parsing And One Fresh-Key Retry

**Files:**
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `tests/fixtures/search_success.json`
- Modify: `tests/test_netfunnel_payloads_parsers.py`
- Modify: `tests/test_client_read_apis.py`

**Interfaces:**
- Consumes: Task 5 hydration/payload helpers and `SrtNetFunnelError.code`.
- Produces: strict `parse_train_search_response(data) -> TrainSearchResult` and private `_search_once(query, *, group)`/`_search_with_retry(query, *, group)`.

- [ ] **Step 1: Add failing malformed-envelope and empty-success tests**

Set `search_success.json` to:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"IRG000000","strResult":"SUCC","qryCnqeCnt":"1"}],"dsOutput1":[{"trnNo":"303","trnGpCd":"300","stlbTrnClsfCd":"17","runDt":"20260710","dptDt":"20260710","dptTm":"060000","arvDt":"20260710","arvTm":"083000","dptRsStnCd":"0551","dptRsStnNm":"수서","arvRsStnCd":"0020","arvRsStnNm":"부산"}]}}
```

```python
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ErrorCode": "ERR", "ErrorMsg": "wrapper failed"},
        {"ErrorCode": "0", "outDataSets": {}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [], "dsOutput1": []}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "", "strResult": ""}], "dsOutput1": []}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRG000000", "strResult": "SUCC"}], "dsOutput1": {}}},
    ],
)
def test_search_parser_rejects_unproven_success(payload):
    with pytest.raises((SrtProtocolError, SrtAppError)):
        parse_train_search_response(payload)


def test_empty_rows_are_valid_only_after_exact_success(load_json_fixture):
    result = parse_train_search_response(load_json_fixture("search_empty.json"))
    assert result.result["msgCd"] == "IRG000000"
    assert result.result["strResult"] == "SUCC"
    assert result.trains == []
```

- [ ] **Step 2: Add failing one-retry and exhausted-retry tests**

```python
def test_net000001_repeats_full_flow_once_with_fresh_keys(load_json_fixture, load_text_fixture):
    calls: list[tuple[str, str]] = []
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        calls.append((request.method, request.url.path))
        if request.url.host == "nf.letskorail.com":
            key = "FIRST" if sum(path == "/ts.wseq" for _, path in calls) == 1 else "SECOND"
            return httpx.Response(200, text=f"NetFunnel.gControl.result='5101:5101:key={key}';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        if post_count == 1:
            return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))
        return httpx.Response(200, json=load_json_fixture("search_success.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler), clock=lambda: 1712345678.901)
    result = client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert result.trains[0].train_no == "303"
    assert [path for _, path in calls].count("/ts.wseq") == 2
    assert calls.count(("GET", "/ara/selectListAra10007_n.do")) == 2
    assert calls.count(("POST", "/ara/selectListAra10007_n.do")) == 2
```

Add:

```python
def test_net000001_is_not_retried_more_than_once(load_json_fixture, load_text_fixture):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:5101:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtNetFunnelError) as exc_info:
        client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert exc_info.value.code == "NET000001"
    assert post_count == 2


def test_ordinary_app_failure_is_not_retried(load_text_fixture):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:5101:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(
            200,
            json={
                "ErrorCode": "0",
                "outDataSets": {
                    "dsOutput0": [{"msgCd": "SEARCH_ERR", "strResult": "FAIL", "msgTxt": "failed"}],
                    "dsOutput1": [],
                },
            },
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtAppError):
        client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert post_count == 1
```

- [ ] **Step 3: Run focused parser and retry tests**

Run: `pytest tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py -q`

Expected: FAIL because missing metadata is accepted and no retry exists.

- [ ] **Step 4: Require a complete success envelope before reading rows**

Replace `parse_train_search_response`:

```python
def parse_train_search_response(data: dict[str, Any]) -> TrainSearchResult:
    wrapper_code = str(data.get("ErrorCode") or "")
    if wrapper_code not in {"", "0"}:
        raise SrtAppError(wrapper_code, str(data.get("ErrorMsg") or ""), raw=data)
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
```

- [ ] **Step 5: Implement bounded whole-flow retry**

```python
def _search_once(self, query: TrainSearchQuery, *, group: bool) -> TrainSearchResult:
    referer = f"{self.config.base_url}/ara/ara0101v.do"
    key = self._get_act10_key(referer)
    state = self._hydrate_search(query, key)
    path = "/ara/selectListAra10082_n.do" if group else "/ara/selectListAra10007_n.do"
    payload = (
        group_search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
        if group
        else search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
    )
    data = self.http.post_form(
        path,
        payload,
        accept="application/json, text/javascript, */*; q=0.01",
        referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
    )
    return parse_train_search_response(data)


def _search_with_retry(self, query: TrainSearchQuery, *, group: bool) -> TrainSearchResult:
    for attempt in range(2):
        try:
            return self._search_once(query, group=group)
        except SrtNetFunnelError as exc:
            if exc.code != "NET000001" or attempt == 1:
                raise
    raise AssertionError("unreachable NetFunnel retry state")
```

Make `search_trains` call `_search_with_retry(query, group=False)` and `search_group_trains` call `_search_with_retry(query, group=True)`. Do not catch transport, protocol, auth, session, or ordinary app errors.

- [ ] **Step 6: Run parser, payload, and client tests**

Run: `pytest tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py -q`

Expected: PASS.

- [ ] **Step 7: Commit only Task 6 files**

```bash
git add src/srt_mobile_api/parsers.py src/srt_mobile_api/client.py tests/fixtures/search_success.json tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py
git commit -m "fix: classify and retry srt search"
```

---

### Task 7: Complete Timetable/Fare Forms And Structured Compatible Results

**Files:**
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/payloads.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `src/srt_mobile_api/__init__.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_client_read_apis.py`
- Modify: `tests/test_netfunnel_payloads_parsers.py`

**Interfaces:**
- Consumes: Task 5 passenger slots and `TrainSummary` station names.
- Produces: `TimetableRow`, `TimetablePage(HtmlPage)`, `FareItem`, `FarePage(HtmlPage)`, `timetable_payload`, `fare_payload`, `parse_timetable_page`, and `parse_fare_page`.

- [ ] **Step 1: Add failing structured page and full fare-form tests**

```python
def test_timetable_and_fare_parsers_return_html_compatible_models(load_text_fixture):
    timetable = parse_timetable_page(load_text_fixture("timetable.html"))
    fare = parse_fare_page(load_text_fixture("fare.html"))
    assert isinstance(timetable, HtmlPage)
    assert timetable.rows[0].station_name == "수서"
    assert timetable.rows[0].times == ("06:00",)
    assert isinstance(fare, HtmlPage)
    assert fare.items[0].label == "어른 일반실"
    assert fare.items[0].amount == 51900
    assert fare.items[0].raw_amount == "51,900원"


def test_fare_payload_contains_all_six_passenger_slots():
    train = TrainSummary(
        train_no="303",
        service_class_code="17",
        run_date="20260710",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    passengers = PassengerCounts(
        adult=1,
        child=1,
        senior=1,
        disability_1_to_3=1,
        disability_4_to_6=1,
        infant=1,
    )
    payload = fare_payload(train, passengers)
    assert [payload[f"psgTpCd{index}"] for index in range(1, 7)] == ["1", "5", "4", "2", "3", "6"]
    assert [payload[f"psgInfoPerPrnb{index}"] for index in range(1, 7)] == ["1"] * 6
    assert payload["psgTpCd6"] == "6"
    assert payload["trnNo"] == "00303"
    assert payload["dptRsStnCd2"] == ""
```

- [ ] **Step 2: Run focused detail tests**

Run: `pytest tests/test_models.py tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py::test_timetable_and_fare -q`

Expected: FAIL because methods return plain `HtmlPage` and fare sends only adult fields.

- [ ] **Step 3: Add compatible structured models**

```python
@dataclass(frozen=True)
class TimetableRow:
    station_name: str
    times: tuple[str, ...]
    raw_text: str


@dataclass(frozen=True)
class TimetablePage(HtmlPage):
    rows: tuple[TimetableRow, ...] = ()


@dataclass(frozen=True)
class FareItem:
    label: str
    amount: int
    raw_amount: str


@dataclass(frozen=True)
class FarePage(HtmlPage):
    items: tuple[FareItem, ...] = ()
```

Export all four types from `__init__.py`.

- [ ] **Step 4: Add exact timetable and fare payload builders**

```python
def _train_sort(train: TrainSummary) -> str:
    return "SRT" if train.service_class_code == "17" else str(train.service_class_code or "")


def _station_course(train: TrainSummary) -> str:
    names = [train.departure_station_name or "", train.arrival_station_name or ""]
    return "-".join(name for name in names if name)


def timetable_payload(train: TrainSummary) -> dict[str, str]:
    return {
        "stnCourseNm": _station_course(train),
        "trnSort": _train_sort(train),
        "runDt": train.run_date or train.departure_date or "",
        "trnNo": train.train_no.zfill(5),
    }


def fare_payload(train: TrainSummary, passengers: PassengerCounts) -> dict[str, str]:
    run_date = train.run_date or train.departure_date or ""
    train_no = train.train_no.zfill(5)
    payload = {
        "stnCourseNm": _station_course(train),
        "trnSort": _train_sort(train),
        "runDt": run_date,
        "trnNo": train_no,
        "chtnDvCd": "1",
        "dptRsStnCd1": train.departure_station_code or "",
        "arvRsStnCd1": train.arrival_station_code or "",
        "runDt1": run_date,
        "trnNo1": train_no,
        "dptRsStnCd2": "",
        "arvRsStnCd2": "",
        "runDt2": "",
        "trnNo2": "",
    }
    payload.update(_passenger_fields(passengers))
    return payload
```

- [ ] **Step 5: Parse table rows before regex fallback**

Add this complete table parser:

```python
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
```

Implement:

```python
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
            items.append(FareItem(label=label, amount=int(match.group(1).replace(",", "")), raw_amount=raw_amount))
    if not items:
        raise SrtProtocolError("SRT fare page did not contain a fare amount")
    return FarePage(text=page.text, raw=page.raw, items=tuple(items))
```

- [ ] **Step 6: Use builders and structured parsers in the client**

Replace the two methods with:

```python
def get_timetable(self, train: TrainSummary) -> TimetablePage:
    raw = self.http.post_form(
        "/ara/selectListAra12009_n.do",
        timetable_payload(train),
        accept="text/html, */*; q=0.01",
    )["html"]
    return parse_timetable_page(raw)


def get_fare(
    self,
    train: TrainSummary,
    passengers: PassengerCounts | None = None,
) -> FarePage:
    raw = self.http.post_form(
        "/ara/selectListAra13010_n.do",
        fare_payload(train, passengers or PassengerCounts()),
        accept="text/html, */*; q=0.01",
    )["html"]
    return parse_fare_page(raw)
```

- [ ] **Step 7: Run detail, model, and full client tests**

Run: `pytest tests/test_models.py tests/test_netfunnel_payloads_parsers.py tests/test_client_read_apis.py -q`

Expected: PASS while existing `.text` and `.raw` assertions remain valid.

- [ ] **Step 8: Commit only Task 7 files**

```bash
git add src/srt_mobile_api/models.py src/srt_mobile_api/payloads.py src/srt_mobile_api/parsers.py src/srt_mobile_api/client.py src/srt_mobile_api/__init__.py tests/test_models.py tests/test_client_read_apis.py tests/test_netfunnel_payloads_parsers.py
git commit -m "feat: parse srt timetable and fare results"
```

---

### Task 8: Safe Full Live Flow And Read-Only Legacy Runner

**Files:**
- Modify: `src/srt_mobile_api/live.py`
- Modify: `scripts/srt_app_api_smoke.py`
- Modify: `tests/test_live.py`
- Create: `tests/test_smoke_script.py`
- Create: `tests/test_live_service.py`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: all stabilized public methods and `TrainSearchQuery`.
- Produces: testable `run_live_smoke(client, *, login_id, password, query)` and existing `run_live_smoke_from_env()` with bounded metadata only.

- [ ] **Step 1: Add failing safe-output and legacy-script tests**

```python
from pathlib import Path


def test_legacy_script_contains_no_mutation_endpoint():
    source = Path("scripts/srt_app_api_smoke.py").read_text(encoding="utf-8")
    for forbidden in (
        "aid=act_19",
        "/arc/selectListArc05013_n.do",
        "/arc/selectListArc10013_n.do",
        "/ard/selectListArd02017_n.do",
    ):
        assert forbidden not in source


def test_live_result_contains_counts_not_ticket_text():
    from unittest.mock import Mock

    train = TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    client = Mock(spec=SrtClient)
    client.login.return_value = SrtSession(login_id="login-id", user_map={"RTNCD": "Y"})
    client.get_main.return_value = HtmlPage(text="main", raw="<html>main</html>")
    client.get_booking_page.return_value = HtmlPage(text="booking", raw="<html>booking</html>")
    client.get_notice_list.return_value = {"noticeList": [{"title": "notice"}]}
    client.get_ticket_list.return_value = HtmlPage(text="ticket", raw="<html>ticket</html>")
    client.search_trains.return_value = TrainSearchResult(trains=[train], result={}, raw={})
    client.search_group_trains.return_value = TrainSearchResult(trains=[train], result={}, raw={})
    client.get_timetable.return_value = TimetablePage(
        text="06:00",
        raw="<html>06:00</html>",
        rows=(TimetableRow(station_name="수서", times=("06:00",), raw_text="수서 06:00"),),
    )
    client.get_fare.return_value = FarePage(
        text="51,900원",
        raw="<html>51,900원</html>",
        items=(FareItem(label="어른 일반실", amount=51900, raw_amount="51,900원"),),
    )
    result = run_live_smoke(
        client,
        login_id="login-id",
        password="password",
        query=TrainSearchQuery(
            "0551",
            "0020",
            "20260710",
            departure_station_name="수서",
            arrival_station_name="부산",
        ),
    )
    assert set(result) == {
        "loggedIn",
        "mainLoaded",
        "bookingLoaded",
        "noticeCount",
        "ticketPageLoaded",
        "personalTrainCount",
        "groupTrainCount",
        "timetableRowCount",
        "fareItemCount",
    }
    assert "text" not in repr(result).lower()
    assert "raw" not in result
    for method_name in (
        "login",
        "get_main",
        "get_booking_page",
        "get_notice_list",
        "get_ticket_list",
        "search_trains",
        "search_group_trains",
        "get_timetable",
        "get_fare",
    ):
        assert getattr(client, method_name).called
```

Import the model and client classes used by this test from `srt_mobile_api` and `srt_mobile_api.models`.

- [ ] **Step 2: Run live-helper and script tests**

Run: `pytest tests/test_live.py tests/test_smoke_script.py -q`

Expected: FAIL because output includes `ticketTextPrefix` and the legacy script still performs `act_19`/reservation probes.

- [ ] **Step 3: Implement a complete bounded live helper**

```python
def run_live_smoke(
    client: SrtClient,
    *,
    login_id: str,
    password: str,
    query: TrainSearchQuery,
) -> dict[str, Any]:
    session = client.login(login_id, password)
    main = client.get_main()
    booking = client.get_booking_page()
    notices = client.get_notice_list()
    tickets = client.get_ticket_list()
    personal = client.search_trains(query)
    group = client.search_group_trains(query)
    timetable = client.get_timetable(personal.trains[0]) if personal.trains else None
    fare = client.get_fare(personal.trains[0], query.passengers) if personal.trains else None
    return {
        "loggedIn": bool(session.user_map),
        "mainLoaded": bool(main.text),
        "bookingLoaded": bool(booking.text),
        "noticeCount": len(notices["noticeList"]),
        "ticketPageLoaded": bool(tickets.text),
        "personalTrainCount": len(personal.trains),
        "groupTrainCount": len(group.trains),
        "timetableRowCount": len(timetable.rows) if timetable else 0,
        "fareItemCount": len(fare.items) if fare else 0,
    }


def run_live_smoke_from_env() -> dict[str, Any]:
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    test_date = os.environ.get("SRT_TEST_DATE")
    if not test_date:
        raise RuntimeError("SRT_TEST_DATE is required for live smoke")
    passengers = PassengerCounts(
        adult=int(os.environ.get("SRT_ADULT_COUNT", "1")),
        child=int(os.environ.get("SRT_CHILD_COUNT", "0")),
        senior=int(os.environ.get("SRT_SENIOR_COUNT", "0")),
        disability_1_to_3=int(os.environ.get("SRT_DISABILITY_1_TO_3_COUNT", "0")),
        disability_4_to_6=int(os.environ.get("SRT_DISABILITY_4_TO_6_COUNT", "0")),
        infant=int(os.environ.get("SRT_INFANT_COUNT", "0")),
    )
    query = TrainSearchQuery(
        departure_station_code=os.environ.get("SRT_DEPARTURE_STATION_CODE", "0551"),
        arrival_station_code=os.environ.get("SRT_ARRIVAL_STATION_CODE", "0020"),
        departure_date=test_date,
        departure_time=os.environ.get("SRT_DEPARTURE_TIME", "060000"),
        passengers=passengers,
        departure_station_name=os.environ.get("SRT_DEPARTURE_STATION_NAME", "수서"),
        arrival_station_name=os.environ.get("SRT_ARRIVAL_STATION_NAME", "부산"),
    )
    client = SrtClient(SrtConfig(device_key=os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF")))
    try:
        return run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
```

Require `SRT_TEST_DATE` explicitly so the helper never sends a stale hard-coded date.

- [ ] **Step 4: Replace the legacy script with a thin safe wrapper**

Replace the entire script with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

from srt_mobile_api import SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.live import read_credentials_from_env, run_live_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SRT read-only app API smoke checks")
    parser.add_argument("--date", required=True, help="YYYYMMDD departure date")
    parser.add_argument("--depart-code", default="0551")
    parser.add_argument("--depart-name", default="수서")
    parser.add_argument("--arrive-code", default="0020")
    parser.add_argument("--arrive-name", default="부산")
    parser.add_argument("--device-key", default=os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF"))
    args = parser.parse_args()
    login_id, password = read_credentials_from_env()
    query = TrainSearchQuery(
        departure_station_code=args.depart_code,
        arrival_station_code=args.arrive_code,
        departure_date=args.date,
        departure_station_name=args.depart_name,
        arrival_station_name=args.arrive_name,
    )
    client = SrtClient(SrtConfig(device_key=args.device_key))
    try:
        result = run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Ignore the local environment file and document the safe command**

Add `.local-live-smoke.env` to `.gitignore`. Document:

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
export SRT_DEVICE_KEY="<device-key>"
export SRT_CHILD_COUNT=1
python3 -c "from srt_mobile_api.live import run_live_smoke_from_env; print(run_live_smoke_from_env())"
```

State that output contains only booleans and bounded counts and that no `act_19` or reservation path exists in the runner. The stabilization live gate must set at least one non-adult count once so the six-slot passenger code mapping is exercised against the fare endpoint.

- [ ] **Step 6: Add an explicitly skipped-by-default live test**

```python
import pytest

from srt_mobile_api.live import live_enabled, run_live_smoke_from_env


pytestmark = pytest.mark.live


def test_read_only_live_smoke():
    if not live_enabled():
        pytest.skip("SRT live smoke requires explicit opt-in")
    result = run_live_smoke_from_env()
    assert result["loggedIn"] is True
    assert result["personalTrainCount"] >= 0
    assert result["groupTrainCount"] >= 0
    assert "raw" not in result
```

- [ ] **Step 7: Run offline live and script tests**

Run: `pytest tests/test_live.py tests/test_smoke_script.py tests/test_live_service.py -q`

Expected: PASS with the service test skipped unless explicit live opt-in exists.

- [ ] **Step 8: Commit only Task 8 files**

```bash
git add src/srt_mobile_api/live.py scripts/srt_app_api_smoke.py tests/test_live.py tests/test_smoke_script.py tests/test_live_service.py .gitignore README.md
git commit -m "test: restrict srt smoke flow to reads"
```

---

### Task 9: Public Surface, Build, And Isolated Import Gate

**Files:**
- Create: `tests/test_public_contract.py`
- Modify: `src/srt_mobile_api/__init__.py`

**Interfaces:**
- Consumes: all stabilized public methods, models, and errors.
- Produces: a regression gate preventing accidental endpoint expansion or loss of compatibility exports.

- [ ] **Step 1: Add the public surface test**

```python
import inspect

import srt_mobile_api
from srt_mobile_api import SrtClient


def test_client_public_method_set_is_stable():
    methods = {
        name
        for name, value in inspect.getmembers(SrtClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {
        "clear_session",
        "close",
        "get_booking_page",
        "get_fare",
        "get_main",
        "get_notice_list",
        "get_ticket_list",
        "get_timetable",
        "login",
        "logout",
        "search_group_trains",
        "search_trains",
    }


def test_completed_types_are_exported():
    for name in (
        "FareItem",
        "FarePage",
        "SrtAppError",
        "SrtNetFunnelError",
        "SrtSessionExpiredError",
        "SrtTransportError",
        "TimetablePage",
        "TimetableRow",
    ):
        assert getattr(srt_mobile_api, name)


def test_existing_method_signatures_remain_compatible():
    assert list(inspect.signature(SrtClient.login).parameters) == [
        "self",
        "login_id",
        "password",
        "login_type",
    ]
    assert list(inspect.signature(SrtClient.get_ticket_list).parameters) == ["self", "page_no"]
    assert list(inspect.signature(SrtClient.get_fare).parameters) == ["self", "train", "passengers"]
```

- [ ] **Step 2: Run the public-contract test**

Run: `pytest tests/test_public_contract.py -q`

Expected: PASS after adding any missing Task 1/7 exports to `__init__.py`.

- [ ] **Step 3: Run the complete offline suite**

Run: `pytest -q`

Expected: PASS with only the explicitly disabled live test skipped.

- [ ] **Step 4: Build wheel and sdist**

Run: `python3 -m build`

Expected: exit 0 and fresh `dist/srt_mobile_api-0.1.0-py3-none-any.whl` plus source archive.

- [ ] **Step 5: Verify isolated installation and imports**

```bash
VERIFY_DIR="$(mktemp -d)"
python3 -m venv "$VERIFY_DIR/venv"
"$VERIFY_DIR/venv/bin/pip" install --quiet dist/srt_mobile_api-0.1.0-py3-none-any.whl
"$VERIFY_DIR/venv/bin/python" -c "from srt_mobile_api import FarePage, SrtClient, SrtSessionExpiredError; print(SrtClient.__name__)"
rm -rf "$VERIFY_DIR"
```

Expected output: `SrtClient`.

- [ ] **Step 6: Run the opted-in live gate**

Load ignored `.local-live-smoke.env` in the shell without printing it, then run:

```bash
pytest -m live tests/test_live_service.py -q
```

Expected: PASS. A server rejection must remain a typed transport, auth, session, app, protocol, or NetFunnel failure; do not weaken it into a successful empty result.

- [ ] **Step 7: Confirm no mutation route or secret was added**

Run: `rg -n "act_19|selectListArc05013|selectListArc10013|selectListArd02017" src scripts tests`

Expected: no match outside explicit rejection assertions in safety/smoke tests.

- [ ] **Step 8: Commit the final contract gate**

```bash
git add tests/test_public_contract.py src/srt_mobile_api/__init__.py
git commit -m "test: lock srt public api contract"
```

---

## Final Verification Checklist

- [ ] `pytest -q` passes.
- [ ] `python3 -m build` succeeds.
- [ ] The built wheel imports in a fresh virtual environment.
- [ ] `pytest -m live tests/test_live_service.py -q` passes with ignored local credentials.
- [ ] Every network request is present in `READ_ONLY_ROUTES`.
- [ ] NetFunnel permits only the exact `act_10` contract.
- [ ] Failed login and hydration leave no old cookie or `current` session.
- [ ] Search preserves hydrated unknown fields and station names.
- [ ] Missing or malformed search metadata raises instead of returning an empty result.
- [ ] `NET000001` repeats the complete search flow once and no other failure retries.
- [ ] Timetable/fare remain `HtmlPage` compatible and expose structured rows/items.
- [ ] Fare sends six passenger slots and return-leg placeholders.
- [ ] The legacy runner contains no `act_19`, reservation, payment, or raw-response persistence.
- [ ] No credential, cookie, NetFunnel key, PNR, card-shaped value, or raw account response appears in test output.
