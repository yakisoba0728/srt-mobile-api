# SRT Python Package Implementation Progress

Last updated: 2026-07-13 KST

## Current State

- The six-selector implementation plus offline, build, and isolated-import
  verification are complete.
- The bounded live completion gate passed with a one-off future
  `SRT_TEST_DATE`; no credential file change was required.
- The selector expansion phase is complete and committed on `main` by the
  finalization commit containing this document.

## Implemented Public Operations

- Login and local logout/session clearing
- Main and booking-page reads
- Notice-list read
- Ticket-list page read
- Personal train search
- Group train search
- Timetable read with structured rows
- Fare read with structured items and six passenger slots
- NetFunnel `act_10` acquisition, parsing, and one fresh-key retry
- Station selector popup read
- Station-map selector popup read
- Date/time selector popup read
- Passenger selector popup read
- Seat-option preference selector popup read
- Train-group selector popup read

The transport currently allows 18 exact app/NetFunnel routes. Reservation,
`act_19`, payment, cancellation, refund, ATA/ARD flows, native bridges, and the
external seat map are not callable.

## Verification

- Offline tests: `216 passed, 1 skipped`
- Wheel and sdist build: passed
- Fresh-venv wheel install/import: passed
- Full bounded read-only live smoke with the provided account: passed
- Selector-expansion live gate: all six selector popup reads passed
- Live reads: main, booking page, one notice, ticket page, 10 personal trains,
  10 group trains, 7 timetable rows, and 9 fare items
- Live summary reported `selectorLoadedCount: 6`
- Adult plus child passenger mapping was exercised against the live fare page
- Live NetFunnel `5002:200` response framing is covered by a sanitized fixture

The local credential file remains ignored and is not tracked. No credential,
cookie, session token, NetFunnel key, or raw personal response is stored.

## Analysis Inventory Versus Implementation

- Documented endpoint-matrix entries: 38, including runtime, static, helper,
  excluded, and repeated failure scenarios
- Runtime-success entries: 19
- Currently implemented underlying routes: 18, including NetFunnel `act_10`
- Therefore the complete documented endpoint matrix is not yet implemented

Runtime-success read candidates still outside the package are mutual
verification and the seat-selection page. Static aliases, reservation
execution, payment handoff, and native integrations remain outside the current
core package.

## Next Candidate Phase

Evaluate mutual verification as a separate read-only phase with its own exact
request evidence, safety review, offline tests, and bounded live gate. Keep the
physical seat-selection page separate because it is adjacent to reservation
flow and needs an explicit safety review. Continue to exclude every mutation
endpoint.

See the shared [next-session prompt](../../NEXT_SESSION_PROMPT.md) for the
combined KORAIL/SRT orchestration instructions.
