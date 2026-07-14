# SRT Mutual Verification Design

**Date:** 2026-07-13

**Status:** Implemented and bounded-live-verified on 2026-07-13

## Goal

Add the single runtime-evidenced SRT mutual-verification read as a manual,
typed API without adding physical seat selection, reservation execution, or an
automatic KORAIL interoperability flow.

## Evidence And Constraints

The retained bounded runtime sequence successfully sent an empty form to:

```text
POST https://app.srail.or.kr/ara/selectListAra10130_n.do
```

The response was a JSON object with `outDataSets.dsOutput0[0]` containing
`msgCd=IRZ000008`, `strResult=SUCC`, an optional `msgTxt`, and a non-empty
`mutMrkVrfCd`. The runtime call occurred after authenticated login and train
search, used the existing cookie jar, and sent the search-result page as referer.
It carried no PNR, reservation, passenger, train, payment, or `act_19` fields.

The minimum server prerequisite was not isolated to login versus search
hydration. The public method therefore remains manually callable, while the
bounded live helper invokes it only after a successful personal search and keeps
the evidenced search-result referer.

## Scope

### In scope

- One exact app-origin POST route.
- An empty form with the evidenced AJAX headers and referer.
- One typed, repr-safe result and strict success parser.
- Exact route, request, parsing, public-contract, redaction, live-helper, build,
  and bounded live verification.

### Out of scope

- Automatic invocation from login, search, fare, or another client method.
- The commented legacy path `ara/selectListAra10h01.do`.
- Physical seat selection at `/arc/selectListArc02012_n.do`.
- KORAIL client calls or cross-package orchestration.
- Reservation, `act_19`, ATA/ARD, payment, cancellation, refund, native bridge,
  or external seat-map flows.
- Any change to NetFunnel `act_10`, hydration, or one-retry behavior.

## Public API

`SrtClient` gains one explicit method:

```python
def get_mutual_verification(self) -> MutualVerificationResult: ...
```

The package root exports:

```python
@dataclass(frozen=True)
class MutualVerificationResult:
    message_code: str
    status: str
    message: str = ""
    verification_code: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
```

The verification code and raw mapping are available to an explicit caller but
are excluded from repr and every built-in log or live-summary path.

## Request Flow

The method runs inside `_session_guard()` and sends exactly an empty form through
`SrtHttpClient.post_form()`:

```python
client.http.post_form(
    "/ara/selectListAra10130_n.do",
    {},
    accept="application/json, text/javascript, */*; q=0.01",
    referer=f"{client.config.base_url}/ara/selectListAra10007_n.do",
)
```

The existing transport supplies form content type, canonical origin,
`X-Requested-With`, app user agent, and the current cookie jar. Route validation
occurs before I/O. The method does not acquire a NetFunnel key and does not call
search, seat selection, or reservation internally.

## Response Parsing

`parse_mutual_verification_response()` first validates top-level JSON framing.
If `ErrorCode` is a non-empty value other than `0`, it raises `SrtAppError` with
repr-safe raw retention. It requires `outDataSets` and normalizes `dsOutput0`
whether the server represents the single row as a list or object.

Success requires all of the following:

- `msgCd == "IRZ000008"`
- `strResult == "SUCC"`
- `mutMrkVrfCd` is a non-empty string
- `msgTxt`, when present, is a string

Wrong business codes or statuses raise `SrtAppError`; missing or malformed
framing raises `SrtProtocolError`. Login-form or redirect responses continue to
raise `SrtSessionExpiredError` and clear local session state through the guard.

## Safety And Redaction

The exact route count rises from 18 to 19. No other path is registered.
`mutMrkVrfCd`, `verification_code`, and spelling variants join the sensitive-key
redaction set. Neither rendered exceptions nor model repr may contain the code,
cookies, login values, raw response, or NetFunnel data.

The API is manual by design. Receiving a mutual-verification value does not
authorize or initiate a reservation or seat-selection flow.

## Live Verification

The existing opted-in live helper calls `get_mutual_verification()` after the
personal search has succeeded. It adds only:

```python
{"mutualVerificationLoaded": True}
```

The boolean is true only when the parser accepted the documented success code,
status, and non-empty verification value. The helper never serializes the value,
message, raw mapping, cookies, search result, ticket data, or credentials.

The six selector calls, group search, timetable, fare, ticket read, exact
NetFunnel `act_10`, and one-retry behavior remain otherwise unchanged.

## Testing

Offline TDD coverage must prove:

- only the exact POST route increases the registry to 19;
- the request has an empty form, exact AJAX accept header, canonical origin,
  exact search-result referer, and no NetFunnel or reservation data;
- list and object `dsOutput0` success framing parse identically;
- wrapper errors, wrong business codes, wrong status, missing code, malformed
  code/message types, missing datasets, and non-object rows raise typed errors;
- login-page and redirect expiry clears session state;
- the model, exception, redaction, and live outputs never render the code/raw;
- the public method set, signature, export, and all existing APIs remain stable;
- the live fake calls mutual verification after personal search and returns only
  the bounded boolean.

After focused tests, run the complete offline suite once, build wheel and sdist,
verify the new root export in a fresh environment, request an independent
read-only review, and run the bounded opted-in live helper once.

## Files Expected To Change

- `src/srt_mobile_api/safety.py`
- `src/srt_mobile_api/models.py`
- `src/srt_mobile_api/parsers.py`
- `src/srt_mobile_api/client.py`
- `src/srt_mobile_api/redaction.py`
- `src/srt_mobile_api/live.py`
- `src/srt_mobile_api/__init__.py`
- focused fixtures and tests under `tests/`
- `README.md`
- `docs/IMPLEMENTATION_PROGRESS.md`

