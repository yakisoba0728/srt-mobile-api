# SRT Python Client Library Design

Date: 2026-07-09

## Goal

Create the first Python package scaffold and login/read-only API client for the SRT Android app API analysis repository.

The package must be shaped to match the KORAIL package, while keeping SRT WebView protocol details isolated inside this repository.

## Fixed Decisions

- Distribution package name: `srt-mobile-api`
- Python import package: `srt_mobile_api`
- Runtime stack: `httpx`, `dataclasses`, `pytest`
- Package layout: `src/srt_mobile_api/`
- MVP includes login and safe read/query APIs only.
- Reservation, payment, refund, cancellation, and payment-detail entry flows are not implemented in this version.
- Dangerous endpoints must not appear as public stub methods in this version.
- Default tests must be offline and non-destructive.
- Live smoke must require credentials and an explicit live opt-in environment variable.

## Source Evidence

Primary source documents:

- `README.md`
- `docs/analysis/srt-app-api-library-spec-2026-07-09.md`
- `scripts/srt_app_api_smoke.py`

Known extraction defect to fix during library extraction:

- `scripts/srt_app_api_smoke.py` assumes `dsOutput0` is list-like. The library parser must normalize `dsOutput0` when it is either an object or a list.

## Package Structure

Create this structure:

```text
pyproject.toml
src/srt_mobile_api/
  __init__.py
  client.py
  config.py
  errors.py
  http.py
  live.py
  models.py
  netfunnel.py
  payloads.py
  parsers.py
  redaction.py
  safety.py
  session.py
tests/
  fixtures/
  test_*.py
```

File responsibilities:

- `client.py`: public `SrtClient` facade.
- `config.py`: `SrtConfig` dataclass with app host, NetFunnel host, user agent, device key, timeout, and live-test options.
- `http.py`: thin `httpx.Client` wrapper with form/query helpers, WebView/Ajax headers, cookies, timeout, and `MockTransport` injection.
- `session.py`: login/logout/session state helpers.
- `netfunnel.py`: `act_10` token fetch and parser. `act_19` is out of scope for this MVP.
- `payloads.py`: search, group search, selector, timetable, fare, and seat-page payload builders.
- `parsers.py`: JSON normalization, train row extraction, timetable/fare HTML parsing, and text extraction helpers.
- `models.py`: dataclass request/response/result models with `raw: dict` escape hatches.
- `errors.py`: transport, protocol, app-level, authentication, parsing, and NetFunnel exceptions.
- `redaction.py`: masking helpers for credentials, cookies, NetFunnel keys, PNR/ticket identifiers, card-like values, and raw response text.
- `safety.py`: constants and documentation helpers for excluded dangerous domains. It must not expose callable destructive API stubs.
- `live.py`: optional live smoke helpers, excluded from default tests.

## Public API

Expose from `srt_mobile_api.__init__`:

```python
from .client import SrtClient
from .config import SrtConfig
from .errors import SrtApiError, SrtAuthError, SrtProtocolError
from .models import (
    PassengerCounts,
    SrtSession,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)
```

MVP public methods on `SrtClient`:

- `login(login_id: str, password: str, *, login_type: str = "3") -> SrtSession`
- `logout() -> None`
- `clear_session() -> None`
- `get_main()`
- `get_booking_page()`
- `get_notice_list()`
- `get_ticket_list(page_no: int = 0)`
- `search_trains(query: TrainSearchQuery) -> TrainSearchResult`
- `search_group_trains(query: TrainSearchQuery) -> TrainSearchResult`
- `get_timetable(train: TrainSummary)`
- `get_fare(train: TrainSummary, passengers: PassengerCounts | None = None)`
- `get_seat_page(train: TrainSummary, *, choice_seat_count: int = 1)`
- `get_station_selector(departure_name: str, arrival_name: str, departure_code: str, arrival_code: str)`
- `get_station_map_selector()`
- `get_date_selector(date: str, *, hour: str = "06")`
- `get_passenger_selector(passengers: PassengerCounts)`
- `get_seat_option_selector(*, request_seat_attr_code: str = "015", location_seat_attr_code: str = "000", seat_name: str = "일반/기본")`
- `get_train_group_selector(train_group_code: str = "109", train_group_name: str = "전체")`

Do not add public methods for:

- reservation create/cancel/change
- NetFunnel `act_19`
- ARD payment/detail page entry
- real payment authorization
- ATA detail with valid reservation context
- external Korail seatmap
- FIDO, push, secure keyboard, mobile ID, fax, map/taxi, or native bridge SDK flows

## Runtime Contract

Defaults:

- Base host: `https://app.srail.or.kr`
- NetFunnel host: `https://nf.letskorail.com:443`
- User agent suffix: `SRT-APP-Android V.2.0.41`
- Form encoding: `application/x-www-form-urlencoded; charset=UTF-8`
- Ajax headers: include `Origin` and `X-Requested-With` where the app flow does.
- Keep one cookie jar per session.

Login flow:

1. `GET /login/login.do`
2. `POST /apb/selectListApb01080_n.do`
3. Require `userMap.RTNCD == "Y"`
4. Optional `GET /main/main.do?deviceId=<device_key>`
5. `GET /ara/ara0101v.do` before booking/search workflows

Search flow:

1. Fetch fresh NetFunnel `act_10` token.
2. Hydrate `GET /ara/selectListAra10007_n.do` with search state and `netfunnelKey`.
3. Preserve hidden fields from the server page when present.
4. `POST /ara/selectListAra10007_n.do` for personal search.
5. `POST /ara/selectListAra10082_n.do` for group search.
6. Normalize `dsOutput0` whether it is an object or a list.
7. Treat empty `dsOutput1[]` as a valid no-train result.

Group search must have a separate request builder. It must not be implemented by changing only the endpoint URL.

## Safety Requirements

Copy these SRT safety statements into implementation docs/tests:

- No user credentials, cookies, NetFunnel keys, raw response bodies, or payment tokens are stored here.
- Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or card-shaped values in the repository.
- Library rule: do not implement real card approval in the core client.

For this MVP:

- Reservation endpoints are not implemented.
- NetFunnel `act_19` is not implemented.
- ARD payment/detail page entry is not implemented.
- Negative reservation payload logic from the smoke script is not extracted into public API.

## Test Strategy

Default command:

```bash
pytest
```

Default tests must not access the network.

Use `httpx.MockTransport` for:

- login page and login API success/failure
- cookie persistence
- WebView/Ajax header policy
- NetFunnel `act_10` parser
- search page payload and Ajax payload keys
- group search payload builder, including group-specific fields
- JSON result normalization for `dsOutput0` as object and list
- empty search results
- `NET000001` app-level failure mapping
- timetable and fare HTML parser behavior
- selector popup payloads, including `totalPessnger` typo
- seat-page request payload
- ticket list and notice list parsing
- redaction of credentials, cookies, NetFunnel keys, PNR/ticket identifiers, card-like values, and raw response text

Suggested sanitized fixtures:

- `login_success.json`
- `login_failure.json`
- `netfunnel_act10.js`
- `search_success.json`
- `search_empty.json`
- `search_netfunnel_failure.json`
- `group_search_success.json`
- `timetable.html`
- `fare.html`
- `ticket_list.html`
- `notice_list.json`
- selector popup HTML snippets

Live tests:

- Must be marked `pytest.mark.live`.
- Must require `SRT_MOBILE_API_LIVE=1`.
- Must require credentials from environment variables.
- Must only perform login and read/query calls.
- Must never call reservation, payment, refund, cancellation, ARD, ATA, or native bridge endpoints.
- Must not persist raw responses inside the repository.

## Agent Execution Model

Implementation will be delegated by task to subagents.

Worker ownership:

- SRT workers may edit only files under `srt-mobile-api`.
- Workers must not modify KORAIL files.
- Each task must have a disjoint or clearly owned write set.
- Reviewers check both spec compliance and code quality after each task.

The orchestrator keeps cross-repo consistency for public API naming, package structure, test policy, and live opt-in behavior.

## Risks And Open Gaps

- The repository currently has no Python package scaffold or `pyproject.toml`.
- The spec is tied to SRT Android app `2.0.41`; endpoints and hidden fields may drift.
- HTML parsing must be defensive.
- Search pagination is not fully runtime-verified and should not be overbuilt in MVP.
- Valid reservation success was intentionally not captured because it can hold live inventory.
- Payment internals remain outside the core client.
