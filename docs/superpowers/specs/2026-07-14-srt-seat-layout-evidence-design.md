# SRT Seat Layout Evidence Gate Design

Status: Approved on 2026-07-14 for bounded read-only evidence collection.

## Context

`SrtClient.get_seat_page(train) -> SeatSelectionPage` already performs one
authenticated read of the internal seat-selection page. Its request contract is
closed to general class, one seat, and the exact registered form. The parser
proves only that an authenticated HTML document contains a visible `좌석선택`
marker.

The tracked synthetic fixture contains no car or seat elements. Retained live
evidence also does not prove an embedded inventory schema. Callback names such
as `scarNo` and `seatNo` describe reservation handoff values, not an iterable
layout. A typed physical-seat model therefore cannot be designed honestly from
the current repository.

## Approaches considered

1. **Evidence-first extractor (selected).** Add a separately invoked internal
   tool that reads one page and emits only a bounded structural report. This
   preserves the safety boundary and lets a later design use observed fields.
2. Infer a schema from callback names or invented `data-seat-*` attributes.
   Rejected because tests would validate an invented server contract.
3. Follow an external KORAIL seat-map handoff. Rejected because that origin and
   route family are outside the current package boundary.

## Deliverable

This increment adds an offline-tested internal evidence extractor. It does not
change the public package API or add car, seat, selection, or reservation
models.

The command is `scripts/capture_seat_layout_evidence.py`. It imports existing
client, configuration, query, and complete-train selection logic. Credentials
remain caller-supplied environment values; the script never reads or names a
repository credential file.

The command requires `SRT_MOBILE_API_LIVE=1` and all existing live-query
requirements. Its network operation budget is exactly:

- one `SrtClient.login` call;
- one `SrtClient.search_trains` operation, including only its existing internal
  hydration/NetFunnel behavior;
- zero or one `SrtClient.get_seat_page` call for the first complete SRT row.

If no complete row exists, it emits a safe `no_complete_train` result and makes
no seat-page request. It must not call `run_live_smoke`, main/booking pages,
selectors, notices, tickets, mutual verification, group search, timetable,
fare, an external seat map, a callback, or any mutation route.

## Structural report

The extractor keeps `SeatSelectionPage.raw` in memory only. It feeds the value
directly to an `HTMLParser`-based collector and then drops the reference. Raw
HTML, visible text, attribute values, element identifiers, URLs, dates,
stations, train numbers, car numbers, seat numbers, credentials, cookies, and
tokens are never written or printed.

The command accepts required `--output PATH` and optional `--force` arguments.
The output is one JSON object with this exact top-level shape:

```text
schema_version: 1
status: success | no_complete_train | login_failed | search_failed |
        seat_page_failed | unsafe_report
calls: {login: 0|1, search: 0|1, seat_page: 0|1}
page: null | {
  marker_present: bool,
  external_handoff_candidate: bool,
  embedded_inventory_candidate: bool,
  script_present: bool,
  form_present: bool,
  tag_names: sorted unique bounded strings,
  attribute_names: sorted unique bounded strings,
  input_names: sorted unique bounded strings,
  structural_class_tokens: sorted unique bounded strings,
  element_count: bounded integer,
  candidate_element_count: bounded integer
}
sufficiency: stable_embedded_candidate | external_or_script_backed |
             no_inventory_candidate | unavailable
```

Collections contain at most 64 entries, strings at most 64 characters, and
counts saturate at 10,000. Attribute values are discarded before storage.
Class tokens are retained only when they are ASCII structural tokens matching
`[A-Za-z0-9_-]+`; tokens containing six consecutive digits, `@`, URL syntax,
or more than 64 characters are discarded. Input names receive the same filter.

External-handoff classification may inspect raw data in memory but emits only a
boolean. It must not resolve or request the target. Embedded-candidate
classification is evidence only and does not claim that a stable schema exists.

Before writing or printing, the serialized report is scanned for the current
credential values plus authorization, cookie, card-shaped, URL, email, and
long-token patterns. A match deletes the pending output and returns
`unsafe_report` without the matching content.

## Error handling

- Missing opt-in or configuration fails before constructing a client.
- Login, search, and seat-page failures are reduced to the fixed status enum;
  exception text and response content are suppressed.
- The client closes in `finally`.
- The extractor has no automatic whole-flow retry. Existing search internals
  retain only their already reviewed retry policy.
- The output path is explicit. Existing files are not overwritten unless the
  caller passes `--force`. For every non-`success` status, `page` is `null`.

## Files and tests

- Create `scripts/capture_seat_layout_evidence.py` for the bounded command and
  in-memory collector.
- Create `tests/test_seat_layout_evidence.py` with synthetic HTML only.
- Update `README.md` and `docs/IMPLEMENTATION_PROGRESS.md` with the evidence
  gate and actual result.

Tests must prove exact call counts, zero seat-page I/O without a complete row,
bounded deterministic output, attribute-value removal, raw/text/URL/credential
non-disclosure, fail-closed secret scanning, no external request, client
cleanup, and refusal without explicit live opt-in. Offline tests mock only the
existing client boundary and never load local credentials.

## Typed-layout gate

A later design may add frozen `SeatCar` and `PhysicalSeat` models only when a
sanitized report plus a separately reviewed synthetic fixture proves a stable,
iterable car/seat structure and availability vocabulary. If evidence reports
external/script-backed or no inventory, this phase finishes by documenting that
typed physical seats remain blocked. It must not widen the origin or mutation
boundary automatically.

## Version and acceptance

The package remains `0.1.0` because this evidence subproject has no public API
change. Acceptance requires focused and full offline tests, a clean secret scan,
one bounded opted-in evidence attempt, no raw artifact, and an explicit typed-
layout sufficiency verdict.
