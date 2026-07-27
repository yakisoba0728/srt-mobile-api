# SRT Client Implementation Audit — 2026-07-22

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Subject:** `srt-mobile-api` read-only client vs. the decompiled ground truth
**Author:** FABLE
**Date:** 2026-07-22

## Overview

This report audits where our read-only SRT client diverges from the decompiled
v2.0.41 app ("ground truth"). Ground truth is, in priority order: the bundled
offline JS/HTML under `analysis/apktool/assets/offline/`, the jadx/smali native
decompile, and — where the app source is server-rendered or absent from the
bundle — the battle-tested `srtgo` reference and prior settled cross-validation
docs. Live-API captures (spec §6) override decompile-usage arguments where they
exist.

Every finding below was adversarially verified against those sources. Only
findings that **survived verification** are listed as bugs; the one rejected
finding is documented (with the reason) in the *Rejected / non-bugs* section and
is **not** counted as a real defect.

### Totals

| Severity | Count |
| --- | --- |
| High | 3 |
| Medium | 5 |
| Low | 5 |
| **Total verified bugs** | **13** |

Rejected findings: 1 (see below). Groups audited: auth-session, search-selectors,
seat-timetable-fare, notice-ticket, netfunnel-transport-safety.

All `src/…`, `analysis/…`, `safety.py`, `payloads.py` etc. paths are relative to
the `srt-mobile-api` repo root (where this doc lives). Cross-repo citations to
`srtgo/…` are the external reference client.

## Prioritized bug table (High → Low)

| # | Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | **High** | Date selector route + safety allowlist (ARA0403P vs ARA0401P) | `src/srt_mobile_api/client.py:162` (also `safety.py:72`) | `analysis/apktool/assets/offline/js/ara/ara0101v.js:203` | The date-picker popup is posted to `/common/ARA/ARA0403P/view.do`, but the app posts the departure-date picker (`POP_REQ_DPT_DT=3`) to `/common/ARA/ARA0401P/view.do`. `ARA0403P` appears NOWHERE in the decompile (only `ARA0401P` and `ARA0501P` are referenced). This is both a wrong route and a mis-classified safety route: `safety.py`'s `READ_ONLY_ROUTES` allowlist permits `ARA0403P` but omits the real `ARA0401P`, so the safety layer actively REJECTS the correct route (`tests/test_safety.py:137` asserts POST `ARA0401P` raises `SrtProtocolError` as a "legacy neighbor"). A client-only fix would be blocked by the safety layer. | Change the date-selector path to `/common/ARA/ARA0401P/view.do` in `client.py:162` AND replace the `ARA0403P` entry in `safety.py:72` with `ARA0401P` (update `tests/test_safety.py:67` vs `:137` accordingly). |
| B2 | **High** | NetFunnel parser — success detection (`SUCCESS_PAIRS`) | `src/srt_mobile_api/netfunnel.py:15` (checked at `netfunnel.py:53`) | `analysis/apktool/assets/offline/js/common/netfunnel.js:84` | `parse_netfunnel_response` treats the second colon field as the success "code" and requires `(raw_type,code)==('5101','5101')`. But the app's own parser `NetFunnel.RetVal(a)` does `_mRtype=parseInt(a.substr(0,4))` and `_mCode=parseInt(a.substr(5,3))` — the code is EXACTLY 3 digits at a fixed offset, so the second field can never be `'5101'` (4 digits). The real success value for a 5101 start is `5101:200:key=…` (`kSuccess=200`; `kContinue=201`=keep-polling; `kTsErrorAComplete=502`=also success); `srtgo` confirms `WAIT_STATUS_PASS='200'`. Our parser reads `code='200'` and raises `SrtNetFunnelError('did not report success')`, so the client can NEVER obtain a NetFunnel key and every search breaks. `tests/test_netfunnel_payloads_parsers.py:116` even asserts the real `5101:200:key=…` is REJECTED; passing tests only work because fixtures use an impossible `5101:5101:…` shape. | Base success on the 3-digit status field, not `rtype==code`: accept status in `{'200','502'}` for the 5101 response. Fix the assertions (`5101:200:key=…` must be a SUCCESS, not a rejection). |
| B3 | **High** | NetFunnel parser — result-assignment regex (`RESULT_ASSIGNMENT_RE`) | `src/srt_mobile_api/netfunnel.py:9` (regex `netfunnel.py:7-13`) | `analysis/apktool/assets/offline/js/common/netfunnel.js:84` | `RESULT_ASSIGNMENT_RE` uses `re.fullmatch` and only optionally consumes a leading `NetFunnel.gRtype=4999;` before `NetFunnel.gControl.result=`. But `4999` appears nowhere in the app (only in crypto constant tables). The real response leads with the ECHOED prefix `NetFunnel.gRtype=<opcode>;`: `gRtype` is never assigned in app code, yet `_showResult` reads it, so it can only be set by the response prefix. Our client sends `prefix=NetFunnel.gRtype=5101;`, so the real response begins `NetFunnel.gRtype=5101;NetFunnel.gControl.result=…`. Our `fullmatch` accepts only `=4999;`, so it raises "did not include a result token" on every real response. `srtgo` avoids this with `re.search` (tolerates any leading statements). | Locate the result assignment with a non-anchored search (like `srtgo`'s `re.search(r"NetFunnel\.gControl\.result='([^']+)'")`), or make the optional leading statement accept `NetFunnel.gRtype=<digits>;` generically instead of hardcoding `4999`. |
| B4 | Medium | Passenger selector payload (ARA0901P) type ordering | `src/srt_mobile_api/payloads.py:76-81` | `analysis/apktool/assets/offline/js/ara/ara0101v.js:234-238` | `passenger_selector_payload` maps `passenger2..passenger5` to the wrong categories and adds a `passenger6` the app never sends. In the app, `passengerN` is indexed by passenger type CODE N: `passenger1`=adult(1), `passenger2`=disability_1_to_3(2), `passenger3`=disability_4_to_6(3), `passenger4`=senior(4), `passenger5`=child(5); there is no `passenger6`. Confirmed request-side (`ara0101v.js:213-238`) and callback-side (`ara0101v.js:795-804`, `passenger1..5` pair with `psgTpCd '1'..'5'`). Our builder sends `passenger2`=child, `passenger3`=senior, `passenger4`=disability_1_to_3, `passenger5`=disability_4_to_6, `passenger6`=infant, so the picker is pre-filled with counts in the wrong categories. (The unit test masks this by using ordinal values 1..6 that coincide with slot numbers.) | Emit `passenger1`=adult, `passenger2`=disability_1_to_3, `passenger3`=disability_4_to_6, `passenger4`=senior, `passenger5`=child; drop `passenger6` (infant is not a picker slot). |
| B5 | Medium | Fare payload (`get_fare` → Ara13010) passenger field names | `src/srt_mobile_api/payloads.py:336` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1219` | `fare_payload` sends the wrong passenger field NAMES. The app's fare request (Ara13010) carries passenger counts under `passenger1`..`passenger5` (5 slots, no infant): `passenger1: lfn_getRsv('psgInfoPerPrnb1') … passenger5: lfn_getRsv('psgInfoPerPrnb5')`. Our `fare_payload` instead calls `_passenger_fields(passengers)`, which appends `psgTpCd1..6`, `psgInfoPerPrnb1..6` and `infantCnt` and NEVER emits `passenger1..5`. So the server never receives the counts it looks for on this endpoint, and the `passengers` arg to `get_fare` is effectively a no-op server-side (fare likely computed for 1 adult). The buggy shape is asserted by tests (`test_netfunnel_payloads_parsers.py:616-617`; `test_client_read_apis.py:1027`). | Replace `payload.update(_passenger_fields(passengers))` with explicit `passenger1..passenger5` keys mapped to `[adult, child, senior, disability_1_to_3, disability_4_to_6]` counts (str). Do NOT send `psgTpCd*`/`psgInfoPerPrnb*`/`infantCnt` to Ara13010. Update tests. |
| B6 | Medium | Timetable + fare payload `trnSort` (Ara12009 / Ara13010) | `src/srt_mobile_api/payloads.py:300` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1184` | `trnSort` is built by `_train_sort()`, which returns literal `'SRT'` when `service_class_code=='17'` (else raw `stlbTrnClsfCd`). For SRT trains — the primary case — timetable and fare therefore send `trnSort=SRT`. The app sends `trnSort: item.trnClsfCd` — the server-provided train-class CODE from the search row (열차종별코드), DISTINCT from `stlbTrnClsfCd` (역무열차종별코드, what our parser maps to `service_class_code`). Our parser does not even extract `trnClsfCd`, so our value cannot match, and `'SRT'` is a client-side name the app never sends where a code is expected. Affects timetable (`ara1001l.js:1184`) and fare (`ara1001l.js:1217`); the wrong value is enshrined at `test_netfunnel_payloads_parsers.py:612`. | Send `trnSort = item.trnClsfCd` (the row's 열차종별코드). First extend `TrainSummary`/`parse_train_search_response` to capture `trnClsfCd` from the `dsOutput1` row (currently unparsed), then use it in both payloads and update the `trnSort=='SRT'` assertion. |
| B7 | Medium | NetFunnel request `js` value (act_10) | `src/srt_mobile_api/netfunnel.py:22` (also `safety.py:164`) | `analysis/apktool/assets/offline/js/common/netfunnel.js:84` | The act_10 NetFunnel request sends `js=true`, but the app sends `js=yes`. In `netfunnel.js` the `getTidchkEnter` build appends `c+="&js=yes"`, and `chkEnter`/`setComplete` likewise append `&js=yes`. Our `build_act10_url` hardcodes `&js=true` and the safety contract requires `js=='true'` (`safety.py:164`), so both the emitted value and the guard diverge. (`srtgo` also uses `js=true` and works, so the server likely tolerates any non-empty `js`; hence medium — but a definite divergence from the app.) | Change `js=true` → `js=yes` in `build_act10_url` (`netfunnel.py:22`) AND in the safety required-params dict (`safety.py:164`) together; they are coupled (changing only one makes the guard reject the request). |
| B8 | Medium | Safety field contract — `psrmClCd` hardcoded (seat page) | `src/srt_mobile_api/safety.py:40` (also `payloads.seat_page_payload:286`) | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1507` (also `:1278`, `:1432`) | The seat-page contract fixes `psrmClCd='1'` in `SEAT_PAGE_FIXED_VALUES`, but the app sends it dynamically: the arc02012 params use `psrmClCd: lfn_getRsv("psrmClCd1")`, and the code sets `sPsrmClCd = 2` for 특실/first-class. `psrmClCd` is the cabin-class code (1=일반실 standard, 2=특실 first-class). Hardcoding `'1'` means a first-class seat-map request returns the STANDARD cabin's map (wrong data), and the safety guard actively REJECTS a legitimate `psrmClCd='2'` request. | Derive `psrmClCd` from the requested cabin class (1 or 2) rather than fixing `'1'`; remove `psrmClCd` from `SEAT_PAGE_FIXED_VALUES` and validate it as a member of `{'1','2'}` instead. |
| B9 | Low | Login `srchDvCd` (login_type) default + no auto-detection | `src/srt_mobile_api/session.py:14` | `srtgo/srtgo/srt.py:691-698` | `SrtSessionClient.login()` hard-defaults `login_type` (`srchDvCd`) to `"3"` (phone) and does no auto-detection from the identifier. SRT's primary credential is the membership number, which requires `srchDvCd="1"`; email login requires `"2"`. A caller passing a membership number or email who relies on the default transmits `srchDvCd="3"` paired with a non-phone `srchDvNm`, so the server resolves it as a phone lookup and login fails/misbehaves. Also, for genuine phone logins the id is sent verbatim (no dash stripping) whereas the reference normalizes it. NOTE: `login.do` tab/type selection is server-rendered and NOT in the offline bundle (grep for `srchDvCd` returns only comments), so this is not provable from the decompile; truth basis is the `srtgo` mapping. Low because `login_type` is a caller-overridable parameter. | Auto-detect `login_type` from `login_id` like `srtgo` (email regex → `"2"`, phone regex → `"3"`, else membership → `"1"`), or at minimum default to `"1"` (membership) and document the mapping; when `srchDvCd=="3"` strip dashes from `srchDvNm` (`re.sub('-','',id)`) as `srtgo` does at `srt.py:697-698`. |
| B10 | Low | Date selector payload extra field (`selectTime`) | `src/srt_mobile_api/payloads.py:68` | `analysis/apktool/assets/offline/js/ara/ara0101v.js:187-191` | `date_selector_payload` includes `selectTime=hour`, but the app's date-picker request contains only `reqCode`, `selectDay` and `selectDt` (the SRT date picker returns a date only, `obj.choiceDate`; there is no time field). The extra `selectTime` param is never sent by the app. | Drop `selectTime` (and the `hour` parameter) from `date_selector_payload`/`get_date_selector`, or leave as a documented harmless extra. |
| B11 | Low | Station / station-map selector payload extra fields | `src/srt_mobile_api/payloads.py:37-40` | `analysis/apktool/assets/offline/js/ara/ara0101v.js:158-165` | `station_selector_payload` and `station_map_selector_payload` send `chk_rtrp='false'`, `page='ARA0101'` and `boolRtrp='false'`, none of which appear in the app's station-picker call-site. The app posts only `reqCode`, `sDptStnNm`, `sArvStnNm`, `sDptStnCd`, `sArvStnCd`, `sNowSel`. | Remove `chk_rtrp`, `page` and `boolRtrp` from `station_selector_payload` (and the analogous keys in `station_map_selector_payload`) to match the app's exact param set. |
| B12 | Low | Search hydration `psgGridcnt` semantics | `src/srt_mobile_api/payloads.py:158` | `analysis/apktool/assets/offline/js/ara/ara0101v.js:836` | `search_page_payload` sets `psgGridcnt = str(passengers.total)` (head count), but `psgGridcnt` means the number of distinct passenger TYPES with count>0. Both ground truths agree: the app sets `psgGridcnt=idx-1` (occupied type count) and `srtgo` sets `psgGridcnt=len(combined_passengers)`. For default single-adult `total==types==1` so it coincides, but for multi-passenger (e.g. 2 adults) our hydration GET sends `psgGridcnt=2` instead of `1`. Impact is limited (only the GET hydration request; the actual search POST reuses the server-rendered value, results key on `psgNum`) but the value is provably wrong. Related: `_passenger_fields` uses fixed non-compacted slots and adds `psgTpCd6`/`infantCnt`, whereas app+`srtgo` compact occupied types contiguously with no infant/type-6 (matters for reserve, out of scope here). | Set `psgGridcnt` to the count of passenger types with count>0 (mirror `srtgo/srt.py:191` / `ara0101v.js:826-836`). |
| B13 | Low | Safety field contract — `choiceSeatCount` hardcoded (seat page) | `src/srt_mobile_api/safety.py:41` (also `payloads.seat_page_payload:296`) | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1511` | The seat-page contract fixes `choiceSeatCount='1'` in `SEAT_PAGE_FIXED_VALUES`, but the app sends `choiceSeatCount: lfn_getRsv("totPrnb")` — the total passenger count. For a 2+ passenger seat request the app sends the actual count; our client always sends `'1'` and the safety guard rejects any other value. | Set `choiceSeatCount` to the total passenger count (`totPrnb`) instead of a fixed `'1'`, and validate it as digits rather than pinning it to `'1'`. |

### Cross-cutting note on the NetFunnel parser (B2 + B3)

B2 and B3 are **independent** — each alone prevents parsing a real successful
`5101` start response, so the read-only client cannot obtain a NetFunnel key and
**all search calls fail live**. The repo has no real captured NetFunnel response;
both fixtures (`netfunnel_act10.js`, `netfunnel_act10_5002.js`) are synthetic and
encode an incorrect shape (`5101:key=…` with no 3-digit status, plus a bogus
leading `NetFunnel.gRtype=4999;`), which is exactly why the current unit tests
pass while the client would fail against the real server. Wire format from the
app's own `NetFunnel.RetVal` is `RRRR:CCC:params` (4-digit rtype, 3-digit code at
offset 5, params from offset 9); codes: `kSuccess=200`, `kContinue=201`,
`kTsBypass=300`, `kTsErrorAComplete=502`.

## Verified correct / intentionally not filed

Items below were checked against ground truth and are **not** divergence bugs.
They are recorded so the audit trail is complete.

**Auth-session**
- The two previously-known auth-session issues are resolved/correct: the
  User-Agent space is FIXED, and `S111` is correct.
- `deviceKey` stub `"0123456789ABCDEF"` (`config.py:19`) differs from the real
  device value (ANDROID_ID / OnePass `GetDeviceID`, `SRWebActivity.java:2520-2523`)
  and from `srtgo`'s `"-"`, but the server does not validate `deviceKey` for login
  (cross-validation:294,325). Same stub is reused for `main.do deviceId`; also works.
  It is a user-overridable placeholder (`SRT_DEVICE_KEY`), not a divergence.
- Login field VALUES `check`/`auto`/`page`/`login_referer` are all `""` vs
  `srtgo`'s `Y`/`Y`/`menu`/full-main URL; both authenticate (cross-validation:296).
  The bundled `main.html` form ships these empty, so our empty values match the APK.
- `Referer` on the login POST = `{base}/login/login.do` (`session.py:34`): the exact
  Referer the app emits is not determinable from the bundle (login form is
  server-rendered); `srtgo` sends none. No evidence it is wrong — left as a caveat.
- **Logout** (`client.py:79-80`) only clears cookies locally and does NOT POST
  `/login/loginOut.do` (form exists at `main.html:455` but is runtime-not-called
  per spec §252). Deliberate read-only design choice, not a divergence.

**Seat / timetable / fare**
- Fare `chtnDvCd` hardcoded `'1'` vs the app's `item.chtnDvCd` is consistent, not
  a divergence: our search is direct-only (`jrnyTpCd=11 ⇒ chtnDvCd=1`).
- (The seat-page `psrmClCd`/`choiceSeatCount` hardcodes were considered
  "defensible read-only defaults" by the seat-timetable-fare pass, but the
  safety-contract audit filed them as B8/B13 because the guard also *rejects*
  legitimate first-class / multi-passenger requests — they are real bugs.)

**Search selectors**
- Station-map selector POST to `/common/ARA/ARA0502P/view.do` (`client.py:154`,
  `safety.py:71`): the station-map popup (`POP_REQ_STN_MAP=2`) is opened from
  inside the server-rendered station picker (`ARA0501P`), whose JS is NOT in the
  bundle, so there is no call-site to verify against. **Unresolved gap**, not a
  proven bug; `reqCode=2` is at least consistent with `const.js:2`.
- Infant passenger type (code `'6'`) with `infantCnt`/`psgTpCd6` has no attestation
  anywhere in the decompile (app has exactly 5 types, `psgTpCd1..5`) or in `srtgo`.
  Default infant=0 so no impact under normal use; the type-6 code is **speculative**.
- `group_search_ajax_payload` clamps `psgNum=max(total,10)` (`payloads.py:225`);
  the app sends user-entered `totPrnb`, which for a valid group is already ≥10, so
  this is a no-op for any valid group request — not flagged.

**Notice / ticket**
- `atc14017?pageNo=0` (ticket list) is a **real, runtime-verified** route (see the
  Rejected section). GET→HTML `parse_html_page` handling is consistent with the
  decompiled WebView behavior (no mis-parse); `safety.py:63` GET read-only
  classification is correct; session-expiry handling is correct.
- Verification gap (not a bug): `/main/noticeList.do`, `pageId=MB0101000000`, and
  the notice row field types (esp. `POST_NO` as int) do NOT appear anywhere in the
  decompile or bundled JS (0 hits) — they are runtime-only captures, and
  `tests/fixtures/notice_list.json` is explicitly synthetic (`PAGE_ID='SYNTHETIC_PAGE'`).
  If a real capture ever shows `POST_NO` as a string, `parsers.py:218`
  (`type(row.get('POST_NO')) is not int`) would reject every real row. Flagged as a
  verification gap because there is no ground truth to confirm the type.

**NetFunnel transport / safety**
- `http.py` transport (`Origin`=app origin, `Content-Type` urlencoded, login-redirect
  detection, `X-Requested-With=XMLHttpRequest`) shows no provable divergence.
- The NetFunnel GET does pass a `Referer` (`client.py:223`) — consistent.
- `config.py device_key='0123456789ABCDEF'` is a user-overridable placeholder, not a
  divergence.

## Rejected / non-bugs

One finding was raised during the audit and **rejected** after verification; it is
**not** a real bug and is excluded from the totals above.

**Ticket-list route/param — `get_ticket_list` uses `atc14017?pageNo=0` (`client.py:120`)** — *REJECTED (was proposed low).*
The claim was that `GET /atc/selectListAtc14017_n.do?pageNo=0` is wrong because the
canonical list is `atc14016` and `pageNo` is only ever paired with `atc14016` by
the app. The cited decompile facts are accurate (`ticketList.html:405`
data-url=`atc14016?pageNo=0`; `SRForegroundDialogActivity.java:31`=`atc14016?pageNo=0`;
`SRWebActivity.java:1592` builds `atc14017` with NO query string), **but the
conclusion that our code is wrong does not hold**:

1. **Runtime-verified success.** The exact route+param our client sends is recorded
   as a success: `docs/analysis/srt-app-api-library-spec-2026-07-09.md:257`
   ("GET `/atc/selectListAtc14017_n.do?pageNo=0` → Runtime success, HTML
   ticket/reservation list") and `full-api-analysis-2026-07-20.md:181`. Live-API
   ground truth beats a decompile-usage argument — the server accepts `?pageNo=0`
   on `atc14017` and returns the list, so there is no correctness defect.
2. **Intentional, documented design decision.** `docs/RELEASE_GAP_PLAN.md:153`
   labels `atc14016` the *alternate* list and tracks it as deferred gap R3;
   `cross-validation-2026-07-21.md:242` documents `atc14017` as our app's
   natively-wired landing route (`btnNo=='2'`), distinct from `srtgo`'s `atc14016`.
   The finding's "canonical vs alternate" labels are the reverse of the project's
   own framing.
3. **Self-contradictory** with the same audit's own verified-correct entries
   (`atc14017` is a real route; GET→HTML parse is consistent; safety GET
   classification and session-expiry handling are correct). The "could surface a
   different list variant" risk is speculative and contradicted by the runtime
   capture.

At most this is a stylistic "also implement `atc14016`" suggestion — already
tracked as gap R3 — not a divergence bug.
