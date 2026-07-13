# SRT Mutual Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one manual, typed, runtime-evidenced SRT mutual-verification read while preserving the exact read-only and NetFunnel boundaries.

**Architecture:** Keep `SrtClient` as the public facade and add one frozen result model plus one strict JSON parser. Register only the exact mutual-verification POST route, send the evidenced empty AJAX form with the search-result referer, and add one bounded boolean to the live helper after personal search. Never auto-chain the result into seat selection or reservation.

**Tech Stack:** Python 3.11+, `httpx>=0.27,<1`, frozen dataclasses, `pytest>=8,<10`, setuptools.

## Global Constraints

- Work only in `/Users/yakisoba/Documents/GitHub/srt-mobile-api`; preserve all unrelated user changes and never reset or stash them.
- Add only `POST /ara/selectListAra10130_n.do` on `https://app.srail.or.kr`.
- Send an empty form, the existing AJAX headers, and exact search-result referer; send no PNR, train, passenger, seat, reservation, or payment fields.
- Keep the method manual. Login and search do not call it automatically; only the opted-in live helper calls it after personal search.
- Do not add the legacy `ara/selectListAra10h01.do`, physical seat-selection page, `act_19`, reservation, ATA/ARD, payment, cancellation, refund, native bridge, or external seat-map routes.
- Preserve exact NetFunnel `act_10`, search hydration, fresh-key retry, and one-retry-only `NET000001` behavior.
- Keep `mutMrkVrfCd` and raw JSON caller-accessible only through repr-hidden fields; never emit them in errors, logs, docs examples, or live output.
- Default tests remain offline with `httpx.MockTransport`; live calls require explicit opt-in and ignored local environment values.
- Keep Python support at `>=3.11` and add no dependency.

---

## File Structure

Files created by this plan:

- `tests/fixtures/mutual_verification_success.json`: sanitized successful list-shaped response.
- `tests/test_mutual_verification.py`: focused parser and exact client orchestration tests.

Existing files modified by this plan:

- `src/srt_mobile_api/models.py`: add `MutualVerificationResult`.
- `src/srt_mobile_api/parsers.py`: add the strict success/error parser.
- `src/srt_mobile_api/safety.py`: register exactly one new app route.
- `src/srt_mobile_api/client.py`: add the manual public method.
- `src/srt_mobile_api/redaction.py`: classify mutual-verification names as sensitive.
- `src/srt_mobile_api/live.py`: call the method after personal search and emit one boolean.
- `src/srt_mobile_api/__init__.py`: export the result model.
- `tests/test_models.py`: lock frozen/repr-safe fields.
- `tests/test_public_contract.py`: lock method set, signature, and export.
- `tests/test_redaction_safety.py`: lock value redaction.
- `tests/test_safety.py`: lock route count 19 and neighboring exclusions.
- `tests/test_live.py`: lock call order and bounded output.
- `tests/test_live_service.py`: require bounded mutual-verification success live.
- `README.md`: document manual use and exclusions.
- `docs/IMPLEMENTATION_PROGRESS.md`: record actual verification and next candidate.

---

### Task 1: Typed Result And Strict Response Parser

**Files:**

- Create: `tests/fixtures/mutual_verification_success.json`
- Create: `tests/test_mutual_verification.py`
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `tests/test_models.py`

**Interfaces:**

- Consumes: `SrtAppError`, `SrtProtocolError`, and the retained `outDataSets.dsOutput0` framing.
- Produces: `MutualVerificationResult` and `parse_mutual_verification_response()`.

- [ ] **Step 1: Add the sanitized fixture and failing parser tests**

Create `tests/fixtures/mutual_verification_success.json`:

```json
{"ErrorCode":"0","ErrorMsg":"","outDataSets":{"dsOutput0":[{"msgCd":"IRZ000008","msgTxt":"Success","strResult":"SUCC","mutMrkVrfCd":"fixture-mutual-code"}]}}
```

Create `tests/test_mutual_verification.py` initially with:

```python
import pytest

from srt_mobile_api.errors import SrtAppError, SrtProtocolError
from srt_mobile_api.parsers import parse_mutual_verification_response


@pytest.mark.parametrize("object_shape", [False, True])
def test_mutual_parser_accepts_evidenced_list_and_object_rows(
    load_json_fixture,
    object_shape,
):
    payload = load_json_fixture("mutual_verification_success.json")
    if object_shape:
        payload["outDataSets"]["dsOutput0"] = payload["outDataSets"][
            "dsOutput0"
        ][0]
    result = parse_mutual_verification_response(payload)
    assert result.message_code == "IRZ000008"
    assert result.status == "SUCC"
    assert result.message == "Success"
    assert result.verification_code == "fixture-mutual-code"
    assert result.raw is payload
    assert "fixture-mutual-code" not in repr(result)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"ErrorCode": 0, "outDataSets": {}},
        {"ErrorCode": "0", "ErrorMsg": 123, "outDataSets": {}},
        {"ErrorCode": "0"},
        {"ErrorCode": "0", "outDataSets": None},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": []}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": ["row"]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": ""}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "strResult": "SUCC", "mutMrkVrfCd": 123}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "msgTxt": 123, "strResult": "SUCC", "mutMrkVrfCd": "code"}]}},
    ],
)
def test_mutual_parser_rejects_malformed_framing(payload):
    with pytest.raises(SrtProtocolError):
        parse_mutual_verification_response(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"ErrorCode": "WRAPPER_ERR", "ErrorMsg": "wrapper failed"},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "OTHER", "msgTxt": "wrong code", "strResult": "SUCC", "mutMrkVrfCd": "code"}]}},
        {"ErrorCode": "0", "outDataSets": {"dsOutput0": [{"msgCd": "IRZ000008", "msgTxt": "wrong status", "strResult": "FAIL", "mutMrkVrfCd": "code"}]}},
    ],
)
def test_mutual_parser_classifies_wrapper_and_business_failures(payload):
    with pytest.raises(SrtAppError) as exc_info:
        parse_mutual_verification_response(payload)
    assert exc_info.value.raw is payload
```

- [ ] **Step 2: Run focused parser tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_mutual_verification.py -q
```

Expected: collection fails because the result model and parser do not exist.

- [ ] **Step 3: Implement the frozen result model**

Append to `src/srt_mobile_api/models.py` before `HtmlPage`:

```python
@dataclass(frozen=True)
class MutualVerificationResult:
    message_code: str
    status: str
    message: str = ""
    verification_code: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
```

- [ ] **Step 4: Implement the strict parser**

Import `MutualVerificationResult` in `src/srt_mobile_api/parsers.py`, then add before `parse_train_search_response()`:

```python
def parse_mutual_verification_response(
    data: dict[str, Any],
) -> MutualVerificationResult:
    if not isinstance(data, dict):
        raise SrtProtocolError(
            "SRT mutual verification response must be a JSON object"
        )
    wrapper_code = data.get("ErrorCode", "")
    wrapper_message = data.get("ErrorMsg", "")
    if not isinstance(wrapper_code, str):
        raise SrtProtocolError(
            "SRT mutual verification ErrorCode must be a string"
        )
    if not isinstance(wrapper_message, str):
        raise SrtProtocolError(
            "SRT mutual verification ErrorMsg must be a string"
        )
    if wrapper_code not in {"", "0"}:
        raise SrtAppError(wrapper_code, wrapper_message, raw=data)

    datasets = data.get("outDataSets")
    if not isinstance(datasets, dict):
        raise SrtProtocolError(
            "SRT mutual verification response missing outDataSets"
        )
    value = datasets.get("dsOutput0")
    if isinstance(value, list):
        if len(value) != 1 or not isinstance(value[0], dict):
            raise SrtProtocolError(
                "SRT mutual verification dsOutput0 must contain one object"
            )
        row = value[0]
    elif isinstance(value, dict):
        row = value
    else:
        raise SrtProtocolError(
            "SRT mutual verification response missing dsOutput0 object"
        )

    code = row.get("msgCd")
    status = row.get("strResult")
    message = row.get("msgTxt", "")
    verification_code = row.get("mutMrkVrfCd")
    if not isinstance(code, str) or not isinstance(status, str):
        raise SrtProtocolError(
            "SRT mutual verification code and status must be strings"
        )
    if not isinstance(message, str):
        raise SrtProtocolError(
            "SRT mutual verification message must be a string"
        )
    if code != "IRZ000008" or status != "SUCC":
        raise SrtAppError(code or None, message or status, raw=data)
    if not isinstance(verification_code, str) or not verification_code.strip():
        raise SrtProtocolError(
            "SRT mutual verification mutMrkVrfCd must be a non-empty string"
        )
    return MutualVerificationResult(
        message_code=code,
        status=status,
        message=message,
        verification_code=verification_code,
        raw=data,
    )
```

- [ ] **Step 5: Lock model freezing/repr and run GREEN**

Import `MutualVerificationResult` in `tests/test_models.py` and append:

```python
def test_mutual_verification_model_is_frozen_and_repr_safe():
    value = MutualVerificationResult(
        message_code="IRZ000008",
        status="SUCC",
        verification_code="mutual-secret",
        raw={"mutMrkVrfCd": "mutual-secret"},
    )
    assert is_dataclass(value)
    assert "mutual-secret" not in repr(value)
    with pytest.raises(FrozenInstanceError):
        value.status = "FAIL"
```

Add `FrozenInstanceError` to the dataclasses import in that test file.

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_mutual_verification.py tests/test_models.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/srt_mobile_api/models.py src/srt_mobile_api/parsers.py tests/fixtures/mutual_verification_success.json tests/test_mutual_verification.py tests/test_models.py
git commit -m "feat: parse srt mutual verification responses"
```

---

### Task 2: Exact Route, Manual Client Method, And Public Contract

**Files:**

- Modify: `src/srt_mobile_api/safety.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `src/srt_mobile_api/__init__.py`
- Modify: `tests/test_safety.py`
- Modify: `tests/test_mutual_verification.py`
- Modify: `tests/test_public_contract.py`

**Interfaces:**

- Consumes: Task 1 parser/result and existing `post_form()` AJAX transport.
- Produces: a 19-route registry and `SrtClient.get_mutual_verification()`.

- [ ] **Step 1: Add failing route and neighboring-rejection tests**

Add this route to the accepted app-route parametrization in `tests/test_safety.py`:

```python
("POST", "/ara/selectListAra10130_n.do"),
```

Change the exact size assertion to:

```python
def test_route_registry_has_exact_expanded_size():
    assert len(READ_ONLY_ROUTES) == 19
```

Append:

```python
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/ara/selectListAra10130_n.do"),
        ("POST", "/ara/selectListAra10h01.do"),
        ("POST", "/ara/%73electListAra10130_n.do"),
        ("POST", "/ara/selectListAra10130_n.do/extra"),
        ("POST", "/arc/selectListArc02012_n.do"),
    ],
)
def test_mutual_policy_rejects_wrong_method_legacy_encoded_and_seat_neighbors(
    method,
    path,
):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            method,
            httpx.URL(f"{config.base_url}{path}"),
            config,
        )
```

- [ ] **Step 2: Add failing exact client-request and expiry tests**

Append to `tests/test_mutual_verification.py`:

```python
import httpx

from srt_mobile_api import SrtClient
from srt_mobile_api.errors import SrtSessionExpiredError
from srt_mobile_api.models import SrtSession


def test_client_sends_exact_empty_mutual_form_headers_and_referer(
    load_json_fixture,
):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json=load_json_fixture("mutual_verification_success.json"),
        )

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        result = client.get_mutual_verification()
    finally:
        client.close()
    assert result.verification_code == "fixture-mutual-code"
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/ara/selectListAra10130_n.do"
    assert request.content == b""
    assert request.headers["accept"] == (
        "application/json, text/javascript, */*; q=0.01"
    )
    assert request.headers["content-type"].startswith(
        "application/x-www-form-urlencoded"
    )
    assert request.headers["origin"] == "https://app.srail.or.kr"
    assert request.headers["x-requested-with"] == "XMLHttpRequest"
    assert request.headers["referer"] == (
        "https://app.srail.or.kr/ara/selectListAra10007_n.do"
    )


def test_mutual_login_form_clears_session_and_cookies():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<form action="/apb/selectListApb01080_n.do">'
                '<input name="hmpgPwdCphd"></form>'
            ),
            headers={"Content-Type": "text/html"},
        )

    client = SrtClient(transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="stale")
    client.http.cookies.set("JSESSIONID", "stale")
    try:
        with pytest.raises(SrtSessionExpiredError):
            client.get_mutual_verification()
        assert client.session.current is None
        assert not list(client.http.cookies.jar)
    finally:
        client.close()
```

- [ ] **Step 3: Add failing public-contract assertions**

Add `get_mutual_verification` to the exact method set in
`tests/test_public_contract.py`, then append:

```python
def test_mutual_method_signature_type_and_export_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import MutualVerificationResult

    signature = inspect.signature(SrtClient.get_mutual_verification)
    assert list(signature.parameters) == ["self"]
    assert (
        get_type_hints(SrtClient.get_mutual_verification)["return"]
        is MutualVerificationResult
    )
    assert srt_mobile_api.MutualVerificationResult is MutualVerificationResult
```

- [ ] **Step 4: Run focused tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_safety.py tests/test_mutual_verification.py tests/test_public_contract.py -q
```

Expected: failures show route count 18 and the missing client method/export.

- [ ] **Step 5: Register only the exact route**

Add to `READ_ONLY_ROUTES` in `src/srt_mobile_api/safety.py`:

```python
ReadOnlyRoute("POST", "app", "/ara/selectListAra10130_n.do"),
```

Do not modify the NetFunnel route or excluded-domain set.

- [ ] **Step 6: Implement the manual client method**

Import `MutualVerificationResult` and `parse_mutual_verification_response` in
`src/srt_mobile_api/client.py`, then add immediately before `_get_act10_key()`:

```python
    def get_mutual_verification(self) -> MutualVerificationResult:
        with self._session_guard():
            data = self.http.post_form(
                "/ara/selectListAra10130_n.do",
                {},
                accept="application/json, text/javascript, */*; q=0.01",
                referer=(
                    f"{self.config.base_url}"
                    "/ara/selectListAra10007_n.do"
                ),
            )
            return parse_mutual_verification_response(data)
```

The method must not call login, search, NetFunnel, seat selection, or reservation.

- [ ] **Step 7: Export the result and run GREEN**

Import `MutualVerificationResult` and add it to `__all__` in
`src/srt_mobile_api/__init__.py`.

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_safety.py tests/test_mutual_verification.py tests/test_public_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/srt_mobile_api/safety.py src/srt_mobile_api/client.py src/srt_mobile_api/__init__.py tests/test_safety.py tests/test_mutual_verification.py tests/test_public_contract.py
git commit -m "feat: expose srt mutual verification read"
```

---

### Task 3: Redaction, Bounded Live Call, And Documentation

**Files:**

- Modify: `src/srt_mobile_api/redaction.py`
- Modify: `src/srt_mobile_api/live.py`
- Modify: `tests/test_redaction_safety.py`
- Modify: `tests/test_live.py`
- Modify: `tests/test_live_service.py`
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PROGRESS.md`

**Interfaces:**

- Consumes: the manual method from Task 2.
- Produces: case-insensitive verification-code redaction and `mutualVerificationLoaded` after personal search.

- [ ] **Step 1: Add failing redaction tests**

Extend the mapping and recursive redaction cases in
`tests/test_redaction_safety.py`, then append:

```python
def test_mutual_verification_names_are_redacted_everywhere():
    redacted = redact_mapping(
        {
            "mutMrkVrfCd": "server-secret",
            "VERIFICATION_CODE": "model-secret",
        }
    )
    assert redacted == {
        "mutMrkVrfCd": "[REDACTED]",
        "VERIFICATION_CODE": "[REDACTED]",
    }
    rendered = redact_text(
        'mutMrkVrfCd="server-secret" verification_code=model-secret'
    )
    assert "server-secret" not in rendered
    assert "model-secret" not in rendered
```

- [ ] **Step 2: Extend the live fake and verify RED**

Import `MutualVerificationResult` in `tests/test_live.py`. In
`test_live_result_contains_counts_not_ticket_text()`, configure:

```python
    client.get_mutual_verification.return_value = MutualVerificationResult(
        message_code="IRZ000008",
        status="SUCC",
        verification_code="mutual-secret",
        raw={"mutMrkVrfCd": "mutual-secret"},
    )
```

Add `mutualVerificationLoaded` to the exact result key set, assert it is `True`,
add `get_mutual_verification` to the called-method loop, and assert:

```python
    method_order = [call[0] for call in client.method_calls]
    assert method_order.index("search_trains") < method_order.index(
        "get_mutual_verification"
    )
    assert method_order.index("get_mutual_verification") < method_order.index(
        "search_group_trains"
    )
    assert "mutual-secret" not in repr(result)
    assert "mutMrkVrfCd" not in repr(result)
```

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_redaction_safety.py tests/test_live.py -q
```

Expected: redaction and live-summary tests fail because neither behavior exists.

- [ ] **Step 3: Add sensitive key names**

Add to `SENSITIVE_KEYS` in `src/srt_mobile_api/redaction.py`:

```python
"mutMrkVrfCd",
"verification_code",
```

- [ ] **Step 4: Add the bounded live call after personal search**

In `run_live_smoke()` in `src/srt_mobile_api/live.py`, change the search sequence to:

```python
    personal = client.search_trains(query)
    mutual = client.get_mutual_verification()
    group = client.search_group_trains(query)
```

Add to the returned mapping:

```python
"mutualVerificationLoaded": bool(mutual.verification_code),
```

Do not return `message`, `verification_code`, `raw`, or any full response field.

- [ ] **Step 5: Run redaction/live tests and verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_redaction_safety.py tests/test_live.py -q
```

Expected: all selected tests pass and call order is search → mutual → group.

- [ ] **Step 6: Lock the live-service assertion**

Add to `test_read_only_live_smoke()` in `tests/test_live_service.py`:

```python
    assert result["mutualVerificationLoaded"] is True
```

Run offline to confirm it remains an explicit skip:

```bash
env -u SRT_MOBILE_API_LIVE PYTHONPATH=src python3 -m pytest tests/test_live_service.py -q
```

Expected: one intentional live skip.

- [ ] **Step 7: Document the manual boundary**

Add this README section:

```markdown
### Mutual verification

`get_mutual_verification()` manually performs the evidenced empty-form mutual
verification read and returns a repr-safe `MutualVerificationResult`. It is not
called automatically by login or search and does not start seat selection or a
reservation. The opted-in live helper calls it only after personal search and
reports `mutualVerificationLoaded`, never the verification value or raw JSON.
```

Update `docs/IMPLEMENTATION_PROGRESS.md` at this stage to state that the manual
method, 19-route boundary, and offline focused tests are implemented while the
full suite/build/live gate remains pending. Keep physical seat selection as a
separate safety-reviewed candidate and every mutation route excluded.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/srt_mobile_api/redaction.py src/srt_mobile_api/live.py tests/test_redaction_safety.py tests/test_live.py tests/test_live_service.py README.md docs/IMPLEMENTATION_PROGRESS.md
git commit -m "docs: add srt mutual verification live boundary"
```

---

### Task 4: Full Verification, Independent Review, And Live Gate

**Files:**

- Verify all changed files.
- Modify: `docs/IMPLEMENTATION_PROGRESS.md` with actual final evidence.

**Interfaces:**

- Consumes: the complete manual mutual-verification feature.
- Produces: fresh offline/build/import/static/live evidence and a clean handoff.

- [ ] **Step 1: Run the complete offline suite once**

Run:

```bash
env -u SRT_MOBILE_API_LIVE -u SRT_LOGIN_ID -u SRT_LOGIN_PASSWORD -u SRT_TEST_DATE PYTHONPATH=src python3 -m pytest -q
```

Expected: every offline test passes and only the explicitly opted-in live test skips.

- [ ] **Step 2: Build wheel and sdist once**

Run:

```bash
python3 -m build
```

Expected: one wheel and one sdist are produced under `dist/` with exit code 0.

- [ ] **Step 3: Verify the built wheel in isolation**

Run:

```bash
tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
python3 -m venv "$tmpdir/venv"
"$tmpdir/venv/bin/python" -m pip install --quiet --disable-pip-version-check dist/srt_mobile_api-0.1.0-py3-none-any.whl
"$tmpdir/venv/bin/python" - <<'PY'
from srt_mobile_api import MutualVerificationResult, SrtClient
print(MutualVerificationResult.__name__, SrtClient.__name__)
PY
```

Expected output: `MutualVerificationResult SrtClient`.

- [ ] **Step 4: Confirm the exact safety boundary statically**

Run:

```bash
PYTHONPATH=src python3 - <<'PY'
from srt_mobile_api.safety import READ_ONLY_ROUTES

assert len(READ_ONLY_ROUTES) == 19
assert sum(route.host_kind == "netfunnel" for route in READ_ONLY_ROUTES) == 1
assert any(
    (route.method, route.host_kind, route.path)
    == ("POST", "app", "/ara/selectListAra10130_n.do")
    for route in READ_ONLY_ROUTES
)
print("routes=19 mutual=1 netfunnel=1")
PY

if rg -n --glob '*.py' 'act_19|selectListAra10h01|selectListArc02012|selectListArc05013|selectListArc06014|selectListArd|selectListAta' src scripts; then
  exit 1
fi
```

- [ ] **Step 5: Request independent read-only review**

Ask a reviewer to compare the diff with the approved spec, focusing on exact
empty form/headers/referer, parser success classification, redaction, manual-only
behavior, call order, unchanged NetFunnel handling, and absence of every excluded
route. Resolve every finding before live verification.

- [ ] **Step 6: Run one bounded opted-in live verification**

Source the ignored `.local-live-smoke.env` without printing it. Supply a one-off
future `SRT_TEST_DATE` in the process environment without editing the ignored
file, then invoke only `run_live_smoke_from_env()` once.

Required outcome:

```python
result["mutualVerificationLoaded"] is True
```

Also confirm the existing bounded fields still report login, main, booking,
selectors, notice, ticket, personal/group search, timetable, and fare status.
Never print the verification value, raw response, search rows, cookies, or
credentials.

- [ ] **Step 7: Record actual evidence and clean generated artifacts**

Update `docs/IMPLEMENTATION_PROGRESS.md` with the actual full test count,
wheel/sdist and isolated-import outcomes, route count 19, bounded mutual live
result, unchanged NetFunnel behavior, and the continuing separate seat-selection
safety gate. Remove generated `dist/` and `build/`, run `git diff --check`, and
confirm no credential file or raw result is staged.

- [ ] **Step 8: Commit final evidence**

```bash
git add docs/IMPLEMENTATION_PROGRESS.md
git commit -m "docs: record srt mutual verification results"
```

Skip this commit only if Task 3 already contains the exact final evidence.

## Final Verification Checklist

- [ ] Every production method was introduced after an observed failing test.
- [ ] The full offline suite passes with only the explicit live skip.
- [ ] Wheel/sdist build and isolated imports pass.
- [ ] The exact route count is 19 with one unchanged NetFunnel route.
- [ ] Mutual verification sends exact empty form, headers, and referer.
- [ ] List/object success framing and all documented failures are typed.
- [ ] Verification code/raw data are hidden from repr, errors, logs, and live output.
- [ ] Search calls mutual verification only in the live helper, never in the client method itself.
- [ ] No legacy mutual, seat, reservation, `act_19`, ATA/ARD, payment, cancel, refund, native, or external route exists.
- [ ] Bounded live verification reports `mutualVerificationLoaded=True`.
- [ ] Progress documentation matches actual evidence.
