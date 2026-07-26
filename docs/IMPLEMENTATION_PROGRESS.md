# SRT Python Package Implementation Progress

Last updated: 2026-07-26 KST (version `0.2.0`; the consent-gated mutation port,
its transport-layer gate and the four-category live enablement are recorded
under `## Unreleased` in `CHANGELOG.md`). Entries dated before that describe the state at HEAD
`955de306` and are kept as the historical record.

## Current State

- Search parsing now distinguishes the exact observed mixed-case personal and
  uppercase group wrappers, rejects partial/dual/wrong-type pairs, and raises
  wrapper app errors before reading datasets.
- `TrainSearchMetadata`, typed optional search-row availability details, and
  hydrated request-context station-name enrichment are additive; legacy
  positional fields remain in place.
- `get_notice_list()` retains its legacy raw mapping contract; the additive
  `get_typed_notice_list()` exposes observed uppercase seven-field typed rows
  with body and raw data excluded from `repr()`. Timetable rows skip leading
  empty cells. `FarePage.items` remains numeric-only and the additive
  `semantic_items` retains both priced and unavailable semantic rows.
- These parser/model changes add no route, request, seat-info operation, or
  mutation behavior and were developed from shape-only evidence with synthetic
  fixtures.
- The package exports the pure offline `parse_reservation_attempt_response()`
  parser and typed repr-safe `ReservationAttemptResult` for the documented
  reservation-attempt response shape. It accepts caller-supplied JSON only and
  raises the existing protocol/app errors for malformed or rejected shapes.
  That parser itself added no route, request builder, `act_19` flow, client
  method, or live call; the reservation route, builder and client method came
  later with the consent-gated mutation port below.
- Internal release preparation is complete at current `HEAD`: typed-package
  metadata, source-manifest contents, an archive verifier, Python 3.11-3.14
  offline CI, and internal release/security/changelog guidance are present.
  This preparation changed no runtime request, route, credential, or live
  behavior and made no live request.
- The authenticated physical seat-selection page read is implemented as
  `get_seat_page(train) -> SeatSelectionPage`.
- Its request defaults to general class, and its `choiceSeatCount` is derived
  from the passenger total (`passengers=`), matching the app's
  `choiceSeatCount: lfn_getRsv("totPrnb")` (`ara1001l.js:1511`), with
  `seat_count=` as an explicit override and one seat as the fallback.
  Prepared-request validation requires no query and exactly thirteen unique
  allowlisted form fields before the single POST is sent.
- The manual mutual-verification method and repr-safe result are implemented.
- Version `0.2.0` adds
  `iter_train_search_pages(query, *, group=False, max_pages=10)` as a bounded,
  lazy personal/group search-page iterator. Existing personal and group search
  methods remain first-page-only and signature-compatible.
- Pagination preserves the hydrated form, unknown inputs, passenger state,
  `dptTm1`, and NetFunnel key. It advances only with the statically evidenced
  `last_row.dptTm[:5] + "1"` cursor, rejects malformed or non-progress state,
  and retries only one failed continuation cursor after one fresh hydration.
- Final whole-feature review hardening keeps the successful result's server
  message, verification code, and raw response out of `repr()` while leaving
  each value caller-accessible. Wrapper and business `SrtAppError` rendering
  now uses fixed local messages; the original response remains available via
  the repr-hidden `raw` attribute.
- The read-only transport boundary allows 22 exact read-only app/NetFunnel
  routes; every mutation route is excluded from it, so
  `assert_read_only_request` refuses all four. The 22nd is the refund's step-1
  read (`/atc/getListAtc14087.do`), classified as a read by inference rather
  than by proof -- see the comment on it in `safety.py`.
- A consent-gated mutation surface was subsequently added (see "Consent-gated
  mutation surface" below). All four categories are live-enabled at the
  transport layer: `reserve` and `cancel` as a pair (live-verified 2026-07-25),
  `payment` and `refund` as a pair (live-verified 2026-07-26). Implementing
  `pay_with_card`, `refund` and the refund's step-1 read
  `get_refund_ticket_info` did not open the gate; the live verification did.
  See "Card payment and refund" below.
- The prior Task 4 verification gate remains recorded: its full offline suite,
  package build, isolated wheel import, exact static boundary, independent
  review, and bounded live gate all passed.
- The bounded seat-layout evidence command now emits `schema_version: 2` with
  explicit source categories. A generic script is distinct from embedded
  DOM/JSON inventory candidates, static Ajax contracts, same-origin references,
  cross-origin reference counts, and external handoffs.
- The seat-layout evidence work changed neither the read-only route allowlist
  nor the mutation boundary. Typed physical seats remain excluded until
  separately authorized response evidence identifies a stable iterable source
  and availability vocabulary.
- Schema v2 introduces no public API or package-version change; the package
  remains `0.2.0`. Its exact operation budget remains one login, one personal
  search operation, and zero or one seat-page read for the first complete SRT
  row.
- The exact safe offline-replay report is retained as
  `tests/fixtures/seat_page_schema_v2_evidence.json`. Tests lock its full nested
  schema, canonical digest, zero offline call counts, and fail-closed safety
  scan; no raw body, visible value, or dynamic identifier is tracked.
- The fixture proves one static `POST /arc/selectListArc02011_n.do` reference
  and a separate self-target form summary with 11 input names. It does not
  preserve the form/script association, input types, response grammar, or DOM
  sink. Arc02011 is not allowlisted, there is no closed response parser, and no
  client route was added or called.

## Implemented Public Operations

- Login and local logout/session clearing
- Main and booking-page reads
- Notice-list read
- Ticket-list page read
- Personal train search
- Group train search
- Bounded lazy personal/group train-search page iteration
- Manual mutual-verification read
- Timetable read with structured rows
- Fare read with structured items and six passenger slots
- NetFunnel `act_10` queue protocol: acquisition (5101), bounded polling
  (5002) and slot release (5004), plus one fresh-key retry
- Station selector popup read
- Station-map selector popup read
- Date/time selector popup read
- Passenger selector popup read
- Seat-option preference selector popup read
- Train-group selector popup read
- Physical seat-selection page read returning `SeatSelectionPage`
- Refund step 1, the issued ticket's identity read (`/atc/getListAtc14087.do`)

The package also exports the offline `parse_reservation_attempt_response()`,
`parse_reservation_hold_response()` and `parse_unpaid_cancel_response()`
helpers; they perform no I/O and are not client routes.

The transport currently allows 22 exact read-only app/NetFunnel routes.
`act_19`, the app's own `Ard02017`/`Ard02018` WebView payment entry, other
ATA/ARD flows, native bridges, callbacks, and external seat-map calls are not
callable. Preview-by-default `reserve`, `cancel`, `pay_with_card` and `refund`
methods exist; all four transmit under an explicit non-dry-run consent for their
own category, and all four are live-verified. See the next section.

## Consent-gated Mutation Surface

- `SrtClient.reserve(train, *, consent, ...) -> MutationPreview |
  SrtReservationHold` requires an explicit `MutationConsent` with
  `allow_reserve=True` and an authenticated session. With the default
  `dry_run=True` it returns a redacted `MutationPreview` of the exact
  `arc/selectListArc05013_n.do` form and performs no I/O. With `dry_run=False`
  it transmits and returns an `SrtReservationHold`; **a success creates a real
  unpaid hold on a real account**, which the caller owns and must cancel or pay.
  The NetFunnel gate is the same `act_10` key flow as train search (srtgo
  `srt.py:987`, *not* `act_19`), so it reuses `_get_act10_key`; a
  caller-supplied `netfunnel_key` is honoured verbatim and suppresses the
  acquisition. The reserve POST is never retried — a retry could double-book —
  so at most one hold exists per call. Session expiry clears the session and
  re-raises, as for every other authenticated call.
- Losing a PNR is the worst outcome the reserve path can produce, so
  `parse_reservation_hold_response` salvages a minimal but **cancelable** hold
  when strict parsing trips over a field unrelated to the PNR, and refuses to
  manufacture one when the server declared a failure (an invented hold would
  make a caller stop trying to recover). `scripts/recover_hold.py` cancels a
  stranded hold from nothing but its PNR string.
- `SrtClient.cancel(reservation, *, consent)` releases a created-but-unpaid
  reservation via `ard/selectListArd02045_n.do`. It takes an
  `SrtReservationHold` or a bare PNR string (a caller recovering from a partial
  failure may have only the PNR), requires `allow_cancel=True` and an
  authenticated session, and with the default `dry_run=True` returns a redacted
  `MutationPreview` and performs no I/O. With `dry_run=False` it transmits and
  returns a parsed `SrtCancelResult`. **The route, its `pnrNo`/`jrnyCnt`/
  `rsvChgTno` body and its `strResult == "SUCC"` success rule were verified
  against the live server on 2026-07-25** — one round trip released a real hold
  and answered `SUCC` / `msgCd=IRG000000` / `정상처리되었습니다`. Their origin is
  unchanged: the shape came from srtgo and is 0-hit across all 21,673 files of
  the v2.0.41 offline bundle (only the `jrnyCnt="1"` value is partially
  corroborated, at `ara0101v.js:92`), so that one run is its only corroboration
  and it covered a **single journey, one adult** only.
  `jrnyCnt` defaults to `"1"` rather than being derived from the hold
  (the reserve response carries a seat count, not a journey count) and any
  supplied journey count is compared numerically, tolerating zero-padding, so a
  formatting difference can never make a hold uncancellable.
- `payment` and `refund` have client methods (`pay_with_card`, `refund`, and the
  refund's step-1 read `get_refund_ticket_info`) and are live-enabled as of
  2026-07-26; see "Card Payment and Refund" below.
- The four state-changing routes are tiered in `safety.SRT_MUTATION_ROUTES` and
  deliberately kept out of `READ_ONLY_ROUTES`, so the 22-route read-only
  allowlist and its guarantee are unchanged and `assert_read_only_request`
  refuses each of them. `SRT_MUTATION_ROUTE_CATEGORIES` binds each route to one
  consent category.
- **Which categories may transmit is enforced at the transport layer, and
  membership means one thing: a live run answered that category's own wire
  format.** `safety.SRT_LIVE_MUTATION_CATEGORIES` holds exactly
  `{"reserve", "cancel", "payment", "refund"}`;
  `SrtHttpClient.post_mutation_form` refuses every category outside it (however
  permissive the consent), and `_send_mutation_request` — the function that
  actually calls `send` — re-asserts the same membership, the route allowlist
  and the route/category binding. The guarantee does not depend on the client
  methods: reaching `SrtClient.http` directly cannot widen it.
- `reserve` and `cancel` were live-enabled **as a pair**, because they are the
  two halves of one reversible operation and enabling reserve without a
  transmittable cancel would strand a real hold on a crash. That was a decision
  about recoverability, not about evidence — opening the gate is what made
  running the round trip possible, and **it was run on 2026-07-25 and both
  halves succeeded** (see the section below). `payment` and `refund` were then
  opened on the same principle — a charge and its reversal, verified as one
  round trip so nothing could be stranded paid — after the 2026-07-26 run.
- The `cancel`/`payment`/`refund` wire formats are all still 0-hit across the
  21,673 files of the v2.0.41 offline evidence bundle and all still came from
  srtgo. One live run apiece now corroborates each shape on the live server;
  none of them is statically corroborated, and each run covered a single-journey
  one-adult case only.
- A payment additionally transmits a PAN in the clear and keeps a separate
  card-kind gate (exactly one of `fake_card_only` / `real_card_acknowledged`)
  behind the live-enablement one. That gate used to sit behind a closed door and
  is now the last check before a real charge.

## Card Payment and Refund (IMPLEMENTED, LIVE-VERIFIED 2026-07-26, LIVE-ENABLED)

Both surfaces build, gate, preview, transmit and parse.
`SRT_LIVE_MUTATION_CATEGORIES` holds `{"reserve", "cancel", "payment",
"refund"}`, and canary tests in four files pin the exact contents so a fifth
category cannot appear quietly.

**The verification, in two stages.** A free probe went first: a fake card and a
non-existent PNR were sent to both routes, and neither answered a 404 or an HTML
error shell. `/atc/getListAtc14087.do` returned
`{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"WRT300005",
"strResult":"FAIL","msgTxt":"조회자료가 없습니다."}]},"ErrorMsg":""}`, and the
payment route `/ata/selectListAta09036_n.do` returned `strResult=FAIL` /
`msgCd=WRT100170`. Proper business envelopes on both, which established that
`Ata09036` and `Atc14087`/`Atc02063` exist on our v2.0.41 app version without
spending anything — all three are srtgo-attested and 0-hit across the 21,673
files of that offline bundle.

**Then one real round trip:** 수서→동탄 (`0551`→`0552`, the shortest SRT hop),
2026-08-09, train 315, one adult, 7,500 KRW. Payment (`Ata09036`) answered
`strResult=SUCC` / `msgCd=IRT000000`; the two-step refund
(`Atc14087`→`Atc02063`) answered `strResult=SUCC` / `msgCd=IRT200277`; the
account was then verified empty of both reservations and tickets from a separate
session. Both routes are therefore **live-verified on 2026-07-26** for a
single-journey, one-adult ticket, and both remain 0-hit in the v2.0.41 bundle
and srtgo-sourced — statements about different evidence, both true.

**Two open questions this closed.** `IRT000000` and `IRT200277` are identical to
korail's confirmation codes for the same two operations, reinforcing the
shared-platform observation already recorded here for `IRR000018`/`IRG000000` —
an observation about the codes, not a proven claim about the backend. And
srtgo's refund spellings `tkRetPwd`/`psgNm`/`pnr_no` are **correct**: the live
run sent them and the server refunded the ticket, so the doubt recorded below is
resolved in srtgo's favour, unlike srtgo's korail `txtPrnNo` which really was a
typo. srtgo was wrong there and right here; single-source field names have to be
tested one at a time, not trusted or distrusted as a class.

**What the run did not settle** is everything below this paragraph: the origin
is unchanged, and the run covered one single-journey, one-adult, general-seat
ticket paid with one personal card in one lump sum. Group, multi-leg, standby,
corporate cards and instalments were not exercised.

- `SrtClient.pay_with_card(reservation, card, *, consent, ...)` builds the
  31-field 카드결제 form for `/ata/selectListAta09036_n.do` from an
  `SrtReservationSummary` row and an `SrtPaymentCard`, and parses the response.
- `SrtClient.get_refund_ticket_info(pnr) -> SrtRefundTicketInfo` is refund step 1
  (`/atc/getListAtc14087.do`, no body, Referer-gated on the PNR, payload at
  `outDataSets.dsOutput1[0]`); `SrtClient.refund(ticket_info, *, consent)` is
  step 2 (`/atc/selectListAtc02063_n.do`).

**The two reference libraries are ONE source, and this was verified rather than
assumed.** srtgo's payment dict is character-for-character identical to
ryanking13/SRT's once the latter's Korean trailing comments are stripped — same
keys, same values, same non-alphabetical order, same local variable names, same
signature. srtgo depended on `SRTrain` (ryanking13/SRT on PyPI) until commit
`8423f90` "Internalize SRT" (2024-12-13) deleted the dependency and added
`srtgo/srt.py` in one move with the payment dict already fully formed; its
README credits ryanking13 under MIT. `srtgo_plus` is a third copy, byte-identical.
For the REFUND the situation is worse: ryanking13/SRT has no refund at all, so
srtgo is the sole origin (added 2024-12-17, four days after vendoring) and there
is no upstream to have agreed with it.

**The blanket "every field name is 0-hit" claim is FALSE**, and the precise
version is what got recorded. The three ROUTES (`Ata09036`, `Atc14087`,
`Atc02063`) are genuinely absent from all 21,673 files, as are the distinctive
field names (`stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`, `athnVal1`, `stlDmnDt`,
`totNewStlAmt`, `mnsStlAmt1`, `ogtkSaleDt`, `ogtkRetPwd`, `cnc_dmn_cont`,
`tkRetPwd`, `psgNm`, `pnr_no`, …). But seven tokens DO hit: `mbCrdNo`
(`ara0101v.js:319,321`), `totPrnb` (`ara1001l.js:104,368,1511,1655`), `jrnyCnt`
(`ara0101v.js:92,311`), and `buyPsNm`/`saleWctNo`/`saleSqno`/`retPwd` — the last
four only inside `webview/b.java:606-649`, which deserialises the base64
SharedPreferences key `"ticketListOffline"` into a display model. They are
offline-reservation-JS variables and local cache keys, never an `Ata09036` or
`Atc02063` request field.

**Our app does not use the payment path at all.** `ara1001l.js:1550` serialises
`#rsvForm` and `:1599`/`:1608` aim it at `Ard02018` (group) / `Ard02017`
(personal), server-rendered WebView pages, and the charge runs through the
TransKey secure keypad (`AndroidManifest.xml:143`, `bridge.js:2,31,66-68`) and
RaonSecure FIDO (`:315`). Whether the plaintext endpoint was a legacy path the
server still honours or dead for our app version was the open question; the
2026-07-26 charge answered it. The server still honours it, even though our app
never takes it.

**Amount fidelity** was decided deliberately, against korail's precedent
(`h_tot_prc` 59,800 vs `h_tot_rcvd_amt` 83,700 on a special-class ticket). The
form takes `rcvdAmt` (수납금액, post-discount, collectable) for both
`totNewStlAmt` and `mnsStlAmt1` and has **no caller override**; the list price
`stdrPrc` is reachable only through the fare page and is deliberately not wired
in. A missing, non-numeric or zero amount is refused rather than defaulted.
Unresolved: the server sends the amount zero-padded, ryanking13/SRT posts it back
padded, srtgo casts to `int`; we reproduce srtgo's bare digits because only
srtgo's form has live attestation.

**The refund's field names were disputed, and the live run settled them** —
srtgo's `tkRetPwd`/`psgNm`/`pnr_no` against our app's cache spellings
`retPwd`/`buyPsNm`/`pnrNo`. A cache field name is not an API field name, and that
argument is now demonstrated rather than argued: on 2026-07-26 the form below
sent srtgo's three spellings and the server refunded the ticket. They are not to
be "corrected" to the cache spellings. The precedent that motivated the doubt
still stands — this project really did ship srtgo's `txtPrnNo` for korail's
`txtPnrNo` — and what it actually teaches is that srtgo was wrong there and
right here, so single-source field names have to be tested one at a time, not
trusted or distrusted as a class.

**Envelopes differ across the two routes and both are pinned.** The payment
answers in `outDataSets.dsOutput0[0]` — the only SRT mutation here that does —
while the refund answers in the ordinary `resultMap`. Both share
`_parse_result_envelope`, which routes through `normalize_result_row` and so
accepts either container, so no third envelope path was written and neither
parser hard-asserts an unverified layout. `SrtPaymentResult.succeeded` and
`.failed` are deliberately non-complementary: an unrecognised status is
*unknown*, because a blind payment retry can charge twice.

**The refund's two steps are separate methods on purpose.** A fused call would
fire step 1 — a real request — and only then hit the step-2 refusal, leaving a
live request behind for an operation that can never complete. Kept apart, a
refused refund makes zero requests, and a dry run needs no network at all.

**Safety additions.** `MutationConsent.real_card_acknowledged` (default `False`,
purely additive) ports the KORAIL real-card pattern: a payment must state
exactly one of `fake_card_only` or `real_card_acknowledged`; neither and both
are refused. Redaction gained the refund return password under all three
spellings, the purchaser/passenger names, `SrtPaymentCard`'s own attribute
names, and `pnr_no` — the last a **pre-existing hole**, since `redact_value`
masks a dataclass by field name and `pnr_no` is the attribute on
`SrtReservationHold` and `SrtReservationSummary`.

## Live Reserve->Cancel Verification (RUN ONCE, 2026-07-25 — PASSED)

- `scripts/verify_reserve_cancel_roundtrip.py` is the operator-run verification
  of reserve's live NetFunnel/referer wiring and of cancel's body (which came
  from srtgo and is 0-hit in our v2.0.41 bundle). **It was run once, on
  2026-07-25, and exited 0.**
- What the run did: 수서 (0551) → 부산 (0020), departure date `20260805`, train
  `303` at 06:00, one adult, general seat.
  - `reserve` (`arc/selectListArc05013_n.do`): `strResult=SUCC`,
    `msgCd=IRR000018`, `msgTxt="결제하지 않으면 예약이 취소됩니다."`, PNR issued.
  - `cancel` (`ard/selectListArd02045_n.do`, body `pnrNo` / `jrnyCnt="1"` /
    `rsvChgTno="0"`): `strResult=SUCC`, `msgCd=IRG000000`,
    `msgTxt="정상처리되었습니다"`.
  - The ticket list re-read afterwards contained no trace of the PNR, and a
    separate later session independently re-confirmed that the account carries
    no PNR-like token from it. The hold was never paid, so nothing was charged.
    The PNR itself is deliberately not recorded in this repository.
- What it confirms: the cancel route and its exact three-field body work against
  the live server for our app version — until this run its shape was attested
  only by srtgo and had zero hits in our v2.0.41 offline decompile. It also
  confirms reserve's live wiring: the NetFunnel `act_10` key flow (the same one
  train search uses, *not* `act_19`) and the referer the client sends were both
  accepted by the server.
- What it does **not** confirm: only one single-journey, one-adult, general-seat
  round trip was exercised. Multi-leg (`jrnyCnt` > 1), group and standby
  reservations were not, so `jrnyCnt="1"` is confirmed for the single-journey
  case only. `payment` and `refund` were unimplemented at the time of this run
  and outside `SRT_LIVE_MUTATION_CATEGORIES`; nothing was learned about their
  shapes here. They were implemented, then verified in their own round trip on
  2026-07-26 and live-enabled — see "Card Payment and Refund" above.
- Observation worth recording: both confirmation codes match the sibling korail
  app's live-verified ones (reserve `IRR000018`, cancel `IRG000000`), suggesting
  the two operators share a reservation platform. Recorded as an observation
  about the code space, not as a proven claim about the backend.
- It requires two explicit opt-ins, `SRT_MOBILE_API_LIVE=1` **and**
  `SRT_LIVE_MUTATION=1`. The second exists because the first only means "live
  reads are acceptable", which is not consent to create a reservation.
- Flow: login, search, select ONE train with a genuinely bookable seat
  (refusing to proceed if none), reserve one adult, print the PNR before
  anything else, cancel immediately, then re-read the ticket list to confirm no
  trace remains. Reserve and cancel run under separate single-category
  consents. The raw `strResult`/`msgCd` are printed for both operations.
- Everything after a successful reserve is wrapped in `try`/`finally`. The
  `finally` retries the cancel if it has not already succeeded — safe in a way a
  reserve retry is not, since cancelling twice cannot create anything — and if
  that also fails it prints the PNR in a banner with the exact
  `scripts/recover_hold.py` command line. A stranded hold whose PNR the operator
  does not know is the worst outcome, and the script is designed against it
  above all else.
- Journey parameters are read through `srt_mobile_api.live`'s own env helpers
  (`read_query_from_env` and friends), the same ones `run_live_smoke_from_env`
  uses, so the two tools cannot drift apart.

## Bounded Seat-Layout Evidence Gate

Run `scripts/capture_seat_layout_evidence.py` only with explicit live opt-in,
the existing live credential environment variables, `SRT_TEST_DATE`, and an
explicit output path:

```bash
SRT_MOBILE_API_LIVE=1 PYTHONPATH="$PWD/src" \
  python3 scripts/capture_seat_layout_evidence.py \
  --output /tmp/srt-seat-layout-evidence.json --force
```

The command permits exactly one login call, one personal train-search operation
with its already-reviewed internal hydration/NetFunnel behavior, and zero or one
seat-page call for the first complete SRT row. It calls no broad smoke helper,
adjacent read, external handoff, callback, or mutation route.

The output is a deterministic bounded `schema_version: 2` structural report.
It records explicit `source_categories`, structural-name/count summaries,
same-origin query/fragment-free paths, cross-origin counts, script type/flag and
static Ajax metadata, bounded inline-script lengths and captured-prefix SHA-256
digests, form and iframe metadata, and bounded
`application/json` key/type/cardinality summaries. JavaScript strings/comments,
dynamic JSON seat keys, and dynamic seat/car path segments are discarded.
Generic scripts alone remain `no_inventory_source`; only concrete inventory
candidates or references can promote sufficiency.

The parser executes no JavaScript and follows no script, form, iframe, Ajax
route, callback, or external handoff. Raw HTML, visible text, attribute/input
values, element IDs, query strings, arbitrary URLs, raw script, credentials,
cookies, tokens, dates, stations, train/car/seat values, and exception messages
are forbidden. The serialized report is fail-closed scanned before a sorted
UTF-8 temporary sibling is atomically replaced into the requested path.

Typed cars and physical seats remain blocked until separately authorized
response evidence identifies a stable iterable car/seat source and availability
vocabulary. No schema-v2 category widens the origin, route, or mutation
boundary.

The retained sanitized fixture proves the exact schema-v2 report shape, one
static same-origin Ajax signal (`POST /arc/selectListArc02011_n.do`), and a
separate self-target form summary containing exactly `trnGpCd`, `runDt`,
`trnNo`, `scarNo`, `psrmClCd`, `dptRsStnCd`, `arvRsStnCd`, `seatAttCd`,
`dptStnRunOrdr`, `arvStnRunOrdr`, and `choiceSeatCount`. It does not retain the
form/script association, input types, response grammar, callback behavior, or
DOM sink, and no iterable JSON or availability schema is evidenced. Arc02011
is not allowlisted, there is no closed response parser, and the current client
does not call it.

The single authorized live evidence attempt on 2026-07-14 failed closed at the
pre-client configuration gate with exit code 2. Network operation counts were
`login=0`, `search=0`, and `seat_page=0`; no fixed report status was emitted and
the sufficiency category is `unavailable`. No page booleans or structural counts
exist for this attempt. Typed physical-seat layout evidence is therefore
unavailable, and typed seats remain blocked. No raw evidence or temporary JSON
artifact was persisted.

The schema-v2 implementation and its offline verification made no live request
and did not read credentials. A later combined 2026-07-15 run used one login
session and retained fixed statuses and counts only. Personal and group
pagination each yielded two 10-row pages, proving a continuation was observed.
The first complete personal row loaded one seat page with the visible marker,
9 scripts, 3 forms, no iframe, no embedded JSON block, 5 source categories,
and `sufficiency=inventory_source_candidate`. No raw HTML, train/car/seat value,
credential, cookie, or token was printed or persisted. The later authorized
offline replay retained only the bounded structural fixture described above.
The candidate classification and static handoff are not yet a stable iterable
car/seat response or availability contract.

## Verification

- Raw-backed parser TDD RED: `34 failed, 13 passed`, covering exact wrapper
  casing/pairs, timetable leading cells, typed notices, lossless fare rows,
  typed search metadata/details, and station-name enrichment.
- Raw-backed parser focused GREEN: `50 passed`; the broader parser/model/client
  contract gate reported `277 passed` before final focused additions.
- Current raw-backed parser full offline gate: `559 passed, 1 deselected`; the
  deselected test is the explicit live-service opt-in. No live request,
  credential read, environment-file read, or captured raw body was used.
- Seat-layout evidence v2 TDD RED: `7 failed, 14 passed`; each failure was the
  intentionally absent v2 schema/classification behavior.
- Seat-layout evidence v2 focused GREEN: `22 passed`.
- Seat-layout evidence v2 full offline gate: `501 passed, 1 deselected`; the
  deselected case was the explicit live-service test. `git diff --check` was
  clean, and no live request or credential access occurred.
- Final evidence-redaction review RED: `5 failed, 21 passed`, covering
  JavaScript string/comment false positives, dynamic JSON keys and paths,
  explicit port zero, and oversized-script tail hashing.
- Final evidence-redaction focused GREEN: `26 passed`.
- Evidence-redaction full offline gate: `505 passed, 1 deselected`.
- Final alphanumeric-seat review RED: the focused regression failed once on
  `seatA1`; after widening the value-shape filter the focused suite reported
  `27 passed`.
- Alphanumeric-seat review full offline gate: `506 passed, 1 deselected`.
- Final ambiguous-script RED: `3 failed, 27 passed`; nested templates and regex
  literals were misclassified, and a safe `.mjs` module reference was omitted.
- Final ambiguous-script focused GREEN: `30 passed`.
- Ambiguous-script review full offline gate: `509 passed, 1 deselected`.
- Final quoted-key RED: the focused regression failed once because
  `"fetch(foo)"` was treated as executable structure. Quoted object keys are now
  fully masked; only unquoted safe simple payload keys are collected.
- Final quoted-key focused GREEN: `31 passed`.
- Sanitized schema-v2 fixture TDD RED: `1 failed, 31 deselected`; the fixture
  path was intentionally absent.
- Sanitized schema-v2 fixture focused GREEN: `1 passed, 31 deselected`; the
  tracked fixture was byte-for-byte identical to the reviewed safe report.
- Sanitized-fixture phase full offline gate: `512 passed, 1 deselected`; the deselected case is
  the explicit live-service test. No live request or credential access occurred.
- Live read-surface capture and verification, 2026-07-26
  (`scripts/capture_live_read_surface.py`, 21 of 22 steps reached across two
  routes): the login-redirect page (an expired session read as an empty ticket
  list), the fare page's placeholder transfer leg (three phantom `0원` fares
  under real labels), the timetable whose station names are absent from the
  markup, the sold-out seat page's error shell accepted as a seat page, JSON
  nulls in search rows, and the LIVE page's own JavaScript refuting our
  `trnSort` derivation and the fare form's passenger field names — the last of
  which the server had been silently ignoring, computing the page's estimated
  total as `0원`. Raw captures were written outside the repository; the
  committed fixtures are redacted.
- Live reserve->cancel round trip re-run 2026-07-26 (수서→천안아산, one adult,
  general seat): reserve `SUCC`/`IRR000018`, cancel `SUCC`/`IRG000000`, ticket
  list clean afterwards. No payment or refund call was made and no hold was left
  outstanding.
- Reservation-list read (`POST /atc/selectListAtc14016_n.do`) added and
  live-verified 2026-07-26 for the EMPTY case: `SrtClient.get_reservations` is
  the first read that enumerates reservations, and `scripts/recover_hold.py
  --list` now prints candidate PNRs instead of requiring one to be typed in.
  The server answered `resultMap[0].strResult=SUCC` / `IRZ000005` /
  "조회할 자료가 없습니다." with `trainListMap: []`, `payListMap: []`,
  `rowCnt: 0`, `totPageCnt: 0` — and a SECOND envelope, `rsMap[0]`, saying
  `FAIL` / `WRT300005` on that same successful response. The POPULATED row
  shape is unverified: every row field name comes from srtgo
  (`srt.py:1069-1082`), and `payListMap`, `tkSpecNum`, `iseLmtTm` and `stlFlg`
  are 0-hit in the v2.0.41 bundle. The bundle attests only the route and its
  `pageNo` parameter, as a WebView GET (`SRForegroundDialogActivity.java:31`,
  `sub/ticketList.html:405`); the JSON-over-POST spelling is srtgo's, and both
  were confirmed live on 2026-07-26. Only the POST is allowlisted.
- NetFunnel queue protocol completed and partially live-verified 2026-07-26.
  Previously only `getTidChkEnter` (5101) was ever sent, so an engaged queue
  (201 kContinue) failed the search outright and the queue slot was never
  released. Added: `chkEnter` (5002) polling with HARD caps (20 polls / 60s
  wall clock, each wait the server's own `ttl` clamped to the app's 1..5s
  `TS_MAX_TTL`), and `setComplete` (5004) release after every guarded request.
  `safety.py`'s `/ts.wseq` contract now registers three exact per-opcode query
  shapes instead of one, rather than being loosened.
  **LIVE-VERIFIED**: a real acquire->release round trip
  (`5002:200:key=<256 hex>&...&ttl=0&nwait=0&ip=rnf14.letskorail.com` then
  `5004:200`). **NOT verified**: the 201 polling path — at normal load the queue
  does not engage and load was deliberately not synthesised to force it.
  The live run caught a silent bug a fixture could not: the key-shape guard
  bounded keys at 128 characters while a real key is 256, so every setComplete
  failed the guard and was swallowed by the best-effort release path.
  Two bundle findings are recorded in code because they contradict the obvious
  assumption: `setComplete` carries NO `sid`/`aid` (the only one of the four
  builders that omits them), and `ttl` sits between `prefix` and `sid` on
  `chkEnter` and is the server's own value, not a constant. The acquire reply
  also names a specific queue node (`ip`/`port`) that the app WOULD follow; we
  deliberately do not, staying pinned to the two canonical origins, and the live
  run showed the front door releases the slot anyway.
- **Error taxonomy (2026-07-26).** Server-side failures used to arrive as one
  undifferentiated `SrtAppError` with only `NET000001` special-cased, so a
  caller had to substring-match Korean `msgTxt` to tell "sold out" from
  "session died" from "the queue refused you" — which is what `srtgo` does
  (`srtgo/srtgo.py:721-744`). Six new types, each **subclassing the one it
  refines** so no existing `except` narrows: `SrtNoResultsError`,
  `SrtInvalidRequestError`, `SrtSeatUnavailableError` (under `SrtAppError`);
  `SrtNetFunnelKeyError`, `SrtQueueRejectedError` (under `SrtNetFunnelError`);
  `SrtIpBlockedError` (under `SrtAuthError`). Classification is on `msgCd`, via
  `errors.classify_app_error`, with the raw code and response kept on every
  exception so the map can be grown from real traffic; an unmapped code still
  yields a plain `SrtAppError`.
  **Bundle evidence.** The only place in all 21,673 files of v2.0.41 where a
  server-supplied string is branched on is a *code*: `resultMap.msgCd == "S111"`
  → `memberShipLogin()` (`ara1001l.js:1562-1573`), which this repo already
  mapped to `SrtSessionExpiredError` and which is left scoped to the reserve
  response, the only handler carrying the branch. Everything else is
  `strResult == "FAIL"` (`ara1001l.js:206`, `:234`, `:1855`) or
  `ErrorCode == -1` (`:193`, `:1840`), which carry no reason. The queue is the
  one subsystem whose bundle DOES discriminate: `_showResultChkEnter` gives
  `kTsBlock` (301) and `kTsIpBlock` (302) their own `"onBlock"`/`"onIpBlock"`
  events beside `"onError"`, which is what `SrtQueueRejectedError` mirrors; 303
  `kTsExpressNumber` also has its own event and is deliberately unmapped
  because it is an admission, not a refusal.
  **A premise that did not survive.** `messages.js` is not a `msgCd` catalogue —
  it is a client-side UI string table keyed `error001`/`rsv001`/`login018`, 172
  strings, zero server codes. It matters in exactly one place: the sold-out seat
  shell embeds `Sr.msgs.error001`, so `SrtSeatUnavailableError.code` is that
  alert *key*, not a `msgCd`.
  **srtgo leads, verified.** Two of six are confirmed but by code, not message:
  `"로그인 후 사용하십시오"` = our `S111`; `"정상적인 경로로 접근 부탁드립니다"` =
  our `NET000001`. Neither exact substring is in our bundle, and neither is
  `NET000001` nor even the field name `netfunnelKey`. The remaining four
  (`잔여석없음`, `사용자가 많아 접속이 원활하지 않습니다`,
  `예약대기 접수가 마감되었습니다`, `예약대기자한도수초과`) are 0-hit, have no
  known `msgCd`, and the last two describe 예약대기 — a surface this library
  does not implement. They are **not** encoded, and a test pins that they stay
  plain `SrtAppError`.
  **No retry behaviour was added.** The single bounded `NET000001` search retry
  remains the only self-directed retry; `reserve` is still never retried
  (a retry duplicates a booking). Both live empty-result shapes are pinned
  against regression: the empty search FAIL (`WRG000000`) now raises
  `SrtNoResultsError`, while the empty reservation list still returns an empty
  list and its second `rsMap`/`WRT300005` FAIL envelope is still never read.
- Current full offline gate (`pytest -q -m "not live"`), after the
  consent-gated mutation port, the transport-layer live-mutation gate, the
  consent-gated cancel surface, the reservation-list read, the NetFunnel
  queue protocol, the error taxonomy, the real-card acknowledgement gate, the
  consent-gated card-payment and refund surfaces and the four-category live
  enablement: `1311 passed, 1 deselected`; the deselected case remains the
  explicit live-service opt-in. Every mutation in the suite is against an
  `httpx.MockTransport`; the live runs are the operator scripts' job.
- Prior offline gate before payment and refund were live-enabled:
  `1285 passed, 1 deselected`.
- Prior offline gate after the mutation port and its transport-layer gate, before
  cancel: `717 passed, 1 deselected`.
- Prior full offline gate at `955de306`, including the additive
  reservation-attempt parser tests: `625 passed, 1 deselected`.
- Prior integrated full offline gate: `587 passed, 1 deselected`. Offline
  replay of the retained runtime bodies passes for typed notices, timetable
  names, all 12 fare rows, and six personal/group search responses. The replay
  also fixed the observed JSON-integer `qryCnqeCnt`, `trnOrdrNo`, and
  `ocurDlayTnum` shapes, retained `rcvdFare` and five composition codes, and
  requires exact request/response station-code agreement before name enrichment.
- Final bounded live gate: login succeeded; personal and group pagination each
  produced two pages with row counts `[10, 10]`; the seat evidence summary was
  marker-present and `inventory_source_candidate`. The client session closed
  after this one combined read-only run.
- Pagination TDD gate: the expected RED was missing continuation/parser/public
  symbols; after implementation the focused client, payload/parser, and public
  contract suite reported `171 passed`.
- Pagination pre-build full offline gate: `497 passed, 1 deselected`; the only
  deselected test is the explicit live-service case. No credential or live
  service was accessed.
- Fresh `0.2.0` distribution gate: Python 3.14 built
  `srt_mobile_api-0.2.0-py3-none-any.whl` and
  `srt_mobile_api-0.2.0.tar.gz` in a temporary artifact directory. The archive
  verifier accepted both artifacts. No live request or credential access was
  performed.
- Historical post-pagination controller gate at that commit: `498 passed, 1
  deselected`; `git diff --check` was clean. The only deselected test remained
  the explicit live case.
- Final review hardening snapshots each page's empty state and last departure
  time before yielding it. Caller mutation of the compatible public
  `TrainSearchResult.trains` list therefore cannot alter continuation control or
  its server-derived cursor.
- The review regression and final focused pagination gate reported `1 passed`
  and `172 passed`, respectively.
- Fresh internal release gate: the focused contract test reported `1 passed`;
  the complete offline suite reported `286 passed, 1 skipped in 0.22s`, with
  only the explicit live-service opt-in skipped.
- Python 3.14 built `srt_mobile_api-0.1.0-py3-none-any.whl` and
  `srt_mobile_api-0.1.0.tar.gz` in a temporary artifact directory. The
  distribution verifier accepted both, including `py.typed`, metadata,
  required source documents, and forbidden-member checks.
- A fresh temporary virtual environment installed the wheel and imported
  `SrtClient` from `site-packages` outside both source worktrees. All temporary
  paths plus generated `build/`, `dist/`, and `src/*.egg-info` directories
  were removed.
- Task 5 focused offline gate: `233 passed`.
- Task 5 single bounded live result: `loggedIn=True`,
  `seatPageLoaded=True`, `seatSelectionMarkerPresent=True`,
  `externalSeatMapHandoffPresent=False`, and
  `embeddedSeatInventoryCandidatePresent=False`.
- The internal SRT page was loaded, but the bounded result alone does not prove
  a stable embedded car/seat DOM contract. Individual physical seats remain
  untyped pending a separately sanitized synthetic fixture.
- The conservative structure probe did not find enough embedded seat-named
  elements to justify a physical-seat model.
- Retained live seat-page evidence is limited to the two false booleans in
  `tests/fixtures/seat_page_live_evidence.json`; no original page body, text,
  URL, identifier, value, DOM detail, or structural count is stored.
- Task 5 pre-review full offline suite: `272 passed, 1 skipped`; the only skip
  was the explicitly opted-in live-service test.
- Final seat-page whole-feature review found no Critical issues. Its three
  Important boundary findings were fixed with regression tests: visible DOM
  marker enforcement excluding script/style/plain JSON, ASCII-only numeric
  form values in both validation layers, and rejection of a bare `?` query
  delimiter. Direct tests now also cover every named adjacent/external route.
- Fresh post-review controller verification: `285 passed, 1 skipped`; the only
  skip was the explicitly opted-in live-service test. The exact boundary
  remained `routes=20`, the excluded-route scan and diff check were clean, and
  the production live call was not repeated.
- Final release-prep package gate: `srt_mobile_api-0.1.0-py3-none-any.whl` and
  `srt_mobile_api-0.1.0.tar.gz` built successfully in an isolated build
  environment. A fresh Python 3.14 virtual environment installed the wheel
  with its dependencies and imported `SeatSelectionPage` and `SrtClient`
  directly from `site-packages`; `SrtClient.get_seat_page` retained the public
  `(self, train: TrainSummary) -> SeatSelectionPage` contract. No live service
  request was made during this package gate.
- Focused request tests verify a body with no query and exactly thirteen unique
  allowlisted fields, fixed general class and one seat, zero I/O on incomplete
  server row data, one seat-page POST, and no adjacent request.
- Final whole-feature review fix: the focused offline command covering mutual
  verification, models, and redaction safety passed with `69 passed`.
- Final controller verification after the secrecy fix: `243 passed, 1 skipped`;
  wheel/sdist build, isolated wheel imports, the `routes=19`, `mutual=1`,
  `netfunnel=1` boundary, and excluded-route scan all passed. The working tree
  was clean with one normal worktree, no stash, and no remote.
- The bounded live call was not repeated after the rendering-only secrecy fix;
  no request behavior, route, live ordering, or bounded result field changed.
- Prior Task 4 full offline suite: `242 passed, 1 skipped`; the only skip was
  the explicitly opted-in live-service test.
- Prior Task 4 package build: `srt_mobile_api-0.1.0-py3-none-any.whl` and
  `srt_mobile_api-0.1.0.tar.gz` built successfully.
- Prior Task 4 isolated wheel install/import: `MutualVerificationResult
  SrtClient` imported successfully from a fresh virtual environment.
- Prior Task 4 exact static boundary: the earlier checks established
  `routes=19` and `netfunnel=1`; a separate exact-tuple sum assertion
  established `mutual_route_count=1`. The excluded-route pattern scan across
  `src/` and `scripts/` returned no matches.
- Prior independent read-only review approved proceeding to the bounded live
  gate.
- Prior bounded live result: `loggedIn=True`, `mainLoaded=True`,
  `bookingLoaded=True`, `selectorLoadedCount=6`, `noticeCount=1`,
  `ticketPageLoaded=True`, `personalTrainCount=10`,
  `mutualVerificationLoaded=True`, `groupTrainCount=10`,
  `timetableRowCount=7`, and `fareItemCount=9`.
- NetFunnel remains the single `act_10` read-only route (`/ts.wseq`), now
  carrying the whole three-opcode queue protocol rather than acquisition alone.
  Single-page search retains its full-flow one-fresh-key retry; pagination
  additionally refreshes and retries only one rejected continuation cursor.
- Physical seat models and selection continue to require separate sanitized
  fixture evidence and a new concrete design before implementation.

The local credential file remains ignored and is not tracked. No credential,
cookie, session token, NetFunnel key, or raw personal response is stored.

## Analysis Inventory Versus Implementation

- Documented endpoint-matrix entries: 38, including runtime, static, helper,
  excluded, and repeated failure scenarios
- Runtime-success entries: 20
- Currently implemented underlying read routes: 20, including NetFunnel `act_10`
- Mutation routes tiered: 4 (reserve, cancel, payment, refund). All four have
  client methods, preview by default and transmit under an explicit non-dry-run
  consent for their own category; all four are live-verified (reserve and cancel
  2026-07-25, payment and refund 2026-07-26)
- Therefore the complete documented endpoint matrix is not yet implemented

Static aliases, the `Ard02017`/`Ard02018` WebView payment handoff, native
integrations, and typed physical-seat inventory remain outside the current core
package. The plaintext `Ata09036` charge is implemented and live-verified; the
app's own WebView-plus-TransKey-plus-FIDO path is the one that stays out.

## Deferred Work

Typed physical-seat layout and selection remain a future candidate requiring
separately authorized Arc02011 response evidence that proves a stable iterable
source, availability vocabulary, and closed parser. The unallowlisted Arc02011
handoff, external seat-map call, callback, and native bridge remain excluded.
All four mutation categories are now implemented, live-enabled and verified:
`reserve` and `cancel` by the 2026-07-25 round trip, `payment` and `refund` by
the 2026-07-26 one (see "Consent-gated Mutation Surface" and "Card Payment and
Refund"). What remains excluded is the app's own payment path — the
`Ard02017`/`Ard02018` WebView pages, the TransKey keypad and FIDO — which this
library does not implement at all. The implemented personal and
group continuation contract has bounded live evidence.
