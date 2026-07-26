# Changelog

## Unreleased

- **Payment and refund are live-verified and live-enabled.**
  `safety.SRT_LIVE_MUTATION_CATEGORIES` now holds
  `{"reserve", "cancel", "payment", "refund"}` — the four categories a live run
  has answered, and nothing is in that set for any other reason. This
  **supersedes the entry below** ("Card payment and refund are implemented, and
  still cannot be transmitted"), which was accurate when it landed: implementing
  them did not open the gate, and verifying them did.
  **The verification, 2026-07-26, in two stages.** A free probe went first: a
  fake card and a non-existent PNR were sent to both routes, and neither
  answered a 404 or an HTML error shell. `/atc/getListAtc14087.do` returned
  `{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"WRT300005",
  "strResult":"FAIL","msgTxt":"조회자료가 없습니다."}]},"ErrorMsg":""}` and the
  payment route `/ata/selectListAta09036_n.do` returned `strResult=FAIL` /
  `msgCd=WRT100170` — proper business envelopes on both, which established that
  `Ata09036` and `Atc14087`/`Atc02063` exist on our v2.0.41 app version without
  spending anything, even though all three are 0-hit in its offline bundle and
  srtgo-attested only. **Then one real round trip:** 수서→동탄
  (`0551`→`0552`, the shortest SRT hop), 2026-08-09, train 315, one adult,
  7,500 KRW. Payment answered `strResult=SUCC` / `msgCd=IRT000000`; the two-step
  refund (`Atc02063`) answered `strResult=SUCC` / `msgCd=IRT200277`; the account
  was then verified empty of both reservations and tickets from a separate
  session. So `Ata09036` and `Atc02063` are **live-verified on 2026-07-26**, for
  a single-journey one-adult ticket, and remain 0-hit in the v2.0.41 bundle —
  two statements about different evidence, both true.
  **Two things this settled that were previously recorded as open.** First,
  `IRT000000` and `IRT200277` are identical to korail's confirmation codes for
  the same two operations, reinforcing the shared-platform observation already
  recorded here for `IRR000018`/`IRG000000` — still an observation about the
  codes, not a proven claim about the backend. Second, **srtgo's refund
  spellings `tkRetPwd`/`psgNm`/`pnr_no` are correct**: the live run sent them
  and the server refunded the ticket, so the doubt recorded below (against our
  app's `retPwd`/`buyPsNm`/`pnrNo` cache spellings) is resolved in srtgo's
  favour. Unlike srtgo's korail `txtPrnNo`, which this project found to be a
  genuine typo. srtgo was wrong there and right here — single-source field names
  have to be tested one at a time, not trusted or distrusted as a class.
  **What it did not settle.** The origin is unchanged: `Ata09036`, `Atc02063`
  and `Atc14087` are still 0-hit across all 21,673 files of the v2.0.41 offline
  bundle (which has no `Atc02*` family at all), our own app still charges
  through the `Ard02017`/`Ard02018` WebView plus TransKey and FIDO, the payment
  shape is still one implementation counted twice and the refund shape one with
  no upstream. One live success is live-server evidence, not static
  corroboration, and it covered a single-journey, one-adult, general-seat ticket
  on one personal card in one lump sum. Group, multi-leg, standby, corporate
  cards and instalments were not exercised.
  **Thirteen tests asserted that payment and refund could not transmit.** None
  of that coverage was deleted; each pin moved onto the invariant that survived,
  and the canaries now pin the exact enabled set so a *fifth* category still
  fails loudly rather than pinning "nothing is enabled". Consent gating,
  `dry_run`, the card-kind XOR, step 1's no-body contract, step 2's dependence
  on a step-1 identity, the route/category binding in both directions and
  `assert_no_card_secrets` all still refuse and still issue zero requests. The
  "cannot be sent" tests became "is built, gated and routed correctly": each
  category's exact wire fields are now asserted off a recorded `MockTransport`
  request under a fully valid consent.
  **`assert_no_card_secrets` matters more now, not less.** While `payment` was
  outside the enabled set, "a PAN cannot leave this process by any path" was
  already guaranteed by the membership gate. It is now the only thing between a
  hand-assembled card body and the wire on every route that is not the payment
  route, so its tests are load-bearing individually.
  Offline gate: `1311 passed, 1 deselected` (was `1285`).

- **Card payment and refund are implemented, and still cannot be transmitted.**
  *(Superseded by the entry above: both were live-verified and live-enabled on
  2026-07-26. The provenance recorded here is unchanged and still applies; only
  the "cannot be transmitted" and "`SRT_LIVE_MUTATION_CATEGORIES` is untouched"
  claims are retired, along with the disputed-spelling doubt.)*
  `SrtClient.pay_with_card` builds the 31-field 카드결제 form for
  `/ata/selectListAta09036_n.do`; `SrtClient.get_refund_ticket_info` reads an
  issued ticket's identity from `/atc/getListAtc14087.do` and
  `SrtClient.refund` builds the 환불 form for `/atc/selectListAtc02063_n.do`.
  All three build, gate, preview and parse. **`SRT_LIVE_MUTATION_CATEGORIES` is
  untouched at exactly `{"reserve", "cancel"}`** — implementing these did not
  live-enable them, that is a separate decision nobody has made, and three
  canary tests plus a test proving a fully-permissive consent (including one
  acknowledging a real chargeable card) still transmits nothing pin it.
  **Read the provenance before trusting any field.** The route
  `Ata09036` and the refund routes `Atc14087`/`Atc02063` are 0-hit across all
  21,673 files of the v2.0.41 offline decompile — the bundle has no `Atc02*`
  family at all — and **our own app does not use the payment path**: it
  serialises `#rsvForm` to `Ard02017`/`Ard02018` (`ara1001l.js:1550,1599,1608`),
  server-rendered WebView pages, then charges through the TransKey secure keypad
  (`AndroidManifest.xml:143`) and RaonSecure FIDO (`:315`). So these plaintext
  endpoints may be a legacy path the server still honours, or dead for our app
  version. **Nobody has tested them.**
  **The two reference libraries are one source, not two, and this was verified
  rather than assumed.** srtgo's payment dict is character-for-character
  identical to ryanking13/SRT's once the latter's Korean comments are stripped
  (same keys, values, non-alphabetical order, variable names, signature); srtgo
  depended on `SRTrain` until commit `8423f90` "Internalize SRT" (2024-12-13)
  vendored it wholesale. For the refund it is worse: ryanking13/SRT has no
  refund at all, so srtgo is the sole origin with no upstream to corroborate it.
  **The blanket "every field name is 0-hit" claim is false**, and the accurate
  version is recorded instead: the routes and the distinctive field names really
  are absent, but `mbCrdNo`, `totPrnb`, `jrnyCnt` (reservation JS) and
  `buyPsNm`, `saleWctNo`, `saleSqno`, `retPwd` (the local `"ticketListOffline"`
  cache handler, `webview/b.java:606-649`) do occur — never as request fields on
  these routes.
  **Amount fidelity was chosen deliberately**, against korail's precedent
  (`h_tot_prc` 59,800 vs `h_tot_rcvd_amt` 83,700): the form sends `rcvdAmt`
  (수납금액, post-discount, collectable) for both `totNewStlAmt` and
  `mnsStlAmt1`, with **no caller override**, and refuses a missing or zero
  amount rather than defaulting. One divergence stays unresolved — the server
  sends it zero-padded, ryanking13/SRT echoes the padding, srtgo casts to `int`;
  we send srtgo's bare digits because only srtgo's form has live attestation.
  **Two refund field names are disputed**: srtgo's `tkRetPwd`/`psgNm` against our
  app's `retPwd`/`buyPsNm` (`webview/b.java:645,648`), plus `pnr_no` against
  `pnrNo`. That b.java site deserialises a base64 SharedPreferences blob into a
  display model — a local cache, not an API schema — so srtgo's spelling ships
  and the doubt is recorded. The project has been burned here before, by srtgo's
  `txtPrnNo` for korail's `txtPnrNo`.
  **The payment's response envelope is the odd one out**: `outDataSets.dsOutput0[0]`
  where every other SRT mutation here uses `resultMap` (the refund included).
  Supporting it cost no new code path — `normalize_result_row` already accepted
  both spellings — and cancel, payment and refund now share one
  `_parse_result_envelope`. `SrtPaymentResult.succeeded`/`.failed` are
  deliberately **not** complements: an unrecognised status means *unknown*,
  because a blind payment retry can charge twice.
  **The refund's two steps are separate methods on purpose**, so a refused
  refund makes zero requests instead of firing step 1 and only then hitting the
  step-2 refusal. Step 1's route is registered as a read; that classification is
  an inference, not a proof, and says so — and because it is allowlisted, its
  "no body at all" contract is now **enforced** rather than merely documented,
  so it cannot be used to POST a card or refund form to a permitted path.
  **A PAN cannot leave this process by any path.** Route and category rules
  could not close one case: a hand-assembled payment body posted to a
  *different, permitted* route — an allowlisted read, or the live-enabled
  reserve route under a valid `category="reserve"` consent — is neither a
  category nor a route violation. `safety.CARD_SECRET_FIELDS` states the rule on
  the **data**: `stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`, `athnVal1` may travel
  only as a `payment`, checked in `assert_read_only_request` and again at the
  mutation send boundary. *(When this landed `payment` was not live-enabled, so
  the effect was absolute and this guard was a second lock. It is now the only
  lock on every non-payment route — see the top of this section.)*

- **`MutationConsent.real_card_acknowledged`**, defaulting to `False` and purely
  additive, ports the KORAIL real-card acknowledgement pattern. A payment must
  state exactly one of `fake_card_only` (a non-chargeable test card) or
  `real_card_acknowledged` (a real charge); **neither and both are refused**,
  because an ambiguous consent is exactly the state a payment must never be sent
  on. Every consent written before this flag existed means exactly what it meant.
  Setting it is still not what enables a payment — live enablement is
  `SRT_LIVE_MUTATION_CATEGORIES`'s job — but since payment was enabled on
  2026-07-26 this XOR is the last gate before a real PAN goes out.

- **Redaction covers the payment and refund secrets**, and closed a
  pre-existing hole: `pnr_no` was absent from `SENSITIVE_KEYS` while `pnrNo` and
  `pnr_number` were present, so `redact_value` — which masks a dataclass by
  field name — passed a real PNR straight through for `SrtReservationHold` and
  `SrtReservationSummary`. Also added: the refund return password under all
  three spellings (`ogtkRetPwd`, `tkRetPwd`, `retPwd`), `buyPsNm`/`psgNm`, and
  `SrtPaymentCard`'s own attribute names, since `CARD_RE` only matches a 13-19
  digit run and a 2-digit PIN, a `YYMM` expiry and a `YYMMDD` birthdate all slip
  past it. The refund's `saleDt`/`saleWctNo`/`saleSqno` are deliberately **not**
  masked: with the password redacted they authorise nothing, and a
  fully-redacted preview says nothing at all.

- **Server-side failures now have a taxonomy.** Almost every rejection arrived
  as one undifferentiated `SrtAppError` with only `NET000001` special-cased, so
  a caller could not tell "this train is sold out" from "your session died" from
  "the queue refused you" without substring-matching Korean `msgTxt` — which is
  what `srtgo` does (`srtgo/srtgo.py:721-744`) and which breaks the day a
  message is reworded. Six new types, **each subclassing the one it refines**,
  so no existing `except` clause changes meaning: `SrtNoResultsError`,
  `SrtInvalidRequestError` and `SrtSeatUnavailableError` under `SrtAppError`;
  `SrtNetFunnelKeyError` and `SrtQueueRejectedError` under `SrtNetFunnelError`;
  `SrtIpBlockedError` under `SrtAuthError`. Read the tree as three caller
  answers: *retry is pointless* (`NoResults`, `InvalidRequest`,
  `SeatUnavailable`, `QueueRejected`, `IpBlocked`), *re-login and try again*
  (`SessionExpired`), *get a fresh key* (`NetFunnelKey`).
  **Classification is on `msgCd`, not on message text, because that is what the
  app does.** The single place in all 21,673 files of the v2.0.41 bundle where a
  server-supplied string is branched on is a code — `resultMap.msgCd == "S111"`
  → `memberShipLogin()` (`ara1001l.js:1562-1573`). Every other branch is
  `strResult == "FAIL"` (`ara1001l.js:206`, `:234`, `:1855`) or
  `ErrorCode == -1` (`:193`, `:1840`), which carry no reason at all, and the app
  never substring-matches `msgTxt` — it only displays it. Each exception keeps
  the raw `.code` and `.raw`, and an unmapped code still yields a plain
  `SrtAppError`, so the map grows from real traffic rather than from guesses.
  The queue is the one subsystem whose own bundle discriminates:
  `_showResultChkEnter` gives `kTsBlock` (301) and `kTsIpBlock` (302) their own
  `"onBlock"`/`"onIpBlock"` events beside `"onError"`.
  **`messages.js` turned out not to be a `msgCd` catalogue** — it is a
  client-side UI string table keyed `error001`/`rsv001`/`login018`, 172 strings,
  zero server codes. It matters in exactly one place: the sold-out seat page's
  error shell embeds `Sr.msgs.error001`, so `SrtSeatUnavailableError.code` is
  that alert *key*.
  **Two of srtgo's six leads are confirmed, but by code:**
  `"로그인 후 사용하십시오"` is our `S111` and
  `"정상적인 경로로 접근 부탁드립니다"` is our `NET000001`. The remaining four
  (`잔여석없음`, `사용자가 많아 접속이 원활하지 않습니다`,
  `예약대기 접수가 마감되었습니다`, `예약대기자한도수초과`) are 0-hit in the
  bundle, have no known `msgCd`, and the last two describe 예약대기 — a surface
  this library does not implement. They are **not** encoded; a test pins that
  they stay plain `SrtAppError`.
  **No retry behaviour was added.** The single bounded `NET000001` search retry
  is still the only self-directed retry, and `reserve` is still never retried
  because a retry duplicates a booking. Both live empty-result shapes are pinned
  against regression: the empty search FAIL (`WRG000000`) now raises
  `SrtNoResultsError`, while an empty reservation list still returns an empty
  list and the second `rsMap`/`WRT300005` FAIL envelope on that same successful
  response is still never read.

- The NetFunnel queue protocol is now complete. We sent only `getTidChkEnter`
  (5101); the bundle's own vendored `netfunnel.js` defines three request types
  (`RTYPE_CHK_ENTER=5002`, `RTYPE_SET_COMPLETE=5004`,
  `RTYPE_GET_TID_CHK_ENTER=5101`, netfunnel.js:84) and we implemented one third
  of it. Two consequences: if the queue actually engaged (201 `kContinue`) the
  search **failed** — the queue working as designed looked like an error — and
  the slot was never released, so our place in line was held until it timed out.
  Added `chkEnter` polling with HARD caps (20 polls or 60s wall clock, whichever
  first; each wait is the server's own `ttl` clamped to the app's 1..5s
  `TS_MAX_TTL`, so it can never become a tight retry loop) and `setComplete`
  after every guarded request, matching the bundle's `TS_AUTO_COMPLETE = true`.
  A failed release is swallowed by design: it runs after the caller's real
  request already succeeded or failed, and must never replace that outcome —
  least of all on a `reserve`, where it would hide a PNR.
  `safety.py`'s `/ts.wseq` contract now registers **three exact per-opcode query
  shapes** instead of one; it was not loosened. Two bundle details are recorded
  because they contradict the obvious assumption that one shape covers all
  three: `setComplete` carries **no `sid` and no `aid`** (the only one of the
  four builders in `netfunnel.js` that omits them), and `ttl` sits **between
  `prefix` and `sid`** on `chkEnter`, carrying the server's returned value
  rather than a constant. `js=yes` stays pinned throughout — srtgo and
  ryanking13/SRT both send `js=true`, and the bundle says `yes`.
  **Live-verified 2026-07-26**: a real acquire → release round trip
  (`5002:200` with a 256-character key and `ttl=0`/`nwait=0`, then `5004:200`).
  **Not verified**: the 201 polling path, because at normal load the queue does
  not engage and load was deliberately not synthesised to force it. That live
  run caught a bug no fixture could — the key-shape guard bounded keys at 128
  characters while a real key is 256, so every `setComplete` failed the guard
  and was silently swallowed. One divergence is deliberate: the acquire reply
  names a specific queue node (`ip`/`port`) the app would follow, and we stay
  pinned to the two canonical origins instead; the live run showed the front
  door releases the slot anyway.

- New read: `SrtClient.get_reservations(page_no=0)` — `POST
  /atc/selectListAtc14016_n.do` with `pageNo`, returning typed
  `SrtReservationSummary` rows in an `SrtReservationListResult`. This is the
  first read that ENUMERATES reservations; before it, the only way back to a
  hold whose PNR had been lost was to type the PNR into
  `scripts/recover_hold.py`, which required already knowing it. That script
  gains `--list`, a pure read that constructs no consent and prints the
  candidate PNRs.
  **Live-verified 2026-07-26 for the EMPTY case only** (the account has no
  reservations): `resultMap[0].strResult=SUCC` / `IRZ000005` /
  "조회할 자료가 없습니다." with `trainListMap: []`, `payListMap: []`,
  `rowCnt: 0`, `totPageCnt: 0`. Two verified oddities are pinned by tests: an
  empty result here is an empty *array*, not the `strResult=FAIL` /
  `WRG000000` the train search uses; and the same successful response carries a
  second envelope, `rsMap[0]`, saying `FAIL` / `WRT300005`, which is
  deliberately not read as a failure. The POPULATED row shape is **unverified**
  — the container pairing and every row field name come from srtgo
  (`srt.py:1069-1082`), and `payListMap`, `tkSpecNum`, `iseLmtTm` and `stlFlg`
  are 0-hit in the v2.0.41 bundle. Our bundle attests the route and `pageNo`
  only, as a WebView GET (`SRForegroundDialogActivity.java:31`,
  `sub/ticketList.html:405`); the JSON-over-POST spelling is srtgo's. Both were
  confirmed live; only the POST is allowlisted, taking `READ_ONLY_ROUTES` from
  20 routes to 21.

- A NetFunnel bypass (`kTsBypass` = 300) is now accepted without a key.
  `SUCCESS_CODES` already held `{"200", "300"}`, but the key check below it was
  unconditional, so the acceptance of 300 was unreachable for the only response
  shape a bypass actually has. The app's `_showResultChkEnter` sets
  `PS_N_RUNNING`, stores the result cookie and fires `onBypass` without ever
  reading `getValue("key")` — a bypassed queue has no place in line to key. Our
  `SrtNetFunnelError` escaped `SrtClient._get_act10_key` with code `None`, which
  `_search_with_retry` does not match (it retries only `NET000001`), so a
  bypassed queue aborted the search instead of searching. `kSuccess` (200) still
  requires a key. An empty key is inert downstream — every builder that consumes
  one emits `netfunnelKey=""`, verified by test, which is also what our own app
  sends, its NetFunnel integration being commented out
  (`ara0101v.js:651-655`, `ara1001l.js:1734-1739`) and `netfunnelKey` appearing
  nowhere in the v2.0.41 bundle.
- `TrainSearchQuery.train_group_code` now defaults to `"109"` (전체), the app's
  own booking-screen default, instead of `"900"` (KTX+SRT). `ara0101v.js:85-86`
  sets the picker to `"109"`/전체 on load and `:98-99` seeds
  `trnGpCd1="109"`/`trnGpNm1="전체"`. All three codes are legitimate on the wire,
  so this is a default *choice* rather than a wire error — but the old value had
  no evidence comment and disagreed with two other defaults in this same
  codebase (`SrtClient.get_train_group_selector` and
  `train_group_selector_payload` both already used `"109"`/`"전체"`). `"300"` and
  `"900"` remain constructible.
- `SrtClient.get_seat_page` derives `choiceSeatCount` from the passenger total
  instead of hardcoding one seat. The app sends
  `choiceSeatCount: lfn_getRsv("totPrnb")` (`ara1001l.js:1511`) — the party size
  the booking screen collected (`ara0101v.js:794`/`:809`) — and
  `safety.SEAT_PAGE_VALUE_PATTERNS` already validated the field as any positive
  integer for that reason, but nothing was wired to it. New keyword-only
  `passengers=`; `seat_count=` is kept as the explicit override and now defaults
  to `None` ("not overridden") rather than `"1"`. With neither, the count is
  still one seat. `run_live_smoke` had the same bug — it searched with
  `query.passengers` and then read the seat page for one seat — and now passes
  the party through.
- `personal_reservation_payload` now sends `arvDt1` (도착일자), which it omitted
  entirely. The app writes it in the same block as the `dptDt1`/`dptTm1`/
  `arvTm1` we already sent (`ara1001l.js:1464`), and srtgo omits it only because
  `SRTTrain` has no arrival date — a divergence
  `docs/analysis/cross-validation-2026-07-21.md` had already recorded as an open
  one. Reserve is the only mutation route whose shape can be checked statically,
  so it is closed rather than left unverified. The value comes from
  `TrainSummary.arrival_date`, in the app's own field position (between `dptTm1`
  and `arvTm1`), and is blank when the row omits `arvDt` — matching the app's
  `#rsvForm` seed, and because a form that cannot be built is a reservation that
  cannot be made. The srtgo wire-fidelity test was changed deliberately, not
  weakened: it now pins srtgo's field set PLUS this one field, with the reason
  recorded in place.
- `personal_reservation_payload` now sends the OPERATING date in `runDt1`
  (`TrainSummary.run_date`), not the departure date. The app writes the two from
  different search-row fields in the same block — `ara1001l.js:1460`
  `"runDt1": item.runDt` (운행일자) versus `:1462` `"dptDt1": item.dptDt`
  (출발일자). srtgo sends `dep_date` for both only because `SRTTrain` carries no
  run date, and reproducing that was indistinguishable for a same-day service
  but wrong for a past-midnight one. We already parse `runDt`, and
  `seat_page_payload`, `timetable_payload` and `fare_payload` already use it;
  the reserve builder was the last one substituting the departure date. A row
  that omits `runDt` still falls back to the departure date, so the srtgo-
  equivalent case is unchanged; a `runDt` that is present but not an 8-digit
  date is rejected rather than silently replaced.
- Corrected the reservation-response polarity to the app's. The attempt parser
  failed on `strResult != "SUCC"`, but `ara1001l.js:1562` is
  `if (resultMap.strResult == "FAIL")` — it alerts and returns there, and any
  other value falls through to `:1577`/`:1609`, which read
  `reservListMap[0].pnrNo` and proceed with a created reservation. The app is
  consistent about this (`:206`, `:234`, `:1855`), and the search parser was
  already corrected the same way. The inverted test was duplicated in the
  salvage gate, so a third status value raised `SrtAppError` **and**
  simultaneously suppressed the PNR salvage — the exact orphaned hold that
  subsystem exists to prevent. Both now test `== "FAIL"`
  (`_declares_a_non_success` is renamed `_declares_a_declared_failure` to say
  what it means). `WRP011002` stays an independent failure signal; it was
  observed live alongside `strResult=FAIL`, so it never contradicts the
  polarity. A genuine FAIL still raises, still authoritatively over malformed
  `msgCd`/`msgTxt`, and is still refused by the salvage branch.
- **The live reserve->cancel round trip was performed on 2026-07-25 and both
  halves succeeded.** One operator run of
  `scripts/verify_reserve_cancel_roundtrip.py` against the real server (수서 →
  부산, one adult, general seat, a single train) exited 0: `reserve` returned
  `strResult=SUCC`, `msgCd=IRR000018` ("결제하지 않으면 예약이 취소됩니다.") and a
  PNR, `cancel` (`ard/selectListArd02045_n.do`, body `pnrNo` / `jrnyCnt="1"` /
  `rsvChgTno="0"`) returned `strResult=SUCC`, `msgCd=IRG000000`
  ("정상처리되었습니다"), and the ticket list re-read afterwards held no trace of
  the reservation — re-verified independently in a later session. The hold was
  never paid, so nothing was charged.
  This confirms, **against the live server and for our app version**, the cancel
  route and its exact three-field body, plus reserve's live wiring: the
  NetFunnel `act_10` key flow (the same one train search uses, *not* `act_19`)
  and the referer the client sends were both accepted. It does not change where
  the cancel shape came from: it was taken from srtgo and is still 0-hit across
  all 21,673 files of our v2.0.41 offline decompile, so this single run is its
  only corroboration.
  **Scope.** ONE single-journey, one-adult, general-seat reservation. Multi-leg
  (`jrnyCnt` > 1), group and standby reservations were not exercised, so
  `jrnyCnt="1"` is confirmed only for the single-journey case. `payment` and
  `refund` were unimplemented at the time of this run, stayed out of
  `SRT_LIVE_MUTATION_CATEGORIES`, and nothing was learned about their shapes
  here — they were implemented, then verified separately on 2026-07-26 and
  live-enabled; see the top of this section.
  Worth recording: both confirmation codes are identical to the sibling korail
  app's live-verified ones (reserve `IRR000018`, cancel `IRG000000`), which
  suggests the two operators run on a shared reservation platform. That is an
  observation about the codes, not a proven claim about the backend.
- Added `scripts/verify_reserve_cancel_roundtrip.py`, the operator-run live
  reserve->cancel verification. **It has since been run once, successfully — see
  the entry at the top of this section.** It logs in, searches,
  selects ONE train that actually has a bookable seat (refusing to proceed if
  none does), reserves one adult in the cheapest class, prints the PNR
  immediately, cancels it, and re-reads the ticket list to confirm nothing
  remains. It requires a second opt-in beyond the normal live flag —
  `SRT_LIVE_MUTATION=1` on top of `SRT_MOBILE_API_LIVE=1` — so it can never
  fire from an ordinary live smoke run, since "live reads are acceptable" is
  not consent to create a reservation. The raw `strResult`/`msgCd` are printed
  for both operations: they are the evidence the run exists to capture. Reserve
  and cancel are performed under separate single-category consents, so neither
  call carries the other's authority. Everything after a successful reserve is
  wrapped in `try`/`finally`; the `finally` retries the cancel if it has not
  already succeeded, and if that fails too the PNR is printed in an unmissable
  banner with the exact `recover_hold.py` command line. Exits non-zero on any
  failure; the password is never printed and the login id is masked.
- Extracted `read_query_from_env()`, `read_passenger_counts_from_env()`,
  `read_device_key_from_env()`, `train_is_reservable()` and
  `first_reservable_srt_train()` into `srt_mobile_api.live`, and rebuilt
  `run_live_smoke_from_env()` on the first three. The round-trip script reads
  the journey environment through these same helpers instead of growing a
  second, silently divergent set. `first_reservable_srt_train()` screens a row
  by asking the reserve builder whether its form can be built, rather than
  re-listing the required fields and drifting from it.
- Added `scripts/recover_hold.py`, the operator safety net for a stranded
  unpaid hold. It takes a PNR on the command line, logs in from
  `SRT_LOGIN_ID`/`SRT_LOGIN_PASSWORD`, and cancels that hold — deliberately
  standalone, needing no hold object or state from the run that created it,
  because the situation it exists for is the one where that run is gone. Its
  consent is constructed explicitly and grants `cancel` only (never reserve,
  payment or refund) with `dry_run=False`, since a dry run would preview and
  release nothing. It exits 0 only when the server reports the hold released,
  prints the raw `strResult`/`msgCd`, and reprints the PNR in a banner on every
  other outcome, including any exception. The password is never printed.
- **`SrtClient.reserve()` can now transmit.** It returns
  `MutationPreview | SrtReservationHold`: unchanged under the default
  `dry_run=True`, but a `dry_run=False` reserve consent now POSTs
  `arc/selectListArc05013_n.do` and returns the parsed `SrtReservationHold`
  whose `pnr_no` feeds `cancel()`. **A success creates a real unpaid hold on a
  real account**, which the caller owns and must cancel or pay. The NetFunnel
  gate is the same `act_10` key flow as train search (srtgo `srt.py:987`, *not*
  `act_19`), so it reuses the existing `_get_act10_key` rather than adding a
  second acquisition path; a caller-supplied `netfunnel_key` is honoured
  verbatim and suppresses the acquisition. A failed reserve is never retried, so
  at most one hold can exist per call, and session expiry clears the session and
  re-raises as it does for every other authenticated call.
  Losing a PNR is the worst outcome this path can produce, so it is designed
  against: if strict parsing trips over a field unrelated to the PNR *after* the
  server has created the hold, a degraded but **cancelable** hold is returned
  instead of raising, while a server-declared failure still raises rather than
  inventing a hold that does not exist. The live NetFunnel/referer wiring was
  unverified when this landed and **has since been exercised successfully** (see
  the 2026-07-25 entry at the top of this section); `scripts/recover_hold.py`
  cancels a stranded hold from nothing but its PNR string.
- **Live-enabled exactly two mutation categories, `reserve` and `cancel`.**
  `safety.SRT_LIVE_MUTATION_CATEGORIES` was an empty frozenset and is now
  `{"reserve", "cancel"}`, so a consented `dry_run=False` call in either
  category reaches the network. They are enabled together and only together:
  reserve creates an unpaid hold and cancel releases one (from a hold object or
  a bare PNR string), so enabling reserve without a transmittable cancel would
  strand a real reservation on any mid-flow failure. **`payment` and `refund`
  stayed out at this point**, and adding either required implementing it
  (neither had a client method then) and live-verifying its own wire format;
  a payment keeps a separate `fake_card_only` gate behind the live-enablement
  one. *(Both requirements were met later in this same unreleased range: the
  methods landed, then the 2026-07-26 live round trip verified them and the set
  grew to four. See the top of this section.)*
  This was a decision about **recoverability, not evidence**, and asserted
  nothing about verification: when it landed, the cancel route `ard02045` was
  srtgo-sourced and unconfirmed against our v2.0.41 app (0 hits across all
  21,673 files of the offline evidence bundle) and the live reserve->cancel round
  trip had not been performed. Opening the gate is what made performing it
  possible — **and it was performed on 2026-07-25**, confirming both halves
  against the live server (see the entry at the top of this section). The 0-hit
  fact is unchanged; what changed is that a live run now corroborates the shape.
- Ported the consent-gated mutation model from the verified korail surface. The
  package stays read-only **by default**: `MutationConsent` grants nothing on
  construction (every `allow_*` flag defaults to `False`), `dry_run` defaults to
  `True`, and `fake_card_only` defaults to `True`;
  `require_mutation_consent()` denies before any request is built, raising the
  new `SrtMutationNotAllowedError`. A `MutationPreview` forces its payload
  through `redact_payload()`, so a preview can never hold card data, PII, a PNR,
  or a NetFunnel key.
- Tiered the four evidenced state-changing routes (reserve `arc05013`, cancel
  `ard02045`, payment `ata09036`, refund `atc02063`) in
  `safety.SRT_MUTATION_ROUTES`, deliberately **outside** `READ_ONLY_ROUTES`:
  `assert_read_only_request()` still refuses every one of them, so the read-only
  allowlist and its 20-route guarantee are unchanged. `SRT_MUTATION_ROUTE_CATEGORIES`
  binds each route to exactly one consent category, so a consent for one
  category cannot be redirected to another category's route.
- Added `SrtClient.reserve()` (personal reservation, `arc/selectListArc05013_n.do`),
  its request builder `personal_reservation_payload()`, the
  `parse_reservation_hold_response()` parser, and the `SeatType` /
  `SrtReservationHold` types. As first added, `reserve()` was **preview-only**:
  `dry_run=False` was refused and the method returned a redacted
  `MutationPreview` of the exact form that would be POSTed, performing no I/O,
  because no cancel existed to release a hold it would create. **Superseded
  within this same unreleased range** — see the `reserve()` entry at the top of
  this section: once `cancel()` existed and both were live-enabled, that refusal
  was removed and `reserve()` now transmits under an explicit non-dry-run
  consent.
- Closed the transport-layer gap that this port opened. `SrtHttpClient.post_mutation_form`
  was ported wholesale and did transmit, so a caller reaching `SrtClient.http`
  directly could bypass `reserve()`'s preview-only hardening for any of the four
  categories. `safety.SRT_LIVE_MUTATION_CATEGORIES` — an empty frozenset when
  introduced — now names the categories permitted to reach the network, and it
  is enforced in `post_mutation_form` and re-asserted in the underlying
  `_send_mutation_request`, the function that actually calls `send`. Which
  categories are in that set changed twice more in this same unreleased range
  (see the top of this section: it now holds
  `{"reserve", "cancel", "payment", "refund"}`); what this entry established,
  and what still holds, is that membership is decided at the **transport layer**
  rather than only at the client methods, so a category outside the set cannot
  be transmitted even by a caller reaching `SrtClient.http` directly.
- Added `SrtClient.cancel()` for a created-but-unpaid reservation (예약취소,
  `ard/selectListArd02045_n.do`), with its request builder
  `unpaid_reservation_cancel_payload()`, the `parse_unpaid_cancel_response()`
  parser and the typed repr-safe `SrtCancelResult`. It accepts an
  `SrtReservationHold` or a bare PNR string (a caller recovering from a partial
  failure may have only the PNR), requires an authenticated session, is gated by
  `require_mutation_consent(consent, "cancel")`, and with the default
  `dry_run=True` returns a redacted `MutationPreview` and performs no I/O. As
  first added it was implemented and offline-tested only, its wire shape taken
  from srtgo and unconfirmed against our v2.0.41 app: the route is 0-hit across
  all 21,673 files of the offline evidence bundle, and only the `jrnyCnt="1"`
  value is partially corroborated by our own app (`ara0101v.js:92`). It could
  not transmit at all, the gate being empty. **Superseded twice within this same
  unreleased range**: `cancel` was live-enabled (see the top of this section) so
  `dry_run=False` reaches the wire, and the "unconfirmed" half of the provenance
  caveat fell on **2026-07-25**, when a live round trip released a real hold
  through this exact form (`SUCC` / `IRG000000`). What is NOT superseded is the
  shape's origin: it still comes from srtgo, is still 0-hit in the v2.0.41
  bundle, and is now corroborated by exactly one live run of one single-journey,
  one-adult hold.
- `jrnyCnt` is defaulted to `"1"`, not derived from the hold: the reserve
  response carries `totSeatNum` (a SEAT count) and no journey count, so
  `SrtReservationHold` has nothing to derive from, and every hold this library
  can create is single-journey. The optional `journey_count` override is
  compared numerically, tolerates zero-padding and whitespace (`"0001"` ->
  `"1"`), and falls back to `"1"` for anything unusable instead of raising —
  applying the korail regression (korail commit `3d7e8a5`), where a builder that
  demanded exactly `"1"` refused a live `h_jrny_cnt="0001"` and stranded a real
  unpaid hold. A cancel form that cannot be built means a hold that cannot be
  released. "Never raises" is now literally true: the zero padding is stripped
  textually before any numeric conversion, and a value past CPython's int/str
  conversion limit (4300 significant digits, on which `int()` raises
  `ValueError`) falls back instead of propagating. The override is reachable
  from `SrtClient.cancel(..., journey_count=...)` as well as from the builder:
  without it, the day live capture shows a multi-leg PNR needing `jrnyCnt="2"`
  a caller would have to hand-roll `payloads` plus `post_mutation_form`, which
  is precisely the path that orphans holds. The default is unchanged.
- `parse_reservation_hold_response()` no longer discards a reserve response that
  fails strict validation. A live reserve can create a hold before we parse, so
  when strict parsing raises a protocol error and a usable
  `reservListMap[0].pnrNo` is present, a minimal `SrtReservationHold` carrying
  the PNR is returned instead (mirroring korail's
  `_hold_from_reservation_response`); with no PNR the original error is
  re-raised, and business failures and session expiries are never salvaged. This
  is a prerequisite for ever enabling live reserve.
- Made "business failures and session expiries are never salvaged" actually
  true. `parse_reservation_attempt_response` read `msgCd`/`msgTxt` strictly
  BEFORE classifying the declared `strResult`, so a FAIL that was also slightly
  malformed (no `msgCd`, an int `msgCd`, no `msgTxt`) raised `SrtProtocolError`
  — the one exception the salvage branch catches — and
  `parse_reservation_hold_response` returned a minimal hold for a reservation
  the server had just refused. Telling a caller a hold exists when it does not
  is as damaging as losing one that does: they stop trying to recover. The
  declared status is now classified first, so such a response raises
  `SrtAppError` / `SrtSessionExpiredError` as its own docstring always claimed,
  and the salvage branch independently re-reads `strResult` off the raw payload
  and refuses to build a hold for any declared non-success. A declared SUCCESS
  is still validated strictly; only a declared failure short-circuits.
  **Partially superseded within this same unreleased range**: "any declared
  non-success" was the wrong set — it is now "a declared `FAIL`", matching the
  app (see the polarity entry at the top of this section). The ordering fix
  itself, and the guarantee that a declared FAIL is never salvaged however
  malformed its optional fields, are unchanged.
- Corrected the statements the cancel method falsified. `reserve`'s docstring
  and refusal message, `safety.SRT_MUTATION_ROUTES` /
  `SRT_LIVE_MUTATION_CATEGORIES`, and `post_mutation_form`'s refusal message
  said "there is no cancel method". The real blocker is restated: a cancel
  method exists but sends through the same closed gate, so a live reserve would
  still create a hold this library could not release — and having a method is not
  evidence that the form it builds is the one this app version sends.
- Supersedes the 0.2.0 entry's statement that no reservation route, request
  builder, or client method was added, and the 0.1.0 entry's statement that
  mutation operations are excluded. Both were accurate at their release; as of
  this section a reservation route, builder, and client method exist, and so do
  a cancel route, builder and preview-by-default method. **This entry's own "no
  state-changing request is transmitted" is itself superseded within this
  range**: all four categories were live-enabled and now transmit under an
  explicit non-dry-run consent (see the top of this section). External seat-map
  and native-bridge flows remain unimplemented. The cancel, payment and refund
  wire formats are all 0-hit across the 21,673 files of the v2.0.41 offline
  evidence bundle, but none is unverified any more: a live round trip exercised
  cancel on 2026-07-25 and payment and refund on 2026-07-26.

## 0.2.0 - 2026-07-15

- Normalized the two observed personal/group search wrapper casings strictly,
  added typed repr-safe search metadata and optional row availability details,
  and enriched missing station names only from hydrated request context.
- Preserved the legacy raw notice mapping and numeric-only fare item contracts;
  added typed uppercase notice results and all semantic fare rows through
  separate additive APIs/fields, and retained leading-empty timetable names.
- Aligned search details with sanitized 51-field personal and 43-field group
  shapes, including integer delay/order values, received fare, and five train
  composition codes.
- Added bounded, lazy personal and group train-search page iteration while
  preserving the existing single-page search methods.
- Reused the hydrated search form and NetFunnel key across continuation pages,
  with exact cursor validation, progress bounds, and one refresh/retry for only
  a continuation page rejected with `NET000001`.
- Kept the reviewed 20-route read-only boundary unchanged. A bounded live run
  verified two personal and two group pages without retaining response values.
- Added the pure offline `parse_reservation_attempt_response()` parser and the
  typed repr-safe `ReservationAttemptResult` for the documented
  reservation-attempt response shape. No reservation route, request builder,
  NetFunnel `act_19` flow, client method, or live call was added; the read-only
  boundary is unchanged.

## 0.1.0 - 2026-07-14

- Prepared the existing installable, typed, read-only SRT mobile API client for
  reproducible internal builds and offline verification.
- Retained the 20-route safety boundary, including the bounded seat-page read;
  mutation operations and physical-seat schemas remain excluded.
