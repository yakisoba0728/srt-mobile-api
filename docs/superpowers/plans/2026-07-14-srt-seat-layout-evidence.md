# SRT Seat Layout Evidence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, bounded SRT seat-page structure extractor that can collect sanitized evidence without persisting raw HTML or changing the public API.

**Architecture:** A standalone script uses the existing client and live-query types, performs only login, personal search, and at most one seat-page read, then passes the in-memory HTML to a bounded `HTMLParser`. The report contains structural names, counts, booleans, and fixed status values only; a secret scan runs before any write.

**Tech Stack:** Python 3.11+, standard-library `argparse`, `html.parser`, `json`, existing `srt_mobile_api`, pytest.

## Global Constraints

- Keep package version `0.1.0`; no public API or physical-seat model change.
- Require `SRT_MOBILE_API_LIVE=1` and existing caller-supplied environment configuration.
- Network budget: one login, one existing personal search operation, zero or one `get_seat_page` call.
- Never call broad `run_live_smoke`, other reads, mutation routes, callbacks, native bridges, or the external KORAIL seat map.
- Raw HTML, visible text, attribute values, identifiers, URLs, credentials, cookies, tokens, and exception messages are memory-only and never emitted.
- Output collections cap at 64 entries, strings at 64 characters, and counts at 10,000.
- A later separately approved design is required before adding typed cars or seats.

---

### Task 1: Bounded seat-layout evidence command

**Files:**
- Create: `scripts/capture_seat_layout_evidence.py`
- Create: `tests/test_seat_layout_evidence.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PROGRESS.md`

**Interfaces:**
- Consumes: `SrtClient`, `SrtConfig`, `TrainSearchQuery`, `read_credentials_from_env`, and `_first_complete_srt_seat_train`.
- Produces: `_SeatLayoutEvidenceCollector`, `collect_page_evidence(raw: str) -> dict[str, object]`, `run_bounded_evidence(client, *, login_id: str, password: str, query: TrainSearchQuery) -> dict[str, object]`, `report_is_safe(serialized: str, secrets: tuple[str, ...]) -> bool`, and `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing extractor and call-budget tests**

Create synthetic HTML containing harmless structural classes, input names, deliberately sensitive attribute values, a script, a form, more than 64 unique names, and more than 10,000 elements. Tests must assert exact top-level keys and that output:

```python
evidence = module.collect_page_evidence(SYNTHETIC_HTML)
assert evidence["marker_present"] is True
assert evidence["script_present"] is True
assert evidence["form_present"] is True
serialized = json.dumps(evidence)
assert "secret-seat-123456" not in serialized
assert "https://example.invalid/private" not in serialized
assert len(evidence["tag_names"]) <= 64
assert len(evidence["attribute_names"]) <= 64
assert evidence["element_count"] <= 10_000
```

Use a mocked client to prove `run_bounded_evidence` calls login once, search once, and seat page once only for the first complete SRT row. A no-complete-row result must call no seat page and return `status="no_complete_train"`, `page=None`, and counts `{login: 1, search: 1, seat_page: 0}`. Assert no broad helper or adjacent method is imported or called.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH="$PWD/src" pytest -q tests/test_seat_layout_evidence.py
```

Expected: collection fails because `scripts/capture_seat_layout_evidence.py` and its interfaces do not exist.

- [ ] **Step 3: Implement the minimal bounded collector and runner**

Implement these fixed limits and filters:

```python
MAX_ITEMS = 64
MAX_STRING = 64
MAX_ELEMENTS = 10_000
SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
SENSITIVE_NAME_RE = re.compile(r"\d{6}|@|://")
STATUS_VALUES = {
    "success", "no_complete_train", "login_failed", "search_failed",
    "seat_page_failed", "unsafe_report",
}
```

The `HTMLParser` stores only lower-cased tag/attribute names, safe input names,
safe class tokens, saturated counts, and booleans. It discards every other
attribute value before returning. Candidate detection may inspect in-memory
names/classes; external-handoff detection returns a boolean and never a target.

`run_bounded_evidence` catches each operation separately and returns only its
fixed failure status. It never includes exception text. It returns the exact
schema from the approved spec and clears the page reference after collection.

- [ ] **Step 4: Add fail-closed serialization and CLI tests**

Tests must prove:

```python
assert module.report_is_safe(serialized, ("member-secret", "password-secret"))
assert not module.report_is_safe('{"x":"member-secret"}', ("member-secret",))
assert not module.report_is_safe('{"x":"4111-1111-1111-1111"}', ())
```

Invoke `main([...])` with `--output`, require live opt-in before client
construction, reject an existing output unless `--force` is present, write one
sorted UTF-8 JSON object through a temporary sibling followed by atomic replace,
and delete the temporary file on every failure. Mock factories and assert client
closure in `finally`. Parse the script AST and reject direct imports of `httpx`,
`requests`, `socket`, or `urllib`.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
PYTHONPATH="$PWD/src" pytest -q tests/test_seat_layout_evidence.py tests/test_smoke_script.py tests/test_live.py
```

Expected: all selected tests pass with no warning or network access.

- [ ] **Step 6: Document the gate and run the full offline suite**

Document the exact operation budget, example command, forbidden raw output, and
typed-layout gate. Do not include credential values or live structural values.

Run:

```bash
SRT_MOBILE_API_LIVE=1 PYTHONPATH="$PWD/src" pytest -q -m "not live"
python3 -m build --wheel --sdist --outdir /tmp/srt-seat-evidence-dist .
python3 scripts/verify_distribution.py /tmp/srt-seat-evidence-dist/*.whl /tmp/srt-seat-evidence-dist/*.tar.gz
git diff --check
```

Expected: full offline suite passes with one live test deselected; distribution
verification passes. Remove `/tmp/srt-seat-evidence-dist` afterward.

- [ ] **Step 7: Commit the offline implementation**

```bash
git add scripts/capture_seat_layout_evidence.py tests/test_seat_layout_evidence.py README.md docs/IMPLEMENTATION_PROGRESS.md
git commit -m "feat: add bounded srt seat layout evidence gate"
```

- [ ] **Step 8: Run the one authorized live evidence attempt**

Source the parent repository's ignored `.local-live-smoke.env` without printing
it, then run only the new script:

```bash
set -a
source /Users/yakisoba/Documents/GitHub/srt-mobile-api/.local-live-smoke.env
set +a
SRT_MOBILE_API_LIVE=1 PYTHONPATH="$PWD/src" python3 scripts/capture_seat_layout_evidence.py --output /tmp/srt-seat-layout-evidence.json --force
```

Inspect only the sanitized report. Record its call counts, fixed status,
booleans, bounded counts, and sufficiency category in
`docs/IMPLEMENTATION_PROGRESS.md`; do not copy structural values into tracked
docs. If the status is not success, record only the category. Delete the `/tmp`
report after the progress update.

- [ ] **Step 9: Verify and commit the evidence result**

```bash
PYTHONPATH="$PWD/src" pytest -q tests/test_seat_layout_evidence.py
git diff --check
git add docs/IMPLEMENTATION_PROGRESS.md
git commit -m "docs: record srt seat layout evidence result"
```

Expected: no raw or sensitive artifact exists in the repository. Return whether
typed layout is supported, externally/script backed, absent, or unavailable;
do not implement typed seats in this task.
