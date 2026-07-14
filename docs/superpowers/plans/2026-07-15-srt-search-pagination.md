# SRT Search Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Keep this as one bounded implementation task and use strict RED-GREEN TDD.

**Goal:** Add an opt-in page iterator for personal and group train search that mirrors the SRT 2.0.41 continuation contract without changing existing first-page methods.

**Architecture:** Prepare one NetFunnel `act_10` key and one hydrated search form, submit the first page, then reuse that form for continuation POSTs. Only request `dptTm` changes to `last_row.dptTm[:5] + "1"`; `dptTm1`, unknown hidden fields, passenger state, and the NetFunnel key remain stable. A `NET000001` continuation failure refreshes key/hydration once and retries only that page. The public iterator yields existing `TrainSearchResult` pages and is bounded by `max_pages` and non-progress checks.

**Tech Stack:** Python 3.11+, httpx, dataclasses, pytest, existing SRT defensive transport/parser layers.

## Global Constraints

- Existing `search_trains()` and `search_group_trains()` remain single-page and signature-compatible.
- Add no route and do not broaden the 20-route safety allowlist.
- Personal continuation uses `POST /ara/selectListAra10007_n.do`; group continuation uses `POST /ara/selectListAra10082_n.do`. Group hydration remains the existing `GET /ara/selectListAra10007_n.do` flow.
- Preserve every hydrated field, including unknown inputs and `netfunnelKey`; never send response-only `fllwPgExt` in a request.
- Do not deduplicate or reorder train rows or pages.
- Do not call reservation, seat selection, payment, cancellation, refund, ARD/ATA, native bridges, or KORAIL handoff routes.
- Static APK evidence supports the continuation contract, but documentation must not claim live success until a separately bounded read-only run proves it.
- A new backward-compatible public read API requires version `0.2.0` under `docs/RELEASE.md`.

---

### Task 1: Implement and verify bounded page iteration

**Files:**
- Create: `docs/superpowers/plans/2026-07-15-srt-search-pagination.md`
- Create: synthetic `Y`, `N`, and empty continuation fixtures as needed
- Modify: `src/srt_mobile_api/payloads.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `tests/test_netfunnel_payloads_parsers.py`
- Modify: `tests/test_client_read_apis.py`
- Modify: `tests/test_public_contract.py`
- Modify: `tests/test_release_readiness.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PROGRESS.md`
- Modify: `docs/analysis/srt-app-api-library-spec-2026-07-09.md`
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

**Public interface:**

```python
def iter_train_search_pages(
    self,
    query: TrainSearchQuery,
    *,
    group: bool = False,
    max_pages: int = 10,
) -> Iterator[TrainSearchResult]: ...
```

`group` and `max_pages` are keyword-only. `max_pages` accepts only a non-boolean positive integer. The iterator yields at most `max_pages` pages and may be stopped early by the caller.

- [x] **Step 1: Write failing payload/parser/public-contract tests**

Add tests proving a continuation builder copies an existing hydrated Ajax form and changes only:

```text
dptTm = last_departure_time[:5] + "1"
trnNo = ""
```

It must preserve `dptTm1`, `netfunnelKey`, unknown hidden fields, `grpDv`, and passenger slots, and must not add `fllwPgExt`. Validate last departure time as exactly six ASCII digits. Add strict pagination metadata tests for `dsOutput0` object/list and exact `fllwPgExt` values `Y` and `N`; existing one-page parsing remains tolerant of a missing flag.

Lock the new public signature while preserving every existing public method and positional dataclass prefix.

- [x] **Step 2: Run focused tests and verify RED**

```bash
PYTHONPATH="$PWD/src" pytest -q \
  tests/test_netfunnel_payloads_parsers.py \
  tests/test_public_contract.py
```

Expected: failures only because continuation helpers and the iterator do not exist.

- [x] **Step 3: Write failing client sequence tests**

Cover these exact flows with `httpx.MockTransport`:

1. Personal: one act_10 GET, one hydration GET, first POST with `Y`, continuation POST with `N`; both POSTs use the same route/key/unknown fields and only continuation `dptTm` changes.
2. First page `N`: yield once and perform no continuation POST.
3. Continuation returns empty `dsOutput1`: yield that empty page once, then stop even if metadata says `Y`.
4. Group: hydration stays on Ara10007; both Ajax POSTs use Ara10082 and preserve `grpDv=1`, group passenger count, and hydrated state.
5. Continuation `NET000001`: obtain one fresh key/hydration and retry only the failing cursor once; do not replay or re-yield earlier pages.
6. A second `NET000001` on the same cursor raises the typed error.
7. Missing/invalid last-row `dptTm`, missing/invalid `fllwPgExt`, repeated cursor, and non-progress cursor raise `SrtProtocolError` without another POST.
8. `max_pages` is an exact bound; invalid values fail before any transport call.
9. Existing `search_trains`/`search_group_trains` request count and retry tests remain unchanged.

- [x] **Step 4: Implement the minimal iterator**

Refactor only enough private client code to separate preparation from page POST. The first page may continue to use the existing full-flow one-retry policy. For continuation:

- reuse the current payload and key;
- calculate the next cursor from the last returned row, not from the prior request;
- require the calculated cursor to be lexicographically greater than the prior request cursor and unseen;
- on `NET000001`, refresh act_10 and hydration once, rebuild the base Ajax payload, apply the same continuation cursor, and retry that page only;
- yield each successfully parsed page exactly once;
- stop on `N`, on an empty page, when the caller closes the iterator, or at `max_pages`.

Do not accumulate pages internally and do not expose NetFunnel keys or hydrated forms.

- [x] **Step 5: Run focused and full offline verification**

```bash
PYTHONPATH="$PWD/src" pytest -q \
  tests/test_client_read_apis.py \
  tests/test_netfunnel_payloads_parsers.py \
  tests/test_public_contract.py
PYTHONPATH="$PWD/src" pytest -q -m "not live"
git diff --check
```

- [x] **Step 6: Synchronize release/docs truth**

Set `pyproject.toml` and pinned release tests to `0.2.0`. Add a newest-first `0.2.0` changelog entry. Document:

- the iterator signature and first-page compatibility;
- exact cursor, stop, hydration, and one-retry behavior;
- unchanged 20-route safety boundary;
- static APK provenance and the fact that live continuation remains unverified until the bounded run;
- fresh offline/build results only after they exist.

Do not rewrite historical `0.1.0` evidence lines as if those older builds were `0.2.0`.

- [x] **Step 7: Build and inspect the distribution**

```bash
tmpdir="$(mktemp -d)"
python3 -m build --wheel --sdist --outdir "$tmpdir" .
python3 scripts/verify_distribution.py "$tmpdir"/*.whl "$tmpdir"/*.tar.gz
rm -rf "$tmpdir"
```

Then rerun the full offline suite and `git diff --check` from a clean process.

- [x] **Step 8: Commit the implementation**

```bash
git add \
  src tests README.md CHANGELOG.md pyproject.toml docs
git commit -m "feat: add bounded srt search pagination"
```

Report RED evidence, focused/full/build results, commit SHA, and any remaining runtime uncertainty. Do not run live or read credentials in this implementation task.
