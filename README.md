# srt-mobile-api

This repository provides an installable read-only-by-default Python package for
the evidenced SRT Android app WebView API surface. Nothing is transmitted
without an explicit, per-category `MutationConsent` with `dry_run=False`: by
default the client transmits only login/read requests, and a mutation method
returns a redacted `MutationPreview` of the exact form that would be POSTed.

Two consent-gated mutation methods exist, `reserve` and `cancel`. Both preview
by default and both transmit when given an explicit `dry_run=False` consent for
their own category. A live `reserve` creates a **real unpaid hold on a real
account**, which the caller then owns. **One live reserve->cancel round trip was
performed on 2026-07-25** and both halves succeeded — reserve
`strResult=SUCC`/`msgCd=IRR000018`, cancel `strResult=SUCC`/`msgCd=IRG000000`,
with no trace of the reservation left in the ticket list. It covered one adult,
one journey, a general seat, one train; nothing broader is claimed, and payment
and refund remain unimplemented and untransmittable.

Which mutations may reach the network at all is enforced at the transport
layer, by two different mechanisms which are worth keeping distinct:

- the read-only send path refuses the four mutation routes **by allowlist** —
  they are deliberately not in `READ_ONLY_ROUTES`, so `assert_read_only_request`
  rejects them;
- `post_mutation_form`, the only method that can send a state-changing request,
  refuses every category outside `safety.SRT_LIVE_MUTATION_CATEGORIES`, which
  holds **exactly `{"reserve", "cancel"}`**. So `payment` and `refund` are
  rejected however permissive the caller's consent is, and neither has a client
  method to begin with. It separately refuses a `dry_run=True` consent, so a
  preview can never be transmitted either. `_send_mutation_request`, the
  function that actually calls `send`, re-asserts the same membership.

`reserve` and `cancel` are enabled together because they are the two halves of
one reversible operation: reserve creates an unpaid hold, cancel releases one
(from a hold object or a bare PNR string). Enabling reserve alone would mean a
crash mid-flow strands a real reservation with no programmatic way out. Opening
that gate was a decision about **recoverability, not evidence** — it is what
made the operator-run reserve->cancel round trip possible, and that round trip
has since been run once (2026-07-25, see below). Adding `payment` or `refund` would require
implementing each (neither exists) and live-verifying its own wire format. The
retained APK specification and smoke tooling remain the evidence context for
that package.

The reviewed safety boundary contains 20 routes. The integrated 0.2.0 gate
recorded `587 passed, 1 deselected` (historical); after the additive
reservation-attempt response parser, the consent-gated reserve mutation
surface, the transport-layer live-mutation gate, the consent-gated cancel
surface, the two-category live enablement and the operator scripts landed, the
current offline suite at HEAD is
`912 passed, 1 deselected`. The deselected case is the
explicitly opted-in live-service test.

Internal editable installation and offline verification:

```bash
python -m pip install -e ".[test]"
PYTHONPATH="$PWD/src" pytest -q -m "not live"
```

The `-m "not live"` filter is the offline gate used by CI
(`.github/workflows/ci.yml`) and by [docs/RELEASE.md](docs/RELEASE.md); it
deselects the live-service test, which additionally requires an explicit
`SRT_MOBILE_API_LIVE=1` opt-in.

Release and handling documents:

- [docs/RELEASE.md](docs/RELEASE.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

The final merged library-oriented specification is:

- `docs/analysis/srt-app-api-library-spec-2026-07-09.md`

The reusable read-only smoke runner is:

- `scripts/srt_app_api_smoke.py`

### Live reserve->cancel verification (operator-run)

Two scripts exist for the one live run that would confirm the reserve and
cancel wire shapes. **Neither has been run yet.** Both create or release real
reservations on a real account.

`scripts/verify_reserve_cancel_roundtrip.py` performs the round trip: login,
search, pick one train that actually has a seat, reserve one adult, print the
PNR, cancel it immediately, then re-read the ticket list to confirm nothing
remains. It requires **two** explicit opt-ins, so it can never fire from an
ordinary live smoke run:

```bash
SRT_MOBILE_API_LIVE=1 SRT_LIVE_MUTATION=1 \
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... SRT_TEST_DATE=YYYYMMDD \
python3 scripts/verify_reserve_cancel_roundtrip.py
```

It reads the same journey variables as the live smoke runner
(`SRT_DEPARTURE_STATION_CODE`, `SRT_ARRIVAL_STATION_CODE`, `SRT_DEPARTURE_TIME`,
the station names and passenger counts), through that module's own helpers. It
refuses to proceed if no train is reservable, prints the raw `strResult`/`msgCd`
for both operations, and exits non-zero on any failure. Everything after a
successful reserve is wrapped so that a failed cancel is retried and, if that
also fails, the PNR is printed in a banner together with the exact recovery
command.

`scripts/recover_hold.py` is that recovery command — it cancels one hold given
nothing but its PNR:

```bash
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py <PNR>
```

It exits 0 only when the server reports the hold released, and reprints the PNR
in a banner on every other outcome. Neither script ever prints the password.

## Scope

This repository documents SRT Android app APIs under `app.srail.or.kr` and the
NetFunnel helper required by the app flow. It excludes external web APIs, real
payment authorization, and automatic production reservation creation.

## Local Artifacts

`srt.apk` and `build/` are intentionally ignored. They are local evidence
artifacts, not retained source files.

Expected APK identity if static evidence needs to be regenerated:

| Item | Value |
|---|---|
| SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| Size | `26,427,764` bytes |
| Package | `kr.co.srail.newapp` |
| Version | `2.0.41` / `versionCode=150` |

Regenerate evidence locally only when needed:

```bash
mkdir -p build
zipinfo -1 srt.apk | sort > build/apk-file-list.txt
apktool d -f srt.apk -o build/apktool
jadx -d build/jadx srt.apk
```

## Safety

Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or
card-shaped values in the repository. The smoke script reads credentials from
environment variables and does not issue reservation or payment requests.
`SrtConfig` pins app and NetFunnel traffic to the documented production HTTPS
origins; its host fields cannot be used to redirect requests to alternate servers.

## Python Package MVP

This repository now contains an installable Python client package under `src/srt_mobile_api`.

Default tests are offline:

```bash
pip install -e ".[test]"
pytest -q -m "not live"
```

### Typed raw-backed read results

Personal search accepts the exact mixed-case `ErrorCode`/`ErrorMsg` wrapper;
group search accepts the exact uppercase `ERROR_CODE`/`ERROR_MSG` wrapper.
Partial, duplicate, conflicting, and non-string wrapper pairs fail closed, and
an app-level wrapper error is raised before result datasets are considered.

`TrainSearchResult.metadata` provides repr-safe `TrainSearchMetadata` with the
message code/status, integer query count, and optional following-page flag. The
legacy raw `result` field and its positional slot remain available. Search rows
also expose optional consist/run order, delay, seat/wait/standing availability,
received-amount, and discount fields. When the server row omits station names,
the client can enrich them from the already-hydrated request form; blank or
code-only context does not invent a name.

`get_notice_list()` preserves its legacy raw `dict` result.
`get_typed_notice_list()` exposes the same one-request read as a
`NoticeListResult` containing typed `Notice` rows for the observed uppercase
seven-field contract. Notice bodies and raw mappings are excluded from
`repr()`. Timetable parsing skips leading empty cells before choosing the
station name. `FarePage.items` preserves its legacy numeric-only rows, while
`FarePage.semantic_items` also retains unavailable rows as
`FareItem(amount=None, available=False, status=...)`. These parser changes add
no route, seat-inventory, or mutation behavior.

### Bounded train-search pagination

`SrtClient.iter_train_search_pages(query, *, group=False, max_pages=10)`
lazily yields `TrainSearchResult` pages for personal or group search. Existing
`search_trains(query)` and `search_group_trains(query)` remain compatible
single-page calls.

The iterator obtains one `act_10` key, hydrates the search form, and preserves
the resulting key, passenger fields, `dptTm1`, and unknown hidden inputs across
continuation POSTs. Each continuation changes only `dptTm` to
`last_row.dptTm[:5] + "1"` and clears `trnNo`; the response-only `fllwPgExt`
field is never sent. Pages stay in server order and are neither accumulated nor
deduplicated.

Iteration stops at exact `fllwPgExt=N`, an empty page, a caller-supplied
`max_pages` bound, or caller closure. Missing or malformed metadata and
non-progressing/repeated cursors fail closed. If a continuation is rejected with
`NET000001`, only that cursor obtains one fresh key and hydration and is retried
once; earlier pages are neither replayed nor yielded again.

This contract comes from static SRT Android app 2.0.41 evidence and synthetic
offline request-sequence tests. Live continuation was verified in one bounded
2026-07-15 session: personal and group each returned two pages with 10 rows per
page. The iterator adds no route: the reviewed 20-route read-only boundary and all
reservation, payment, cancellation, refund, native-bridge, and external-seatmap
exclusions from the read-only allowlist remain unchanged.

### Read-only selector popups

`SrtClient` exposes the six runtime-evidenced selector popup reads:

- `get_station_selector(...)`
- `get_station_map_selector()`
- `get_date_selector(...)`
- `get_passenger_selector(...)`
- `get_seat_option_selector(...)`
- `get_train_group_selector(...)`

Each method posts only to its exact allowlisted `/common/ARA/` route and returns
the existing `HtmlPage`, so callers retain compatible `text` and `raw` access.
The live helper calls all six after booking-page hydration and reports only the
bounded integer `selectorLoadedCount`; it never emits popup HTML or extracted
popup text.

These APIs select search-form preferences only. Reservation, payment, refund,
cancellation, `act_19`, ATA/ARD, native bridges, and external seat-map calls
remain outside the read-only allowlist.

### Physical seat-selection page read

`SrtClient.get_seat_page(train)` performs one authenticated read of the
internal SRT seat-selection HTML page for a complete server-returned SRT row.
The request defaults to general class, carries exactly thirteen allowlisted form
fields, and returns `SeatSelectionPage` after requiring the `좌석선택` marker.
Its `choiceSeatCount` is the party size, as the app's is
(`choiceSeatCount: lfn_getRsv("totPrnb")`, `ara1001l.js:1511`): pass
`passengers=` and the count is derived from the total, or `seat_count=` to
override it explicitly. With neither it is one seat.

This method does not select or hold a seat. It does not call NetFunnel
`act_19`, submit a reservation, follow the external Korail seat map, execute
JavaScript/callbacks, retry, or scan fallback trains. The live helper reports
only bounded booleans and never emits the page body.

The internal SRT page was loaded, but the retained sanitized schema-v2 evidence
proves only a bounded car/UI candidate and a static Ajax handoff. It does not
prove a stable iterable physical-seat record or availability vocabulary, so
individual physical seats remain untyped.

### Bounded seat-layout evidence gate

`scripts/capture_seat_layout_evidence.py` is a separately invoked internal
evidence command. It requires `SRT_MOBILE_API_LIVE=1`, the existing live
credential environment variables, and `SRT_TEST_DATE`. Its complete operation
budget is exactly one `SrtClient.login` call, one `SrtClient.search_trains`
operation, and zero or one `SrtClient.get_seat_page` call for the first complete
SRT row. When no complete row exists, it makes no seat-page request.

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
PYTHONPATH="$PWD/src" python3 scripts/capture_seat_layout_evidence.py \
  --output /tmp/srt-seat-layout-evidence.json --force
```

The command writes one deterministic `schema_version: 2` report through a
temporary sibling and atomic replace. It classifies embedded DOM/JSON
candidates, generic scripts, same-origin script/form/iframe references, static
Ajax contracts, cross-origin reference counts, and external seat-map handoffs.
A generic script alone produces `no_inventory_source`; it is not evidence of a
seat inventory source.

The parser analyzes only the already-returned HTML. It does not execute
JavaScript or follow a script, form, iframe, Ajax route, external handoff, or
callback. Same-origin targets and inline route literals are retained only as
query/fragment-free static `.do`/`.js`/`.mjs` paths without dynamic seat/car
segments; cross-origin targets are counts/categories only. Inline scripts retain bounded
lengths, truncation flags, and SHA-256 digests of the captured prefix—not source
text or the truncated tail. JavaScript strings/comments cannot create structural
inventory evidence; backtick and ambiguous slash tails are masked
conservatively. `application/json` blocks retain only bounded key/type,
array-cardinality, depth, and inventory-name summaries after dynamic seat keys
are discarded. Static JavaScript payload metadata accepts only unquoted safe
simple key names; quoted object keys are ignored.

Raw HTML, visible text, attribute/input values, element IDs, query strings,
arbitrary URLs, train/car/seat values, credentials, cookies, tokens, and
exception messages are never written. Typed cars and physical seats remain
unimplemented until separately authorized response evidence identifies a stable
iterable source and availability vocabulary. Schema-v2 evidence does not
authorize another origin, route, or mutation.

The exact sanitized offline-replay report is retained as
`tests/fixtures/seat_page_schema_v2_evidence.json`. Its regression test locks
the complete nested schema, canonical digest, zero offline call counts, and the
existing fail-closed safety scan. The fixture stores only bounded structural
metadata: no raw body, visible value, dynamic identifier, credential, cookie,
or session scalar.

That evidence proves one static same-origin `POST` reference to
`/arc/selectListArc02011_n.do` and a separate self-target form summary with
these 11 input names: `trnGpCd`, `runDt`, `trnNo`, `scarNo`, `psrmClCd`,
`dptRsStnCd`, `arvRsStnCd`, `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, and
`choiceSeatCount`. The retained fixture does not prove that the script
serializes that form, the controls' input types, the response grammar, or the
DOM sink. It exposes no iterable response schema. Arc02011 is not allowlisted,
there is no closed response parser, and the client neither calls nor implements
it.

The same bounded 2026-07-15 session loaded one seat page from the first
complete personal-search row. The fixed live summary reported the visible
marker, 9 scripts, 3 forms, no iframe, no embedded JSON block, 5 source
categories, and `sufficiency=inventory_source_candidate`; it emitted no raw
HTML or identifiers. A later authorized offline replay produced only the
sanitized fixture described above. Together they prove a candidate source and
the static handoff, not an iterable car/seat response or availability
vocabulary, so typed physical seats remain excluded.

### Mutual verification

`get_mutual_verification()` manually performs the evidenced empty-form mutual
verification read and returns a repr-safe `MutualVerificationResult`. It is not
called automatically by login or search and does not start seat selection or a
reservation. The opted-in live helper calls it only after personal search and
reports `mutualVerificationLoaded`, never the verification value or raw JSON.

Live smoke is opt-in and limited to login plus read/query calls:

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
export SRT_DEVICE_KEY="<device-key>"
export SRT_CHILD_COUNT=1
python3 -c "from srt_mobile_api.live import run_live_smoke_from_env; print(run_live_smoke_from_env())"
```

The live helper reports only booleans and bounded counts. It exercises one
non-adult passenger mapping in the example above and contains no `act_19` or
reservation path.

### Offline reservation-attempt response parsing

`parse_reservation_attempt_response()` is a pure offline parser for the
documented reservation-attempt response shape
(`resultMap`/`reservListMap`/`trainListMap`/`commandMap`). It accepts
caller-supplied JSON and returns a typed `ReservationAttemptResult` for a
complete success shape; malformed or rejected shapes raise the existing
protocol/app error types. Server message, temporary job sequence, command map,
and the raw mapping are excluded from `repr()`. This parser itself adds no
route, request builder, NetFunnel `act_19` flow, client method, or live call,
and leaves the reviewed 20-route read-only boundary unchanged; the reservation
surface described next was added separately.

### Consent-gated mutation surface

Two consent-gated methods are implemented and offline-tested:

- `reserve` (`arc/selectListArc05013_n.do`, `jobId=1101` personal) previews by
  default. Given a `dry_run=False` reserve consent it transmits and returns an
  `SrtReservationHold` whose `pnr_no` feeds `cancel`. It obtains its NetFunnel
  key from the **same `act_10` flow as train search** (srtgo `srt.py:987`; *not*
  `act_19`), reusing `_get_act10_key` rather than a second acquisition path; a
  caller-supplied `netfunnel_key` is honoured verbatim and suppresses the
  acquisition. A failed reserve is never retried, so at most one hold can exist
  per call. If strict parsing trips over an unrelated malformed field after the
  server has already created the hold, a degraded but **cancelable** hold is
  returned rather than raising — losing a PNR is the worst outcome this method
  can produce. Its live NetFunnel/referer wiring was accepted by the server in
  the 2026-07-25 round trip below.
- `cancel` (`ard/selectListArd02045_n.do`, unpaid reservation) accepts an
  `SrtReservationHold` or a bare PNR string and previews by default. Given an
  explicit `dry_run=False` cancel consent it transmits, and returns a parsed
  `SrtCancelResult` (a business failure is carried as data, not raised). **Its
  wire shape — the route, the `pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"` body and the
  `strResult == "SUCC"` success rule — was verified against the live server on
  2026-07-25**, answering `SUCC` / `msgCd=IRG000000` / `정상처리되었습니다` and
  leaving no trace of the reservation in the ticket list. That shape came from
  srtgo and is 0-hit across all 21,673 files of our v2.0.41 offline bundle
  (only the `jrnyCnt="1"` value is partially corroborated by our own app,
  `ara0101v.js:92`), so the single live run is its only corroboration — and it
  exercised one adult on a **single journey**, which is the only case for which
  `jrnyCnt="1"` is confirmed.

The live verification (2026-07-25) was one run of
`scripts/verify_reserve_cancel_roundtrip.py` against a real account: 수서→부산,
one adult, general seat, one train. `reserve` returned `strResult=SUCC`,
`msgCd=IRR000018` ("결제하지 않으면 예약이 취소됩니다.") and a PNR; `cancel`
returned `strResult=SUCC`, `msgCd=IRG000000`; the ticket list re-read afterwards
contained no trace of it, re-verified independently in a later session. The hold
was never paid, so nothing was charged. Incidentally, those two confirmation
codes are the same ones korail's live-verified reserve and cancel return, which
suggests the two operators share a reservation platform — an observation, not a
proven fact about the backend. Not covered by that run: multi-leg (`jrnyCnt` >
1), group, standby, and anything to do with payment or refund.

Payment and refund are tiered routes only — no client method exists for them,
and their wire formats are likewise 0-hit across all 21,673 files of the v2.0.41
offline evidence bundle, so they need live response capture (see
docs/MUTATION_HANDOFF.md in the korail repo). The 2026-07-25 round trip taught
nothing about either: it never paid the hold, so no payment or refund shape was
observed. Native-bridge and external seat-map flows remain excluded entirely.

Independently of which methods exist, `payment` and `refund` cannot be
transmitted at all: `post_mutation_form` and `_send_mutation_request` both
refuse any category outside `safety.SRT_LIVE_MUTATION_CATEGORIES`, and the
read-only guard refuses all four routes by allowlist.
