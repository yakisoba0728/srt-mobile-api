# Security

Report security concerns privately through the owner's existing private
channel. Include only the minimum sanitized detail needed to reproduce the
issue.

Do not disclose credentials, cookies, tokens, PNRs, raw responses, or
production identifiers in public issues, discussions, logs, fixtures, or
commits. Remove or replace those values before sharing any diagnostic output.

This package intentionally transmits no state-changing request. Payment,
cancellation, refund, and seat holding or selection have no client method at
all. Reservation has a consent-gated, preview-only method (`reserve`) that
refuses `dry_run=False` and performs no I/O, and the mutation send path itself
(`post_mutation_form`, and the underlying `_send_mutation_request`) refuses
every category because `safety.SRT_LIVE_MUTATION_CATEGORIES` is empty — so no
mutation route can be reached even through the low-level client. A security
report must not attempt to defeat that gate, exercise an excluded mutation, or
make an unapproved production request.
