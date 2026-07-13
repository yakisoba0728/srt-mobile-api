# SRT Selector Popup Expansion Design

**Date:** 2026-07-13

**Status:** Implemented and bounded-live-verified on 2026-07-13

## Goal

Add the six previously runtime-successful, read-only SRT selector popup APIs as
explicit public methods without adding seat selection, mutual verification,
reservation-adjacent execution, or any mutation flow.

## Context

The current public API stabilization working tree is intentionally uncommitted.
Its fresh offline baseline is `169 passed, 1 skipped`, with the skipped test
being the explicitly opted-in live service test. The transport currently
permits 12 exact app/NetFunnel routes, and NetFunnel is restricted to the exact
`act_10` acquisition contract.

The six popup endpoints were successful in bounded runtime analysis. Their
stable contract is the request form and JavaScript callback field family, not a
fixed DOM layout.

## Scope

### In scope

- Six exact POST routes on the canonical SRT app origin.
- Six dedicated `SrtClient` methods.
- Six focused request builders using the evidenced form keys and defaults.
- Existing `HtmlPage` framing and authenticated-session expiry detection.
- Sanitized HTML fixtures and MockTransport request tests.
- Public-contract and bounded live-smoke updates.

### Out of scope

- The static-only legacy date path `/common/ARA/ARA0401P/view.do`.
- Mutual verification.
- App seat-selection page `/arc/selectListArc02012_n.do`.
- Reservation execution, cancellation, payment, refund, `act_19`, ATA/ARD,
  native bridges, and the external Korail seat map.
- DOM-specific structured selector models.
- NetFunnel changes or token acquisition for popup requests.

## Public API

`SrtClient` gains:

```python
def get_station_selector(
    self,
    departure_name: str,
    arrival_name: str,
    departure_code: str,
    arrival_code: str,
) -> HtmlPage: ...

def get_station_map_selector(self) -> HtmlPage: ...

def get_date_selector(
    self,
    date: str,
    *,
    hour: str = "06",
) -> HtmlPage: ...

def get_passenger_selector(
    self,
    passengers: PassengerCounts,
) -> HtmlPage: ...

def get_seat_option_selector(
    self,
    *,
    request_seat_attr_code: str = "015",
    location_seat_attr_code: str = "000",
    seat_name: str = "일반/기본",
) -> HtmlPage: ...

def get_train_group_selector(
    self,
    train_group_code: str = "109",
    train_group_name: str = "전체",
) -> HtmlPage: ...
```

The methods return the existing repr-safe `HtmlPage`. Raw HTML remains
caller-accessible for compatibility but is never logged or emitted by the live
helper.

Station names/codes and all seat-option strings must remain nonempty after
trimming. `PassengerCounts` retains its existing nonnegative-count and
at-least-one-passenger validation. These validation failures occur before I/O.

## Exact Routes And Forms

All requests use:

- origin `https://app.srail.or.kr`;
- method `POST`;
- content type `application/x-www-form-urlencoded; charset=UTF-8`;
- accept `text/html, */*; q=0.01`;
- referer `https://app.srail.or.kr/ara/ara0101v.do`.

### Station selector

`POST /common/ARA/ARA0501P/view.do`

```python
{
    "reqCode": "1",
    "sDptStnNm": departure_name,
    "sArvStnNm": arrival_name,
    "sDptStnCd": departure_code,
    "sArvStnCd": arrival_code,
    "chk_rtrp": "false",
    "sNowSel": "1",
    "page": "ARA0101",
    "boolRtrp": "false",
}
```

### Station-map selector

`POST /common/ARA/ARA0502P/view.do`

```python
{
    "reqCode": "2",
    "chk_rtrp": "false",
    "sNowSel": "1",
    "page": "ARA0101",
    "boolRtrp": "false",
}
```

### Date/time selector

`POST /common/ARA/ARA0403P/view.do`

```python
{
    "reqCode": "3",
    "selectDay": "",
    "selectDt": date,
    "selectTime": hour,
}
```

`date` must be eight decimal digits in `YYYYMMDD` form. `hour` must be two
decimal digits from `00` through `23`. Invalid values fail before I/O.

### Passenger selector

`POST /common/ARA/ARA0901P/view.do`

```python
{
    "reqCode": "6",
    "isOrg": "2",
    "passenger1": str(passengers.adult),
    "passenger2": str(passengers.child),
    "passenger3": str(passengers.senior),
    "passenger4": str(passengers.disability_1_to_3),
    "passenger5": str(passengers.disability_4_to_6),
    "passenger6": str(passengers.infant),
    "totalPessnger": str(passengers.total),
}
```

The server spelling `totalPessnger` is intentional and must not be corrected.

### Seat-option selector

`POST /common/ARA/ARA0701P/view.do`

```python
{
    "reqCode": "5",
    "rqSeatAttCd": request_seat_attr_code,
    "locSeatAttCd": location_seat_attr_code,
    "seatAttNm": seat_name,
}
```

This selects preference values only. It does not select, hold, or reserve a
physical seat.

### Train-group selector

`POST /common/ARA/ARA0201V/view.do`

```python
{
    "reqCode": "7",
    "trnGpCd": train_group_code,
    "trnGpCdNm": train_group_name,
}
```

The accepted codes are the existing evidenced set `300`, `900`, and `109`.
The defaults preserve the observed `109` / `전체` pair. Empty labels or
unsupported codes fail before I/O.

## Request And Response Flow

1. The public method enters the existing `_session_guard()`.
2. A dedicated payload builder validates caller input and builds the exact form.
3. `SrtHttpClient.post_html_form()` validates canonical configuration and the
   exact method/host/path allowlist before I/O, then sends the form with the
   exact HTML accept and referer headers.
4. HTML framing returns the response text. A JSON object with a non-success
   `ErrorCode` raises `SrtAppError(raw=payload)`; every other JSON or non-HTML
   success shape raises `SrtProtocolError(raw=payload)` before client parsing.
   Both errors preserve raw diagnostic data on `.raw`, while their string and
   repr rendering remain redacted and never include that raw payload.
5. `parse_html_page(..., require_authenticated=True)` rejects empty bodies and
   recognizes an actual login form as `SrtSessionExpiredError`.
6. `_session_guard()` clears cookies/current session on expiry and re-raises.
7. A valid response is returned as `HtmlPage`.

The client does not parse selector choices from DOM structure. Callback field
names can appear in sanitized fixtures as evidence, but they are not converted
into a new unstable model.

## Safety Policy

Add only these app routes:

```text
POST /common/ARA/ARA0501P/view.do
POST /common/ARA/ARA0502P/view.do
POST /common/ARA/ARA0403P/view.do
POST /common/ARA/ARA0901P/view.do
POST /common/ARA/ARA0701P/view.do
POST /common/ARA/ARA0201V/view.do
```

The SRT route count becomes 18. The NetFunnel route and exact query validator
remain unchanged, so only `act_10` is callable. No `act_19`, seat page,
reservation, ATA/ARD, native bridge, or external origin is added.

## Live Verification

The existing live helper calls the six selectors after the booking page is
loaded and before train search. It uses the existing `TrainSearchQuery` values
for station, date, passenger, seat-option, and train-group inputs.

The result adds only:

```python
{
    "selectorLoadedCount": int,
}
```

`selectorLoadedCount` is `sum(bool(page.text) for page in selectors)`: it counts
selector pages with nonempty extracted text, not merely completed requests. A
value of `6` therefore means all six pages produced text. A valid markup-only
`HtmlPage` may contribute zero and lower the count without itself being a
request failure. Transport, app, protocol, and session failures still raise
their existing typed errors. No popup HTML, extracted text, callback value,
credential, cookie, or NetFunnel key is returned or printed.

## Test Strategy

Every behavior is developed with a failing test first.

- Exact acceptance of the six new routes and rejection of wrong methods,
  off-origin URLs, encoded bypasses, and neighboring paths before transport.
- One exact path/form/accept/referer test per public method.
- Validation of station inputs, date/hour shape, passenger totals, seat-option
  values, and train-group codes.
- Explicit regression coverage for all six passenger slots and
  `totalPessnger`.
- Nonempty HTML success through `HtmlPage`.
- JSON selector app failures become raw-preserving, redacted `SrtAppError`;
  every other JSON or non-HTML success shape becomes raw-preserving
  `SrtProtocolError` before `parse_html_page()`.
- Empty body protocol failure.
- Authenticated popup returning a real login form clears session/cookies and
  raises `SrtSessionExpiredError`.
- Public method-set/signature updates and a package-root `HtmlPage` import gate.
- Bounded live output with exactly six selector calls, a nonempty-text count
  from `0` through `6`, and no raw/text keys.
- Regression coverage proving NetFunnel URL/query construction and retry
  behavior are unchanged.

Use six small sanitized fixture pages, one per route. They may contain synthetic
callback field names but no account, cookie, PNR, ticket, seat, or NetFunnel
data.

## Files And Responsibilities

- `src/srt_mobile_api/safety.py`: add exactly six popup routes.
- `src/srt_mobile_api/payloads.py`: define six validated form builders.
- `src/srt_mobile_api/http.py`: provide `post_html_form()` and classify JSON
  framing before returning selector HTML to the client.
- `src/srt_mobile_api/errors.py`: let `SrtProtocolError` retain raw diagnostic
  framing without exposing it through string or repr rendering.
- `src/srt_mobile_api/client.py`: expose six guarded `HtmlPage` methods.
- `src/srt_mobile_api/__init__.py`: export the existing `HtmlPage` model from
  the package root so the documented return type is importable.
- `tests/fixtures/`: add six sanitized selector pages.
- `tests/test_safety.py`: lock exact route and bypass rejection behavior.
- `tests/test_netfunnel_payloads_parsers.py`: test selector payloads without
  altering NetFunnel behavior.
- `tests/test_client_read_apis.py`: test HTTP orchestration, JSON framing,
  raw-preserving typed errors, and session expiry.
- `tests/test_http.py`: retain HTTP framing, login-form, and redacted transport
  regression coverage around the new HTML form helper.
- `tests/test_redaction_safety.py`: prove typed exception rendering does not
  expose retained raw payload data.
- `tests/test_public_contract.py`: lock the expanded method set/signatures.
- `src/srt_mobile_api/live.py` and `tests/test_live.py`: add bounded selector
  live coverage.
- `README.md`: document the expanded read-only surface.
- `docs/IMPLEMENTATION_PROGRESS.md`: record final verification after the
  implementation is complete.

No new public model is required. `PassengerCounts` is already exported from the
package root; the existing `HtmlPage` model must be added to that root export and
covered by the public-contract and isolated-wheel import gates.

## Completion Criteria

- All six methods send the exact evidenced form to the exact canonical path.
- Valid pages remain `HtmlPage` compatible and session expiry stays typed.
- NetFunnel remains stateful and restricted to exact `act_10`.
- The full offline suite, wheel/sdist build, and isolated wheel root import of
  `HtmlPage`, `PassengerCounts`, and `SrtClient` pass.
- Bounded opted-in live verification reports `selectorLoadedCount` without raw
  data; `6` means all six pages had nonempty extracted text, while a valid
  markup-only page may lower the count.
- No seat-selection, mutation, native, ATA/ARD, external-seat-map, or sensitive
  material is added.
- The working tree remains uncommitted unless the user explicitly requests a
  commit.
