# Security

Report security concerns privately through the owner's existing private
channel. Include only the minimum sanitized detail needed to reproduce the
issue.

Do not disclose credentials, cookies, tokens, PNRs, raw responses, or
production identifiers in public issues, discussions, logs, fixtures, or
commits. Remove or replace those values before sharing any diagnostic output.

This package transmits no state-changing request without an explicit,
per-category `MutationConsent` carrying `dry_run=False`. Seat holding and
selection have no client method at all. Reservation (`reserve`), cancellation
(`cancel`), card payment (`pay_with_card`) and refund (`refund`) each have a
consent-gated method that previews by default and, under an explicit non-dry-run
consent for its own category, transmits — a live `reserve` creates a real unpaid
hold, and a live `pay_with_card` moves real money. All four were exercised
against the live server: reserve and cancel on 2026-07-25 in one round trip
(`SUCC`/`IRR000018`, `SUCC`/`IRG000000`), payment and refund on 2026-07-26 in
another (`SUCC`/`IRT000000`, `SUCC`/`IRT200277`, 7,500 KRW, one adult, one
journey). Each of those wire shapes came from srtgo and remains 0-hit in our
v2.0.41 offline bundle, so one live run apiece is their only corroboration.

The mutation send path itself (`post_mutation_form`, and the underlying
`_send_mutation_request`) refuses every category outside
`safety.SRT_LIVE_MUTATION_CATEGORIES`, which holds exactly `{"reserve",
"cancel", "payment", "refund"}` — the four a live run has answered. Each of the
two also binds the target route to the caller's category
(`assert_mutation_route` plus `assert_mutation_route_category`), so a category
cannot be aimed at another category's endpoint, and the read-only guard refuses
all four mutation routes by allowlist.

A payment carries two further gates behind that: the consent must state exactly
one of `fake_card_only` / `real_card_acknowledged`, and `assert_no_card_secrets`
enforces on the request **body** that a PAN, card PIN, expiry or cardholder
birthdate may travel only as a `payment`. That body-shaped guard is what stops a
hand-assembled card form riding a read route or a genuine `reserve`/`cancel`
consent, and it became load-bearing when `payment` was live-enabled.

A security report must not attempt to defeat those gates, exercise an excluded
mutation, or make an unapproved production request.
