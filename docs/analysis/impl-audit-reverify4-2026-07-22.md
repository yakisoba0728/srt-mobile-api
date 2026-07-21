# SRT Client Implementation Audit — Re-verify Pass 4

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Client under audit:** `srt-mobile-api` (read-only Python client)
**Date:** 2026-07-22
**Author:** FABLE
**Scope:** Divergences between our read-only client and the decompiled ground truth (apktool/jadx offline bundle), cross-checked against the battle-tested `srtgo` wire reference.

## Overview

This pass re-verifies candidate divergences across five subsystem groups: `auth-session`, `search-selectors`, `seat-timetable-fare`, `notice-ticket`, and `netfunnel-transport-safety`. Each candidate was adversarially verified against both the decompile and the available wire reference; only findings that survived verification are reported here as real bugs. Ground truth is the decompile; where `srtgo` differs from the app it is treated as the outlier, and unfalsifiable items (server-rendered pages absent from the APK, synthetic-fixture-only fields) are surfaced as residual risk rather than filed as bugs.

**Result: 4 provable divergences — 1 HIGH, 3 LOW.** The single high-severity finding is a concrete, decompile-provable wire bug: the seat-page builder sources `seatAttCd` from the search-response row instead of the request-side constant, which makes `get_seat_page` unable to build a request from a genuine captured train. The three lows are an IP-block login misclassification, a group-search `psgNum`/`totPrnb` clamp that only diverges on input the app forbids, and an over-strict `msgCd` requirement in the mutual-verification parser. No finding was formally rejected on verification; the `notice-ticket` and `netfunnel-transport-safety` groups yielded no provable divergence.

| Metric | Count |
| --- | --- |
| High | 1 |
| Medium | 0 |
| Low | 3 |
| Rejected (non-bugs) | 0 |

## Prioritized bug table

Sorted High → Low. Includes only findings the verifier did **not** reject. Both-sides `file:line` citations are retained in every row.

| Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- |
| High | seat page builder — `seatAttCd` sourced from the wrong field | `src/srt_mobile_api/payloads.py:329` (value from `parsers.py:896`, gated at `payloads.py:308-309`) | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1508`; seed `ara0101v.js:132`; `srtgo/srtgo/srt.py:193,427-449` | `get_seat_page` sends `seatAttCd = _required_digits(train.seat_attr_code, 3)`, and `train.seat_attr_code` is parsed from the `dsOutput1` search-response row's `seatAttCd` key. The app sources this from the **request** side: `ara1001l.js:1508` sends `seatAttCd: lfn_getRsv("rqSeatAttCd1")`, seeded to the constant `"015"` (`ara0101v.js:132`). `srtgo` confirms the design — it hardcodes `rqSeatAttCd1="015"` (`srt.py:193`) and its row parser (`srt.py:427-449`) never reads a row `seatAttCd`. Consequences: (1) real `dsOutput1` rows very likely omit `seatAttCd`, so `train.seat_attr_code` is `None` and `payloads.py:308-309/329` raises `ValueError` — the request cannot be built from a genuine captured train (documented by the client's own `test_get_seat_page_rejects_incomplete_train_before_transport`, `tests/test_client_read_apis.py:970`); (2) when present it is the wrong provenance and may diverge from the requested `rqSeatAttCd1`. Passing tests mask this because `_complete_seat_train` (`tests/test_client_read_apis.py:913`) injects `seat_attr_code='015'`. All other 12 seat-page fields are correctly sourced from the response row per `fn_moveRsv` (`ara1001l.js:1456-1467`). | Do not source `seatAttCd` from `train.seat_attr_code`. Send the search-requested seat-attribute code (`rqSeatAttCd1`): default to the constant `'015'` (as `srtgo` and the app seed do), optionally letting the caller pass the code they searched with, and drop the hard dependency on a response-row `seatAttCd` that real responses do not carry. |
| Low | login error classification (IP block) | `src/srt_mobile_api/http.py:75` (raise `SrtProtocolError` on non-JSON login response); reached via `src/srt_mobile_api/session.py:44` login POST | `srtgo/srtgo/srt.py:719-720` | On an IP block the SRT server returns a **non-JSON plain-text** body (e.g. `"Your IP Address Blocked ..."`), which `srtgo` explicitly surfaces as a login failure (`srt.py:719-720`: `if "Your IP Address Blocked" in r.text: raise SRTLoginError(r.text.strip())`). Our `login()` posts via `http.post_form` with `Accept: application/json`, so a non-JSON body is caught in `_parse_json_object` (`http.py:66-75`) and raised as `SrtProtocolError` **before** `session.py`'s failure branch (`session.py:67-79`) is ever reached. An IP block therefore surfaces as `SrtProtocolError`, not an auth error: callers catching `SrtAuthError`/`SrtSessionExpiredError` from `login()` will miss it, and the block reason is not surfaced. The client has no IP-block handling at all (grep of `src/` for `Blocked`/`IP Address` = none). | In the login flow, obtain the raw login-response body (or catch `SrtProtocolError` from the login POST specifically) and, when the body is non-JSON and contains `Your IP Address Blocked`, raise `SrtAuthError` with the block message. More generally, a non-JSON body on the `Apb01080` login endpoint should be classified as an auth failure rather than a protocol error. |
| Low | group search payload — `psgNum` vs `totPrnb` invariant | `src/srt_mobile_api/payloads.py:259` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:165` (also `:104`); guard `ara0101v.js:551-554` | `group_search_ajax_payload()` sets `psgNum = str(max(query.passengers.total, 10))` but leaves `totPrnb` (carried in `hydrated_fields` from `search_page_payload`, which sets `totPrnb = passengers.total`) untouched. In the app `psgNum` is **always** `lfn_getRsv("totPrnb")` for both individual and group searches (`ara1001l.js:104` `sPsgNum=lfn_getRsv("totPrnb")`, `:165` `"psgNum":sPsgNum`) — the two are identical, and the app never bumps `psgNum`: it instead client-side-rejects a group search when `totPrnb<10` (`ara0101v.js:551-554` alert, no request). So for a group query with `total<10` our client emits an inconsistent payload (`psgNum=10` while `totPrnb=1`) the app would never send. In the only valid case (`total>=10`), `max(total,10)==total==totPrnb`, so no divergence occurs in supported usage; the clamp only differs on input the app forbids. Edge-only / effectively harmless, but a provable deviation from the app's `psgNum==totPrnb` invariant. | Match the app: send `psgNum = str(query.passengers.total)` (`== totPrnb`), and mirror the app's own guard by validating `total>=10` for group search (raise `ValueError`) rather than silently clamping `psgNum` to 10 while `totPrnb` stays below it. |
| Low | mutual-verification parser — over-strict required field | `src/srt_mobile_api/parsers.py:419` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:234` (handler 234-241); schema `docs/analysis/full-api-analysis-2026-07-20.md §4.4` | `parse_mutual_verification_response` requires `msgCd` to be present and a string: it reads `code = row.get('msgCd')` (`parsers.py:419`) then raises `SrtProtocolError` unless `isinstance(code, str)` (`parsers.py:423-426`). The app never reads `msgCd` for this response — `fn_searchMutMrkVrfCd` only checks `dsOutput0.strResult=='FAIL'` then reads `dsOutput0.mutMrkVrfCd` (`ara1001l.js:234-241`). The documented `Ara10130` `dsOutput0` schema is `{strResult, msgTxt, mutMrkVrfCd}` with no `msgCd`. If the live response follows that JS-implied schema, our parser rejects an otherwise valid `SUCC` response, so `get_mutual_verification` would always fail. **Caveat:** not fully provable from the decompile — the standard SRT envelope elsewhere (e.g. search `dsOutput0`) does carry `msgCd`, so the field may be present here too; the sole fixture (`mutual_verification_success.json`) is synthetic and includes `msgCd`, which is why tests pass. | Make `msgCd` optional (`message_code = row.get('msgCd') if str else None`) and gate success only on `strResult != 'FAIL'` plus a present `mutMrkVrfCd`, mirroring `ara1001l.js:234-241`, so a valid response lacking `msgCd` is not rejected. |

## Detailed findings

### HIGH — seat page builder sources `seatAttCd` from the wrong field (`seat-timetable-fare`)

- **Our ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/src/srt_mobile_api/payloads.py:329` (value parsed at `parsers.py:896`, gated at `payloads.py:308-309`)
- **Ground-truth ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/analysis/apktool/assets/offline/js/ara/ara1001l.js:1508`; seed `ara0101v.js:132`; wire ref `/Users/yakisoba/Documents/GitHub/srtgo/srtgo/srt.py:193,427-449`

`get_seat_page` builds `seatAttCd` from the **search-response row**: `payloads.py:329` sends `seatAttCd = _required_digits(train.seat_attr_code, length=3)`, and `train.seat_attr_code` is parsed from the `dsOutput1` row's `seatAttCd` key at `parsers.py:896`. But the app sources this field from the **request** side, not the response. `ara1001l.js:1508` sends `seatAttCd: lfn_getRsv("rqSeatAttCd1")`, where `rqSeatAttCd1` is the seat-attribute code the app itself set at search time, seeded to the constant `"015"` (`ara0101v.js:132`). `srtgo` confirms this design: it hardcodes `rqSeatAttCd1="015"` in its request (`srt.py:193`), and its search-row parser (`srt.py:427-449`) **never** reads a row `seatAttCd`.

Two consequences follow:

1. Real `dsOutput1` rows very likely **omit** `seatAttCd` (neither the app nor `srtgo` read it), so `train.seat_attr_code` is `None`, and `payloads.py:308-309/329` raises `ValueError` — `get_seat_page` cannot build a request at all from a genuine captured train. The client's own test `test_get_seat_page_rejects_incomplete_train_before_transport` (`tests/test_client_read_apis.py:970`) documents exactly this rejection for a train lacking `seat_attr_code`.
2. Even when a value is present, it is the wrong provenance and can diverge from the requested `rqSeatAttCd1`.

Passing tests mask the bug because `_complete_seat_train` (`tests/test_client_read_apis.py:913`) manually injects `seat_attr_code='015'`. All other 12 seat-page fields are correctly sourced — they map to `item.*` response-row values the app stores in `fn_moveRsv` (`ara1001l.js:1456-1467`), matching `srtgo`'s row fields. `seatAttCd` is the sole field the app pulls from the request side.

**Suggested fix:** Do not source `seatAttCd` from `train.seat_attr_code`. Match the app by sending the search-requested seat-attribute code (`rqSeatAttCd1`). The simplest faithful fix is to default `seatAttCd` to the request-side constant `'015'` (as `srtgo` and the app default seed do), optionally letting the caller pass the `seat_attr_code` they searched with; drop the hard dependency on a response-row `seatAttCd` that real responses do not carry.

### LOW — login error classification on IP block (`auth-session`)

- **Our ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/src/srt_mobile_api/http.py:75` (raise `SrtProtocolError` on non-JSON login response); reached via `/Users/yakisoba/Documents/GitHub/srt-mobile-api/src/srt_mobile_api/session.py:44` login POST
- **Ground-truth ref:** `/Users/yakisoba/Documents/GitHub/srtgo/srtgo/srt.py:719-720`

On an IP block, the SRT server returns a **non-JSON plain-text** body (e.g. `"Your IP Address Blocked ..."`), which the battle-tested reference explicitly surfaces as a login failure: `srtgo` does `if "Your IP Address Blocked" in r.text: raise SRTLoginError(r.text.strip())` (`srt.py:719-720`). Our `login()` posts via `http.post_form` with `Accept: application/json`, so a non-JSON body is caught in `_parse_json_object` (`http.py:66-75`) and raised as `SrtProtocolError` **before** `session.py`'s failure branch (`session.py:67-79`) is ever reached.

The result: an IP block surfaces as `SrtProtocolError`, not an auth error. Callers catching `SrtAuthError`/`SrtSessionExpiredError` from `login()` will not catch it, and the block reason is never surfaced. Our client has no IP-block handling at all (grep of `src/` for `Blocked`/`IP Address` = none).

**Suggested fix:** In the login flow, obtain the raw login-response body (or catch `SrtProtocolError` from the login POST specifically) and, when the body is non-JSON and contains `Your IP Address Blocked`, raise `SrtAuthError` with the block message instead of `SrtProtocolError`. More generally, a non-JSON body on the `Apb01080` login endpoint should be classified as an auth failure rather than a protocol error.

### LOW — group search `psgNum` vs `totPrnb` invariant (`search-selectors`)

- **Our ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/src/srt_mobile_api/payloads.py:259`
- **Ground-truth ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/analysis/apktool/assets/offline/js/ara/ara1001l.js:165` (also `:104`); client-side guard `ara0101v.js:551-554`

`group_search_ajax_payload()` sets `psgNum = str(max(query.passengers.total, 10))` but leaves `totPrnb` (carried in `hydrated_fields` from `search_page_payload`, which sets `totPrnb = passengers.total`) untouched. In the app, `psgNum` is **always** `lfn_getRsv("totPrnb")` for both individual and group searches (`ara1001l.js:104` `sPsgNum=lfn_getRsv("totPrnb")`, `:165` `"psgNum":sPsgNum`) — the two are identical. The app never bumps `psgNum`: it instead client-side-rejects a group search when `totPrnb<10` (`ara0101v.js:551-554` alert, no request).

So for a group query with `total<10` our client emits an inconsistent payload (e.g. `psgNum=10` while `totPrnb=1`) that the app would never send. In the only valid case (`total>=10`), `max(total,10)==total==totPrnb`, so no divergence occurs in supported usage; the clamp only differs on input the app forbids. Edge-only / effectively harmless, but a provable deviation from the app's `psgNum==totPrnb` invariant.

**Suggested fix:** Match the app — send `psgNum = str(query.passengers.total)` (`== totPrnb`) — and, to mirror the app's own guard, validate `total>=10` for group search (raise `ValueError`) rather than silently clamping `psgNum` to 10 while `totPrnb` stays below it.

### LOW — mutual-verification parser over-strict on `msgCd` (`seat-timetable-fare`)

- **Our ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/src/srt_mobile_api/parsers.py:419`
- **Ground-truth ref:** `/Users/yakisoba/Documents/GitHub/srt-mobile-api/analysis/apktool/assets/offline/js/ara/ara1001l.js:234` (handler 234-241); schema `docs/analysis/full-api-analysis-2026-07-20.md §4.4`

`parse_mutual_verification_response` requires `msgCd` to be present and a string: it reads `code = row.get('msgCd')` (`parsers.py:419`) and then raises `SrtProtocolError` unless `isinstance(code, str)` (`parsers.py:423-426`). The app never reads `msgCd` for this response — `fn_searchMutMrkVrfCd` only checks `dsOutput0.strResult=='FAIL'` and then reads `dsOutput0.mutMrkVrfCd` (`ara1001l.js:234-241`). The documented `Ara10130` `dsOutput0` schema is `{strResult, msgTxt, mutMrkVrfCd}` with no `msgCd` (`docs/analysis/full-api-analysis-2026-07-20.md §4.4` and the endpoint table). If the live response follows that JS-implied schema (no `msgCd`), our parser rejects an otherwise valid `SUCC` response, so `get_mutual_verification` would always fail.

**Caveat (provability):** this is not fully provable from the decompile alone — the standard SRT envelope elsewhere (e.g. search `dsOutput0`) does carry `msgCd`, so the field may be present here too; the sole fixture (`mutual_verification_success.json`) is synthetic and includes `msgCd`, which is why tests pass. Filed LOW with this explicit caveat.

**Suggested fix:** Make `msgCd` optional (`message_code = row.get('msgCd') if str else None`) and gate success only on `strResult != 'FAIL'` plus a present `mutMrkVrfCd`, mirroring `ara1001l.js:234-241`, so a valid response lacking `msgCd` is not rejected.

## Verified correct

Items examined this pass and confirmed **faithful** to the ground truth (not filed as bugs):

- **`auth-session` — UA-space and `S111` fixes** confirmed correct by prior audits (`docs/analysis/impl-audit-reverify{,2,3}-2026-07-22.md`); re-scrutinized, still correct.
- **`auth-session` — login field VALUES** (`session.py:47-59`, `auto=''`, `check=''`, `page=''`, `login_referer=''`): the bundled static form (`main.html:724-726`) shows these fields empty by default, so our empty values **match** the ground-truth form. `srtgo`'s non-empty variants (`auto='Y'` etc., `srt.py:700-710`) are the outlier; server is lenient and both variants log in. Per decompile > srtgo priority, ours is correct.
- **`auth-session` — extra fields `customerYn`/`ciUptYn`/`dupInfoVal`** (`session.py:60-62`): `customerYn=''` matches `srtgo`; the other two are sent empty, harmless extras.
- **`auth-session` — `login_type` detection via `fullmatch`** (`session.py:22-25`) vs `srtgo`'s `match` (`srt.py:693-694`): equivalent for all valid ids, arguably safer on malformed input.
- **`search-selectors` — date-picker `ARA0403P`→`ARA0401P` + phantom `selectTime`** already fixed (prior-audit-flagged risk), verified resolved.
- **`search-selectors` — `dptTm1` full time and unfiltered rows** kept faithful to the app; `srtgo`'s `dptTm1=time[:2]+"0000"` and `stlbTrnClsfCd=="17"` filter are the outlier.
- **`search-selectors` — station-selector `sNowSel`/passenger-selector `isOrg`** hardcoded to individual-flow values (`"1"`/`"2"`): valid for a headless page fetch; `popCallbacks` ignore them.
- **`seat-timetable-fare` — the other 12 seat-page fields** (`fn_moveRsv`, `ara1001l.js:1456-1467`) correctly sourced from `item.*` response-row values, matching `srtgo`'s row fields.
- **`seat-timetable-fare` — fare `chtnDvCd='1'`** (`payloads.py:382`): correct for the direct single-leg SRT searches this client performs.
- **`netfunnel-transport-safety` — sending `ts.wseq` / `netfunnelKey`**: validated behavior, not a bug. The mobile app itself short-circuits NetFunnel (`TS_BYPASS=true`, `netfunnel.js:24`; ARA calls commented out, `ara0101v.js:651-655`, `ara1001l.js:1734-1739`), but battle-tested `srtgo` on the same host **does** fetch a real key (opcode 5101, `srt.py:88`) and sends `netfunnelKey` (`srt.py:819,987`) and works — proving the server accepts a real key. Our client mirrors `srtgo`.
- **`netfunnel-transport-safety` — GET `/ara/selectListAra10007_n.do`** to hydrate search-form state (`client.py:230`): the app only POSTs this (`ara1001l.js:186,1834`), but the extra GET was live-validated to return the search-result HTML (`docs/analysis/srt-app-api-library-spec-2026-07-09.md:289`).
- **`netfunnel-transport-safety` — `X-Requested-With: XMLHttpRequest`** on POST forms (`http.py:188`): matches the app's jQuery XHR default; server does not appear to enforce it. Our client correctly pins UA `2.0.41` (vs `srtgo`'s older `2.0.38`).
- **`netfunnel/http/config/safety`** wire surface: clean after multiple prior hardening passes; no provable divergence.

## Rejected / non-bugs

**No candidate was formally rejected on verification this pass** (`rejected: []` in every group). The following were examined and deliberately **not** filed as bugs because they are not provable divergences — recorded here so the next pass does not re-litigate them.

### Unprovable — decompile is silent (server-rendered / no bundled JS)

- **`auth-session` — `RTNCD` success gate** (`session.py:68` requires `userMap.RTNCD=='Y'`): the decompile contains **no** occurrence of `userMap` or `RTNCD` (`login.do` / `Apb01080` response handler is server-rendered, absent from the APK). `srtgo` does **not** gate on `RTNCD` — it treats login as successful whenever the three failure strings are absent (`srt.py:715-726`). Our gate carries a one-way false-negative risk: a real success whose `userMap` lacks `RTNCD` would wrongly raise `SrtAuthError`. Docs claim a prior runtime capture showed `RTNCD=Y` (fixture `login_success.json` encodes it). **Unprovable either way → residual risk, not a bug.**
- **`search-selectors` — `ARA0502P` station-map picker**: route/params appear nowhere in `apktool`/`jadx` (opens from inside the server-rendered `ARA0501P`); unfalsifiable. Also flagged in `netfunnel` group as the highest-risk unverified allowlist entry — **recommend live capture.**
- **`seat-timetable-fare` — response parsers** for the seat/timetable/fare pages (`parse_seat_selection_page`, `parse_timetable_page`, `parse_fare_page`): the `arc02012` seat page and both timetable/fare pages are server-rendered HTML absent from the APK, so their parsers cannot be validated against the decompile; fixtures are synthetic. In particular `parse_seat_selection_page` requiring the literal marker `좌석선택` (`parsers.py:171-183`) could over-reject — `좌석선택` is only the client-side titletext (`ara1001l.js:1309`), so whether the server HTML contains it is unverifiable.
- **`notice-ticket` — both core reads are decompile-silent**: `/main/noticeList.do` (`pageId=MB0101000000`) and every notice row field (`IS_MAIN`/`PAGE_ID`/`BODY`/`POST_NO`/`CREATE_DATE`/`IS_NOTICE`/`SUBJ`) return **zero** hits across `apktool`+`jadx` (`main.do` server-rendered, JS not bundled; `srtgo` has no notice feature). The ticket list (`atc14017`) is a server-rendered WebView page with no bundled `atc` JS. Attested only by the live capture in `docs/analysis/srt-app-api-library-spec-2026-07-09.md:256`. Neither read can be proven wrong. Reproduces prior audits' conclusion.

### Latent risks — plausible but unprovable, not filed

- **`notice-ticket` — `POST_NO` strict-int check** (`parsers.py:218` requires `type(row['POST_NO']) is int`): many SRT JSON endpoints return numerics as strings; if the real notice endpoint returns `POST_NO` as a numeric string (or nulls/omits it), the parser raises `SrtProtocolError`. Only the synthetic fixture backs the int assumption.
- **`notice-ticket` — notice error wrapper** accepts only `ErrorCode`/`ErrorMsg` (`parsers.py:189-196`), unlike search/reservation parsers which also accept `ERROR_CODE`/`ERROR_MSG` (`parsers.py:639-642`). Uppercase-underscore notice errors would slip through unclassified. No ground truth to decide.
- **`notice-ticket` — `atc14017` pagination**: `client.py:122` always appends `?pageNo=<n>`; the decompile attaches `pageNo` only to `atc14016` (`SRForegroundDialogActivity.java:31`), and the `atc14017` native landing carries no query string (`SRWebActivity.java:1592`). `pageNo=0` is runtime-verified (`spec-2026-07-09.md:257`), so not a bug, but whether `atc14017` paginates on `pageNo>0` is **unproven** — `get_ticket_list(page_no=N>0)` could silently return page 0. **Recommend live capture before relying on ticket-list pagination.**
- **`netfunnel-transport-safety` — allowlist entries** `/main/noticeList.do` (`safety.py:68`, POSTed `client.py:106`) and `/common/ARA/ARA0502P/view.do` (`safety.py:77`, POSTed `client.py:156`) appear nowhere in `apktool`+`jadx`; both are server-rendered so absence is not proof of wrongness. `ARA0502P` was derived "by analogy" with no static/live evidence; the `noticeList` fixture is documented synthetic (`impl-audit-reverify3-2026-07-22.md:87-89`). **Highest-risk unverified surface — recommend live capture to confirm or retire both.**

### Caller-default deltas — caller-responsibility, not wire bugs

- **`search-selectors` / `seat-timetable-fare` — `get_seat_page` `choiceSeatCount` defaults to `'1'`** while the app uses `lfn_getRsv("totPrnb")` (`ara1001l.js:1511`): a caller-overridable param; the read-only client only views availability.
- **`seat-timetable-fare` — `get_fare` defaults to all-adult `PassengerCounts`** while the app uses the search-time `psgInfoPerPrnb`: caller-overridable; read-only client only views fare.
- **`search-selectors` — `get_date_selector` exposes only the outbound `reqCode=3` path**, not the return-leg `reqCode=4` (same `ARA0401P` route, `selectDay="2"`): a missing feature for a one-way read-only client, not a wrong param/route.

### Harmless / equivalent

- **`auth-session` — `X-Requested-With: XMLHttpRequest`** on the login POST (`http.py:188`) despite the bundled form being `data-ajax='false'`: harmless — the endpoint returns JSON regardless and `srtgo` sends no `X-Requested-With` at all on the main session.
- **`netfunnel-transport-safety` — the only notice-like app link** is a GET HTML `/cms/article/list.do?pageId=KR0502000000` (`main.html:732`) for "SR news", a different feature from `noticeList.do`.

---

*This pass independently reproduces the conclusions of `docs/analysis/impl-audit-reverify{,2,3}-2026-07-22.md` for the `auth-session`, `notice-ticket`, and `netfunnel-transport-safety` groups (no new provable bug there), and adds one HIGH (`seatAttCd` provenance) plus two LOWs (IP-block classification, group `psgNum` clamp) and one caveated LOW (`msgCd` over-strictness) surfaced by re-auditing the `search-selectors` and `seat-timetable-fare` builders against the bundled `ara0101v.js`/`ara1001l.js`.*
