<!--
DO NOT paste real credentials, cookies, NetFunnel keys, PNRs, card-shaped
values, or raw response bodies from SRT into this pull request or its commits.
It is public. Fixtures under tests/fixtures/ must be sanitized or
reconstructed, never a raw capture — see CONTRIBUTING.md's "Fixtures" section.
-->

## What this changes

<!-- One or two sentences. -->

## Evidence

<!--
Per CONTRIBUTING.md's "Evidence, not assertion": every route, field, default
value or claim about server behavior needs one of bundle-evidenced (file:line
citation), live-verified (date + server confirmation code), or inferred
(labelled as such). State which tier applies here.
-->

## Does this touch the mutation consent / safety model?

<!--
`consent.py`, `safety.py`, `MutationConsent`, `assert_mutation_route`,
`assert_mutation_route_category`, `assert_no_card_secrets`, or
`SRT_LIVE_MUTATION_CATEGORIES` — if none of these are touched, delete this
section. If any are, read CONTRIBUTING.md's "Changing the mutation consent /
safety model" section and answer:
-->

- [ ] Which of the four gates (consent object / `dry_run` / per-category
      opt-in / transport-layer kill switch) does this change, and how?
- [ ] If this widens `SRT_LIVE_MUTATION_CATEGORIES`: date and confirmation
      code of the live round trip that verified it.
- [ ] If this adds a card-secret-bearing field: confirm it is covered by
      `assert_no_card_secrets` and `SENSITIVE_KEYS` in this same PR.

## Checklist

- [ ] `python3 -m pytest -q -m "not live"` passes locally.
- [ ] No live request was made as part of this change.
- [ ] No credential, cookie, NetFunnel key, PNR, card-shaped value, or raw
      response body is present anywhere in this diff, including fixtures.
- [ ] Any new hardcoded count (test count, route count, etc.) is derived by a
      test rather than hand-maintained in a second place.
