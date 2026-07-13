# SRT Python Package Implementation Progress

Last updated: 2026-07-13 KST

## Current State

- The manual mutual-verification method and repr-safe result are implemented.
- The transport boundary now allows 19 exact app/NetFunnel routes while every
  mutation route remains excluded.
- Task-focused offline redaction and live-helper tests pass, and the live-service
  test remains an explicit offline skip.
- The full offline suite, package build, isolated-import check, and bounded live
  gate for this phase remain pending.

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

- Task-focused redaction/live-helper tests: `16 passed`
- Live-service test with live opt-in removed: `1 skipped` intentionally
- The prior selector phase completed its full offline suite, wheel/sdist build,
  isolated wheel import, and bounded live smoke.
- This mutual-verification phase still requires the full suite, package build,
  isolated-import check, and bounded live gate.

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

Keep the physical seat-selection page as a separate safety-reviewed candidate
because it is adjacent to reservation flow. Continue to exclude every mutation
endpoint.

See the shared [next-session prompt](../../NEXT_SESSION_PROMPT.md) for the
combined KORAIL/SRT orchestration instructions.
