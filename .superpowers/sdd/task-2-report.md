# Task 2 Report: HTTP, Parsers, Redaction, And Safety Core

Implemented the Task 2 core surface for the Python client package:

- Added `SrtHttpClient` in `src/srt_mobile_api/http.py` with form posting, text/JSON GET helpers, cookie access, and transport error wrapping.
- Added `extract_text()` and `normalize_result_row()` in `src/srt_mobile_api/parsers.py`.
- Added `redact_text()` and `redact_mapping()` in `src/srt_mobile_api/redaction.py`.
- Added `EXCLUDED_API_DOMAINS` and `SAFETY_STATEMENTS` in `src/srt_mobile_api/safety.py`.
- Updated `tests/conftest.py` to include the fixture helpers required by the brief.
- Added focused tests for HTTP behavior, parser normalization, text extraction, redaction, and safety domain exclusions.

Validation:

- `pytest tests/test_http.py tests/test_redaction_safety.py -q`
- `pytest -q`

Result: 10 tests passed.

Commit created:

- `1e8f2b3d feat: add srt http and safety core`

Concerns:

- None at this stage. This task intentionally stops short of login, NetFunnel acquisition, search payload builders, facade read APIs, reservation/payment/refund/cancellation flows, and live smoke coverage.

Fix note:

- Tightened `get_json()` and JSON-expected `post_form()` paths to raise `SrtProtocolError` on malformed JSON, non-JSON bodies, and non-dict JSON payloads.
- Preserved HTML fallback only for non-JSON requests to read-only HTML endpoints.
- Made `redact_mapping()` case-insensitive for sensitive keys so lowercase `cookie` and `set-cookie` are masked.

Test output:

```text
$ pytest tests/test_http.py tests/test_redaction_safety.py -q
10 passed in 0.06s

$ pytest -q
14 passed in 0.06s
```
