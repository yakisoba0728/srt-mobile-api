# SRT Python Package Implementation Progress

Last updated: 2026-07-14 KST

## Current State

- Internal release preparation is complete at current `HEAD`: typed-package
  metadata, source-manifest contents, an archive verifier, Python 3.11-3.14
  offline CI, and internal release/security/changelog guidance are present.
  This preparation changed no runtime request, route, credential, or live
  behavior and made no live request.
- The authenticated physical seat-selection page read is implemented as
  `get_seat_page(train) -> SeatSelectionPage`.
- Its request is fixed to general class and one seat. Prepared-request
  validation requires no query and exactly thirteen unique allowlisted form
  fields before the single POST is sent.
- The manual mutual-verification method and repr-safe result are implemented.
- Final whole-feature review hardening keeps the successful result's server
  message, verification code, and raw response out of `repr()` while leaving
  each value caller-accessible. Wrapper and business `SrtAppError` rendering
  now uses fixed local messages; the original response remains available via
  the repr-hidden `raw` attribute.
- The transport boundary now allows 20 exact read-only app/NetFunnel routes
  while every mutation route remains excluded.
- The prior Task 4 verification gate remains recorded: its full offline suite,
  package build, isolated wheel import, exact static boundary, independent
  review, and bounded live gate all passed.
- NetFunnel behavior remains unchanged. Typed physical seats remain excluded
  unless a future task supplies a separately sanitized synthetic fixture and
  concrete schema plan.

## Implemented Public Operations

- Login and local logout/session clearing
- Main and booking-page reads
- Notice-list read
- Ticket-list page read
- Personal train search
- Group train search
- Manual mutual-verification read
- Timetable read with structured rows
- Fare read with structured items and six passenger slots
- NetFunnel `act_10` acquisition, parsing, and one fresh-key retry
- Station selector popup read
- Station-map selector popup read
- Date/time selector popup read
- Passenger selector popup read
- Seat-option preference selector popup read
- Train-group selector popup read
- Physical seat-selection page read returning `SeatSelectionPage`

The transport currently allows 20 exact read-only app/NetFunnel routes.
Reservation, `act_19`, payment, cancellation, refund, ATA/ARD flows, native
bridges, callbacks, and external seat-map calls are not callable.

## Verification

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
- NetFunnel remains the single unchanged `act_10` read-only route with its
  existing acquisition, parsing, and one-fresh-key retry behavior.
- Physical seat models and selection continue to require separate sanitized
  fixture evidence and a new concrete design before implementation.

The local credential file remains ignored and is not tracked. No credential,
cookie, session token, NetFunnel key, or raw personal response is stored.

## Analysis Inventory Versus Implementation

- Documented endpoint-matrix entries: 38, including runtime, static, helper,
  excluded, and repeated failure scenarios
- Runtime-success entries: 20
- Currently implemented underlying routes: 20, including NetFunnel `act_10`
- Therefore the complete documented endpoint matrix is not yet implemented

Static aliases, reservation execution, payment handoff, native integrations,
and typed physical-seat inventory remain outside the current core package.

## Next Candidate Phase

Keep typed physical-seat layout and selection as a future candidate requiring
a separately sanitized synthetic fixture and concrete schema plan. Continue
to exclude every mutation endpoint, external seat-map call, callback, and
native bridge.

See the shared [next-session prompt](../../NEXT_SESSION_PROMPT.md) for the
combined KORAIL/SRT orchestration instructions.

The shared parent handoff was refreshed after the final reviewed SRT and KORAIL
heads and final verification counts became available.
