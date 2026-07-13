# SRT Selector Popup Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this whole plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. One implementation agent owns this entire repository plan; do not dispatch implementation subtasks.

**Status:** Completed and bounded-live-verified on 2026-07-13. The original
no-stage/no-commit constraint below governed implementation; the user later
explicitly requested final staging and a commit on `main`.

**Goal:** Add six runtime-evidenced read-only selector popup APIs with exact forms and authenticated HTML framing while preserving NetFunnel and all mutation exclusions.

**Architecture:** Keep `SrtClient` as the facade, add one validated builder per selector in `payloads.py`, and reuse a private client helper that sends exact POST forms and returns the existing repr-safe `HtmlPage`. Expand the route registry by exactly six canonical app paths, leave the exact `act_10` NetFunnel contract untouched, and expose only `selectorLoadedCount` through the live helper.

**Tech Stack:** Python 3.11+, `httpx>=0.27,<1`, frozen dataclasses, standard-library HTML parsing, `pytest>=8,<10`, setuptools.

## Global Constraints

- Work directly in the intentional dirty tree at `/Users/yakisoba/Documents/GitHub/srt-mobile-api`; never reset, discard, stash, or overwrite unrelated changes.
- Do not create a worktree and do not commit, stage, push, or open a pull request unless the user explicitly requests it.
- Follow TDD for each task: add a focused failing test, run it and observe the expected failure, implement the minimum behavior, rerun the focused test, then run the affected suite.
- Add only the six approved popup paths under `/common/ARA/`; do not add the legacy static date path, mutual verification, or the app seat-selection page.
- Never add or call reservation, payment, cancellation, refund, `act_19`, ATA/ARD, native bridge, or external seat-map APIs.
- Preserve canonical origins `https://app.srail.or.kr` and `https://nf.letskorail.com:443` and exact method/host/path validation before I/O.
- Preserve NetFunnel `act_10` URL construction, parser framing, fresh-key retry, and the one-retry-only `NET000001` behavior exactly.
- Raw popup HTML remains caller-accessible through `HtmlPage.raw` but stays excluded from repr, logs, live output, and progress-document examples.
- Default tests remain offline and use `httpx.MockTransport`; live calls require the existing explicit opt-in and ignored local environment file.
- Keep Python support at `>=3.11` and add no runtime dependency.

---

## File Structure

Files created by this plan:

- `tests/fixtures/selector_station.html`
- `tests/fixtures/selector_station_map.html`
- `tests/fixtures/selector_date.html`
- `tests/fixtures/selector_passenger.html`
- `tests/fixtures/selector_seat_option.html`
- `tests/fixtures/selector_train_group.html`

Existing files modified by this plan:

- `src/srt_mobile_api/payloads.py`: add six validated exact form builders.
- `src/srt_mobile_api/safety.py`: add exactly six canonical app POST routes.
- `src/srt_mobile_api/http.py`: add `post_html_form()` and classify selector JSON/non-HTML framing before client parsing.
- `src/srt_mobile_api/errors.py`: retain raw protocol framing on `SrtProtocolError` without exposing it in rendered errors.
- `src/srt_mobile_api/client.py`: add six public methods and one private HTML helper.
- `src/srt_mobile_api/__init__.py`: export the existing `HtmlPage` model from the package root.
- `src/srt_mobile_api/live.py`: call all six selectors and return one bounded count.
- `tests/test_netfunnel_payloads_parsers.py`: lock selector form construction without altering NetFunnel tests.
- `tests/test_safety.py`: lock the 18-route policy and bypass rejection.
- `tests/test_client_read_apis.py`: lock path/form/header/referer and expiry behavior.
- `tests/test_http.py`: retain HTML/JSON framing, login-form, and transport regressions.
- `tests/test_redaction_safety.py`: lock redacted rendering for typed errors with retained raw data.
- `tests/test_public_contract.py`: lock the expanded 18-method public surface and signatures.
- `tests/test_live.py`: lock six calls and count-only output.
- `README.md`: document the selector surface and exclusions.
- `docs/IMPLEMENTATION_PROGRESS.md`: record actual final verification and remaining candidates.

No new public model is required. `PassengerCounts` is already exported; this plan must add the existing `HtmlPage` model to the package-root exports and verify that root import from the built wheel.

---

### Task 1: Exact Selector Payload Builders

**Files:**

- Modify: `src/srt_mobile_api/payloads.py`
- Modify: `tests/test_netfunnel_payloads_parsers.py`

**Interfaces:**

- Consumes: `PassengerCounts` and existing `TRAIN_GROUP_OPTIONS`.
- Produces: `station_selector_payload()`, `station_map_selector_payload()`, `date_selector_payload()`, `passenger_selector_payload()`, `seat_option_selector_payload()`, and `train_group_selector_payload()`.

- [ ] **Step 1: Add failing exact-form tests**

Add imports for the six builders to `tests/test_netfunnel_payloads_parsers.py`, then add:

```python
def test_station_selector_payload_is_exact():
    assert station_selector_payload("수서", "부산", "0551", "0020") == {
        "reqCode": "1",
        "sDptStnNm": "수서",
        "sArvStnNm": "부산",
        "sDptStnCd": "0551",
        "sArvStnCd": "0020",
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def test_station_map_selector_payload_is_exact():
    assert station_map_selector_payload() == {
        "reqCode": "2",
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def test_date_selector_payload_is_exact():
    assert date_selector_payload("20260714", "06") == {
        "reqCode": "3",
        "selectDay": "",
        "selectDt": "20260714",
        "selectTime": "06",
    }


def test_passenger_selector_payload_keeps_six_slots_and_server_typo():
    passengers = PassengerCounts(
        adult=1,
        child=2,
        senior=3,
        disability_1_to_3=4,
        disability_4_to_6=5,
        infant=6,
    )
    assert passenger_selector_payload(passengers) == {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": "1",
        "passenger2": "2",
        "passenger3": "3",
        "passenger4": "4",
        "passenger5": "5",
        "passenger6": "6",
        "totalPessnger": "21",
    }


def test_seat_option_selector_payload_is_exact():
    assert seat_option_selector_payload("015", "000", "일반/기본") == {
        "reqCode": "5",
        "rqSeatAttCd": "015",
        "locSeatAttCd": "000",
        "seatAttNm": "일반/기본",
    }


def test_train_group_selector_payload_is_exact():
    assert train_group_selector_payload("109", "전체") == {
        "reqCode": "7",
        "trnGpCd": "109",
        "trnGpCdNm": "전체",
    }
```

Add validation coverage:

```python
@pytest.mark.parametrize(
    ("builder", "args"),
    [
        (station_selector_payload, ("", "부산", "0551", "0020")),
        (station_selector_payload, ("수서", "부산", "", "0020")),
        (date_selector_payload, ("2026-07-14", "06")),
        (date_selector_payload, ("20260714", "24")),
        (seat_option_selector_payload, ("", "000", "일반/기본")),
        (seat_option_selector_payload, ("015", "000", "")),
        (train_group_selector_payload, ("999", "전체")),
        (train_group_selector_payload, ("109", "")),
    ],
)
def test_selector_payloads_reject_invalid_input(builder, args):
    with pytest.raises(ValueError):
        builder(*args)
```

- [ ] **Step 2: Run the focused payload tests and confirm collection failure**

Run:

```bash
python3 -m pytest tests/test_netfunnel_payloads_parsers.py -q
```

Expected: collection fails because the six builders do not exist.

- [ ] **Step 3: Implement input validation and the six builders**

Add to `src/srt_mobile_api/payloads.py`:

```python
def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def station_selector_payload(
    departure_name: str,
    arrival_name: str,
    departure_code: str,
    arrival_code: str,
) -> dict[str, str]:
    return {
        "reqCode": "1",
        "sDptStnNm": _required_text(departure_name, "departure_name"),
        "sArvStnNm": _required_text(arrival_name, "arrival_name"),
        "sDptStnCd": _required_text(departure_code, "departure_code"),
        "sArvStnCd": _required_text(arrival_code, "arrival_code"),
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def station_map_selector_payload() -> dict[str, str]:
    return {
        "reqCode": "2",
        "chk_rtrp": "false",
        "sNowSel": "1",
        "page": "ARA0101",
        "boolRtrp": "false",
    }


def date_selector_payload(date: str, hour: str = "06") -> dict[str, str]:
    if len(date) != 8 or not date.isdigit():
        raise ValueError("date must use YYYYMMDD")
    if len(hour) != 2 or not hour.isdigit() or not 0 <= int(hour) <= 23:
        raise ValueError("hour must use HH from 00 through 23")
    return {"reqCode": "3", "selectDay": "", "selectDt": date, "selectTime": hour}


def passenger_selector_payload(passengers: PassengerCounts) -> dict[str, str]:
    return {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": str(passengers.adult),
        "passenger2": str(passengers.child),
        "passenger3": str(passengers.senior),
        "passenger4": str(passengers.disability_1_to_3),
        "passenger5": str(passengers.disability_4_to_6),
        "passenger6": str(passengers.infant),
        "totalPessnger": str(passengers.total),
    }


def seat_option_selector_payload(
    request_seat_attr_code: str = "015",
    location_seat_attr_code: str = "000",
    seat_name: str = "일반/기본",
) -> dict[str, str]:
    return {
        "reqCode": "5",
        "rqSeatAttCd": _required_text(request_seat_attr_code, "request_seat_attr_code"),
        "locSeatAttCd": _required_text(location_seat_attr_code, "location_seat_attr_code"),
        "seatAttNm": _required_text(seat_name, "seat_name"),
    }


def train_group_selector_payload(
    train_group_code: str = "109",
    train_group_name: str = "전체",
) -> dict[str, str]:
    if train_group_code not in TRAIN_GROUP_OPTIONS:
        raise ValueError("train_group_code must be one of 300, 900, or 109")
    return {
        "reqCode": "7",
        "trnGpCd": train_group_code,
        "trnGpCdNm": _required_text(train_group_name, "train_group_name"),
    }
```

- [ ] **Step 4: Run payload and existing NetFunnel/search tests**

Run:

```bash
python3 -m pytest tests/test_netfunnel_payloads_parsers.py -q
```

Expected: all pass, including existing exact `act_10`, hydration, search, fare, and retry-related payload tests.

- [ ] **Step 5: Review the Task 1 diff without staging or committing**

Run:

```bash
git diff -- src/srt_mobile_api/payloads.py tests/test_netfunnel_payloads_parsers.py
```

Expected: six focused builders and their tests only; no search or NetFunnel implementation change.

---

### Task 2: Exact Six-Route Safety Expansion

**Files:**

- Modify: `src/srt_mobile_api/safety.py`
- Modify: `tests/test_safety.py`

**Interfaces:**

- Consumes: `ReadOnlyRoute` and `assert_read_only_request()`.
- Produces: an 18-route registry containing exactly 17 app routes and the existing single NetFunnel `act_10` route.

- [ ] **Step 1: Add failing accepted/rejected route tests**

Extend the accepted-route parameterization in `tests/test_safety.py` with:

```python
("POST", "/common/ARA/ARA0501P/view.do"),
("POST", "/common/ARA/ARA0502P/view.do"),
("POST", "/common/ARA/ARA0403P/view.do"),
("POST", "/common/ARA/ARA0901P/view.do"),
("POST", "/common/ARA/ARA0701P/view.do"),
("POST", "/common/ARA/ARA0201V/view.do"),
```

Also add `READ_ONLY_ROUTES` to the existing import from
`srt_mobile_api.safety` so the exact-size assertion uses the production
registry.

Add:

```python
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/common/ARA/ARA0501P/view.do"),
        ("POST", "/common/ARA/ARA0401P/view.do"),
        ("POST", "/common/ARA/ARA0501P/view.do/extra"),
        ("POST", "/arc/selectListArc02012_n.do"),
    ],
)
def test_selector_policy_rejects_wrong_method_legacy_neighbor_and_seat_page(method, path):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(method, httpx.URL(f"{config.base_url}{path}"), config)


def test_route_registry_has_exact_expanded_size():
    assert len(READ_ONLY_ROUTES) == 18
```

- [ ] **Step 2: Run the focused safety tests and confirm failure**

Run:

```bash
python3 -m pytest tests/test_safety.py tests/test_http.py -q
```

Expected: failures because the six routes are missing and the registry still has 12 entries.

- [ ] **Step 3: Add only the approved routes**

Add to `READ_ONLY_ROUTES` in `src/srt_mobile_api/safety.py`:

```python
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0501P/view.do"),
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0502P/view.do"),
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0403P/view.do"),
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0901P/view.do"),
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0701P/view.do"),
ReadOnlyRoute("POST", "app", "/common/ARA/ARA0201V/view.do"),
```

Do not change any NetFunnel query validation or excluded-domain entry.

- [ ] **Step 4: Run safety, HTTP, and NetFunnel tests**

Run:

```bash
python3 -m pytest tests/test_safety.py tests/test_http.py tests/test_netfunnel_payloads_parsers.py -q
```

Expected: all pass; `act_19` remains rejected and `act_10` remains exact.

- [ ] **Step 5: Review the Task 2 diff without staging or committing**

Run:

```bash
git diff -- src/srt_mobile_api/safety.py tests/test_safety.py
```

Expected: six route entries and focused tests only.

---

### Task 3: Selector Fixtures And Guarded Client Methods

**Files:**

- Create: `tests/fixtures/selector_station.html`
- Create: `tests/fixtures/selector_station_map.html`
- Create: `tests/fixtures/selector_date.html`
- Create: `tests/fixtures/selector_passenger.html`
- Create: `tests/fixtures/selector_seat_option.html`
- Create: `tests/fixtures/selector_train_group.html`
- Modify: `src/srt_mobile_api/errors.py`
- Modify: `src/srt_mobile_api/http.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `tests/test_client_read_apis.py`
- Modify: `tests/test_http.py`
- Modify: `tests/test_redaction_safety.py`

**Interfaces:**

- Consumes: the six payload builders, `parse_html_page()`, `_session_guard()`, and `SrtHttpClient.post_html_form()`.
- Produces: raw-preserving `SrtProtocolError`, typed HTML/JSON framing, six public methods returning `HtmlPage`, and private `_get_selector_page(path, payload, context)`.

- [ ] **Step 1: Add six small sanitized fixtures**

Each fixture must be a complete nonempty synthetic HTML document with only its callback field names. Use these bodies:

```html
<!-- selector_station.html -->
<html><body>startStnNm startStnCd arrivalStnNm arrivalStnCd</body></html>
<!-- selector_station_map.html -->
<html><body>station map startStnCd arrivalStnCd</body></html>
<!-- selector_date.html -->
<html><body>choiceDate</body></html>
<!-- selector_passenger.html -->
<html><body>passenger1 passenger2 passenger3 passenger4 passenger5</body></html>
<!-- selector_seat_option.html -->
<html><body>seatOption seatPosition seatOptionString</body></html>
<!-- selector_train_group.html -->
<html><body>trainOption trainOptionNm</body></html>
```

Write each comment's following document to the named file; do not include the comments themselves.

- [ ] **Step 2: Add failing exact orchestration tests**

Add a parameterized test to `tests/test_client_read_apis.py` that records six MockTransport requests and invokes the methods with evidenced values:

```python
from urllib.parse import parse_qsl


def test_selector_methods_send_exact_path_form_accept_and_referer(load_text_fixture):
    responses = {
        "/common/ARA/ARA0501P/view.do": "selector_station.html",
        "/common/ARA/ARA0502P/view.do": "selector_station_map.html",
        "/common/ARA/ARA0403P/view.do": "selector_date.html",
        "/common/ARA/ARA0901P/view.do": "selector_passenger.html",
        "/common/ARA/ARA0701P/view.do": "selector_seat_option.html",
        "/common/ARA/ARA0201V/view.do": "selector_train_group.html",
    }
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=load_text_fixture(responses[request.url.path]))

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        pages = [
            client.get_station_selector("수서", "부산", "0551", "0020"),
            client.get_station_map_selector(),
            client.get_date_selector("20260714", hour="06"),
            client.get_passenger_selector(PassengerCounts(adult=1, child=1)),
            client.get_seat_option_selector(),
            client.get_train_group_selector(),
        ]
    finally:
        client.close()

    assert [request.url.path for request in seen] == list(responses)
    assert all(request.method == "POST" for request in seen)
    assert all(request.headers["accept"] == "text/html, */*; q=0.01" for request in seen)
    assert all(request.headers["referer"].endswith("/ara/ara0101v.do") for request in seen)
    assert dict(parse_qsl(seen[3].content.decode(), keep_blank_values=True))["totalPessnger"] == "2"
    assert all(page.text for page in pages)
```

Add a focused login-form regression test using the existing authenticated login-form fixture/pattern:

```python
def test_selector_login_form_clears_session_and_cookies():
    login_html = '<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=login_html)

    client = SrtClient(transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "synthetic-cookie")
    try:
        with pytest.raises(SrtSessionExpiredError):
            client.get_station_map_selector()
        assert client.session.current is None
        assert not list(client.http.cookies.jar)
    finally:
        client.close()
```

Add exact JSON framing and redaction regressions:

```python
def test_selector_json_app_error_is_typed_raw_preserving_and_redacted():
    payload = {
        "ErrorCode": "SELECTOR_ERR",
        "ErrorMsg": '{"netfunnelKey":"key-secret"}',
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SrtAppError) as exc_info:
            client.get_station_map_selector()
        assert exc_info.value.code == "SELECTOR_ERR"
        assert exc_info.value.raw == payload
        assert "key-secret" not in str(exc_info.value)
        assert "key-secret" not in repr(exc_info.value)
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"ErrorCode": "0", "netfunnelKey": "key-secret"},
        {"html": "<html><body>JSON is not popup HTML framing</body></html>"},
        ["not", "an", "object"],
    ],
)
def test_selector_json_success_or_non_object_shape_is_protocol_failure(payload):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SrtProtocolError) as exc_info:
            client.get_station_map_selector()
        assert exc_info.value.raw == payload
        assert "key-secret" not in str(exc_info.value)
        assert "key-secret" not in repr(exc_info.value)
    finally:
        client.close()
```

- [ ] **Step 3: Run focused client tests and confirm methods are absent**

Run:

```bash
python3 -m pytest tests/test_client_read_apis.py -q
```

Expected: failures because the six methods and typed selector HTML/JSON framing do not exist.

- [ ] **Step 4: Add the private HTML helper and public methods**

Give `SrtProtocolError` the same raw-diagnostic contract used by the selector
framing tests:

```python
class SrtProtocolError(SrtApiError):
    """The server response did not match the documented protocol."""

    def __init__(
        self,
        message: str = "SRT protocol response was invalid",
        *,
        raw: object | None = None,
    ) -> None:
        self.raw = raw
        super().__init__(message)
```

In `src/srt_mobile_api/http.py`, import `SrtAppError`, extract the existing form
request into `_post_form_response()`, keep `post_form()` behavior compatible,
and add the typed selector HTML method:

```python
def post_form(
    self,
    path: str,
    data: Mapping[str, Any] | None = None,
    *,
    accept: str = "*/*",
    referer: str | None = None,
) -> dict[str, Any]:
    response = self._post_form_response(
        path,
        data,
        accept=accept,
        referer=referer,
    )
    content_type = response.headers.get("content-type", "")
    if self._expects_json(accept) or self._is_json_content_type(content_type):
        return self._parse_json_object(response)
    return {"html": self._parse_text(response)}


def _post_form_response(
    self,
    path: str,
    data: Mapping[str, Any] | None,
    *,
    accept: str,
    referer: str | None,
) -> httpx.Response:
    headers = {
        "Accept": accept,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": self.config.base_url,
        "X-Requested-With": "XMLHttpRequest",
    }
    if referer:
        headers["Referer"] = referer
    return self._request("POST", path, data=dict(data or {}), headers=headers)


def post_html_form(
    self,
    path: str,
    data: Mapping[str, Any] | None = None,
    *,
    referer: str | None = None,
) -> str:
    response = self._post_form_response(
        path,
        data,
        accept="text/html, */*; q=0.01",
        referer=referer,
    )
    content_type = response.headers.get("content-type", "")
    if not self._is_json_content_type(content_type):
        return self._parse_text(response)
    try:
        payload = response.json()
    except ValueError:
        if self._is_authenticated_login_form(response):
            raise SrtSessionExpiredError(
                "SRT authenticated request returned the login form",
                raw=response.text,
            ) from None
        raise SrtProtocolError(
            "Expected selector HTML but received invalid JSON framing",
            raw=response.text,
        ) from None
    if not isinstance(payload, dict):
        raise SrtProtocolError(
            "Expected selector HTML but received non-object JSON framing",
            raw=payload,
        )
    error_code = payload.get("ErrorCode")
    if isinstance(error_code, str) and error_code not in {"", "0"}:
        message = payload.get("ErrorMsg")
        raise SrtAppError(
            error_code,
            message if isinstance(message, str) else str(message or ""),
            raw=payload,
        )
    raise SrtProtocolError(
        "Expected selector HTML but received JSON framing",
        raw=payload,
    )
```

Import the six builders in `src/srt_mobile_api/client.py`, then add before `_get_act10_key()`:

```python
def _get_selector_page(
    self,
    path: str,
    payload: dict[str, str],
    *,
    context: str,
) -> HtmlPage:
    raw = self.http.post_html_form(
        path,
        payload,
        referer=f"{self.config.base_url}/ara/ara0101v.do",
    )
    return parse_html_page(raw, context=context, require_authenticated=True)


def get_station_selector(
    self,
    departure_name: str,
    arrival_name: str,
    departure_code: str,
    arrival_code: str,
) -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0501P/view.do",
            station_selector_payload(departure_name, arrival_name, departure_code, arrival_code),
            context="station selector",
        )


def get_station_map_selector(self) -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0502P/view.do",
            station_map_selector_payload(),
            context="station map selector",
        )


def get_date_selector(self, date: str, *, hour: str = "06") -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0403P/view.do",
            date_selector_payload(date, hour),
            context="date selector",
        )


def get_passenger_selector(self, passengers: PassengerCounts) -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0901P/view.do",
            passenger_selector_payload(passengers),
            context="passenger selector",
        )


def get_seat_option_selector(
    self,
    *,
    request_seat_attr_code: str = "015",
    location_seat_attr_code: str = "000",
    seat_name: str = "일반/기본",
) -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0701P/view.do",
            seat_option_selector_payload(request_seat_attr_code, location_seat_attr_code, seat_name),
            context="seat option selector",
        )


def get_train_group_selector(
    self,
    train_group_code: str = "109",
    train_group_name: str = "전체",
) -> HtmlPage:
    with self._session_guard():
        return self._get_selector_page(
            "/common/ARA/ARA0201V/view.do",
            train_group_selector_payload(train_group_code, train_group_name),
            context="train group selector",
        )
```

- [ ] **Step 5: Run client, parser, session, and HTTP suites**

Run:

```bash
python3 -m pytest tests/test_client_read_apis.py tests/test_netfunnel_payloads_parsers.py tests/test_session.py tests/test_http.py tests/test_redaction_safety.py -q
```

Expected: all pass with valid popup pages, typed JSON app/protocol framing,
redacted error rendering, and typed expiry behavior.

- [ ] **Step 6: Review the Task 3 diff without staging or committing**

Run:

```bash
git diff -- src/srt_mobile_api/errors.py src/srt_mobile_api/http.py src/srt_mobile_api/client.py tests/test_client_read_apis.py tests/test_http.py tests/test_redaction_safety.py
git status --short tests/fixtures/selector_*.html
```

Expected: six methods, one private helper, six sanitized fixtures, and no search/NetFunnel behavior change.

---

### Task 4: Public Contract, Bounded Live Flow, And Documentation

**Files:**

- Modify: `tests/test_public_contract.py`
- Modify: `src/srt_mobile_api/__init__.py`
- Modify: `src/srt_mobile_api/live.py`
- Modify: `tests/test_live.py`
- Modify: `README.md`

**Interfaces:**

- Consumes: all six selector methods and `TRAIN_GROUP_OPTIONS`.
- Produces: an expanded 18-method `SrtClient` contract, package-root `HtmlPage` export, and live key `selectorLoadedCount: int`.

- [ ] **Step 1: Add failing public-surface and signature assertions**

Update the expected method set in `tests/test_public_contract.py` with:

```python
"get_date_selector",
"get_passenger_selector",
"get_seat_option_selector",
"get_station_map_selector",
"get_station_selector",
"get_train_group_selector",
```

Add:

```python
def test_selector_method_signatures_are_stable():
    assert list(inspect.signature(SrtClient.get_station_selector).parameters) == [
        "self", "departure_name", "arrival_name", "departure_code", "arrival_code"
    ]
    assert list(inspect.signature(SrtClient.get_station_map_selector).parameters) == ["self"]
    assert list(inspect.signature(SrtClient.get_date_selector).parameters) == ["self", "date", "hour"]
    assert list(inspect.signature(SrtClient.get_passenger_selector).parameters) == ["self", "passengers"]
    assert list(inspect.signature(SrtClient.get_seat_option_selector).parameters) == [
        "self", "request_seat_attr_code", "location_seat_attr_code", "seat_name"
    ]
    assert list(inspect.signature(SrtClient.get_train_group_selector).parameters) == [
        "self", "train_group_code", "train_group_name"
    ]
```

Add the package-root export gate:

```python
def test_html_page_is_available_from_the_package_root():
    from srt_mobile_api import HtmlPage
    from srt_mobile_api.models import HtmlPage as ModelHtmlPage

    assert HtmlPage is ModelHtmlPage
```

- [ ] **Step 2: Extend the failing fake-client live contract**

In `tests/test_live.py`, configure five selector methods to return
`HtmlPage(text="selector", raw="<html>selector</html>")` and make the station-map
selector return valid markup with empty extracted text:

```python
client.get_station_map_selector.return_value = HtmlPage(
    text="",
    raw='<html><body><input name="startStnCd"></body></html>',
)

assert result["selectorLoadedCount"] == 5
assert "raw" not in result
assert "text" not in repr(result).lower()
for method_name in (
    "get_station_selector",
    "get_station_map_selector",
    "get_date_selector",
    "get_passenger_selector",
    "get_seat_option_selector",
    "get_train_group_selector",
):
    assert getattr(client, method_name).called
```

Keep the existing exact result-key assertion and add `selectorLoadedCount` to that expected set.
This locks the metric as a count of pages with nonempty extracted text. When all
six pages have nonempty `.text`, the count is `6`; a valid markup-only page may
lower it without representing a failed HTTP request.

- [ ] **Step 3: Run public and live tests and confirm the live key is absent**

Run:

```bash
python3 -m pytest tests/test_public_contract.py tests/test_live.py -q
```

Expected: public tests fail because `HtmlPage` is not exported from the package root; live tests fail because selector calls/count are absent.

- [ ] **Step 4: Export `HtmlPage` and add six bounded live calls**

Add `HtmlPage` to both the model import block and `__all__` in
`src/srt_mobile_api/__init__.py` without changing the model itself.

Import `TRAIN_GROUP_OPTIONS` from `srt_mobile_api.payloads` in `src/srt_mobile_api/live.py`. In `run_live_smoke()` after `booking = client.get_booking_page()` and before notices/search, add:

```python
group_name = TRAIN_GROUP_OPTIONS[query.train_group_code][0]
selectors = (
    client.get_station_selector(
        query.departure_station_name or query.departure_station_code,
        query.arrival_station_name or query.arrival_station_code,
        query.departure_station_code,
        query.arrival_station_code,
    ),
    client.get_station_map_selector(),
    client.get_date_selector(query.departure_date, hour=query.departure_time[:2]),
    client.get_passenger_selector(query.passengers),
    client.get_seat_option_selector(request_seat_attr_code=query.seat_attr_code),
    client.get_train_group_selector(query.train_group_code, group_name),
)
```

Add to the returned mapping:

```python
"selectorLoadedCount": sum(bool(page.text) for page in selectors),
```

Do not return `selectors`, `page.text`, or `page.raw`.
The expression counts nonempty extracted text, not completed selector calls.

- [ ] **Step 5: Document the expanded selector surface**

Update `README.md` with the six public method names, exact read-only popup scope, `HtmlPage` compatibility, `selectorLoadedCount` live output, and the continuing exclusion of seat selection, mutual verification, `act_19`, ATA/ARD, reservation, native bridges, and external seat maps.

- [ ] **Step 6: Run public, live, smoke-script, and redaction suites**

Run:

```bash
python3 -m pytest tests/test_public_contract.py tests/test_live.py tests/test_smoke_script.py tests/test_redaction_safety.py -q
```

Expected: all pass with only bounded metadata and the thin legacy script still delegating to the safe helper.

- [ ] **Step 7: Review the Task 4 diff without staging or committing**

Run:

```bash
git diff -- tests/test_public_contract.py src/srt_mobile_api/__init__.py src/srt_mobile_api/live.py tests/test_live.py README.md
```

Expected: six live calls, one bounded count, expanded public assertions, and read-only documentation only.

---

### Task 5: Full Verification, Independent Review, And Progress Handoff

**Files:**

- Modify: `docs/IMPLEMENTATION_PROGRESS.md`
- Verify: all files named in Tasks 1-4.

**Interfaces:**

- Consumes: the completed selector expansion and existing package/live tooling.
- Produces: verified build artifacts, isolated import evidence, bounded live evidence, and an updated uncommitted handoff.

- [ ] **Step 1: Run the complete offline suite**

Run:

```bash
python3 -m pytest -q
```

Expected: exit 0; only `tests/test_live_service.py` is skipped without explicit live opt-in.

- [ ] **Step 2: Build wheel and sdist**

Run:

```bash
python3 -m build
```

Expected: exit 0 with a newly built wheel and source archive under `dist/`.

- [ ] **Step 3: Verify an isolated wheel import**

Run:

```bash
VERIFY_DIR="$(mktemp -d)"
python3 -m venv "$VERIFY_DIR/venv"
"$VERIFY_DIR/venv/bin/pip" install --quiet dist/srt_mobile_api-0.1.0-py3-none-any.whl
"$VERIFY_DIR/venv/bin/python" -c "from srt_mobile_api import HtmlPage, PassengerCounts, SrtClient; print(SrtClient.__name__)"
rm -rf "$VERIFY_DIR"
```

Expected output: `SrtClient`.

- [ ] **Step 4: Confirm the route and NetFunnel boundaries statically**

Run:

```bash
python3 - <<'PY'
from srt_mobile_api.safety import READ_ONLY_ROUTES
assert len(READ_ONLY_ROUTES) == 18
assert sum(route.host_kind == "netfunnel" for route in READ_ONLY_ROUTES) == 1
assert next(route for route in READ_ONLY_ROUTES if route.host_kind == "netfunnel").path == "/ts.wseq"
print("18 routes; one NetFunnel act_10 transport route")
PY
rg -n "act_19|selectListArc02012|selectListArc05013|selectListArc10013|selectListArd02017|seatmap" src/srt_mobile_api/client.py src/srt_mobile_api/live.py scripts
```

Expected: route assertions pass; forbidden strings are absent from callable source and the safe wrapper. Rejection assertions in tests are allowed.

- [ ] **Step 5: Request independent read-only review**

Provide the approved design, this plan, `git diff`, and fresh test output to a reviewer that must not edit files. Require review of spec coverage, exact six forms/routes, session expiry, canonical origins, raw/repr behavior, live output, NetFunnel non-regression, and forbidden domains. If findings are valid, the same SRT implementation agent fixes them and reruns the affected and full suites.

- [ ] **Step 6: Run bounded opted-in live verification**

Load the existing ignored `.local-live-smoke.env` without printing it, then run:

```bash
pytest -m live tests/test_live_service.py -q
```

Expected under the strict live assertion: pass with `selectorLoadedCount == 6`
and no popup raw/text output, proving all six responses had nonempty extracted
text. If the helper returns a lower count without a typed exception, report the
exact bounded value as compatible with valid markup-only pages and report the
strict live assertion as unmet; do not misclassify it as a failed request. A
server rejection remains a typed failure, and unavailable live configuration is
reported as not run.

- [ ] **Step 7: Update the progress document from actual evidence**

Update `docs/IMPLEMENTATION_PROGRESS.md` with the actual offline count, build/import result, route count 18, bounded live result or explicit not-run reason, all six new methods, unchanged NetFunnel behavior, and remaining mutual-verification/seat-review candidates. Do not include credentials, cookies, raw HTML, callback values, ticket data, or NetFunnel keys.

- [ ] **Step 8: Perform the final uncommitted-tree review**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors, all intentional pre-existing and new changes remain visible, nothing is staged, and no commit has been created.

## Final Verification Checklist

- [ ] `python3 -m pytest -q` passes with only the explicitly disabled live test skipped.
- [ ] Wheel and sdist build successfully.
- [ ] The built wheel imports `HtmlPage`, `PassengerCounts`, and `SrtClient` in isolation.
- [ ] The exact route count is 18 with one unchanged NetFunnel transport route.
- [ ] All six selector methods send the evidenced form/path/referer and return `HtmlPage`.
- [ ] The passenger form preserves six slots and the exact `totalPessnger` spelling.
- [ ] Empty/login HTML remains a typed protocol/session failure and clears session state on expiry.
- [ ] Raw popup HTML is absent from repr, logs, exceptions, and live output.
- [ ] Existing NetFunnel `act_10`, hydration, and one-retry tests pass unchanged.
- [ ] Independent read-only review has no unresolved finding.
- [ ] Bounded live verification passes with six selectors or is explicitly reported as not run.
- [ ] `docs/IMPLEMENTATION_PROGRESS.md` reflects actual evidence.
- [ ] No file is staged or committed.
