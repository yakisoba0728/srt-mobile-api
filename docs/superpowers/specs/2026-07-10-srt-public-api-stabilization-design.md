# SRT Public API Stabilization Design

Date: 2026-07-10
Status: Draft for user review

## Goal

Make every currently exposed read-only SRT client operation behave consistently with the observed Android WebView and live-server contracts before adding more API methods.

This phase is stabilization, not endpoint expansion. It fixes page hydration, NetFunnel handling, request construction, response validation, session state, result parsing, redaction, and safety boundaries while preserving the existing caller-facing API wherever practical.

## Relationship To The KORAIL Package

SRT and KORAIL remain independent distributions. They do not share a runtime base package.

They do share these behavioral rules:

- configuration is explicit and owned by one client instance;
- a login attempt commits session state only after every required step succeeds;
- successful responses return models and failed responses raise typed exceptions;
- application failures are never converted into empty successful results;
- raw responses remain available for compatibility but are never logged automatically;
- all network requests cross one read-only endpoint policy;
- live verification reads credentials from ignored local environment files only.

## Evidence Authority

Resolve conflicting documentation in this order:

1. controlled live-server observations;
2. APK/JADX/smali source evidence;
3. `docs/analysis/srt-app-api-library-spec-2026-07-09.md`;
4. endpoint-specific flow notes and cited smoke-script evidence;
5. historical design and implementation plans;
6. synthetic fixtures.

The historical design describes additional safe selectors and a seat page. They remain valid candidates for the next API-expansion phase, but they are not current public methods and are not implemented in this stabilization phase.

## In Scope

Current `SrtClient` operations:

- `login`
- `logout`
- `clear_session`
- `close`
- `get_main`
- `get_booking_page`
- `get_notice_list`
- `get_ticket_list`
- `search_trains`
- `search_group_trains`
- `get_timetable`
- `get_fare`

Also in scope:

- request and result models used by the methods above;
- NetFunnel `act_10` fetch, parsing, retry, and redaction behavior;
- package-level exceptions, redaction, live-smoke helpers, and safety enforcement.

## Out Of Scope

- seat page and station/date/passenger/seat-option/train-group selector methods;
- reservation creation, change, cancellation, and wait-list operations;
- NetFunnel `act_19`;
- ARD payment entry, payment authorization, refund, and ATA reservation detail;
- native bridges, external KORAIL seat map, and other SDK flows;
- automatic re-login or storage of user passwords;
- implementation of additional documented read-only endpoints.

Those read-only endpoints are considered only after this stabilization gate passes.

## Compatibility Policy

- Keep current public method names and their ordinary calling forms.
- Keep existing result attributes, including `raw` and `text`.
- Specialized timetable and fare results may extend the existing HTML-page contract, but may not remove existing access.
- Do not silently reinterpret malformed or failed JSON as a successful empty result.
- Treat accidental low-level access such as `client.http` as non-public, while still enforcing safety if callers reach it.

## Architecture

The request path is:

```text
SrtConfig
  -> SrtClient public method
  -> session, hydration, or payload construction
  -> read-only endpoint policy
  -> SrtHttpClient
  -> JSON/HTML contract validation
  -> typed result or typed exception
```

Responsibilities:

- `config.py`: immutable app, device, timeout, and NetFunnel-host configuration;
- `client.py`: public facade and endpoint-specific orchestration;
- `session.py`: transactional login and cookie/current state;
- `payloads.py`: app-compatible hydrated request builders;
- `netfunnel.py`: `act_10` URL construction and response classification;
- `http.py`: headers, allowed routes, transport, and JSON/HTML framing;
- `parsers.py`: result-code validation and structured page parsing;
- `models.py`: caller input and response models;
- `errors.py`: stable exception hierarchy;
- `redaction.py`: recursive secret filtering;
- `safety.py`: explicit read-only route registry;
- `live.py`: non-destructive live verification.

## Configuration And Request State

The caller's `SrtConfig` snapshot supplies the base host, NetFunnel host, app user agent, device key, and timeout. Request builders do not replace caller values with unrelated defaults after client creation.

One cookie jar belongs to one client instance. NetFunnel keys are request-scoped and never retained as durable client state or included in exception URLs.

Time providers used to construct NetFunnel requests may be injected for deterministic tests without becoming global mutable state.

## Login And Session Transaction

Login follows this state machine:

```text
clear old state
  -> GET login page
  -> POST credentials
  -> validate userMap.RTNCD
  -> hydrate main page
  -> hydrate booking page
  -> commit current session
```

Rules:

- clear cookies and current state before each login attempt;
- commit `current` only after every required hydration request succeeds;
- clear cookies and current state after authentication, protocol, transport, or hydration failure;
- never preserve a previous authenticated session after a failed re-login;
- never store the password for automatic re-login;
- classify logged-out/session-expired responses separately from malformed data.

`logout` remains a local session clear in this phase; no new server-side mutation endpoint is introduced.

## Search Data Flow

Personal search follows the observed sequence:

1. fetch a fresh NetFunnel `act_10` key;
2. hydrate `GET /ara/selectListAra10007_n.do`;
3. parse and preserve all hidden inputs from the returned page;
4. overlay only normalized caller search fields;
5. send station codes in code fields and hydrated station names in name fields;
6. POST the personal-search request;
7. validate the result envelope before parsing train rows.

Group search uses its separately evidenced request builder and endpoint. It is not implemented by changing only the personal-search URL.

Train-group mappings are explicit and tested:

- SRT group `300` uses the evidenced SRT service class `17`;
- combined KTX+SRT group uses `900`;
- all-train group uses `109`.

The parser accepts the evidenced object-or-list form of `dsOutput0`, requires the successful application status/code contract, and treats an empty `dsOutput1` as a valid no-train result only after success is proven.

When the server returns `NET000001`, the entire search flow obtains a fresh `act_10` key and retries exactly once. A second failure raises the classified exception.

## Timetable And Fare Results

`get_timetable` and `get_fare` send the complete app-evidenced forms, including train class, run date, zero-padded train number, journey fields, and station fields.

Fare requests support all six passenger categories represented by `PassengerCounts`; they do not reduce the request to adult count only.

For compatibility:

- existing `HtmlPage.text` and `HtmlPage.raw` access remains available;
- timetable and fare may return specialized `HtmlPage`-compatible result types;
- specialized types expose parsed rows/items in addition to the original HTML;
- malformed HTML required for the structured contract raises a protocol/parsing error rather than returning fabricated empty data.

## Error Contract

The package exposes one coherent hierarchy:

```text
SrtApiError
  SrtTransportError
  SrtProtocolError
  SrtAppError
  SrtAuthError
    SrtSessionExpiredError
  SrtNetFunnelError
```

- HTTP, timeout, DNS, and connection failures are transport errors.
- Invalid JSON/HTML framing and missing required fields are protocol errors.
- A valid response with a failed application status/code is an app error.
- Invalid credentials and incomplete login are auth errors.
- evidenced logged-out responses are session-expired errors.
- invalid, rejected, or exhausted NetFunnel responses are NetFunnel errors.

General transport and application errors are not retried automatically. The single `NET000001` search retry is the only stabilization-phase exception.

## Safety And Redaction

Replace descriptive/blocklist-only safety with an explicit `method + host + path` registry for every current read-only request. The transport rejects unregistered paths before network I/O, including calls made through a reachable low-level client object.

Absolute URL requests are allowed only for the configured NetFunnel host and evidenced `act_10` path/query contract. The registry does not include reservation endpoints, `act_19`, payment, cancellation, refund, or external seat-map flows.

The legacy smoke script must not issue reservation-like probes merely because credentials are present.

Redaction is recursive and case-insensitive. It covers mappings, sequences, dataclasses, exception formatting, and URL query strings. Passwords, cookies, session IDs, NetFunnel keys, PNR/ticket identifiers, and card-shaped values must not appear in logs or `repr` output.

Raw response objects remain caller-accessible but are not automatically persisted or emitted by live helpers.

## Test Strategy

Use test-driven changes with offline tests as the default suite.

Required layers:

1. model and configuration validation;
2. exact method/path/header/form tests through `httpx.MockTransport`;
3. page-hydration and hidden-input preservation tests;
4. success, empty, failure, malformed, and session-expiry parser tests;
5. login commit/rollback state tests;
6. NetFunnel success, redaction, one-retry, and exhausted-retry tests;
7. full six-category timetable/fare payload and structured-parser tests;
8. route allowlist and bypass-attempt tests;
9. recursive redaction and exception-leak tests;
10. package build and isolated install/import tests;
11. explicitly enabled, read-only live smoke tests.

Live verification covers login, main and booking hydration, notice list, personal and group search, timetable, fare, and ticket list. It records only status/classification and bounded counts, never raw account data or credentials.

## Completion Gate

Stabilization is complete only when:

- the full offline suite passes;
- every current public method has a request-contract test;
- known failure, session-expiry, and NetFunnel responses raise the intended exception;
- package build and isolated import succeed;
- live login succeeds with environment-provided credentials;
- safe live reads succeed or return accurately classified server errors;
- captured request paths contain no mutation endpoint;
- repository and test output contain no credential, cookie, or token leak.

Only after this gate passes may implementation planning begin for additional read-only SRT APIs.
