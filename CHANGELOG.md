# Changelog

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
