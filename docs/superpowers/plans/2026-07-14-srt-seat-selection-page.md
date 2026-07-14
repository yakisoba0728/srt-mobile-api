# SRT Seat Selection Page Read Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one strictly bounded public API that reads the authenticated internal SRT seat-selection HTML page without selecting, holding, reserving, or paying for a seat.

**Architecture:** Extend `TrainSummary` with the three server-returned values needed by the seat-page request, build one exact fixed general-class/one-seat form, and enforce that form again against the prepared HTTP request at the transport boundary. Return an inert `SeatSelectionPage(HtmlPage)`, require the evidenced `좌석선택` marker, expose only bounded live booleans, and use one live request as an evidence gate rather than inventing a physical-seat DOM model.

**Tech Stack:** Python 3.11+, frozen dataclasses, `httpx`, standard-library `html.parser` and `urllib.parse`, `pytest` 8–9.

## Global Constraints

- The only newly callable route is exact `POST https://app.srail.or.kr/arc/selectListArc02012_n.do`.
- The request has exactly thirteen evidenced form keys, no URL query, no duplicate keys, and no unknown keys.
- `reqCode="9"`, `trnGpCd="300"`, `psrmClCd="1"`, and `choiceSeatCount="1"` are fixed in this increment.
- `trnNo` is numeric, at most five digits at the model boundary, and encoded as exactly five digits with `zfill(5)`.
- No NetFunnel `act_19`, reservation POST, `/ard/`, `/ata/`, external Korail request, JavaScript execution, callback execution, retry, or fallback train scan is added.
- `SeatSelectionPage.raw` remains caller-accessible for compatibility but repr-hidden; the live helper never returns or logs it.
- The original live HTML is never persisted. Test HTML is synthetic and contains only the evidenced marker and non-sensitive structure.
- Run focused offline tests while developing, make exactly one live seat-page request, then run the complete offline suite once at the end.
- If the single bounded live result does not prove a stable embedded physical-seat schema, do not add `Seat`, `SeatCar`, or seat-availability types.

---

## File Map

- `src/srt_mobile_api/models.py`: append typed search-row fields and define the inert `SeatSelectionPage` result.
- `src/srt_mobile_api/parsers.py`: map the new search fields and require the seat-page marker.
- `src/srt_mobile_api/payloads.py`: build and validate the exact thirteen-field form.
- `src/srt_mobile_api/safety.py`: validate a prepared request, including the new route's query, content type, duplicate keys, key set, fixed values, and numeric shapes.
- `src/srt_mobile_api/http.py`: pass the prepared `httpx.Request` into the safety guard.
- `src/srt_mobile_api/client.py`: expose exactly one `get_seat_page(train)` POST.
- `src/srt_mobile_api/live.py`: choose the first complete SRT row once and emit bounded page/evidence booleans.
- `src/srt_mobile_api/__init__.py`: export `SeatSelectionPage`.
- `tests/fixtures/search_success.json`: add the three evidenced search-row values.
- `tests/fixtures/seat_selection_page.html`: synthetic, non-sensitive marker fixture.
- `tests/fixtures/seat_page_live_evidence.json`: boolean-only sanitized live evidence; never raw HTML.
- `tests/test_netfunnel_payloads_parsers.py`: search mapping and payload contract tests.
- `tests/test_safety.py`: prepared-request and exact seat-form safety tests.
- `tests/test_client_read_apis.py`: seat-page parser and one-request client tests.
- `tests/test_models.py`: field-order compatibility and repr safety.
- `tests/test_public_contract.py`: public method, return type, and export tests.
- `tests/test_live.py`: bounded selection/order/result tests.
- `tests/test_live_service.py`: opt-in live assertions for the new booleans.
- `README.md`: document the read-only API and retained exclusions.
- `docs/IMPLEMENTATION_PROGRESS.md`: record the twentieth route and the single live result.

---

### Task 1: Preserve Seat Request Fields and Build the Exact Form

**Files:**
- Modify: `tests/fixtures/search_success.json`
- Modify: `tests/test_netfunnel_payloads_parsers.py`
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/payloads.py`

**Interfaces:**
- Consumes: the existing `TrainSummary` and `parse_train_search_response()` contracts.
- Produces: `TrainSummary.departure_run_order`, `arrival_run_order`, `seat_attr_code`, and `seat_page_payload(train: TrainSummary) -> dict[str, str]`.

- [ ] **Step 1: Add the failing search-mapping and payload tests**

Replace `tests/fixtures/search_success.json` with this synthetic row, adding only the three evidenced values:

```json
{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"IRG000000","strResult":"SUCC","qryCnqeCnt":"1"}],"dsOutput1":[{"trnNo":"303","trnGpCd":"300","stlbTrnClsfCd":"17","runDt":"20260710","dptDt":"20260710","dptTm":"060000","arvDt":"20260710","arvTm":"083000","dptRsStnCd":"0551","dptRsStnNm":"수서","arvRsStnCd":"0020","arvRsStnNm":"부산","dptStnRunOrdr":"000001","arvStnRunOrdr":"000010","seatAttCd":"015"}]}}
```

In `tests/test_netfunnel_payloads_parsers.py`, import `replace` and `seat_page_payload`, extend the existing parser assertion, and add these tests:

```python
from dataclasses import replace

from srt_mobile_api.payloads import seat_page_payload


def _complete_seat_page_train() -> TrainSummary:
    return TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
    )


def test_search_parser_preserves_seat_page_fields(load_json_fixture):
    train = parse_train_search_response(
        load_json_fixture("search_success.json")
    ).trains[0]

    assert train.departure_run_order == "000001"
    assert train.arrival_run_order == "000010"
    assert train.seat_attr_code == "015"


def test_seat_page_payload_is_the_exact_fixed_contract():
    assert seat_page_payload(_complete_seat_page_train()) == {
        "reqCode": "9",
        "runDt": "20260710",
        "dptDt": "20260710",
        "trnNo": "00303",
        "dptTm": "060000",
        "trnGpCd": "300",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "psrmClCd": "1",
        "seatAttCd": "015",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000010",
        "choiceSeatCount": "1",
    }


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"train_no": ""}, "train_no"),
        ({"train_no": "123456"}, "train_no"),
        ({"train_no": "30A"}, "train_no"),
        ({"train_group_code": "900"}, "train_group_code"),
        ({"run_date": None}, "run_date"),
        ({"departure_date": "2026-07-10"}, "departure_date"),
        ({"departure_time": "0600"}, "departure_time"),
        ({"departure_station_code": None}, "departure_station_code"),
        ({"arrival_station_code": "20"}, "arrival_station_code"),
        ({"departure_run_order": None}, "departure_run_order"),
        ({"arrival_run_order": "A10"}, "arrival_run_order"),
        ({"seat_attr_code": "15"}, "seat_attr_code"),
    ],
)
def test_seat_page_payload_rejects_incomplete_or_malformed_train(changes, message):
    with pytest.raises(ValueError, match=message):
        seat_page_payload(replace(_complete_seat_page_train(), **changes))
```

- [ ] **Step 2: Run the focused tests and confirm the intended failure**

Run:

```bash
pytest -q \
  tests/test_netfunnel_payloads_parsers.py::test_search_parser_preserves_seat_page_fields \
  tests/test_netfunnel_payloads_parsers.py::test_seat_page_payload_is_the_exact_fixed_contract \
  tests/test_netfunnel_payloads_parsers.py::test_seat_page_payload_rejects_incomplete_or_malformed_train
```

Expected: collection fails because `seat_page_payload` and the new `TrainSummary` fields do not exist.

- [ ] **Step 3: Add the minimal model mapping and payload builder**

Append these fields after the existing station-name fields in `TrainSummary` so every legacy positional field remains in its current position:

```python
    departure_run_order: str | None = None
    arrival_run_order: str | None = None
    seat_attr_code: str | None = None
```

Add these keyword mappings to `parse_train_search_response()`:

```python
            departure_run_order=row.get("dptStnRunOrdr"),
            arrival_run_order=row.get("arvStnRunOrdr"),
            seat_attr_code=row.get("seatAttCd"),
```

Add this validation helper and builder to `payloads.py`:

```python
def _required_digits(
    value: str | None,
    name: str,
    *,
    length: int | None = None,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str) or not value or not value.isdigit():
        raise ValueError(f"{name} must contain only digits")
    if length is not None and len(value) != length:
        raise ValueError(f"{name} must contain exactly {length} digits")
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{name} must contain at most {max_length} digits")
    return value


def seat_page_payload(train: TrainSummary) -> dict[str, str]:
    if train.train_group_code != "300":
        raise ValueError("train_group_code must be 300 for an SRT seat page")
    train_no = _required_digits(train.train_no, "train_no", max_length=5).zfill(5)
    return {
        "reqCode": "9",
        "runDt": _required_digits(train.run_date, "run_date", length=8),
        "dptDt": _required_digits(train.departure_date, "departure_date", length=8),
        "trnNo": train_no,
        "dptTm": _required_digits(train.departure_time, "departure_time", length=6),
        "trnGpCd": "300",
        "dptRsStnCd": _required_digits(
            train.departure_station_code,
            "departure_station_code",
            length=4,
        ),
        "arvRsStnCd": _required_digits(
            train.arrival_station_code,
            "arrival_station_code",
            length=4,
        ),
        "psrmClCd": "1",
        "seatAttCd": _required_digits(train.seat_attr_code, "seat_attr_code", length=3),
        "dptStnRunOrdr": _required_digits(
            train.departure_run_order,
            "departure_run_order",
        ),
        "arvStnRunOrdr": _required_digits(
            train.arrival_run_order,
            "arrival_run_order",
        ),
        "choiceSeatCount": "1",
    }
```

- [ ] **Step 4: Run the focused tests and confirm they pass**

Run the Step 2 command again.

Expected: all selected cases pass.

- [ ] **Step 5: Commit the domain contract**

```bash
git add \
  tests/fixtures/search_success.json \
  tests/test_netfunnel_payloads_parsers.py \
  src/srt_mobile_api/models.py \
  src/srt_mobile_api/parsers.py \
  src/srt_mobile_api/payloads.py
git commit -m "feat: build exact srt seat page request"
```

---

### Task 2: Enforce the Prepared Seat Request at the Transport Boundary

**Files:**
- Modify: `tests/test_safety.py`
- Modify: `src/srt_mobile_api/safety.py`
- Modify: `src/srt_mobile_api/http.py`

**Interfaces:**
- Consumes: the exact form produced by `seat_page_payload()`.
- Produces: `assert_read_only_request(request: httpx.Request, config: SrtConfig) -> None`, with exact seat-form enforcement and the existing exact NetFunnel enforcement.

- [ ] **Step 1: Convert safety tests to prepared requests and add failing seat-form cases**

In `tests/test_safety.py`, add `urlencode`, create these helpers, and pass prepared requests to every existing `assert_read_only_request` call:

```python
from urllib.parse import urlencode


def _request(method: str, url: str | httpx.URL) -> httpx.Request:
    return httpx.Request(method, url)


def _seat_form() -> dict[str, str]:
    return {
        "reqCode": "9",
        "runDt": "20260710",
        "dptDt": "20260710",
        "trnNo": "00303",
        "dptTm": "060000",
        "trnGpCd": "300",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "psrmClCd": "1",
        "seatAttCd": "015",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000010",
        "choiceSeatCount": "1",
    }


def _seat_request(
    *,
    query: str = "",
    body: str | None = None,
    content_type: str = "application/x-www-form-urlencoded",
) -> httpx.Request:
    config = SrtConfig()
    url = config.base_url + "/arc/selectListArc02012_n.do" + query
    encoded = body if body is not None else urlencode(_seat_form())
    return httpx.Request(
        "POST",
        url,
        content=encoded.encode("ascii"),
        headers={"Content-Type": content_type},
    )
```

Apply this exact call-shape conversion throughout the existing file:

```python
# Before
assert_read_only_request(method, httpx.URL(config.base_url + path), config)

# After
assert_read_only_request(_request(method, config.base_url + path), config)
```

Use the same conversion for the NetFunnel URL and every rejected URL. Remove the valid POST seat path from the two existing neighbor-rejection parameter lists; keep wrong method, encoded path, extra path, reservation, ARD, and ATA neighbors rejected.

Add these tests and update the route-count assertion to `20`:

```python
def test_exact_seat_page_form_is_allowed():
    assert_read_only_request(_seat_request(), SrtConfig())


@pytest.mark.parametrize(
    "request",
    [
        _request(
            "GET",
            SrtConfig().base_url + "/arc/selectListArc02012_n.do",
        ),
        _seat_request(query="?extra=1"),
        _seat_request(body=urlencode(_seat_form()) + "&reqCode=9"),
        _seat_request(
            body=urlencode(
                {
                    name: value
                    for name, value in _seat_form().items()
                    if name != "seatAttCd"
                }
            )
        ),
        _seat_request(body=urlencode({**_seat_form(), "seatNo1_1": ""})),
        _seat_request(body=urlencode({**_seat_form(), "choiceSeatCount": "2"})),
        _seat_request(body=urlencode({**_seat_form(), "psrmClCd": "2"})),
        _seat_request(body=urlencode({**_seat_form(), "trnGpCd": "900"})),
        _seat_request(body=urlencode({**_seat_form(), "trnNo": "303"})),
        _seat_request(content_type="application/json"),
    ],
)
def test_seat_page_rejects_query_duplicates_unknown_fields_and_wrong_values(request):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(request, SrtConfig())


def test_seat_page_rejects_percent_encoded_route_spelling():
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            _request(
                "POST",
                config.base_url + "/arc/%73electListArc02012_n.do",
            ),
            config,
        )


def test_route_registry_has_exact_expanded_size():
    assert len(READ_ONLY_ROUTES) == 20
```

- [ ] **Step 2: Run the safety tests and confirm the intended failure**

Run:

```bash
pytest -q tests/test_safety.py
```

Expected: failures report the old three-argument safety signature and the still-blocked seat route.

- [ ] **Step 3: Validate the full prepared request before send**

In `safety.py`, import `Counter`, `re`, and `parse_qsl`, add the route and exact form constants, and implement the body guard:

```python
from collections import Counter
import re
from urllib.parse import parse_qsl


SEAT_PAGE_PATH = "/arc/selectListArc02012_n.do"
SEAT_PAGE_FIELDS = frozenset(
    {
        "reqCode",
        "runDt",
        "dptDt",
        "trnNo",
        "dptTm",
        "trnGpCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "psrmClCd",
        "seatAttCd",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "choiceSeatCount",
    }
)
SEAT_PAGE_FIXED_VALUES = {
    "reqCode": "9",
    "trnGpCd": "300",
    "psrmClCd": "1",
    "choiceSeatCount": "1",
}
SEAT_PAGE_VALUE_PATTERNS = {
    "runDt": r"\d{8}",
    "dptDt": r"\d{8}",
    "trnNo": r"\d{5}",
    "dptTm": r"\d{6}",
    "dptRsStnCd": r"\d{4}",
    "arvRsStnCd": r"\d{4}",
    "seatAttCd": r"\d{3}",
    "dptStnRunOrdr": r"\d+",
    "arvStnRunOrdr": r"\d+",
}


def _assert_seat_page_request(request: httpx.Request) -> None:
    if request.url.query:
        raise SrtProtocolError("SRT seat page request must not use URL query parameters")
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise SrtProtocolError("SRT seat page request must use URL-encoded form data")
    try:
        body = request.content.decode("ascii")
        items = parse_qsl(body, keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        raise SrtProtocolError("SRT seat page form encoding is invalid") from None
    counts = Counter(name for name, _value in items)
    if set(counts) != SEAT_PAGE_FIELDS or any(count != 1 for count in counts.values()):
        raise SrtProtocolError("SRT seat page form keys do not match the registered contract")
    values = dict(items)
    if any(values.get(name) != value for name, value in SEAT_PAGE_FIXED_VALUES.items()):
        raise SrtProtocolError("SRT seat page fixed form values do not match the registered contract")
    if any(
        re.fullmatch(pattern, values.get(name, "")) is None
        for name, pattern in SEAT_PAGE_VALUE_PATTERNS.items()
    ):
        raise SrtProtocolError("SRT seat page dynamic form values are malformed")
```

Add this registry entry:

```python
        ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH),
```

Replace the safety entry point with this complete prepared-request version:

```python
def assert_read_only_request(request: httpx.Request, config: SrtConfig) -> None:
    if config.base_url != APP_ORIGIN or config.netfunnel_url != NETFUNNEL_ORIGIN:
        raise SrtProtocolError("SRT request configuration does not use canonical origins")
    method = request.method
    url = request.url
    app = httpx.URL(APP_ORIGIN)
    netfunnel = httpx.URL(NETFUNNEL_ORIGIN)
    host_kind = (
        "app"
        if _same_origin(url, app)
        else "netfunnel"
        if _same_origin(url, netfunnel)
        else ""
    )
    path = url.path
    raw_path = url.raw_path.partition(b"?")[0]
    try:
        canonical_raw_path = path.encode("ascii")
    except UnicodeEncodeError:
        raise SrtProtocolError(
            "SRT request path must use the exact ASCII route spelling"
        ) from None
    if raw_path != canonical_raw_path:
        raise SrtProtocolError(
            "SRT request path must not use percent-encoded route characters"
        )
    route = ReadOnlyRoute(method.upper(), host_kind, path)
    if route not in READ_ONLY_ROUTES:
        raise SrtProtocolError(
            f"SRT request route is not allowed: {method.upper()} {path}"
        )
    if route == ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH):
        _assert_seat_page_request(request)
        return
    if host_kind != "netfunnel":
        return

    items = url.params.multi_items()
    params = dict(items)
    timestamp_keys = [name for name, value in items if name.isdigit() and value == ""]
    required = {
        "opcode": "5101",
        "nfid": "0",
        "prefix": "NetFunnel.gRtype=5101;",
        "sid": "service_1",
        "aid": "act_10",
        "js": "true",
    }
    if (
        any(params.get(name) != value for name, value in required.items())
        or len(timestamp_keys) != 1
        or len(items) != len(required) + 1
        or any(
            sum(name == item_name for item_name, _value in items) != 1
            for name in required
        )
    ):
        raise SrtProtocolError(
            "SRT NetFunnel request is not the registered act_10 contract"
        )
```

In `SrtHttpClient._request()`, change the call after `build_request()` to:

```python
        assert_read_only_request(request, self.config)
```

- [ ] **Step 4: Run the safety tests and the HTTP transport tests**

Run:

```bash
pytest -q tests/test_safety.py tests/test_http.py
```

Expected: all selected tests pass, including NetFunnel `act_10` query validation and the new exact seat form.

- [ ] **Step 5: Commit the transport boundary**

```bash
git add tests/test_safety.py src/srt_mobile_api/safety.py src/srt_mobile_api/http.py
git commit -m "feat: guard exact srt seat page form"
```

---

### Task 3: Expose the Inert Seat Selection Page API

**Files:**
- Create: `tests/fixtures/seat_selection_page.html`
- Modify: `tests/test_client_read_apis.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_public_contract.py`
- Modify: `src/srt_mobile_api/models.py`
- Modify: `src/srt_mobile_api/parsers.py`
- Modify: `src/srt_mobile_api/client.py`
- Modify: `src/srt_mobile_api/__init__.py`

**Interfaces:**
- Consumes: `seat_page_payload(train)` and the prepared-request safety guard.
- Produces: `SeatSelectionPage(HtmlPage)`, `parse_seat_selection_page(html)`, and `SrtClient.get_seat_page(train) -> SeatSelectionPage`.

- [ ] **Step 1: Create the synthetic marker fixture and failing API tests**

Create `tests/fixtures/seat_selection_page.html` with no journey, user, token, or seat values:

```html
<!doctype html>
<html lang="ko">
  <body>
    <main>
      <h1>좌석선택</h1>
      <p>합성 테스트 페이지</p>
    </main>
  </body>
</html>
```

In `tests/test_client_read_apis.py`, import `SeatSelectionPage` and `parse_seat_selection_page`, then add:

```python
def _complete_seat_train() -> TrainSummary:
    return TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
    )


def test_seat_selection_parser_requires_authenticated_marker(load_text_fixture):
    page = parse_seat_selection_page(load_text_fixture("seat_selection_page.html"))
    assert isinstance(page, SeatSelectionPage)
    assert "좌석선택" in page.text
    assert "합성 테스트 페이지" in page.raw

    with pytest.raises(SrtProtocolError, match="seat selection"):
        parse_seat_selection_page("<html><body>unexpected page</body></html>")
    with pytest.raises(SrtSessionExpiredError):
        parse_seat_selection_page(
            '<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>'
        )


def test_get_seat_page_posts_once_and_returns_inert_page(load_text_fixture):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=load_text_fixture("seat_selection_page.html"),
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    page = client.get_seat_page(_complete_seat_train())

    assert isinstance(page, SeatSelectionPage)
    assert "좌석선택" in page.text
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/arc/selectListArc02012_n.do"
    assert not requests[0].url.query
    assert dict(parse_qsl(requests[0].content.decode(), keep_blank_values=True))[
        "choiceSeatCount"
    ] == "1"
```

In `tests/test_models.py`, import `SeatSelectionPage` and extend repr safety:

```python
    seat_page = SeatSelectionPage(text="좌석선택", raw="seat-page-secret")
    assert "seat-page-secret" not in repr(seat_page)
```

In `tests/test_public_contract.py`, add `get_seat_page` to the exact method set and add:

```python
def test_seat_page_method_type_and_export_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import SeatSelectionPage

    signature = inspect.signature(SrtClient.get_seat_page)
    assert list(signature.parameters) == ["self", "train"]
    assert get_type_hints(SrtClient.get_seat_page)["return"] is SeatSelectionPage
    assert srt_mobile_api.SeatSelectionPage is SeatSelectionPage
```

- [ ] **Step 2: Run the focused tests and confirm the intended failure**

Run:

```bash
pytest -q \
  tests/test_client_read_apis.py::test_seat_selection_parser_requires_authenticated_marker \
  tests/test_client_read_apis.py::test_get_seat_page_posts_once_and_returns_inert_page \
  tests/test_public_contract.py::test_seat_page_method_type_and_export_are_stable
```

Expected: collection fails because `SeatSelectionPage`, its parser, and `get_seat_page` do not exist.

- [ ] **Step 3: Implement the typed inert page and exactly one client POST**

Add this model immediately after `HtmlPage`:

```python
@dataclass(frozen=True)
class SeatSelectionPage(HtmlPage):
    pass
```

Import it into `parsers.py` and add:

```python
def parse_seat_selection_page(html: str) -> SeatSelectionPage:
    page = parse_html_page(
        html,
        context="seat selection page",
        require_authenticated=True,
    )
    if "좌석선택" not in page.text:
        raise SrtProtocolError(
            "SRT seat selection page did not contain the required marker"
        )
    return SeatSelectionPage(text=page.text, raw=page.raw)
```

Import `SeatSelectionPage`, `parse_seat_selection_page`, and `seat_page_payload` into `client.py`, then add this public method after the search methods and before timetable/fare detail reads:

```python
    def get_seat_page(self, train: TrainSummary) -> SeatSelectionPage:
        with self._session_guard():
            raw = self.http.post_html_form(
                "/arc/selectListArc02012_n.do",
                seat_page_payload(train),
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )
            return parse_seat_selection_page(raw)
```

Import and export `SeatSelectionPage` in `src/srt_mobile_api/__init__.py`.

- [ ] **Step 4: Run all focused page/API tests**

Run:

```bash
pytest -q \
  tests/test_client_read_apis.py \
  tests/test_models.py \
  tests/test_public_contract.py
```

Expected: all selected tests pass and the handler observes exactly one request.

- [ ] **Step 5: Commit the public read API**

```bash
git add \
  tests/fixtures/seat_selection_page.html \
  tests/test_client_read_apis.py \
  tests/test_models.py \
  tests/test_public_contract.py \
  src/srt_mobile_api/models.py \
  src/srt_mobile_api/parsers.py \
  src/srt_mobile_api/client.py \
  src/srt_mobile_api/__init__.py
git commit -m "feat: read srt seat selection page"
```

---

### Task 4: Add One Bounded Live Seat Page Observation

**Files:**
- Modify: `tests/test_live.py`
- Modify: `tests/test_live_service.py`
- Modify: `src/srt_mobile_api/live.py`

**Interfaces:**
- Consumes: `SrtClient.get_seat_page(train)` and personal search results.
- Produces: exactly one seat-page call for the first complete SRT row and the bounded booleans `seatPageLoaded`, `seatSelectionMarkerPresent`, `externalSeatMapHandoffPresent`, and `embeddedSeatInventoryCandidatePresent`.

- [ ] **Step 1: Add failing bounded-live tests**

In `tests/test_live.py`, import `SeatSelectionPage`, give the existing train all
three seat-page fields, configure the mock, add the four new keys to the exact
result set, add `get_seat_page` to the existing called-method tuple, and assert
order/secrecy:

```python
    train = TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    client.get_seat_page.return_value = SeatSelectionPage(
        text="좌석선택",
        raw=(
            "<html><body><h1>좌석선택</h1>"
            "<script>const map='https://www.korail.com/ticket/search/list?srtJob=seatmap';"
            "</script></body></html>"
        ),
    )
```

Add these result and call assertions to the existing test:

```python
    assert result["seatPageLoaded"] is True
    assert result["seatSelectionMarkerPresent"] is True
    assert result["externalSeatMapHandoffPresent"] is True
    assert result["embeddedSeatInventoryCandidatePresent"] is False
    client.get_seat_page.assert_called_once_with(train)
    assert method_order.index("search_trains") < method_order.index("get_seat_page")
    assert method_order.index("get_seat_page") < method_order.index(
        "get_mutual_verification"
    )
    assert "korail.com" not in repr(result)
```

Also add a focused selector test:

```python
def test_first_complete_srt_seat_train_does_not_fallback_or_read_raw():
    complete = TrainSummary(
        train_no="303",
        train_group_code="300",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
        raw={"must_not_be_read": object()},
    )
    trains = [
        TrainSummary("101", train_group_code="900"),
        TrainSummary("301", train_group_code="300"),
        complete,
        TrainSummary("305", train_group_code="300"),
    ]

    assert _first_complete_srt_seat_train(trains) is complete


def test_embedded_inventory_probe_uses_structure_without_returning_it():
    page = SeatSelectionPage(
        text="좌석선택",
        raw=(
            '<div class="seat available"></div>'
            '<button data-seat-no="SYNTHETIC"></button>'
        ),
    )

    assert _embedded_seat_inventory_candidate_present(page) is True
```

Import `_first_complete_srt_seat_train` and
`_embedded_seat_inventory_candidate_present` from `srt_mobile_api.live` for
these tests.

In `tests/test_live_service.py`, add:

```python
    assert result["seatPageLoaded"] is True
    assert result["seatSelectionMarkerPresent"] is True
    assert isinstance(result["externalSeatMapHandoffPresent"], bool)
    assert isinstance(result["embeddedSeatInventoryCandidatePresent"], bool)
```

- [ ] **Step 2: Run the offline live-helper tests and confirm the intended failure**

Run:

```bash
pytest -q tests/test_live.py tests/test_live_service.py
```

Expected: the ordinary live-helper test fails because the selector and result keys do not exist; the opt-in service test remains skipped without `SRT_MOBILE_API_LIVE=1`.

- [ ] **Step 3: Select one complete SRT row and return booleans only**

In `live.py`, add these imports, extend the model import with
`SeatSelectionPage` and `TrainSummary`, then add the implementation below:

```python
import re
from collections.abc import Sequence
from html.parser import HTMLParser
```

```python
def _first_complete_srt_seat_train(
    trains: Sequence[TrainSummary],
) -> TrainSummary | None:
    for train in trains:
        required = (
            train.train_no,
            train.run_date,
            train.departure_date,
            train.departure_time,
            train.departure_station_code,
            train.arrival_station_code,
            train.departure_run_order,
            train.arrival_run_order,
            train.seat_attr_code,
        )
        if train.train_group_code == "300" and all(
            isinstance(value, str) and bool(value) for value in required
        ):
            return train
    return None


def _external_seat_map_handoff_present(page: SeatSelectionPage | None) -> bool:
    if page is None:
        return False
    raw_lower = page.raw.casefold()
    return "korail.com" in raw_lower and "srtjob=seatmap" in raw_lower


SEAT_IDENTIFIER_RE = re.compile(
    r"(?:^|[\s_-])(?:seat|scar)(?:[\s_-]|$)",
    re.IGNORECASE,
)


class _EmbeddedSeatInventoryProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.candidate_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() in {"a", "form", "input", "script", "style"}:
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        identifiers = f"{values.get('id', '')} {values.get('class', '')}"
        has_seat_data_attribute = any(
            name.casefold().startswith("data-") and "seat" in name.casefold()
            for name, _value in attrs
        )
        if has_seat_data_attribute or SEAT_IDENTIFIER_RE.search(identifiers):
            self.candidate_count += 1


def _embedded_seat_inventory_candidate_present(
    page: SeatSelectionPage | None,
) -> bool:
    if page is None:
        return False
    parser = _EmbeddedSeatInventoryProbe()
    parser.feed(page.raw)
    return parser.candidate_count >= 2
```

Immediately after personal search in `run_live_smoke()`, call at most one page:

```python
    personal = client.search_trains(query)
    seat_train = _first_complete_srt_seat_train(personal.trains)
    seat_page = client.get_seat_page(seat_train) if seat_train is not None else None
    mutual = client.get_mutual_verification()
```

Add only these bounded fields to the result:

```python
        "seatPageLoaded": bool(seat_page and seat_page.text),
        "seatSelectionMarkerPresent": bool(
            seat_page and "좌석선택" in seat_page.text
        ),
        "externalSeatMapHandoffPresent": _external_seat_map_handoff_present(
            seat_page
        ),
        "embeddedSeatInventoryCandidatePresent": (
            _embedded_seat_inventory_candidate_present(seat_page)
        ),
```

Do not return train details, status labels, page text, page HTML, URLs, seat callback values, or a physical-seat inference.

- [ ] **Step 4: Run the offline live-helper tests**

Run the Step 2 command again with no live flag.

Expected: the helper tests pass and the service test is the only selected skip.

- [ ] **Step 5: Commit the bounded live integration**

```bash
git add tests/test_live.py tests/test_live_service.py src/srt_mobile_api/live.py
git commit -m "feat: add bounded srt seat page smoke"
```

---

### Task 5: Run the Single Evidence Gate, Document the Outcome, and Verify Once

**Files:**
- Modify: `README.md`
- Modify: `docs/IMPLEMENTATION_PROGRESS.md`
- Create: `tests/fixtures/seat_page_live_evidence.json`

**Interfaces:**
- Consumes: the completed offline implementation and existing ignored live credential configuration.
- Produces: one bounded live result, final scope documentation, a clean full-suite result, and no persisted live body.

- [ ] **Step 1: Run focused offline coverage before touching production**

Run:

```bash
pytest -q \
  tests/test_netfunnel_payloads_parsers.py \
  tests/test_safety.py \
  tests/test_http.py \
  tests/test_client_read_apis.py \
  tests/test_models.py \
  tests/test_public_contract.py \
  tests/test_live.py
```

Expected: all selected tests pass. Do not run the complete suite yet.

- [ ] **Step 2: Confirm live inputs exist without displaying their values**

Run:

```bash
for name in SRT_LOGIN_ID SRT_LOGIN_PASSWORD SRT_TEST_DATE; do
  if [ -n "${(P)name}" ]; then
    print "$name=set"
  else
    print "$name=missing"
  fi
done
```

Expected: all three names print `set`. If any prints `missing`, stop before network I/O and ask the user to reload the existing ignored credential configuration; do not search shell history or unrelated repositories.

- [ ] **Step 3: Run exactly one live smoke and retain only its bounded JSON**

Run this once:

```bash
SRT_MOBILE_API_LIVE=1 python -c \
  'import json; from srt_mobile_api.live import run_live_smoke_from_env; print(json.dumps(run_live_smoke_from_env(), ensure_ascii=False, sort_keys=True))'
```

Expected bounded fields include:

```json
{
  "loggedIn": true,
  "seatPageLoaded": true,
  "seatSelectionMarkerPresent": true,
  "externalSeatMapHandoffPresent": true,
  "embeddedSeatInventoryCandidatePresent": false
}
```

The two evidence booleans may differ from the example; record their actual
values. Do not run the live command again. The command must not print page
text, HTML, train/station identifiers, credentials, cookies, NetFunnel keys,
PNRs, seat values, URLs, DOM identifiers, or structural counts.

- [ ] **Step 4: Apply the evidence gate without guessing a physical-seat schema**

Convert the original response to a minimal boolean-only evidence fixture
without persisting any original HTML. First create
`tests/fixtures/seat_page_live_evidence.json` with this all-false form:

```json
{
  "externalSeatMapHandoffPresent": false,
  "embeddedSeatInventoryCandidatePresent": false
}
```

If `externalSeatMapHandoffPresent` is `true`, change only
`"externalSeatMapHandoffPresent": false` to `true`. If
`embeddedSeatInventoryCandidatePresent` is `true`, change only
`"embeddedSeatInventoryCandidatePresent": false` to `true`. These two
booleans are the entire retained live evidence. They contain no original tag
tree, values, text, URL, query, train, station, seat, session, account data,
DOM identifier, or structural count.

Then use the matching documentation outcomes below:

Use exactly one of these documentation outcomes:

```text
externalSeatMapHandoffPresent=true:
  The internal SRT page was loaded, but retained bounded evidence confirms an
  external Korail seat-map handoff. Individual physical seats remain excluded.

externalSeatMapHandoffPresent=false:
  The internal SRT page was loaded, but the bounded result alone does not prove
  a stable embedded car/seat DOM contract. Individual physical seats remain
  untyped pending a separately sanitized synthetic fixture.

embeddedSeatInventoryCandidatePresent=true:
  The in-memory structure probe found at least two non-form, non-script
  seat-named elements. This is a candidate only, not a stable schema; retain
  the boolean and require a separate fixture-backed design before adding types.

embeddedSeatInventoryCandidatePresent=false:
  The conservative structure probe did not find enough embedded seat-named
  elements to justify a physical-seat model.
```

In either outcome, do not add `Seat`, `SeatCar`, selected-seat callbacks, external requests, or another live call. A future typed-layout task requires a new concrete fixture-backed plan.

- [ ] **Step 5: Update README and progress with exact final state**

Add this API section to `README.md`, using the actual external-handoff boolean from Step 3 in the final paragraph:

```markdown
### Physical seat-selection page read

`SrtClient.get_seat_page(train)` performs one authenticated read of the
internal SRT seat-selection HTML page for a complete server-returned SRT row.
The request is fixed to general class and one seat, carries exactly thirteen
allowlisted form fields, and returns `SeatSelectionPage` after requiring the
`좌석선택` marker.

This method does not select or hold a seat. It does not call NetFunnel
`act_19`, submit a reservation, follow the external Korail seat map, execute
JavaScript/callbacks, retry, or scan fallback trains. The live helper reports
only bounded booleans and never emits the page body.
```

Update `docs/IMPLEMENTATION_PROGRESS.md` with:

- last-updated date `2026-07-14 KST`;
- `20` exact read-only routes;
- `get_seat_page(train) -> SeatSelectionPage` in implemented operations;
- fixed general-class/one-seat request and exact prepared-body validation;
- the actual four live seat booleans;
- continued exclusion of `act_19`, reservations, ARD/ATA, native bridges, callbacks, and external seat-map calls;
- the actual final test count from Step 6;
- the evidence-gate outcome text from Step 4.

- [ ] **Step 6: Run the complete offline suite once and scan the final diff**

Run:

```bash
pytest -q
git diff --check
git diff -- \
  src/srt_mobile_api \
  tests \
  README.md \
  docs/IMPLEMENTATION_PROGRESS.md
rg -n \
  'act_19|selectListArc05013|selectListArc06014|selectListArc10013|selectListArd|selectListAta|srtJob=seatmap' \
  src/srt_mobile_api/client.py src/srt_mobile_api/live.py scripts
```

Expected:

- the complete offline suite passes with only the explicit opt-in live-service skip;
- `git diff --check` is silent;
- the diff contains no live body, credential, cookie, token, journey identifier, or selected-seat value;
- the forbidden scan is silent. The external handoff is detected only by generic string fragments in `live.py`; if the exact `srtJob=seatmap` fragment is retained there, replace the final scan with an exact assertion that it occurs once in the boolean detector and nowhere in `client.py` or `scripts/`.

- [ ] **Step 7: Commit the evidence-backed documentation**

```bash
git add README.md docs/IMPLEMENTATION_PROGRESS.md
git add tests/fixtures/seat_page_live_evidence.json
git commit -m "docs: record srt seat page verification"
git status --short --branch
```

Expected: the commit succeeds and the worktree is clean.

---

## Final Review Checklist

- The public method set grows by exactly `get_seat_page`.
- The allowlist grows from nineteen to twenty exact routes.
- The prepared seat request has no query and exactly thirteen unique form keys.
- Only general class and one seat are accepted.
- A server train number such as `303` is sent as `00303`.
- Missing run order or seat attribute data fails before I/O.
- Authentication pages and pages missing `좌석선택` fail closed.
- The client sends exactly one seat-page POST and no adjacent request.
- The live helper reads no `raw` search mapping and emits no HTML/text/URL.
- The original live response is never stored.
- No typed physical-seat model exists without new sanitized fixture evidence.
- One live smoke and one final full offline suite are the only final verification runs.
