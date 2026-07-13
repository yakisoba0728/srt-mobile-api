# SRT Python Package Implementation Progress

Last updated: 2026-07-13 KST

## Current State

- The manual mutual-verification method and repr-safe result are implemented.
- Final whole-feature review hardening keeps the successful result's server
  message, verification code, and raw response out of `repr()` while leaving
  each value caller-accessible. Wrapper and business `SrtAppError` rendering
  now uses fixed local messages; the original response remains available via
  the repr-hidden `raw` attribute.
- The transport boundary now allows 19 exact app/NetFunnel routes while every
  mutation route remains excluded.
- The prior Task 4 verification gate remains recorded: its full offline suite,
  package build, isolated wheel import, exact static boundary, independent
  review, and bounded live gate all passed.
- NetFunnel behavior remains unchanged, and physical seat selection remains a
  candidate requiring a separate safety review rather than part of this package.

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

The transport currently allows 19 exact app/NetFunnel routes. Reservation,
`act_19`, payment, cancellation, refund, ATA/ARD flows, native bridges, and the
external seat map are not callable.

## Verification

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
- Physical seat selection continues to require its own separate safety review
  before any implementation or live verification.

The local credential file remains ignored and is not tracked. No credential,
cookie, session token, NetFunnel key, or raw personal response is stored.

## Analysis Inventory Versus Implementation

- Documented endpoint-matrix entries: 38, including runtime, static, helper,
  excluded, and repeated failure scenarios
- Runtime-success entries: 19
- Currently implemented underlying routes: 19, including NetFunnel `act_10`
- Therefore the complete documented endpoint matrix is not yet implemented

The runtime-success seat-selection page remains outside the package. Static
aliases, reservation execution, payment handoff, and native integrations also
remain outside the current core package.

## Next Candidate Phase

Keep the physical seat-selection page as a candidate requiring a separate
safety review because it is adjacent to reservation flow. Continue to exclude
every mutation endpoint.

See the shared [next-session prompt](../../NEXT_SESSION_PROMPT.md) for the
combined KORAIL/SRT orchestration instructions.

The parent handoff must be refreshed after the final reviewed SRT and KORAIL
heads are both available. This repository records that requirement without
editing the parent handoff file.
