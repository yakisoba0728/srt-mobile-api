# Changelog

## Unreleased

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
  `refund` remain unimplemented, stay out of `SRT_LIVE_MUTATION_CATEGORIES`, and
  nothing was learned about their shapes.
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
  stay out** and remain unreachable even through the low-level client; adding
  either requires implementing it (neither has a client method) and
  live-verifying its own wire format, and a payment keeps a separate
  `fake_card_only` gate behind the live-enablement one.
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
  categories are in that set changed later in this same unreleased range (see
  the top of this section: it now holds `{"reserve", "cancel"}`); what this
  entry established, and what still holds, is that membership is decided at the
  **transport layer** rather than only at the client methods, so `payment` and
  `refund` cannot be transmitted even by a caller reaching `SrtClient.http`
  directly.
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
  range**: reserve and cancel were live-enabled and both now transmit under an
  explicit non-dry-run consent (see the top of this section). Payment, refund,
  external seat-map, and native-bridge flows remain unimplemented, and the
  payment and refund wire formats are 0-hit across all 21,673 files of the
  v2.0.41 offline evidence bundle and still need live capture. Cancel's format
  is 0-hit in that bundle too, but is no longer unverified — a live round trip
  exercised it on 2026-07-25.

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
