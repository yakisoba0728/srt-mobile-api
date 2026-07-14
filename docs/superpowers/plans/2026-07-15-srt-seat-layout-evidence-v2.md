# SRT Seat Layout Evidence v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development and superpowers:test-driven-development. Execute this as one bounded implementation task.

**Goal:** Replace the coarse SRT seat-page evidence classification with a bounded, value-free schema that distinguishes generic scripts from actual embedded seat data, same-origin script references, Ajax contracts, forms, iframes, and external handoffs.

**Architecture:** Parse the already-authorized single seat-page HTML without executing JavaScript or making additional requests. Emit only bounded structural names, counts, same-origin query/fragment-free paths, script metadata, captured-prefix inline SHA-256 digests and lengths, route literals, HTTP primitive/method indicators, unquoted safe simple payload-key names, response-property paths, and JSON key/type/cardinality summaries. Never retain input values, element identifiers, query strings, raw script text or truncated tails, seat/car numbers, credentials, cookies, tokens, or arbitrary URLs.

**Tech Stack:** Python 3.11+, standard-library `html.parser`, `hashlib`, `json`, `urllib.parse`, pytest, existing SRT live safety helpers.

## Global Constraints

- Keep the current single `login -> search -> seat-page POST` read-only network boundary. Add no route and make no external-script, iframe, Ajax, reservation, seat-selection, or payment request.
- Bump the report to `schema_version: 2`; old report files remain historical evidence.
- A generic `<script>` tag alone must never imply a seat inventory source.
- Recognize camelCase and numeric-suffix seat/scar structural markers, but emit only counts and safe names—not identifier values.
- External script and form/iframe targets may be emitted only as same-origin, query/fragment-stripped static `.do`/`.js`/`.mjs` paths without dynamic seat/car segments. Cross-origin targets are represented only by category/count.
- All collections, string lengths, element counts, script sizes, JSON depth, and JSON array cardinalities must be bounded.
- Synthetic tests must contain credentials, tokens, card-like data, e-mail addresses, URLs, seat/car identifiers, and query secrets and prove none can appear in serialized evidence.
- Do not claim a typed physical-seat contract or live success from static evidence.

---

### Task 1: Implement, verify, document, and commit evidence schema v2

**Files:**
- Modify: `scripts/capture_seat_layout_evidence.py`
- Modify: `tests/test_seat_layout_evidence.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PROGRESS.md`
- Modify: `.superpowers/sdd/progress.md` (ignored execution ledger)

**Interfaces:**
- Preserve `collect_page_evidence(raw: str) -> dict[str, object]` and `run_bounded_evidence(...)`.
- Preserve the CLI safety/no-clobber behavior and one-seat-page call bound.
- Replace the v1 page schema/sufficiency vocabulary with explicit v2 source categories.

- [ ] **Step 1: Add failing schema-v2 tests**

Cover generic scripts, inline/Ajax candidates, same-origin and cross-origin script/form/iframe references, `application/json` summaries, camelCase/numeric seat markers, malformed markup/JSON, deterministic bounds, fixed failure reports, and secret non-disclosure. Run the focused file and capture RED caused only by the missing v2 behavior.

- [ ] **Step 2: Implement the bounded parser and classification**

Use conservative static extraction. Classify sufficiency from actual evidence categories; do not promote generic scripts. Keep report serialization deterministic and compatible with the existing safety scanner.

- [ ] **Step 3: Run focused and full offline verification**

```bash
PYTHONPATH="$PWD/src" pytest -q tests/test_seat_layout_evidence.py
PYTHONPATH="$PWD/src" pytest -q -m "not live"
git diff --check
```

- [ ] **Step 4: Synchronize documentation truth**

Document schema v2, its exact one-page/no-JS/no-follow-up boundary, and that physical-seat inventory remains unimplemented until bounded live evidence identifies a stable source. Keep version `0.2.0` and the 20-route allowlist unchanged.

- [ ] **Step 5: Build and inspect distribution, then commit**

```bash
tmpdir="$(mktemp -d)"
python3 -m build --wheel --sdist --outdir "$tmpdir" .
python3 scripts/verify_distribution.py "$tmpdir"/*.whl "$tmpdir"/*.tar.gz
rm -rf "$tmpdir"
git commit -m "fix: classify srt seat layout evidence sources"
```

Report RED, focused/full/build evidence, the commit SHA, and remaining live uncertainty. Do not run live or read credentials in this task.
