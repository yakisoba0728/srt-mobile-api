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
  `assert_read_only_request` refuses all five. The 22nd is the refund's step-1
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
  and availability vocabulary. **Superseded 2026-07-26:** that evidence arrived,
  from a live read of the handoff's own target rather than from this command —
  see "좌석배치도 (Seat Grid) Read" below. Physical seats are typed as
  `SeatGridSeat`; the read allowlist grew by one route and the mutation boundary
  is still untouched.
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
- One 호차's 좌석배치도 read returning `SeatGrid` of typed `SeatGridSeat`
  (`get_seat_grid(train, car_number)`, live-confirmed 2026-07-26)
- Refund step 1, the issued ticket's identity read (`/atc/getListAtc14087.do`)
- 할인쿠폰 list read returning `DiscountCouponList`
  (`get_discount_coupons()`, `/apa/selectListApa03020_n.do`,
  live-verified empty 2026-07-26)
- 공공할인 entitlement read returning `PublicDiscountPage`
  (`get_public_discounts()`, `/common/ARA/ARA0301V/view.do`,
  live-verified unapproved 2026-07-26)

The package also exports the offline `parse_reservation_attempt_response()`,
`parse_reservation_hold_response()` and `parse_unpaid_cancel_response()`
helpers; they perform no I/O and are not client routes.

The transport currently allows 25 exact read-only app/NetFunnel routes.
`act_19`, the app's own `Ard02017`/`Ard02018` WebView payment entry, other
ATA/ARD flows, native bridges, callbacks, and external seat-map calls are not
callable. Preview-by-default `reserve`, `reserve_transfer`, `cancel`,
`pay_with_card` and `refund` methods exist; all transmit under an explicit
non-dry-run consent for their own category. Four operations are live-verified.
`reserve_transfer` and the `standby` / `round_trip` variants of `reserve` are
**not** — they are bundle-evidenced only. A sixth method, `reserve_group`,
existed until 2026-07-26 and was removed; see "단체 (group) booking: removed".
See the next three sections.

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
- The state-changing routes are tiered in `safety.SRT_MUTATION_ROUTES` and
  deliberately kept out of `READ_ONLY_ROUTES`, so the 25-route read-only
  allowlist and its guarantee are unchanged and `assert_read_only_request`
  refuses each of them. `SRT_MUTATION_ROUTE_CATEGORIES` binds each route to one
  consent category. There are **four routes across four categories**, one
  each. It was five until 2026-07-26: the 단체 reservation endpoint
  `/arc/selectListArc06014_n.do` was a second URL for the existing `reserve`
  category (`ara1001l.js:1542-1547` switches only the URL, on `grpDv`), and it
  was **unregistered** when group booking was removed — a route no client method
  can reach must not stay transmittable. Route count and category count are
  still allowed to differ on purpose; the category is what gates transmission.
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

## Reservation Variants (IMPLEMENTED, BUNDLE-EVIDENCED, NOT LIVE-VERIFIED)

Standby (예약대기) and the round trip / 오는열차 second leg. The evidentiary
situation is the **inverse** of payment and refund: those had to be built from
srtgo because their routes are 0-hit here, whereas both of these are evidenced
in our own v2.0.41 bundle. srtgo was therefore used only as a cross-check, and
where the two disagree the bundle won. **Neither has been live-verified**; the
operator will do that next, and only for the combinations actually exercised.

A third variant, 단체 (group), was implemented here and then removed on
2026-07-26 after a live probe showed the endpoint returns a payment page rather
than a hold. See "단체 (group) booking: removed" below — the code is gone, the
knowledge is not.

The app names all three of its job types in one comment on its own reservation
form seed — `ara0101v.js:90`,
`"jobId" : "1101"  //조정구분코드(1101:개인예약, 1102:예약대기, 1103:시트맵예약)`.

- `SrtClient.reserve(train, *, standby=False, ...)` — **standby, `jobId=1102`**.
  Bundle: `ara1001l.js:1445-1448` (fn_moveRsv defaults `1101` and overwrites with
  `1102` when the selected row's general-cabin image is the 예약대기 image).
  Three fields move together: `jobId` → `1102`, `psrmClCd1` forced to `1`
  (`:1431` is the only line that can pair a 예약대기 row with a cabin class, and
  the 특실 branch beside it tests only the two 예약가능 images), and
  `reserveType` **dropped** (srtgo `srt.py:990-991` sets it for personal only;
  the field is 0-hit in our bundle, so srtgo is the only source for both its
  presence and its absence). Forcing the cabin is required, not cosmetic: the
  default `GENERAL_FIRST` resolves to 특실 whenever the general cabin is not
  "예약가능", which is exactly what a standby train looks like. `stndFlg` stays
  `"N"` — that is 입석여부, a different concept the app never writes.
- **Standby eligibility is where the bundle and srtgo disagree, and the bundle
  wins.** srtgo selects standby from `rsvWaitPsbCd >= 0`; our app reads
  `gnrmRsvPsbImg` (`ara1001l.js:32-33`, `:1447`). Not interchangeable: the group
  search `Ara10082` omits `rsvWaitPsbCd` entirely (our own group fixture
  confirms it) while `gnrmRsvPsbImg` is on both personal and group rows. Both
  spellings of the image count — the server sends `grd_WF_Waiting.png`, the app
  rewrites it to `_S` on tap (`:1045`). A row with a DIFFERENT image is refused;
  a row with NO image column is ACCEPTED, since absence is not ineligibility
  (the same rule `arvDt1` gets). srtgo's follow-up standby-option POST
  `/ata/selectListAta01135_n.do` is 0-hit here with no equivalent, so it is
  deliberately not implemented.
- `SrtClient.reserve(train, *, round_trip=False, ...)` — **round trip,
  `rtnDv="1"`**, and that one flag is the entire wire delta. SRT models a round
  trip as 오는열차, not as a multi-leg reservation: the app reserves the
  가는열차, re-searches with the stations swapped and `back_dptDt1`/
  `back_dptTm1` (`ara1001l.js:110-115`), then reserves the 오는열차 as a SECOND
  POST to the same endpoint whose leg-1 fields are overwritten with the return
  train (`:1454-1470`, `:1580-1596`). So the public API is two ordinary
  `reserve` calls, with `TrainSearchQuery.for_return_leg(date, time)` building
  the swapped query. Two calls preserves "one call creates at most one hold";
  the caller owns both PNRs. Whether the server LINKS the two holds is
  unverified — the app carries the outbound result forward in `go_baseDsXml`/
  `go_seatDsXml` (`ara0101v.js:143-144`), which is not reproducible from a
  search row.
- **`jrnyCnt` does not become `"2"` for a round trip.** It has three hits in the
  whole bundle: the seed `"1"` (`ara0101v.js:92`), a null-check read
  (`ara1001l.js:1654`), and one write — the **환승** toggle, which sets
  `jrnyCnt="2"` with `jrnyTpCd="14"` (`ara0101v.js:288-311`). Nothing on the
  왕복 path touches it, and 환승 + 왕복 is mutually exclusive anyway. By
  extension the `...2` suffix indexes the 여정 (journey) slot — the app's gloss
  is `여정일련번호1(001:선행, 002:후행)` (`ara0101v.js:97`, `ara1001l.js:1607`) —
  so slot 2 is a transfer's FOLLOWING leg, never filled by a round trip, and
  certainly not a second passenger (passengers are `psgTpCd1..5`, indexed by
  type).
- **`jobId=1103` (시트맵예약) deliberately left out.** The value is evidenced
  (`ara0101v.js:90`, `ara1001l.js:1436`) but the request is not: `1103` is set on
  the ARC0201C branch, which navigates to the seat-map page (read-only here as
  `get_seat_page`) and hands off to a `fn_submit()` whose only hit in all 21,673
  files is the call site (`ara0101v.js:882`) — its definition is server-rendered,
  so neither the submit target nor the body is knowable offline.
  `payloads.RESERVE_SEATMAP_JOBID` records the value and the field family such a
  body would carry (`seatNo1_1..N`, `scarGridcnt1`/`2`, `scarNo1`/`2`,
  `ara0101v.js:871-878`), and a test asserts nothing emits it.
  **Superseded 2026-07-26:** implemented as `reserve(..., designated_seats=…)`
  — see "좌석지정 (Seat-Designated Reservation)" below. The BODY was knowable
  after all (the field family above is the whole of it); the submit TARGET is
  still not, and is now the one open question rather than the whole feature. The
  test that asserted nothing emits `1103` was kept and narrowed: no
  *undesignated* reservation may emit it or any field of its family.
- Compatibility is pinned, not assumed: every new parameter is keyword-only and
  defaulted off, and `test_reserve_variants` asserts the default form is
  byte-for-byte AND order-for-order what it was, so the existing
  single-passenger pins in `test_mutation_live_paths` pass unchanged.

## 환승 (Transfer) Search and Reservation (IMPLEMENTED, NOT LIVE-VERIFIED)

The remaining reservation shape, and the inverse of the round trip. 왕복 is two
reservations of one journey each; 환승 is ONE reservation carrying TWO 여정
slots. Nothing was added to `SRT_LIVE_MUTATION_CATEGORIES`, nothing was added to
`SRT_MUTATION_ROUTES` (five routes / four categories at the time; four routes
since 단체 was removed on 2026-07-26), and the canaries are
untouched: `reserve_transfer` POSTs the same `/arc/selectListArc05013_n.do` under
the same `reserve` category as `reserve`.

**Both premises this work started from survived the bundle.**

- `jrnyTpCd` `11` = 편도 / rmk 직통 and `14` = 환승편도 / rmk 환승, in the app's
  own code table (`commCode.js:296-309`), repeated inline at `ara0101v.js:91`.
- `jrnyCnt="2"` has exactly ONE write in the whole bundle, the 환승 toggle, which
  sets it together with `jrnyTpCd="14"` (`ara0101v.js:302-303`, emitted
  `:310-311`). 환승 and 왕복 are refused against each other in BOTH directions
  with the same alert (`:296-299`, `:331-334`).
- The `...2` suffix on JOURNEY fields is the 후행 leg
  (`//여정일련번호1(001:선행, 002:후행)`, `ara0101v.js:97`, repeated
  `ara1001l.js:1607`, and again unsuffixed at `:1611`
  `frm.jrnySqno.value = 1; // 0001 : 선행, 0002 : 후행`).

**One qualification to the second premise, recorded rather than glossed over.**
The `...2` suffix is a journey slot only on JOURNEY-scoped fields. On passenger
fields it is a passenger-TYPE index — `psgTpCd2`/`psgInfoPerPrnb2` are slot 2 of
the five-type picker (`ara0101v.js:118-121`, compacted `:824-836`) — and both
families coexist in this one form. The transfer builder emits the party once.

**Search: same endpoint, one field.** `chtnDvCd` `"1"` → `"2"`, derived by the
app at `ara1001l.js:98` (`jrnyTpCd == "11" ? "1" : "2"  //직통:1, 환승:2`) and
sent at `:159`. The URL is chosen by `grpDv` alone (`:174-181`), so 직통 and 환승
share `Ara10007`; the hydration GET carries the toggle's `jrnyTpCd=14` /
`jrnyCnt=2`. `chtnDvCd` is also a COLUMN on every row (`:1206` reads
`item.chtnDvCd`), present in the 2026-07-26 live capture, and kept on
`TrainSummary.raw`.

**How a transfer itinerary comes back is LIVE-CONFIRMED (2026-07-26), and the
bundle could not have said so.** The bundled list screen has no transfer branch
at all: `fn_postSearch` renders one single-leg `<tr>` per row
(`ara1001l.js:384-460`), `fn_moveRsv` writes only slot 1 (`:1453-1468`),
`fn_validChk` validates only slot 1 under a `//직통` heading (`:1649-1700`), and
the "select both legs" error `rsv023` is defined but never called
(`messages.js:217`). The 환승 list is server-rendered — the stylesheet still
ships its taller two-row card with a layover band (`.time_Difference`,
`.timeDiff`, `custom.css:4412`, `:4431`).

A read-only probe of 동대구(0015) → 광주송정(0036), 20260809 from 080000, settled
it. The direct search answered `WRD000061`; the transfer search returned **10
ordinary `dsOutput1` rows, ONE PER LEG**, every row `chtnDvCd="2"`, with the legs
of one itinerary sharing a `trnOrdrNo`: `1` → trains 382 (동대구→오송) and 411
(오송→광주송정), `2` → 14 (동대구→천안아산) and 475 (천안아산→광주송정), `3` →
316 and 655. So `trnOrdrNo` is the ITINERARY index here, not a position in the
whole list. The `...2` columns exist on every row and are **empty strings**
(`trnNo2: ""`, `dptRsStnCd2: ""`, `jrnySqno: ""`) because the second leg is a
separate ROW. `fllwPgExt2` was `null`.

`search_transfer_trains` therefore returns a `TransferSearchResult`
(`itineraries` / `unpaired` / `search`, plus `rows` and `raw`), and
`parsers.pair_transfer_itineraries` is the grouping. Three properties are
deliberate:

- **Leg order is derived from the STATIONS, not from row position.** The probe
  delivered legs in order, but that is one observation, and a reversed pair
  builds a clean reservation that books the journey backwards. Both orientations
  are handed to `TransferItinerary` and the one that validates wins, so
  "is this an itinerary?" has exactly one implementation.
- **A group that does not fit is set aside with a reason, never dropped and
  never forced** (`TransferSearchResult.unpaired`). Losing an itinerary silently
  hides a journey; a mispaired one produces a reservation whose two slots are not
  one journey and which the server would accept. The second is worse.
- **Rows present and zero itineraries raises `SrtProtocolError`** carrying `raw`,
  because that means the grouping rule is wrong for the response in hand and an
  empty list would be the one genuinely silent failure available. An empty
  response is not that case.

`iter_train_search_pages` is still not extended to transfer: the probe returned
`fllwPgExt2` as `null` exactly as every direct search does, so what the second
cursor is FOR remains unobserved and nothing in the bundle reads it.

**`WRD000061` is now classified.** `SrtNoDirectTrainError`, refining
`SrtNoResultsError` — "직통열차는 없지만, 환승으로 조회 가능합니다." is the
server naming its own remedy, and it is the natural signal to re-ask the query as
a transfer search. It previously fell through to a bare `SrtAppError`, so nothing
narrowed; it sits one level deeper rather than beside `SrtNoResultsError` because
the direct query genuinely matched nothing, and because the sibling korail client
classifies the identical code the same way. No transfer search is issued
automatically — the app offers the re-query in a dialog and waits.

**`TransferItinerary` is the safety property**, and the pairing above already
runs it, so anything in `result.itineraries` is reservable as it stands.

A transfer row is an ordinary
`TrainSummary` that `reserve()` would book on its own, producing a real PNR to
the 환승역 and no further. `reserve_transfer` accepts only a
`TransferItinerary(first_leg=…, second_leg=…)`, validated at construction: exact
`TrainSummary` on both sides, the first leg must ARRIVE where the second
DEPARTS, the second must not depart before the first arrives (the comparison the
app applies to the 왕복 second leg, `ara1001l.js:1258-1272`), and the two must
not be the same train.

**The form** is `personal_reservation_payload` for the first leg with
`jrnyTpCd`→`14`, `jrnyCnt`→`2`, `rtnDv` pinned to `"0"`, and 23 slot-2 keys
appended after slot 1's unchanged keys and order. `payloads.
TRANSFER_SLOT2_FIELD_EVIDENCE` grades every one of them and a test pins the
grades:

| tier | keys | source |
| --- | --- | --- |
| web bundle | `dptRsStnCd2` `arvRsStnCd2` `runDt2` `trnNo2` | 운임요금 params, `ara1001l.js:1209-1216`; the LIVE fare page renders a second leg from them with `selectTransferTrain()` (`tests/fixtures/fare_transfer_placeholder.html`) |
| web bundle | `smkSeatAttCd2` `dirSeatAttCd2` `locSeatAttCd2` `rqSeatAttCd2` `etcSeatAttCd2` | seeded `ara0101v.js:136-140`, written with slot 1's VALUES at `:775-777` |
| native | `psrmClCd2` `dptDt2` `dptTm2` `arvDt2` `arvTm2` | the app's own two-leg offline-ticket model, gated on `isTransfer == "true"` (`analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:785-815`), with a 수서→천안아산→부산 layout placeholder (`analysis/apktool/res/layout/listview_offline_detail_item.xml:31,43,59`) |
| hydrated | `jrnySqno2` `trnGpCd2` `dptRsStnCdNm2` `arvRsStnCdNm2` | 0-hit in the bundle; already sent on the Ara10007 hydration GET by `search_page_payload`, accepted live every run |
| **INFERRED** | `stlbTrnClsfCd2` `dptStnConsOrdr2` `arvStnConsOrdr2` `dptStnRunOrdr2` `arvStnRunOrdr2` | 0-hit in any form; slot 1's name with the suffix changed |

The live search moved **no tier**, deliberately. It settled the RESPONSE and
showed that a search ROW carries `...2` columns as empty strings — blank because
the second leg arrives as its own row, which says nothing about whether the
RESERVATION form wants them filled. A response column and a request field
sharing a name are two different things; only a reserve capture settles the
request side. **Search shape: live-confirmed 2026-07-26. Reservation form
slot-2 handling: still inferred.**

The server-rendered `#rsvForm` is not in the bundle (the app POSTs
`$("#rsvForm").serialize()`, `ara1001l.js:1550`), which is why the last two tiers
exist. `reserveType` is sent as `"11"` — srtgo-only, 0-hit here
(`srt.py:990-991`) — and whether it tracks `jrnyTpCd` is unknown; it was left
alone rather than guessed to `"14"`.

**Composition, decided from the bundle in every case.**

| feature | with 환승 | evidence |
| --- | --- | --- |
| passenger mix | **yes**, one party | `psgTpCd1..5` indexed by TYPE, not slot |
| `seat_type` / `window_seat` | **yes**, one preference for both legs | the 좌석옵션 callback writes slot 1 then the identical `...2` quartet (`ara0101v.js:769-778`) |
| 왕복 | **refused** | `ara0101v.js:296-299`, `:331-334`, both directions |
| 예약대기 | **not implemented** | `jobId=1102` comes from ONE row's image (`ara1001l.js:1445-1448`); a transfer has two rows and the app has no rule |
| 단체 | **not implemented** (scope, not exclusion) | 단체환승 is real to SRT (`eventTrainInfo.js:12`, `:19`; 환승단체권 `tkKndCd` 27) and forbidden nowhere, but this library does not book 단체 at all since 2026-07-26, so there is no group half to compose with — see "단체 (group) booking: removed" |
| 좌석지정 | **not implemented** | it BLANKS slot 2 (`scarGridcnt2=0`, `scarNo2=""`, `ara0101v.js:875-879`) |
| non-SRT leg | **refused** | both legs must be `stlbTrnClsfCd == "17"` |

A counter-note on the 왕복 exclusion, kept because it cuts the other way: the
ticket-kind table contains 환승단체왕편권 / 환승단체복편권 (`tkKndCd` 28/29,
`commCode.js:1597-1612`), so such a ticket exists as an SRT product. The refusal
is a client-side booking rule in this app, not proof the server would refuse.

**Left unchanged on purpose.** `fare_payload` still sends `chtnDvCd="1"` with
blank slot-2 fare fields, and `parse_fare_page` still discards the placeholder
second table; a transfer fare lookup is a separate change needing its own live
capture. `cancel` was not touched — but a transfer hold has TWO journeys, so it
must be released with `cancel(hold, journey_count="2")`, and the default `"1"` is
wrong for this shape. README records that where an operator would read it, along
with the precondition the whole feature needs: a station pair SRT does not serve
directly (경부선 and 호남선 meet only at 오송 `0297`, so 동대구→광주송정,
부산→목포 or 대전→광주송정).

**Compatibility is pinned.** `tests/test_transfer.py` asserts that the one-leg
reservation form is unchanged including key order, that both search builders are
byte-for-byte identical with `transfer` defaulted, and that every new parameter
is keyword-only and defaulted off.

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

**CORRECTED 2026-07-26.** The paragraph above is kept as the record of what the
2026-07-15 structural capture proved, which is still exactly what it proved. All
three claims in its last sentence are now false: Arc02011 IS in
`READ_ONLY_ROUTES` with its own exact eleven-field contract,
`parsers.parse_seat_grid_response` closes its response, and
`SrtClient.get_seat_grid` calls it. Nothing about the capture changed — a live
read of the route settled what a structural summary of the page never could.

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
  consent-gated card-payment and refund surfaces, the four-category live
  enablement, the bundle-evidenced reservation variants, the 환승
  (transfer) search and reservation, the 좌석배치도 (seat grid) read and the
  좌석지정 (seat-designated) reservation — and after 단체 (group) booking was
  removed again, and after the 할인 code tables, the 할인쿠폰 read, the 공공할인
  read and the seven-type `PassengerCounts` landed:
  `1520 passed, 1 deselected`; the deselected case remains the
  explicit live-service opt-in. Every mutation in the suite is against an
  `httpx.MockTransport`; the live runs are the operator scripts' job.
- Prior offline gate before the seven passenger types: `1497 passed, 1 deselected`.
- Prior offline gate before the 공공할인 read: `1485 passed, 1 deselected`.
- Prior offline gate before the 할인쿠폰 read: `1471 passed, 1 deselected`.
- Prior offline gate before the 할인 code tables: `1455 passed, 1 deselected`.
- Prior offline gate with 단체 (group) booking still implemented:
  `1463 passed, 1 deselected`.
- Prior offline gate after the seat-grid read, before seat designation:
  `1448 passed, 1 deselected`.
- Prior offline gate before the seat-grid read: `1404 passed, 1 deselected`.
- Prior offline gate before the reservation variants (group, standby, round
  trip): `1311 passed, 1 deselected`.
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
- Mutation routes tiered: 4 across 4 categories (reserve `arc05013`, cancel,
  payment, refund), one route per category since the 단체 sibling `arc06014`
  was unregistered on 2026-07-26. All have client methods, preview by default
  and transmit under an explicit non-dry-run consent for their own category;
  the four CATEGORIES are live-verified (reserve and cancel 2026-07-25, payment
  and refund 2026-07-26), but the `standby`/`round_trip` variants of `arc05013`
  are bundle-evidenced only
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

Two reservation variants now exist and are **awaiting live verification**:
standby (`jobId=1102`) and the round trip / 오는열차 second leg (`rtnDv=1`). See
"Reservation Variants" for what each rests on. A third, group (`arc06014`),
existed and was removed on 2026-07-26 — see "단체 (group) booking: removed".
Still deferred within that surface: **`jobId=1103`
(시트맵예약)**, whose submit target and body are not knowable from the offline
bundle (`fn_submit()` is defined in the server-rendered page), and srtgo's
standby-option POST `/ata/selectListAta01135_n.do`, which is 0-hit here with no
equivalent in our app. Both would need capture, not inference.

## Live status of the reservation variants (2026-07-26)

**Round trip — VERIFIED.** 수서→동탄 20260809 train 315 outbound and
동탄→수서 20260810 train 604 return, one adult each, `round_trip=True` on both
calls. `TrainSearchQuery.for_return_leg` swapped the stations correctly
(0551→0552 became 0552→0551), each call produced its own PNR, both cancelled
`SUCC`/`IRG000000`, and the account was verified empty. This confirms the
bundle-derived model: a round trip is TWO separate reservations, not one
request carrying two legs, and `jrnyCnt` stays `"1"` throughout.

**Standby — NOT VERIFIED, for want of an eligible train.** The app decides
standby eligibility from the search row's `gnrmRsvPsbImg`, and live searches
returned only `IMAGE::grd_WF_Soldout.png` and `IMAGE::grd_WF_Ok01.png` — never
`IMAGE::grd_WF_Waiting.png`. Four searches were tried across sold-out
수서→부산 and 수서→동대구 departures on four dates; every train was plainly
sold out with no standby offered. The image values themselves are now
live-confirmed, which corroborates the bundle over srtgo (srtgo keys standby
off `rsvWaitPsbCd`, a column our app never reads for this and which the group
search does not even return). Whether SRT offers 예약대기 at all on these
routes is unknown; the code path remains offline-tested only.

**Group — ATTEMPTED 2026-07-26, then REMOVED.** The first attempt (ten adults,
수서→동탄 20260809 train 315, chosen from `search_group_trains`) came back with
a wrapper-level failure before any business envelope::

    {"ERROR_CODE": "-1",
     "ERROR_MSG": "조회 중 에러가 발생 하였습니다. 관리자에게 문의하십시오."}

That was **our own missing field**, not an account entitlement, and the second
attempt got past it — onto a payment page, not a reservation. The booking code
was removed the same day. The full account is in
"단체 (group) booking: removed" below; the account is deliberately kept
because it was expensive to learn.

**Correction to what this section used to say.** It previously carried a
standing warning that a live group attempt could strand an uncancellable
ten-seat hold, reasoning from `ara1001l.js:1597-1610` — the app forces
`pnrNo = -1` for a group and identifies it by `resultMap.tmpJobSqno1`, so
`cancel`, which takes a PNR, would have nothing to act on. **The bundle reading
was right and the conclusion was wrong.** `Arc06014` creates no reservation at
all, so there is nothing to strand and never was. The warning is corrected here
rather than deleted, so a future reader does not re-inherit a fear that was
disproved.

## 환승 live verification (2026-07-26) — search AND reservation

**Verified end to end, no payment.** 동대구 (0015) → 광주송정 (0036), 20260812.

- The direct search raised `SrtNoDirectTrainError` / `WRD000061`. Same code,
  same meaning as korail.
- `search_transfer_trains` returned five itineraries, paired by `trnOrdrNo`
  exactly as the earlier probe showed.
- **SRT's transfer search mixes operators.** Legs came back with
  `service_class_code` `17` (SRT), `00` and `07` — the first itinerary offered
  had a non-SRT second leg. `reserve_transfer` refused it, correctly, before
  sending anything. Only an all-`17` itinerary is reservable here, and callers
  must filter for that.
- The all-SRT itinerary — train 316 동대구→오송 then 655 오송→광주송정 —
  reserved successfully: `SUCC` / `IRR000018`, `jrnyCnt=2`, `jrnySqno2=002`.
- `cancel(pnr, journey_count="2")` released it first try, `SUCC` / `IRG000000`,
  and the account returned to zero reservations.

**This settles the request side.** The five slot-2 fields that were graded
INFERRED — `stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`,
`dptStnRunOrdr2`, `arvStnRunOrdr2` — were accepted by the live server, as was
`reserveType="11"`. Declining to guess `"14"` there was right. The evidence
grades in `TRANSFER_SLOT2_FIELD_EVIDENCE` can now be read as live-accepted
rather than inferred, though acceptance of a form is weaker evidence than
seeing the app send it: the server may simply ignore a field it does not need.

## 예약대기 — still no eligible train (2026-07-26, second sweep)

Ten live searches now, spanning 20260727 to 20260817 across 수서→부산,
수서→목포, 수서→동대구 and 부산→수서, including sold-out holiday departures.
**Not one standby-eligible row.** The code path stays offline-tested only.

The sweep did map the wait vocabulary, which is worth keeping:

| `rsvWaitPsbCd` | `rsvWaitPsbCdNm` | `gnrmRsvPsbImg` | meaning |
|---|---|---|---|
| `-2` | `-` | `grd_WF_Ok01.png` | seats available |
| `-1` | `-` | `grd_WF_Soldout.png` | sold out, standby not offered |
| `' 0'` | `매진` | `grd_WF_Soldout.png` | sold out, zero standby slots |

Every sold-out SRT departure observed carried `' 0'` or `-1`. For contrast,
korail offered standby on a comparable sold-out route the same day, with its
own flag at `" 9"` — so the difference is the operator's, not ours.

Note the values are space-padded to width two, as korail's are, and that our
implementation deliberately keys off `gnrmRsvPsbImg` rather than this column,
because that is what the app reads. The column is a useful cross-signal, not
the decision.

**What would settle it:** a departure where SRT actually opens 예약대기. On
this evidence that may be rare or currently disabled; it is not something to
force. Re-run the sweep near a peak booking window rather than probing
repeatedly — ten searches in a session is already close to what this project
considers polite.

## Seat designation (1103) needs no MITM — the pages are fetchable (2026-07-26)

Everything previously written about `1103` said its submit form lives in a
server-rendered page and therefore needs a traffic capture. The first half is
true and the conclusion is wrong: **those pages are served to our own
authenticated session, so their HTML and inline JavaScript can simply be read.**

Demonstrated in three read-only calls:

1. `get_seat_page` (`/arc/selectListArc02012_n.do`) returns ~55 KB of HTML. It
   does NOT contain `fn_submit`, which is why the offline bundle search kept
   coming up empty — but it does carry the car `<option>` list and a form.
2. That page defines `<form id="trnScarSeatFrm">` with eleven inputs, seeded
   with the journey's own values: `trnGpCd`, `runDt`, `trnNo`, `scarNo`
   (empty until a car is picked), `psrmClCd`, `dptRsStnCd`, `arvRsStnCd`,
   `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, `choiceSeatCount`.
3. Its inline script shows what picking a car does: set `scarNo`, serialise the
   form, and `$.ajax` POST it to **`/arc/selectListArc02011_n.do`** with
   `dataType: "html"`, then split the response on `#`.

`Arc02011` and `trnScarSeatFrm` are both 0-hit in the v2.0.41 bundle. They
exist only in what the server renders, which is exactly why static analysis
could not reach them and exactly why fetching the page does.

A hand-built POST to `Arc02011` with guessed `dptStnRunOrdr`/`arvStnRunOrdr`
came back as an alert shell rather than a seat grid, so the remaining work is
getting the field values from the train row instead of hardcoding them. That is
ordinary implementation, not a capture problem.

**The general lesson, which applies beyond this endpoint:** when this project
concludes "server-rendered, needs a capture", check first whether the page can
be requested with the session we already have. A WebView shell hides its logic
from the APK, not from an authenticated HTTP client.


## 좌석배치도 (Seat Grid) Read — LIVE-CONFIRMED 2026-07-26

The follow-up read the section above predicted, implemented as
`SrtClient.get_seat_grid(train, car_number) -> SeatGrid` over
`POST /arc/selectListArc02011_n.do`, parsed by
`parsers.parse_seat_grid_response`, built by `payloads.seat_grid_payload`, and
registered in `READ_ONLY_ROUTES` (22 routes -> 23) with its own exact
eleven-field contract enforced at the transport boundary. Nothing was added to
`SRT_MUTATION_ROUTES` or `SRT_LIVE_MUTATION_CATEGORIES`; this route creates
nothing, and `assert_mutation_route` refuses it.

**The live read.** 수서 -> 동탄 (0551 -> 0552), 20260812, train 315, one adult:
the request returned 25,930 bytes containing 74 seat cells for one 호차.

**The zero-padding is the gate, and it is the whole story of this endpoint.**
The train number goes on the wire **zero-padded to five characters**:

| `trnNo` sent | response |
| --- | --- |
| `315` | 147-byte alert shell, "출발 20분 전부터 좌석이 자동배정됩니다…" |
| `00315` | the seat grid, 25,930 bytes, 74 cells |

Referer made no difference and route length made no difference; all three were
checked against the live server. The alert text reads like a timing rule and is
not one — it is what this server says when it cannot find the train — and
believing it is the kind of thing that keeps an endpoint closed for months. The
app pads identically and documents itself doing so: `lfn_getTrNoData`,
*"열차번호를 5자리로 채워서 가져옴"* (`main.html:642-661`), used at the single
write of `trnNo1` (`ara1001l.js:1461`). `payloads.SEAT_TRAIN_NUMBER_LENGTH`
carries that reasoning, `safety.SEAT_GRID_VALUE_PATTERNS` re-checks it as
`[0-9]{5}` so a hand-assembled unpadded body cannot leave the process, and a
test pins it with the three-character train number 315.

**The request** is `trnScarSeatFrm` serialised: `trnGpCd`, `runDt`, `trnNo`,
`scarNo`, `psrmClCd`, `dptRsStnCd`, `arvRsStnCd`, `seatAttCd`, `dptStnRunOrdr`,
`arvStnRunOrdr`, `choiceSeatCount`. Two independent offline records agree on
that set — the retained 2026-07-15 structural capture
(`tests/fixtures/seat_page_schema_v2_evidence.json`, which also pins the route
and the POST) and the live page — and both the route and the form are 0-hit in
the v2.0.41 bundle. It is the seat PAGE's form minus `reqCode`/`dptDt`/`dptTm`
plus `scarNo`. `dptStnRunOrdr`/`arvStnRunOrdr` come from the search row; an
earlier hand-built probe hardcoded them and got an alert shell, which is what
made this look harder than it was.

**Every seat has two identifiers.** A cell is

```html
<div role="text" tabindex="0" aria-label="1C" id="scarSeat_1C"
     class="seatChoice015Y" onclick="choiceSeatNo('3', '1C', 'Y');"><span>1C</span></div>
```

so `choiceSeatNo(<internal seat number>, <printed label>, <'Y'|'N'>)`, the
element id is built from the PRINTED label, and the class is
`seatChoice<seatAttCd><Y|N>` (`000`, `015`, `021`, `028` all appeared in the
captured car). `SeatGridSeat` therefore has `internal_seat_number` and
`printed_seat_label` as two separate fields with two unmistakable names.
Conflating them is not hypothetical: on the sibling korail client the
reservation form sends the internal seat number while the reservation detail
echoes the printed spec, and comparing the wrong pair made it look as though the
server had ignored the seat map.

**The `#` envelope is a business refusal.** The page's own handler is
`tmp = args.trim().split("#"); if (tmp[0] == "0") alert(tmp[1]);`, so a body
whose first segment is exactly `0` carries a server message rather than a grid.
That is a request the server understood and declined, so it raises
`SrtSeatUnavailableError` (an `SrtAppError`, catchable like every other business
refusal) and not `SrtProtocolError`. Its `code` is the envelope's own `"0"`:
this route is HTML and has no `msgCd` at all, the same situation the sold-out
seat page is in with its alert key. A body with no `choiceSeatNo` cell and no
envelope is neither, and raises `SrtProtocolError` rather than returning an
empty grid.

**What an operator must do to re-confirm this read.** Log in, search a real
journey, `get_seat_page(train, passengers=…)`, take a `car_number` from
`page.cars`, then `get_seat_grid(train, car_number, passengers=…)`. It is a
read: no consent, no NetFunnel, no hold. The one thing worth watching is a
`"0#…"` refusal on a train whose seats the page said were free — that would mean
the envelope carries conditions this repository has not seen.

## 좌석지정 (Seat-Designated Reservation, `jobId=1103`) — BODY EVIDENCED, TARGET INFERRED

`SrtClient.reserve(train, *, designated_seats=…, consent=…)`. Keyword-only and
defaulted to `None`, so every existing caller's form is byte-for-byte and
order-for-order what the 2026-07-25 live round trip sent; a test asserts exactly
that. Nothing was added to `SRT_MUTATION_ROUTES` (still five) or to
`SRT_LIVE_MUTATION_CATEGORIES` (still four) — a designated reservation is the
same operation on the same route under the same `reserve` consent.

The flow is four calls, three of which already existed:

```python
page  = client.get_seat_page(train, passengers=party)
grid  = client.get_seat_grid(train, page.cars[0].car_number, passengers=party)
seats = grid.choose("1B", "2C")
hold  = client.reserve(train, passengers=party, designated_seats=seats, consent=…)
```

### The three evidence tiers, which are not the same tier

| Part | Tier | Source |
| --- | --- | --- |
| The seats themselves (grid read, padding, Y/N, both identifiers) | **live-confirmed 2026-07-26** | the live read of `Arc02011` |
| `jobId="1103"` | **bundle-evidenced** | `ara0101v.js:90` (gloss), `ara1001l.js:1435-1436` (the single write) |
| `seatNo1_1..N`, `scarGridcnt1`, `scarGridcnt2="0"`, `scarNo1`, `scarNo2=""` | **bundle-evidenced** | `ara0101v.js:866-882`, line by line |
| `seatNo1_*` carrying the PRINTED label | **bundle-evidenced** | `ara0101v.js:870-874`: built from `scarSeatNm`; `scarSeatNo` is received and never used |
| Field ORDER within the body | **ours** | the app writes into the `gds_rsv` store, not an ordered form; appended last so the undesignated body is unchanged |
| `reserveType="11"` on a `1103` body | **unknown** | srtgo-only field, 0-hit in the bundle, and srtgo has no seat-map reservation; left where the personal path put it |
| **The submit target** | **INFERRED** | `fn_submit()` is called at `ara0101v.js:882` and defined nowhere in the bundle; the next line is the commented-out `//Sr.ara1001l.fn_callReserv();`, the function that POSTs `/arc/selectListArc05013_n.do` (`ara1001l.js:1541-1550`) |

### What the operator must fetch next

**Fetch `/ara/ara0101v.do` with an authenticated session and read its inline
`fn_submit`.** That is the same technique that opened the seat grid — the page
is server-rendered, which hides it from the APK and not from us — and it is the
one thing standing between "a valid body" and "a valid request". If `fn_submit`
POSTs `Arc05013`, this implementation is complete as written; if it targets
something else, the body is still right and only the route moves. Reading the
page is a read, costs nothing, and creates nothing.

Only after that is a live designated reservation worth attempting, and it should
be the same shape as the 2026-07-25 round trip: 수서 → 동탄, one adult, one seat,
`dry_run=False` with `allow_reserve=True`, PNR kept, cancelled immediately.
`scripts/recover_hold.py` releases a hold from the PNR string alone. What to
check on the response is whether the seat came back as the one that was asked
for — and note that a reservation detail may echo the seat in the OTHER
identifier space, which is the korail trap: compare printed label to printed
label.

### What does not compose, and why

* **`standby`** — `jobId` cannot be both `1102` and `1103`, and the app reaches
  them from two different branches (`ara1001l.js:1435-1449`). `ValueError`.
* **`round_trip`** — 좌석지정 왕복 exists in the app
  (`POP_REQ_SEATSELECT_GO_BACK`, `const.js:10`) but its callback writes **no**
  seat fields; it just calls `fn_callReserv()` (`ara0101v.js:884-892`). Only the
  편도 branch produces the family, so the 왕복 designated body is unevidenced and
  guessing it would mean guessing on a route that creates real holds.
  `ValueError`.
* **단체 (group)** — moot since 2026-07-26: there is no group booking method
  to compose with. While it existed, 단체 reset the seat option and disabled
  the picker outright (`ara0101v.js:446-457`).
* **`reserve_transfer`** — 좌석지정 blanks the transfer's slot 2
  (`ara0101v.js:875-879`), which is the opposite of what a transfer needs.

### Validation, and where it lives

`SeatDesignation` refuses at construction to hold a seat the grid marked `N`, a
repeated seat, an empty seat list, or a non-numeric car — so an unselectable
seat is unrepresentable rather than merely rejected. The party-size rule lives
in `payloads._seat_designation_fields`, the one place both the seats and the
passenger counts are in scope: `choiceSeatCount` is `totPrnb`
(`ara1001l.js:1511`), so the app asks the seat map for exactly as many seats as
there are passengers, and a mismatch is a body the app cannot produce.

## Seat designation (1103) — live-verified end to end (2026-07-26)

수서→동탄 train 315 on 20260812, one adult, car 1.

- `get_seat_page` → car list; `get_seat_grid(train, "1")` → **56 seats parsed,
  27 selectable**, each carrying both identifiers separately
  (`internal_seat_number="1"`, `printed_seat_label="1A"`, `seat_attribute_code="015"`).
- `reserve(..., designated_seats=grid.choose("1C"))` → `SUCC` / `IRR000018`,
  and the hold came back with **`scarNo=1`, `seatNo=1C` — exactly the seat
  requested**. Cancelled `IRG000000`, account back to zero. No payment.

**This settles the one thing the implementation had to infer.** The submit
target was unknown because `fn_submit`'s definition could not be found — it is
in neither the bundle, nor `/ara/ara0101v.do`, nor `/main/main.do`, nor the
seat-grid response, all of which were fetched and searched. The implementation
reasoned from the commented-out `fn_callReserv()` beside its call site that the
existing reservation route was the target, and the live server confirmed it:
the ordinary `Arc05013` accepts the seat fields and honours them.

It also confirms the bundle's reading that the form transmits the PRINTED
label, not the internal number — we sent `1C` and got `1C` back. korail is the
opposite way round (its form takes the internal `seat_no` and echoes the
printed `seat_spec`), so the two clients genuinely differ here and the
identifier types must not be carried across.

**The five-digit zero-padding of `trnNo` was the whole gate on the grid read.**
Sending `315` returns a 147-byte alert shell whose message
("출발 20분 전부터 좌석이 자동배정됩니다") reads like a timing rule and is a red
herring; `00315` returns the grid. Referer and route length make no difference.

## 단체 (group) booking: removed (2026-07-26)

**The code was removed deliberately.** `SrtClient.reserve_group`,
`payloads.group_reservation_payload` and the `SRT_MUTATION_ROUTES` /
`SRT_MUTATION_ROUTE_CATEGORIES` registration of
`/arc/selectListArc06014_n.do` were deleted, together with the offline tests
that covered the booking path. The request they built was *correct*. What put
group booking out of scope is what the endpoint answers with — established live,
and recorded below so it never has to be rediscovered.

**What was NOT removed.** `SrtClient.search_group_trains`,
`payloads.group_search_ajax_payload` and `payloads.GROUP_MIN_PARTY_SIZE` all
stay. The group search is a read, it works, it predates the booking code, and
group availability and fares are worth looking up even when this client cannot
complete the booking. The ≥10 floor stays with it because the app enforces the
same number on the SEARCH (`ara0101v.js:551-554`, and the converse at
`:562-566` pushes any party over 9 *into* group booking, so 10 is a two-sided
boundary rather than a hint). `SRT_LIVE_MUTATION_CATEGORIES` is **unchanged** at
`{"reserve", "cancel", "payment", "refund"}` — group rode the `reserve`
category, and removing it may not shrink the set, because reserve and cancel
are the two halves of one reversible operation.

Re-examined with the page-fetching technique. Two findings, both material.

**1. `psgGridcnt` was the blocker.** The booking page's own group branch sets
BOTH values, not just the one we were sending::

    $('#grpDv').val('1');
    $('#psgGridcnt').val('2');

We compute `psgGridcnt` as the number of distinct passenger types, which is `1`
for ten adults. Sending `2` instead made the wrapper-level
`{"ERROR_CODE": "-1", "ERROR_MSG": "조회 중 에러가 발생 하였습니다…"}` disappear
entirely. So the earlier conclusion — "probably an account entitlement" — was
wrong, and the guess that it might equally be an undisclosed field was right.

**2. `Arc06014` does not return JSON, and does not create a hold.** With the
corrected field it answers with a 66 KB server-rendered page headed
`단체승차권 직통 / 예약내역 페이지`. That is why our JSON parser found neither
`pnrNo` nor `tmpJobSqno1` — there was no JSON to find. The account's reservation
list stayed empty afterwards.

The page is the group PAYMENT step: it carries `<form id="ata0201cForm">`,
functions `goToPay` / `goToPayAlert` / `kakaoPayReturn` / `kakao_direct_open`,
`tmpJobSqno` six times and `pnrNo` twice, and it posts to
**`/ata/selectListAta01033_n.do`** (and an `_Simple` variant) — NOT the
`Ata09036` this library implements for personal payment.

**So SRT group booking is a different shape from personal booking**: reserve
and pay are one flow ending at a payment page keyed by `tmpJobSqno`, rather
than a hold with a PNR that can be cancelled and paid separately. The earlier
worry — that a group booking might produce an uncancellable ten-seat hold —
does not arise, because no hold is produced at all.

**Not attempted:** the payment step. `Ata01033` is unimplemented and untested,
group fares are ten seats, and the KakaoPay hooks suggest at least one path
that leaves this client entirely. Anyone continuing should fetch that page for
a group they are willing to pay for, read `goToPay`, and decide deliberately.

### What bringing group booking back would take

**Not a revert.** The deleted code would send a correct request to a route that
cannot answer it in the shape this library models. Restoring the method without
the rest would produce a client that "succeeds" and returns nothing usable. In
order:

1. **`psgGridcnt="2"` on the group branch.** This library derives `psgGridcnt`
   from the count of distinct passenger types, which is `1` for ten adults, so
   this is a group-specific override rather than a fix to the shared builder.
2. **A second payment surface.** `/ata/selectListAta01033_n.do` (and its
   `_Simple` variant), whose form is `ata0201cForm` on the returned page, keyed
   by `tmpJobSqno` rather than a PNR. `Ata09036`, the personal payment route
   this library implements, cannot be reused.
3. **An HTML page parser** for a 66 KB server-rendered response. Every other
   mutation here parses JSON; this one does not return any.
4. **A story for KakaoPay.** The `kakaoPayReturn` / `kakao_direct_open` hooks
   suggest at least one path that leaves an HTTP client entirely, which no part
   of this library is built for.
5. **Re-registering the route** in `SRT_MUTATION_ROUTES` and
   `SRT_MUTATION_ROUTE_CATEGORIES` — and deciding deliberately whether a flow
   that reserves and pays in one step still belongs to the `reserve` category,
   or needs `payment` consent as well. That is a safety decision of the same
   weight as adding a category, not a bookkeeping one.
6. **A cancel story, or an explicit statement that there is none.** There is no
   PNR at that step, so `cancel` cannot act on the result. Whatever the group
   flow produces has to be releasable, or the method must say plainly that it
   is not.

None of this is impossible. It is a second payment implementation plus an
external redirect flow, for a booking type with a ten-person minimum — which is
why it is out of scope.


## 할인 / 쿠폰 / 공공할인 — the survey (2026-07-26)

The starting premise was `/ata/selectListAta01032_n.do`, the offline bundle's
only discount route. That premise did not survive contact, and the surface that
replaced it is larger and reachable. Everything below says where it came from:
**[bundle]** = the committed v2.0.41 offline bundle, **[page]** = a live
read-only GET of a server-rendered page, both dated 2026-07-26.

### What was already there

`PassengerCounts` carries the five `psgTpCd` types and nothing else, and the
bundle's `commCode.js` agrees with it exactly (`psgTpCd` 1..5, no more) — as
does the LIVE `/js/commCode.js`, fetched the same day, which still stops at 5.
Nothing about the ordinary booking path was wrong.

### What exists and is now implemented

| surface | route | evidence |
| --- | --- | --- |
| 할인종류코드 (`dcntKndCd`), 173 codes | — (data) | [bundle] `commCode.js:416-848` |
| 공공할인코드 (`PBL_DISC_CD`) `01`–`06` | — (data) | [page] `ARA0901P` popup's own comment block |
| 할인쿠폰 list | `GET /apa/selectListApa03020_n.do` | [page] the MY SRT menu on `/ara/ara0101v.do` |
| 공공할인 entitlements | `GET /common/ARA/ARA0301V/view.do` | [page] the same menu |

### What exists and is deliberately NOT implemented

**`POST /arb/selectListArb02A01_n.do` — 할인쿠폰 등록.** [page] The coupon page's
own `couponReg()` serialises `#couponInfo` (`dscp_no`, `dscp_pwd`) and posts it,
reading `resultMap[0].RTNCD` / `.MSG` back as JSON. It registers a coupon
against the account, so it is a mutation, and it belongs to no member of
`SRT_LIVE_MUTATION_CATEGORIES` — which is `{reserve, cancel, payment, refund}`
and pinned by a canary. Implementing it would mean adding a fifth category. It
is registered in neither allowlist and a test asserts that.

**`/ara/selectListAra10131_n.do` — the 할인 승차권 search.** [page] `goSubmit()`
on `ARA0301V` retargets `#rsvForm` here and submits it behind NetFunnel
`act_10`. The form is the booking form plus four fields (`PBL_DISC_CD`,
`PBL_DISC_NM`, `PBL_DISC_MG_NO`, `TGT_DTRM_YN`). **The route exists**: a bare
live GET answered `200` with a 조회결과 shell, where `/ara/selectListAra99999_n.do`
answered `404`. It is not implemented because exercising it needs an approved
공공할인, and nothing on this project has one — so every field this library
would put in `PBL_DISC_*` would be a guess, and the result would be unverifiable
in principle rather than merely unverified.

**`/ata/selectListAta01032_n.do` — the premise, and why it is dead.** [bundle]
`arc0102c.js:34` is its only caller anywhere in 21,673 files:

```js
$("#btn_dcnt").click(function() {
    $.mobile.changePage( contextPath + "/ata/selectListAta01032_n.do", {
        data: "pnrNo=${commandMap.pnrNo}"
    });
});
```

`${commandMap.pnrNo}` is a JSP expression sitting in a STATIC asset. The offline
bundle is never processed by a JSP engine, so that string goes on the wire
verbatim — this handler cannot ever have sent a real PNR from this file. It is a
fragment of a server-rendered page that was copied into the offline bundle and
left there. `btn_dcnt` and `arc0102c` are 0-hit everywhere else.

The live server agrees, and says so in a way worth recording because it is a
technique: **`404` and `500` are different answers.**

| request | status |
| --- | --- |
| `GET /ata/selectListAta99999_n.do` (control) | `404` |
| `GET /arc/selectListArc0102c_n.do` (control) | `404` |
| `GET /ata/selectListAta01032_n.do?pnrNo=` | `500` |
| `GET /ata/selectListAta01032_n.do?pnrNo=000000000000` | `500` |

All four render the identical "페이지가 존재하지 않습니다" body, so the body is
worthless and the status code is the whole signal. A 404 is the dispatcher
finding no controller; a 500 is a controller that ran and threw. So `Ata01032`
is **mapped but not exercisable without a real, owned PNR** — which would
require making a reservation, which this survey may not do. It is left
unimplemented, and `tests/test_safety.py` already refuses the route by name.

**What would settle it:** one `GET /ata/selectListAta01032_n.do?pnrNo=<a real
PNR the account holds>`, with `Referer` set to the reservation list. That is a
read; the reservation that has to exist first is not.

### The gap, stated plainly

`PassengerCounts` and the reservation payload could express five passenger
types. The live app can express **seven**, and both extras are invisible to the
bundle. That was the most consequential thing this survey found, and it has
since been closed: see "The 유아 fold and psgTpCd 6 — implemented".

## 공공할인 is a passenger vocabulary, not just a price

The repository stated, in five places, that SRT has no infant type and that
`infantCnt` and `psgTpCd` 6 do not exist. Every one of those statements was
true of the v2.0.41 offline bundle and false of the live server, and the error
was the same each time: reading "absent from the bundle" as "absent from the
protocol". They were corrected on 2026-07-26 rather than deleted.

**유아 (infant).** The live 승차인원선택 popup — fetched through this library's own
already-allowlisted `get_passenger_selector` — renders a SIXTH counter,
`passenger6`, labelled "유아 (만 6세미만)". The live booking page reads it and
does two things with it at once:

```js
var passenger6 = parseInt($('#passenger6').val()); // 유아
...
if(i==5){
    passenger = passenger + passenger6;   // folded into the 어린이 slot COUNT
    $('#infantCnt').val(passenger6);      // and sent separately as infantCnt
}
```

So an infant is counted inside `psgInfoPerPrnb` for 어린이 *and* declared again
in `infantCnt`. Both fields are on the live `#rsvForm`.

**청소년 (youth), as `psgTpCd` 6.** The same popup renders a SEVENTH counter,
`passenger7`, labelled 청소년 — `style="display: none;"` unless the 공공할인 code
is `"04"`, at which point the page reveals it and decrements the adult count.
`setTotalPassenger` sums `i=1..7`, and `returnPassenger` returns all seven. The
할인 승차권 page then maps `passenger7` into `psgTpCd6`/`psgInfoPerPrnb6`.

**`psgTpCd` 6 is in neither copy of `commCode.js`** — not v2.0.41 and not the
live `/js/commCode.js` fetched the same day, both of which stop at 5. It exists
only in what the server renders on the 공공할인 path.

**IMPLEMENTED 2026-07-26 (see the next section).** The paragraph that stood
here said nothing had been changed in `PassengerCounts` and explained why. That
was the right call for a survey and the wrong end state: the user asked for the
surface in full, and both types are now carried.

### Live reads this survey performed

All GET, all read-only, paced ~2s apart, on 2026-07-26. Nothing was reserved,
paid, refunded or cancelled.

| page | bytes | what it settled |
| --- | --- | --- |
| `/ara/ara0101v.do` | 156,478 | the MY SRT menu → both new routes; `infantCnt`, `psgTpCd6` |
| `/atc/selectListAtc14017_n.do` | 91,412 | the same menu, corroborating |
| `/apa/selectListApa03020_n.do` | 77,056 | 할인쿠폰: empty state, row template, `couponReg` |
| `/common/ARA/ARA0301V/view.do` | 206,268 | 공공할인: eight flags, four extra form fields, `Ara10131` |
| `/common/ARA/ARA0901P/view.do` | 12,231 | `PBL_DISC_CD` 01–06 by name; `passenger6`/`passenger7` |
| `/js/commCode.js` | 41,673 | `psgTpCd` still 1..5 live; four `dcntKndCd` renames |
| `/js/common/messages.js` | 30,086 | `rsv071`, `notice006` verbatim |
| `/ata/selectListAta01032_n.do` | — | `500` vs the controls' `404` |
| `/ara/selectListAra10131_n.do` | 136,326 | `200` vs the control's `404` |


## The 유아 fold and psgTpCd 6 — implemented, and what the server confirmed

`PassengerCounts` now carries seven counts. `infant` and `youth` were APPENDED,
so every existing positional construction keeps its meaning, and both default to
zero.

### The folding rule, exactly as the page writes it

Not paraphrased, because the tidier model is wrong in two places. From the live
booking page's `goRevFn`:

```js
for(var i = 1; i <= 5; i++) {
    var passenger = ...$('#passenger' + i)...;
    if(i==5){
        var passenger6 = ...$('#passenger6')...;
        passenger = passenger + passenger6;   // (1) folded into the 어린이 COUNT
        $('#infantCnt').val(passenger6);      // (2) declared again, separately
    }
    if(passenger != '' && passenger != '0'){  // (3) the test is on the SUM
        $('#psgTpCd' + no).val(i);
        $('#psgInfoPerPrnb' + no).val(passenger);
        no = no + 1;
    }
    totPrnb += passenger;                     // (4) so an infant is a HEAD
}
$('#psgGridcnt').val(no-1);                   // (5) but NOT a passenger type
```

The 할인 승차권 page's `setPassenger_callback` states the same fold again for its
own six-slot form (`psgInfoPerPrnb5 = parseInt(obj.passenger5) +
parseInt(obj.passenger6)`, `infantCnt = obj.passenger6`), which is why it is
implemented once, in `payloads._passenger_slot_counts`, and inherited by the
search, fare, reservation and transfer builders alike.

Two consequences that a cleaner model would have got wrong:

* **(3) infants with no children still fill the 어린이 slot**, because the test
  runs on the sum. `PassengerCounts(adult=1, infant=2)` transmits `psgTpCd=5`
  with count 2. Following the page.
* **(4) and (5) disagree on purpose.** An infant raises `totPrnb` and does NOT
  raise `psgGridcnt`. `total` and `_distinct_passenger_type_count` therefore had
  to stop being two views of one number.

`choiceSeatCount` is `totPrnb` (`ara1001l.js:1511`), so a folded infant also
counts as a seat for the seat-designation guard. That is the app's arithmetic,
not a decision taken here.

### psgTpCd 6, and why it is not gated

`youth` compacts last and widens the padded search form from five slots to six
— five being what the booking page's `i = 1..5` loop sends, six being what
ARA0301V's `oData` writes. `PADDED_PASSENGER_SLOTS` carries that reasoning.

The 승차인원선택 popup only reveals `passenger7` when the server renders
`pblDiscCd == "04"` into the page, but that is an account-level UI gate, not a
rule a payload builder can evaluate. Refusing a non-zero `youth` here would lock
out precisely the accounts the type exists for, so it is accepted and the
dependency is documented instead. `get_public_discounts()` is how a caller asks
whether their account holds it.

### What zero costs: nothing

With `infant=0` and `youth=0` every builder emits exactly what it emitted
before these fields existed — no `infantCnt`, no sixth slot, no changed count.
That is why `infantCnt` is conditional even though the live form always carries
`infantCnt=0`: sending it would tell the server what it already assumes while
retiring the byte-for-byte evidence from the 2026-07-25 live reserve→cancel
round trip. A parametrised test pins the invariance across all five builders,
and every pre-existing reservation-form test passed **unmodified**.

### Live-verified, and not (2026-07-26, read-only)

The search route echoes the request back in its own `commandMap`, which makes it
the cheapest possible confirmation that a field reached the server:

| sent | echoed back | rows |
| --- | --- | --- |
| `adult=1, child=2, infant=3` | `psgTpCd2="5"`, `psgInfoPerPrnb2="5"`, `infantCnt="3"` | 10 |
| `adult=1, youth=1` | `psgTpCd2="6"`, `psgInfoPerPrnb2="1"` | 10 |

**유아 — VERIFIED.** Both halves of the rule, from one infant count, confirmed by
the server's own echo, on a search that returned ten rows rather than an error.

**청소년 — VERIFIED ONLY AS FAR AS A READ REACHES.** The server accepted
`psgTpCd=6`, echoed it, and returned rows. It has NOT been shown that a 청소년
can be reserved, or is priced differently.

**Why the 운임 read cannot close that gap.** It was tried. `get_fare` returns a
per-TYPE price list — 어른/어린이/경로 × 특실/일반실, six items — and it was
byte-identical across `adult=1`, `adult=2`, `adult=1,child=1`,
`adult=1,infant=1` and `adult=1,youth=1`. It prices types, not parties, so it
cannot distinguish a party the fold changed from one it did not.

**Why the popup cannot either.** It accepts `passenger6`/`passenger7` and echoes
them in its own `commandMap` dump, but never seeds them back into its DOM (the
seeding branch writes only `passenger1..5`), and it keeps the 청소년 row
`display:none` regardless, because that reveal is gated on the server rendering
`pblDiscCd == "04"`.

**What the operator needs to close it**: an account approved for 공공할인 `04`
(청소년), and then one reservation carrying `psgTpCd6`. Both halves are outside
what this work may do — the first is an entitlement, the second is a mutation.
For 유아 the remaining question is smaller and also needs a mutation: whether the
server issues a 유아 a seat, since `choiceSeatCount` counts it.
