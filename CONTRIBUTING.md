# Contributing

## Before you start

This client is reverse-engineered from a real, load-bearing public service.
Read [SECURITY.md](SECURITY.md) and the "Nothing sends by accident" section of
[README.md](README.md) before writing any code that touches a mutation
(`reserve`, `cancel`, `pay_with_card`, `refund`, `register_discount_coupon`).
Never run a live request against `app.srail.or.kr` as part of ordinary
development — this repository's own workflow forbids it (see
[docs/RELEASE.md](docs/RELEASE.md)) and a pull request must never include one.

## Workflow

1. Python 3.11 or newer.
2. `python3 -m pip install -e ".[test]"`
3. Make your change.
4. `python3 -m pytest -q -m "not live"` must pass before you open a pull
   request. This is the only gate: there is no separate lint step and no
   live-service step in CI.
5. Open the pull request. CI runs the same offline suite across Python
   3.11–3.14 and a distribution-build check; both must be green.

`-m "not live"` deselects exactly one test — the live-service smoke test,
which additionally requires an explicit `SRT_MOBILE_API_LIVE=1` and real SRT
account credentials. CI never sets that variable, and a pull request does not
need to run this test either.

## Evidence, not assertion

Every route, field name, default value and response shape in this codebase is
tied to where it came from, and a new one must be too. There are three tiers,
and code and docstrings say which one applies:

- **Bundle-evidenced** — recovered by decompiling the SRT Android app and
  cited as `file:line` (e.g. `ara0101v.js:317-326`). Reproducible by anyone
  who decompiles the same APK.
- **Live-verified** — confirmed against the real server, with the date and
  the server's own confirmation code (e.g. `SUCC`/`IRG000000`) recorded in
  `docs/VERIFICATION.md` or `CHANGELOG.md`.
- **Inferred** — reasoned from adjacent evidence (a sibling field's spelling,
  a reference client's wire format) and *labelled as inferred* rather than
  presented as settled. `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` is the
  pattern to follow when a body has fields at more than one evidence tier.

A change that adds a route, a field, or a claim about what the server does
needs one of these, stated in the docstring or the commit message, not just
"the tests pass." If you used a third-party reference client (srtgo, srtgo_plus
or similar) to find a wire shape, say so and cite it the way
`docs/analysis/ref-srtgo_plus.md` does — as a source of *facts about the
protocol*, never as source code to copy. See `NOTICE` for why that distinction
is load-bearing here.

## Changing the mutation consent / safety model

This is the part of the codebase with the least room for a "seems fine to me."
`reserve`, `cancel`, `pay_with_card`, `refund` and `register_discount_coupon`
are gated by four independent layers (consent object, `dry_run`, per-category
opt-in, and the transport-layer kill switch `safety.SRT_LIVE_MUTATION_CATEGORIES`)
described in README's "Nothing sends by accident". If your change touches any
of `consent.py`, `safety.py`, `MutationConsent`, `assert_mutation_route`,
`assert_mutation_route_category`, `assert_no_card_secrets`, or
`SRT_LIVE_MUTATION_CATEGORIES`:

- **State which gate you are changing and why**, in terms of the four-layer
  model, not just the code diff. "This widens what a `reserve` consent can
  reach" is the kind of sentence a reviewer needs.
- **Widening `SRT_LIVE_MUTATION_CATEGORIES`** — adding a category to the set
  of what can actually transmit — requires a live-verified round trip against
  the real service, with its date and confirmation code, the same way
  `reserve`/`cancel` (2026-07-25) and `payment`/`refund` (2026-07-26) were
  added. It is not something a pull request from this repository will accept
  on bundle evidence alone; the canary test that pins the set exists
  specifically so this is a deliberate, visible act and not a drive-by change.
- **Card secrets** (`stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`, `athnVal1`) must
  stay policed on the request body by `assert_no_card_secrets`, not only by
  which route or category a caller intends to use. If your change adds a new
  field that carries a PAN, PIN, expiry or cardholder birthdate, it belongs in
  that check and in `SENSITIVE_KEYS` for redaction, in the same commit.
- Add or extend the adversarial test that tries to defeat the gate you
  touched — a MockTransport probe that asserts zero bytes left the client
  when the gate should refuse, the same shape `test_mutation_live_paths.py`
  and `test_payment_mutation.py` already use.

## Don't hand-maintain a count

This repository has twice shipped a number in a document (a route count, an
offline test count) that a human was supposed to update by hand and didn't.
Where a count is asserted about the repository — how many tests pass, how
many routes are allowlisted — write a test that derives it from the source of
truth (`len(READ_ONLY_ROUTES)`, `pytest --collect-only`) and asserts the
document states that number, the way `tests/test_release_readiness.py` and
`tests/test_safety.py::test_route_registry_has_exact_expanded_size` do.
Do not add a second hardcoded copy of a number that already has one.

## Fixtures

Test fixtures under `tests/fixtures/` are sanitized captures or reconstructions
of real server responses. Never commit a raw response, a real PNR, a real
credential, a cookie, or a NetFunnel key. If a fixture is built from something
SR's own JavaScript renders, keep only what a test needs to exercise a parser
— identifiers, field names, routes, structural HTML/JS a test greps for — and
strip runnable function bodies that aren't the thing under test.
