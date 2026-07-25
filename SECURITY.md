# Security

Report security concerns privately through the owner's existing private
channel. Include only the minimum sanitized detail needed to reproduce the
issue.

Do not disclose credentials, cookies, tokens, PNRs, raw responses, or
production identifiers in public issues, discussions, logs, fixtures, or
commits. Remove or replace those values before sharing any diagnostic output.

This package transmits no state-changing request without an explicit,
per-category `MutationConsent` carrying `dry_run=False`. Payment, refund, and
seat holding or selection have no client method at all. Reservation (`reserve`)
and cancellation (`cancel`) each have a consent-gated method that previews by
default and, under an explicit non-dry-run consent for its own category,
transmits — a live `reserve` creates a real unpaid hold. Both were exercised
against the live server once, on 2026-07-25, in a single reserve->cancel round
trip (one adult, one journey); `cancel`'s wire shape came from srtgo and remains
0-hit in our v2.0.41 offline bundle, so that one run is its only corroboration.

The mutation send path itself (`post_mutation_form`, and the underlying
`_send_mutation_request`) refuses every category outside
`safety.SRT_LIVE_MUTATION_CATEGORIES`, which holds exactly `{"reserve",
"cancel"}` — the two halves of one reversible operation. **`payment` and
`refund` therefore cannot be reached even through the low-level client**, and a
payment carries a further `fake_card_only` gate behind that one. A security
report must not attempt to defeat those gates, exercise an excluded mutation, or
make an unapproved production request.
