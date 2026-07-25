# Changelog

## Unreleased

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
  `SrtReservationHold` types. `reserve()` is **preview-only**: `dry_run=False` is
  refused and the method returns a redacted `MutationPreview` of the exact form
  that would be POSTed, performing no I/O. Live sending stays deferred until a
  `cancel` method exists and a reserve->cancel round trip has been live-verified,
  because SRT offers no way to release a hold this library creates.
- Closed the transport-layer gap that this port opened. `SrtHttpClient.post_mutation_form`
  was ported wholesale and did transmit, so a caller reaching `SrtClient.http`
  directly could bypass `reserve()`'s preview-only hardening for any of the four
  categories. `safety.SRT_LIVE_MUTATION_CATEGORIES` — currently an empty
  frozenset — now names the categories permitted to reach the network, and it is
  enforced in `post_mutation_form` and re-asserted in the underlying
  `_send_mutation_request`, the function that actually calls `send`. **No SRT
  mutation of any category is transmitted by this library**, and that now holds
  at the transport layer rather than only at the client methods. Enabling a
  category requires it to be both implemented and live-verified.
- Supersedes the 0.2.0 entry's statement that no reservation route, request
  builder, or client method was added, and the 0.1.0 entry's statement that
  mutation operations are excluded. Both were accurate at their release; as of
  this section a reservation route, builder, and preview-only client method
  exist. What remains true, and is now enforced one layer lower, is that no
  state-changing request is transmitted. Payment, refund, cancellation, external
  seat-map, and native-bridge flows remain unimplemented (their wire formats are
  0-hit across all 21,673 files of the v2.0.41 offline evidence bundle and need
  live capture).

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
