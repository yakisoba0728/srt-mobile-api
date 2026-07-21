# SRT Client Implementation Audit — Re-verify — 2026-07-22

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Subject:** `srt-mobile-api` read-only client vs. the decompiled ground truth
**Author:** FABLE
**Date:** 2026-07-22

## Overview

This is a re-verification pass over where our read-only SRT client diverges from
the decompiled v2.0.41 app ("ground truth"). Ground truth is, in priority order:
the bundled offline JS/HTML under `analysis/apktool/assets/offline/`, the
jadx/smali native decompile, and — where the app source is server-rendered or
absent from the bundle — the battle-tested `srtgo` reference and prior settled
cross-validation docs. Live-API captures override decompile-usage arguments where
they exist.

Every candidate finding was adversarially verified against those sources. **Only
findings that survived verification are listed as bugs.** Findings that were
rejected (unconfirmable or provably non-defects) are documented, with reasons, in
the *Rejected / non-bugs* section and are **not** counted as real defects.

Headline results this pass:

- **No auth-session divergences** remain provable; the two prior fixes
  (User-Agent space, `S111`) are verified correct.
- **No notice-ticket divergences**; route, params, headers, safety and error
  handling all match ground truth.
- **No netfunnel-transport-safety divergences**; `js=yes` matches the app, the
  `act_19` phantom is gone, only `act_10` / opcode `5101` remain.
- The four surviving bugs are all **passenger-composition / response-classification**
  issues in the search and fare/mutual builders — one Medium, three Low. None is
  High. All are provable wire- or logic-divergences from the decompile.

### Totals

| Severity | Count |
| --- | --- |
| High | 0 |
| Medium | 1 |
| Low | 3 |
| **Total verified bugs** | **4** |

Rejected findings: 1 (station-map selector — unconfirmable; see below). Groups
audited: auth-session, search-selectors, seat-timetable-fare, notice-ticket,
netfunnel-transport-safety.

All `src/…`, `analysis/…`, `safety.py`, `payloads.py`, `parsers.py` paths are
relative to the `srt-mobile-api` repo root (where this doc lives). Cross-repo
citations to `srtgo/…` are the external reference client.

## Prioritized bug table (High → Low)

| # | Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | **Medium** | search / passenger-fields (non-compacted `psgTpCd` slots) | `src/srt_mobile_api/payloads.py:109-121` (also `PASSENGER_SLOTS` `:11-18`; consumed by `search_page_payload:180` and `search_ajax_payload:221`) | `analysis/apktool/assets/offline/js/ara/ara0101v.js:824-836` (compaction) + `:117-127` (5 slots, default `psgTpCd1="1"`) + `analysis/apktool/assets/offline/js/commCode.js:55-88` (`psgTpCd` 1..5 only) | The app always POSTs a **compacted** `psgTpCd` list: the passenger popup callback moves only the non-zero types into contiguous slots `psgTpCd1..N` (idx increments, zeros skipped) and sets `psgGridcnt=idx-1`, over exactly 5 type slots. Our `_passenger_fields` instead writes **fixed positional** slots keyed by our own `PASSENGER_SLOTS` order (adult, child, senior, dis1-3, dis4-6), leaving empty holes for any composition that is not a prefix of that order. Example: `PassengerCounts(adult=1, senior=1)` → we send `psgTpCd1="1", psgTpCd2="", psgTpCd3="4"` with `psgGridcnt=2`, whereas the app sends `psgTpCd1="1", psgTpCd2="4"` with `psgGridcnt=2`. adult+senior (and any disability-only / senior-only / child-only) are common combinations that gap: `psgGridcnt` claims N types while the `psgTpCd` entries sit at non-contiguous indices, mis-stating passenger composition. Impact is bounded for read-only search (srtgo's `search_train` omits `psgTpCd`/`psgGridcnt` entirely and keys on `psgNum`, so trains still return), but the emitted payload diverges from what the real app sends and would be wrong for any `psgTpCd`-consuming path. | Compact the non-zero passenger types into contiguous `psgTpCd1..N` / `psgInfoPerPrnb1..N` slots (zeros removed) in `psgTpCd` type-code order, matching `ara0101v.js:824-836` and srtgo `get_passenger_dict`, so `psgGridcnt` aligns with the filled slots. |
| B2 | Low | search / passenger-fields (fabricated `psgTpCd6` + `infantCnt`) | `src/srt_mobile_api/payloads.py:11-18` (`PASSENGER_SLOTS` infant slot) + `:120` (`infantCnt`) | `analysis/apktool/assets/offline/js/commCode.js:55-88` (no `psgTpCd "6"`) + `analysis/apktool/assets/offline/js/ara/ara0101v.js:117-127` (only `psgTpCd1..5`; no `infantCnt` anywhere in app) | `_passenger_fields` emits `psgTpCd6` / `psgInfoPerPrnb6` (with the value `"6"`) for `infant>0`, plus an unconditional `infantCnt` field. Neither exists in the SRT protocol: `commCode.js` lists `psgTpCd` values only 1..5 (`"6"` is not a valid passenger-type code), the app form has only `psgTpCd1..5`, and the string `infantCnt` appears nowhere in the entire decompile (apktool + jadx) nor in srtgo. SRT has no infant passenger type in the 6-selector picker. For `infant=0` the extras are empty (`psgTpCd6=""`, `psgInfoPerPrnb6="0"`, `infantCnt="0"`); for `infant>0` the client sends an invalid `psgTpCd` value `"6"`. | Drop the infant slot (`psgTpCd6`/`psgInfoPerPrnb6`) and the `infantCnt` field from the search payload builders; cap passenger slots at 5. Remove the infant field from the model or exclude it from SRT search payloads. |
| B3 | Low | fare payload passenger mapping (non-compacted `passenger1..5`) | `src/srt_mobile_api/payloads.py:358` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1219` (with compaction at `analysis/apktool/assets/offline/js/ara/ara0101v.js:824-836`) | The app's fare request (Ara13010) sends `passenger1..5 = lfn_getRsv("psgInfoPerPrnb1..5")`, which are the **compacted** `gds_rsv` slots: the picker packs only non-zero types into contiguous slots 1..N in canonical `psgTpCd` order (adult, 장애1~3, 장애4~6, 경로, 어린이), leaving trailing slots empty. Our `fare_payload` instead writes each type into a **fixed canonical slot** (`passenger1`=adult, `passenger2`=dis_1_to_3, `passenger3`=dis_4_to_6, `passenger4`=senior, `passenger5`=child) with zeros in the gaps. For any query where an earlier canonical type is absent but a later one is present (e.g. the very common 1 adult + 1 child family case) the wire bytes differ: app sends `passenger1=1, passenger2=1, passenger3=0, passenger4=0, passenger5=0`; we send `passenger1=1, passenger2=0, passenger3=0, passenger4=0, passenger5=1`. All-adult (default) and any gap-free set are identical, so most calls are unaffected. Functional impact is likely nil because the fare request carries **no** `psgTpCd`, so the server cannot key on fixed positions (the app compacting and still being correct proves position is not a fixed-type key), and our HTML fare-table parser does not depend on positions. Reported as a provable ground-truth wire divergence. | Build fare `passenger1..5` by compacting non-zero counts into contiguous slots in canonical `psgTpCd` order (adult, disability_1_to_3, disability_4_to_6, senior, child), padding the remaining slots with `0` — mirroring the app's `psgInfoPerPrnb` compaction and srtgo's `Passenger.combine()`+`enumerate` (`srtgo/srt.py:188-202`). Note this compaction also affects the search payload (B1). |
| B4 | Low | mutual-verification response classification (over-strict `msgCd` gate) | `src/srt_mobile_api/parsers.py:431` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:234` | The decompiled app treats the Ara10130 response as success whenever `dsOutput0.strResult != "FAIL"` and simply reads `dsOutput0.mutMrkVrfCd` (`ara1001l.js:234-241`); it never inspects `msgCd`. Our parser is strictly narrower: it raises `SrtAppError` unless `code == "IRZ000008"` **AND** `status == "SUCC"`. If the live server ever returns a success (`strResult SUCC` + a populated `mutMrkVrfCd`) under any `msgCd` other than the literal `"IRZ000008"`, our client mis-classifies that success as an app error, whereas the app would accept it. The success fixture uses `IRZ000008` so tests pass, and the live divergence is not proven, but the classification logic is provably stricter than ground truth. | Match the app's condition: treat `status != "FAIL"` (with a non-empty `mutMrkVrfCd`) as success rather than gating on the exact `msgCd "IRZ000008"`; at most keep the `msgCd` as informational. |

### Cross-cutting note on the passenger builders (B1 + B2 + B3)

B1, B2 and B3 share a common root: our passenger-field builders use a **fixed,
non-compacted slot layout** keyed by our own `PASSENGER_SLOTS` order, whereas the
app and srtgo compact occupied types contiguously in canonical `psgTpCd` order
(adult, 장애1~3, 장애4~6, 경로, 어린이) with **no infant / type-6 slot**. Fixing
compaction in `_passenger_fields` (B1) and removing the `psgTpCd6`/`psgInfoPerPrnb6`
/`infantCnt` fabrication (B2) resolves both search bugs together; applying the
same compaction to `fare_payload`'s `passenger1..5` (B3) resolves the fare case.
The passenger **selector** request (`passenger1..5`, `ARA0901P`) is correct and
unaffected — only the **search** `psgTpCd` builders and the **fare** `passengerN`
builder carry the gap/fabrication issue.

## Verified correct / intentionally not filed

Items below were checked against ground truth and are **not** divergence bugs.
They are recorded so the audit trail is complete.

**Auth-session** (0 bugs)
- The two previously-known auth-session issues are resolved/correct: the
  User-Agent space is **fixed**, and `S111` is correct.
- Envelope **values** differ from srtgo — we send `check=''`/`auto=''`/`page=''`/
  `login_referer=''` and `deviceKey='0123456789ABCDEF'` (`session.py:47-56`) vs
  srtgo's `check='Y'`/`auto='Y'`/`page='menu'`/`login_referer=<main url>`/
  `deviceKey='-'` (`srtgo/srt.py:700-710`). The bundled login form ships these
  fields with empty defaults (`main.html:722-727`), the server is lenient
  (`cross-validation-2026-07-21.md:294,296`), and both value-sets authenticate.
  These flags are client-side (auto-login / redirect / validation); no evidence
  empty values break auth → **not a provable wrong-value bug**.
- We additionally send `ciUptYn=''` and `dupInfoVal=''` (`session.py:56-57`),
  which srtgo omits but which belong to the server-rendered `login.do` form
  (`spec-2026-07-09.md:142-143`) — harmless / more faithful, empty.
- `deviceKey` stub differs from the real `ANDROID_ID` / OnePass `GetDeviceID`
  source (`SRWebActivity.smali:4007/13316`) but is user-overridable and
  server-unvalidated for login.
- Logout (`client.py:81-82`) only clears local cookies and does **not** POST
  `/login/loginOut.do` (form at `main.html:455`; srtgo `srt.py:733-753` POSTs it)
  — deliberate read-only design, not a wire divergence.
- `X-Requested-With: XMLHttpRequest` on the login POST (`http.py:188`) is additive
  vs srtgo; the endpoint returns JSON regardless → harmless.
- **Ground-truth caveat:** the login/response envelope (`RTNCD`, `MSG`, and the
  value-population JS for `check`/`auto`/`page`) is server-rendered on `login.do`
  and **not** in the offline APK bundle, so those specific values are unverifiable
  from the decompile — they rest on prior runtime-capture analysis. A live smoke
  test to confirm empty `check`/`auto`/`page` still authenticate is recommended
  before treating them as fully settled.

**Search-selectors** (2 bugs filed: B1, B2)
- Date-picker route: **no bug**. The decompile uses `ARA0401P`
  (`ara0101v.js:203`) and our client already posts `ARA0401P` (`client.py:164`)
  and sends **no** `selectTime` (SRT picker is date-only). Neither `ARA0403P` nor
  `ARA0502P` appears anywhere in the decompiled app (apktool + jadx).
- Passenger **selector** request (`passenger1..5`) is correct and unaffected.
- Selector methods only fetch popup HTML (`parse_html_page` text extraction), so
  there is **no selector response-parsing surface** to diverge — only request
  URL+payload matter, all six audited.

**Seat-timetable-fare** (2 bugs filed: B3, B4)
- No divergence on the core FOCUS items: `arc02012` (not `arc02011`) is correct,
  the seat page is HTML-handled correctly, and the seat/timetable/fare/mutual
  routes, methods and field sets all match the decompiled app.
- Our source uses the **correct** `commCode` `psgTpCd` mapping (2=장애1~3, 3=장애4~6,
  4=경로, 5=어린이).

**Notice-ticket** (0 bugs)
- Notice list route/param/headers (`client.py:105-108`, `http.py:184-192`): POST
  `/main/noticeList.do` `{pageId: MB0101000000}` with JSON `Accept` +
  urlencoded `Content-Type` + `Origin` + `X-Requested-With` matches the runtime
  capture (spec:256) exactly — no missing/extra fields.
- Safety classification (`safety.py:68-69`), session-expiry handling
  (`client.py:123` + `parsers.py:166-167` login-form detection), and notice
  error-envelope tolerance (`parsers.py:189-196`) all confirmed against ground
  truth.
- There is **no bundled `atc` JS parse contract**: `ticketList.html` inline
  scripts parse the **offline localStorage** cache (`loadPrfs`/`offTicketList` →
  `atob` → `JSON.parse obj['list']`), not the server HTML our client GETs.
  `get_ticket_list` returns raw HTML + extracted text with no structured parse,
  so no mis-parse divergence is possible.

**Netfunnel-transport-safety** (0 bugs)
- The single most important correctness point: our code uses `js=yes` (matching
  `netfunnel.js:84`) rather than srtgo's `js=true`, and the `act_19` phantom is
  fully gone (only `act_10` / opcode `5101` remain).
- The request bytes we send for the `5101` `getTidchkEnter` start are exactly
  correct.

## Rejected / non-bugs

The following candidates were considered and **rejected** — either unconfirmable
from ground truth (so not a *provable* divergence) or provably not a defect. None
is counted as a real bug.

- **Station-map selector endpoint + params (REJECTED — unconfirmable).**
  `station_map_selector_payload` (`client.py:153-159` + `payloads.py:45-51`) posts
  only `{reqCode:"2", sNowSel:"1"}` to `/common/ARA/ARA0502P/view.do`. But
  `ARA0502P` appears **nowhere** in apktool + jadx (grep confirmed), and
  `ara0101v.js:743-757` (`POP_REQ_STN_MAP=2`) is a **result-handler** callback that
  consumes `obj.startStnCd/startStnNm/arrivalStnCd/arrivalStnNm` and writes
  `dptRsStnCd1`/`arvRsStnCd1` into the reservation object — it does **not** reveal
  what the map-open **request** posts. With no ground-truth request shape,
  `{reqCode:"2", sNowSel:"1"}` cannot be shown wrong, nor can `ARA0502P` be shown
  to be the wrong URL. This is a legitimate *capture-to-confirm* flag, but under
  adversarial skepticism it is not a confirmed bug. Recommendation: capture the
  live `ARA0502P` request; if kept, mirror `ARA0501P`'s context fields
  (`sDptStnNm`/`sArvStnNm`/`sDptStnCd`/`sArvStnCd`) or explicitly document the
  endpoint as unverified.
- **`atc14017` vs `atc14016` ticket route (`client.py:122`) — NOT a bug.** GET
  `/atc/selectListAtc14017_n.do?pageNo=0` is a runtime-verified success (spec:257)
  and matches the natively-wired landing route (`SRWebActivity.java:1592`, btnNo
  `'2'`, GET, no query). `atc14016` (`ticketList.html:405` offline data-url,
  `SRForegroundDialogActivity.java:31` native notification, srtgo `srt.py:95`) is
  the alternate variant tracked as deferred gap R3; not emitting it is
  intentional. Already adjudicated/rejected in `impl-audit-2026-07-22.md:139-166`.
  Live ground truth beats the decompile-usage argument.
- **`POST_NO` strict-int check (`parsers.py:218`, `type(row.get('POST_NO')) is not int`) — NOT provable.**
  Notice field names (`IS_MAIN`/`PAGE_ID`/`BODY`/`POST_NO`/`CREATE_DATE`/
  `IS_NOTICE`/`SUBJ`) have 0 hits across jadx + apktool (only unrelated
  `POST_NOTIFICATIONS`). The only fixture is synthetic (`notice_list.json`,
  `PAGE_ID='SYNTHETIC_PAGE'`, `POST_NO:42` int), and `test_raw_backed_parsers.py:187`
  hard-codes that `POST_NO='42'` (string) must be rejected. A genuine
  verification gap that would reject real rows if a real capture ever showed
  `POST_NO` as a string, but unprovable without ground truth → excluded per
  "only report provable divergences".
- **`group_search` `psgNum` forced to `max(total,10)` (`payloads.py:234`) — not filed.**
  The app does not force this — it requires the user to enter ≥10
  (`ara0101v.js:553,563` alert "단체예약은 10매 이상") and sends the actual
  `totPrnb`. Forcing `psgNum=10` for a <10 group query makes `psgNum` inconsistent
  with `totPrnb` / `psgInfoPerPrnb` sum, but that is an app-blocked state → low
  practical risk, not filed.
- **Unverified extras (flagged for capture, not proven wrong).**
  `search_ajax_payload` sends `disability="N"` (`payloads.py:217`) and
  `adjStnScdlOfrFlg="N"` (`payloads.py:218`, also `search_page_payload:176`);
  neither string appears in the decompile or srtgo. Likely benign hidden-form
  echoes, but their canonical values are unconfirmed.
- **Netfunnel queue-wait (code 201) not handled — scope/robustness gap, not a wire divergence.**
  `netfunnel.py` implements only opcode `5101` (`getTidchkEnter`); it never issues
  `chkEnter` (`5002`) or `setComplete` (`5004`). `parse_netfunnel_response`
  accepts codes `200`/`502` and raises on `201` (`kContinue`). srtgo
  (`srt.py:542-568`) loops `5002` while `status==201` then calls `5004`. For a
  no-queue read-only search this is fine (`5101` returns `200` immediately with a
  valid key), and the request bytes are exactly correct; during a **live queue**
  the client would hard-fail. The client partially compensates via its
  `NET000001` retry that re-fetches a fresh `5101` key (`client.py:271-278`). Not
  a wrong param/route/parse → not filed.
- **Seat-page `reqCode` pinned to `'9'` — consistent for this client's scope.**
  `const.js:9-11`: `POP_REQ_SEATSELECT_DPT_ONEWAY=9` (one-way), `GO_BACK=10` /
  `GO_BACK_DONE=11` (round-trip). The whole client is one-way only
  (`search_page_payload` sets `rtnDv=0`/`grpDv=0`), so `9` is the only reachable
  value. If round-trip is ever added, `safety.py`'s
  `SEAT_PAGE_FIXED_VALUES['reqCode']` would need to allow `10`/`11`.
- **Synthetic default UA lacks Android WebView tokens — cosmetic, unprovable.**
  Our synthetic default UA lacks the `; wv` / `Build/...` platform tokens that a
  real device WebView (and srtgo's UA) include; the server is not shown to
  validate these, and the app uses whatever the device WebView provides.

## Documentation discrepancies (for the caller — not code bugs)

These are inaccuracies in the **prose analysis docs**, not in our source. The
code is correct in each case; the docs are stale/wrong and should be updated.

- `docs/analysis/full-api-analysis-2026-07-20.md:378` states `psgTpCd`
  "`2=어린이, 3=경로, 4=중증장애, 5=경증장애`", which is **wrong** per the decompiled
  `commCode.js` (`2=장애1~3, 3=장애4~6, 4=경로, 5=어린이`). Our source uses the correct
  mapping.
- `docs/analysis/full-api-analysis-2026-07-20.md:532,555` and
  `RELEASE_GAP_PLAN.md:513-520` still claim the client posts `ARA0403P` with a
  `selectTime` field. That documentation is **stale**: the code was corrected to
  `ARA0401P` (`client.py:164`) and sends no `selectTime` (SRT picker is
  date-only). Recommend updating those docs.

## Ground-truth sources used

- `analysis/apktool/assets/offline/js/ara/ara0101v.js` — selectors, passenger
  picker + compaction (`:824-836`), popup callbacks.
- `analysis/apktool/assets/offline/js/ara/ara1001l.js` — seat/timetable/fare/
  mutual builders (`:234` mutual, `:1219` fare passengers).
- `analysis/apktool/assets/offline/js/commCode.js` — `psgTpCd`/`trnGpCd` tables
  (`:55-88`, `psgTpCd` 1..5 only).
- `analysis/apktool/assets/offline/js/common/const.js` — `POP_REQ_*` reqCode
  constants (1..9).
- `analysis/apktool/assets/offline/js/common/netfunnel.js` — `NetFunnel.RetVal`
  parser and `js=yes` build (`:84`).
- Cross-checked against `srtgo/srt.py` and prior settled docs
  (`impl-audit-2026-07-22.md`, `cross-validation-2026-07-21.md`,
  `srt-app-api-library-spec-2026-07-09.md`). Fixtures for fare/timetable/seat/
  mutual are synthetic, so they cannot independently confirm live server behavior;
  the seat page uses a real captured evidence fixture
  (`tests/fixtures/seat_page_schema_v2_evidence.json`).
