# SRT Seat Selection Page Read Design

Date: 2026-07-14
Status: Implemented and bounded-live-verified on 2026-07-14 (page read only; physical-seat schemas remain unimplemented)

## Context

The client currently implements nineteen exact read-only SRT and NetFunnel
routes. Physical seat selection is deliberately excluded because it sits next
to reservation execution, even though the first SRT seat-page request is a
page-rendering read rather than an inventory mutation.

Retained runtime evidence identifies one internal SRT endpoint:

```text
POST https://app.srail.or.kr/arc/selectListArc02012_n.do
```

The response is authenticated HTML whose extracted text contains
`좌석선택`. The retained evidence does not include a raw HTML fixture, so it
does not prove a car-grid or per-seat DOM schema. The page may delegate the
actual visual map to an external Korail URL, which remains outside this
library.

## Decision

Implement an evidence-gated seat-page read:

1. Expose the authenticated internal SRT seat-selection HTML page.
2. Perform exactly one bounded live read to obtain a sanitized fixture.
3. Add typed car and seat parsing only if that fixture proves a stable,
   self-contained internal DOM contract.
4. If the internal page contains no physical inventory, finish this increment
   with the typed page wrapper and document that individual seats remain
   unavailable without the excluded external map.

This design supersedes only the prior exclusion of
`/arc/selectListArc02012_n.do`. All reservation, payment, cancellation, native
bridge, and external-seatmap exclusions remain in force.

## Goals

- Read the internal seat-selection page for a server-returned SRT train.
- Preserve the three search-row fields required by the seat-page request as
  explicit typed attributes.
- Enforce the exact route and exact form contract before network I/O.
- Return a typed HTML page without executing scripts, following links, or
  invoking callbacks.
- Inspect one sanitized live response and parse only structures demonstrated
  by that response.
- Keep the smoke test bounded, non-mutating, and free of raw response output.

## Non-goals

- Selecting or holding a seat.
- Calling NetFunnel `act_19`.
- Submitting personal or group reservations.
- Calling any `/ard/` or `/ata/` route.
- Following `https://www.korail.com/...srtJob=seatmap`.
- Executing page JavaScript, native bridges, or seat-selection callbacks.
- Inventing a physical-seat model from static callback names alone.

## Public API

The client adds one method:

```python
def get_seat_page(
    self,
    train: TrainSummary,
) -> SeatSelectionPage:
    ...
```

The first increment deliberately supports only the exact retained successful
contract: general class (`psrmClCd="1"`) and one seat
(`choiceSeatCount="1"`). Broader room-class or passenger-count inputs are not
part of the public API until a separate runtime fixture proves their accepted
values.

`SeatSelectionPage` extends the existing `HtmlPage` contract so callers retain
access to normalized text and raw HTML. It may gain typed car/seat collections
in this increment only after the live fixture proves their fields and states.
No public placeholder fields are added speculatively.

## Search Model Changes

`TrainSummary` adds optional, append-only fields populated from the search
response row:

```python
departure_run_order: str | None = None
arrival_run_order: str | None = None
seat_attr_code: str | None = None
```

They map to `dptStnRunOrdr`, `arvStnRunOrdr`, and `seatAttCd`. Keeping them
typed avoids constructing a safety-sensitive request directly from the
unvalidated `raw` mapping. Existing constructor calls remain compatible
because the fields are optional and appended.

## Request Contract

The payload builder emits exactly these thirteen form fields:

```text
reqCode
runDt
dptDt
trnNo
dptTm
trnGpCd
dptRsStnCd
arvRsStnCd
psrmClCd
seatAttCd
dptStnRunOrdr
arvStnRunOrdr
choiceSeatCount
```

The builder requires all train-derived values, validates date/time and
numeric-code shapes, requires `trnGpCd == "300"`, fixes `reqCode == "9"`,
`psrmClCd == "1"`, and `choiceSeatCount == "1"`. It serializes `trnNo` as
`train.train_no.zfill(5)` after rejecting non-numeric or overlong values.
Missing or invalid data raises `ValueError` before network I/O.

The transport safety layer receives the prepared `httpx.Request`, not only its
method and URL. For this route it rejects every URL query parameter, requires
the expected form content type, parses the encoded body without collapsing
duplicates, and requires every allowed key exactly once with the fixed values
above. This second check prevents a future caller from reusing the newly
allowlisted path with reservation-adjacent fields. Unknown or duplicate keys,
including `netfunnelKey`, `mutMrkVrfCd`, PNR/JRNY keys, passenger fields,
`scarNo*`, and `seatNo*`, are rejected.

## Client and Parsing Flow

```text
authenticated session
  -> personal SRT search
  -> server-returned TrainSummary
  -> exact seat-page payload
  -> exact internal POST once
  -> existing authentication-page checks
  -> SeatSelectionPage
```

`get_seat_page` uses the existing session guard and authenticated HTML POST
path. It does not acquire a NetFunnel key or make any preparatory mutual,
reservation, external-map, or retry request.

The first parser requires the normalized extracted text to contain the
evidenced `좌석선택` marker and preserves the HTML using the existing page
conventions. A login page uses the existing authentication error; missing
marker or another unexpected response raises the existing protocol error. The
parser does not evaluate scripts or interpret callback values as selected
seats.

After the single live response is sanitized into a test fixture:

- If the HTML itself contains stable car, seat identifier, and availability
  fields, introduce typed immutable models based only on those fields and add
  fixture-backed parser tests.
- If it only contains navigation or an external-map handoff, do not add car or
  seat models. Return the page wrapper and record the evidence limitation.

## Safety Boundary

Only this route is added to the read-only allowlist:

```text
POST app.srail.or.kr/arc/selectListArc02012_n.do
```

The route count consequently changes from nineteen to twenty. The following
remain explicitly rejected:

- NetFunnel `act_19`.
- `/arc/selectListArc05013_n.do` and `/arc/selectListArc06014_n.do`.
- Other reservation-adjacent `/arc/` routes.
- Every `/ard/` and `/ata/` route.
- External Korail seat-map URLs.
- Native bridge and callback execution.

The page response is treated as inert data. No form found in it is submitted
and no link found in it is followed.

## Live Verification

The opt-in smoke extends the existing authenticated personal-search flow:

1. Log in using the existing environment configuration.
2. Run the existing personal SRT search.
3. Select the first `trnGpCd="300"` SRT train containing every typed field
   required by the seat-page contract. Availability-label semantics are not
   guessed and are not used for selection.
4. Call `get_seat_page` exactly once; it always requests general class and one
   seat in this increment.
5. Emit only bounded booleans such as `seatPageLoaded`,
   `seatSelectionMarkerPresent`, and `embeddedSeatInventoryDetected`.

There is no retry, fallback train scan, raw HTML output, selected-seat output,
or reservation call. The original response is never persisted. A minimal
synthetic fixture containing only the DOM needed for parser tests is created
from an in-memory inspection, then the repository is scanned for credentials,
cookies, tokens, dates, station/train identifiers, selected-seat values, and
external-map query values before commit.

## Testing

The implementation uses test-driven development and adds focused coverage for:

- Search-row mapping into the three new typed fields.
- Exact payload keys and values.
- Missing/invalid train fields and strict five-digit train-number encoding
  before I/O.
- Transport rejection of extra or reservation-adjacent fields.
- Transport rejection of query parameters and duplicate form keys.
- Successful authenticated HTML parsing and unexpected-page errors.
- Exactly one client POST with no NetFunnel or follow-up request.
- Public export and method signature stability.
- Route count twenty and continued rejection of every neighboring mutation
  route and external origin.
- Fixture-backed physical-seat parsing only if the live HTML proves it.

Verification is intentionally bounded: run focused tests before the live
request, run one opt-in live smoke, add fixture-backed parsing only if that
response proves it, and run the full unit suite once at the end. Avoid repeated
production requests.

## Acceptance Criteria

- A valid SRT search result can load the internal seat-selection page through
  the public client API.
- The request contains exactly the evidenced thirteen fields and is rejected
  before I/O when incomplete or out of bounds.
- The first increment always requests general class and exactly one seat, with
  a validated five-digit train number.
- The client performs no `act_19`, reservation, payment, external-map, script,
  callback, or retry action.
- Live output contains only bounded booleans and no raw or sensitive data.
- Typed physical-seat output exists only if supported by a sanitized fixture;
  otherwise the limitation is explicitly documented.
- Focused tests, the full unit suite, and the single live smoke pass.
