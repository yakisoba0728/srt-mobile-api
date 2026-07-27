# SRT Client Implementation Audit — Re-verify Pass 5

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Client under audit:** `srt-mobile-api` (read-only Python client)
**Date:** 2026-07-22
**Author:** FABLE
**Scope:** Divergences between our read-only client and the decompiled ground truth (apktool/jadx offline bundle), cross-checked against the battle-tested `srtgo` wire reference.

## Overview

This pass re-verifies candidate divergences across the same five subsystem groups audited in prior rounds: `auth-session`, `search-selectors`, `seat-timetable-fare`, `notice-ticket`, and `netfunnel-transport-safety`. Each candidate was adversarially verified against both the decompile and the available wire reference. Ground truth is the decompile; where `srtgo` differs from the app it is treated as the outlier, and unfalsifiable items (server-rendered pages absent from the APK, synthetic-fixture-only fields) are surfaced as residual risk rather than filed as bugs.

**Result: 0 provable divergences.** Two candidate findings were raised this round — a low-severity `X-Requested-With` header-value claim in `auth-session` and a low-severity NetFunnel `user_data` omission in `netfunnel-transport-safety` — and **both were rejected on verification** because each rested on a mis-cited or false ground-truth premise. Every other subsystem produced no candidate at all. The bug table below is therefore intentionally empty; all substantive content is in the **Verified correct** and **Rejected / non-bugs** sections.

| Metric | Count |
| --- | --- |
| High | 0 |
| Medium | 0 |
| Low | 0 |
| Rejected (non-bugs) | 2 |

## Prioritized bug table

Sorted High → Low. Includes only findings the verifier did **not** reject. Both-sides `file:line` citations are retained in every row.

| Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- |
| _(none)_ | — | — | — | No candidate divergence survived verification this pass. The two candidates raised (see **Rejected / non-bugs**) were both rejected on false or mis-cited ground-truth premises. | — |

## Verified correct

Everything below was examined this pass and confirmed to match the decompiled ground truth (and, where applicable, the runtime-capture spec and `srtgo`). None of it is a bug.

### auth-session

- **UA-space and S111 fixes** — both verified correct (carried forward from prior rounds).
- **Login envelope field-set** — the `LoginRequest` body field-set matches the decompile and the runtime-capture spec.
- **`login_type` / `srchDvCd` detection, `deviceKey`, plaintext password, route/method** — all check out against the decompile and `srtgo`.
- **RTNCD success gate** (`src/srt_mobile_api/session.py:68`) — grounded in a prior runtime capture. Carries a one-way false-negative *risk* only if a real success response ever lacks `userMap.RTNCD` (`srtgo` does not gate on it); residual risk, not a bug.
- **Extra login fields `ciUptYn=""` and `dupInfoVal=""`** (`src/srt_mobile_api/session.py:61-62`) — absent from `srtgo` but **present** in the runtime-capture `LoginRequest` spec (`docs/analysis/srt-app-api-library-spec-2026-07-09.md:142-143`), so legitimate, not phantom.
- **Login body default values** `check=""`, `auto=""`, `page=""`, `login_referer=""` — differ from `srtgo`'s `check=Y`/`auto=Y`/`page=menu`/`login_referer=<main.do URL>` (`srtgo/srtgo/srt.py:700-710`), but the decompiled offline form renders these as empty defaults (`analysis/apktool/assets/offline/sub/main.html:722-727`); tie-break trusts the decompile. `auto`/`check` are auto-login flags that do not gate `JSESSIONID` issuance, so empty does not break session establishment. Not provably wrong.
- **HTTP `Referer` on the login POST** = `.../login/login.do` (`src/srt_mobile_api/session.py:65`). We `GET login.do` then `POST` — a coherent login-page flow; `srtgo` uses a blanket `Referer` of `https://app.srail.or.kr/` and puts `main.do` only in the `login_referer` form field. Harmless (endpoint returns JSON regardless).
- **`Accept` header on login** = `application/json, text/javascript, */*; q=0.01` (`src/srt_mobile_api/session.py:64`) vs `srtgo`'s `*/*`. Server returns JSON regardless of `Accept`. Harmless.
- **`config.device_key` default** `"0123456789ABCDEF"` (uppercase) vs a typical lowercase 16-hex `android_id`. User-overridable and only echoed as `deviceId` on `main.do`; server does not appear to validate. Not a bug.

### search-selectors

All previously-flagged bugs are confirmed **FIXED** against ground truth:

- Date-picker route `ARA0403P` → `ARA0401P`, plus the safety-allowlist mismatch.
- The phantom `selectTime` field (removed).
- Station-selector `chk_rtrp` / `page` / `boolRtrp` extras (removed).
- Passenger per-type vs compacted ordering.
- `safety.py` pinning `psrmClCd` / `choiceSeatCount` to fixed values.

### seat-timetable-fare

- All four request builders match the decompiled app field-for-field.
- The mutual-verification parser matches the app's classification logic.
- **Fare `chtnDvCd`** hardcoded `"1"` (`src/srt_mobile_api/payloads.py:401`) vs the app sourcing `chtnDvCd:item.chtnDvCd` (`analysis/apktool/assets/offline/js/ara/ara1001l.js:1206`): direct point-to-point search (`selectListAra10007`, `jrnyTpCd=11`) only returns direct legs whose `chtnDvCd` is always `"1"`, and `TrainSummary` carries no `chtnDvCd` to source from, so the emitted value is identical to the app's for every fare-lookup target. Not a provable divergence.
- **`stnCourseNm`** prefers a row/context station name over the code lookup (`_station_course`, `src/srt_mobile_api/payloads.py:376-382`) vs the app always building `getStnNameByCd(dptRsStnCd)+"-"+getStnNameByCd(arvRsStnCd)` (`ara1001l.js:1176-1177,1203-1204`): `stnCourseNm` is a display string (the request also sends `dptRsStnCd1`/`arvRsStnCd1` separately; the timetable train is keyed by `runDt+trnNo`), and the row name is itself resolved from `getStnNameByCd`, so values are normally identical. Not a provable functional divergence.

### notice-ticket

- Both core reads are server-rendered and decompile-silent; nothing in this group can be proven wrong against the decompiled ground truth. Fixtures are explicitly synthetic and the tests are self-referential. This reproduces the conclusion of prior audit rounds (`docs/analysis/impl-audit-reverify{,2,4}-2026-07-22.md`).

### netfunnel-transport-safety

- The FOCUS files (`netfunnel.py`, `http.py`, `config.py`, `safety.py`) are almost entirely faithful to ground truth when checked against the decompiled `netfunnel.js`, ara/arc bundled JS, `SRWebActivity.java`/smali, `main.html`, and `const.js`, cross-checked against `srtgo/srt.py`.
- **`GET /ara/selectListAra10007_n.do` hydration** (`src/srt_mobile_api/client.py:230`) — both bundled-JS call sites for `Ara10007` are POST (ajax refresh), but the app's initial navigation into the `ara1001l` page is a server-rendered link/form not present in the APK, so GET-then-POST cannot be shown wrong (already accepted in `full-api-analysis`).
- **`setComplete` (opcode 5004) intentionally never issued** — the app sets `TS_AUTO_COMPLETE=true` (`netfunnel.js:27`) and `srtgo` issues `setComplete`, but whether the SRT search endpoint requires a completed key cannot be proven statically; act_10-only is the intended design.
- **Seat-page `reqCode` pinned to 9 (one-way)** — the app also uses `reqCode=10` for round-trip (`POP_REQ_SEATSELECT_GO_BACK=10`, `const.js:10`); our read-only client only fetches one-way seat maps, so pinning to 9 is a valid app value, not a divergence.

## Rejected / non-bugs

### Rejected candidate findings (this pass)

Two candidates were raised and **rejected** on verification. Both-sides citations are retained.

#### REJECTED — `auth-session`: `X-Requested-With` header value on the login POST

- **Our ref:** `src/srt_mobile_api/http.py:204` (every POST sends `X-Requested-With: XMLHttpRequest`)
- **Claimed ground-truth ref:** `srtgo/srtgo/srt.py:521` (claimed to send `X-Requested-With: kr.co.srail.newapp`)

**Why rejected — mis-cited ground truth.** The cited `srtgo/srt.py:521` is inside `NetFunnelHelper.DEFAULT_HEADERS` (`srt.py:511-534`), a `curl_cffi` Chrome-impersonation header block scoped to `Host=nf.letskorail.com` (the NetFunnel waiting-queue service) — **not** the login POST and not the SRT API session. `srtgo`'s actual login POST (`srt.py:712`, `url=/apb/selectListApb01080_n.do`) uses the main session whose headers = module-level `DEFAULT_HEADERS` (`srt.py:25-28`) = `{User-Agent, Accept: application/json}` **only**, with **no** `X-Requested-With` header at all. So the finding's core claim — that `srtgo` / "real app traffic" sends `X-Requested-With: kr.co.srail.newapp` on the login POST — is unsupported by its own citation; `srtgo` sends nothing there. Decompiled app grep (`analysis/jadx/sources`) shows no explicit `X-Requested-With`/`setRequestHeader` (only `kr.co.srail.newapp.R` package refs), so any package-name value would be Android-WebView auto-injection, unverifiable statically. The finding itself concedes impact is unprovable, the server is lenient (returns JSON regardless), and it is "not required for correctness". **Low severity + mis-cited ground truth + no provable divergence = reject.**

#### REJECTED — `netfunnel-transport-safety`: act_10 request missing `user_data` param

- **Our ref:** `src/srt_mobile_api/netfunnel.py:30-35` (`build_act10_url`) and `src/srt_mobile_api/safety.py:164-183` (7-param netfunnel contract: `opcode,nfid,prefix,sid,aid,js,timestamp`)
- **Claimed ground-truth ref:** `analysis/apktool/assets/offline/js/common/netfunnel.js:41` (`TS_USER_DATA_KEYS` `srailSID`) and `:84` (`getUserdata` + `if(b!=""){c+="&user_data="+b}` in `getTidChkEnterProc`)

**Why rejected — false central premise.** The finding assumes that after login the `srailSID` cookie is present, so `getTidChkEnterProc` would append `&user_data=<srailSID>` and our omission diverges. Both citations are textually accurate, **but** `getUserdata()` for type `'c'` returns `NetFunnel.Cookie.get("srailSID")` — a literal-name lookup on `document.cookie`, and the SRT app never sets a cookie named `srailSID`:

1. The string `srailSID` appears **nowhere** in the entire decompiled APK except that single `netfunnel.js:41` config line (`grep -rniE` across all of `analysis/` = zero other hits in jadx sources, apktool smali, and raw).
2. The app's actual session cookies are `JSESSIONID` — `main.html:479-480` exposes `KR_JSESSIONID` and `SR_JSESSIONID` (both literally `JSESSIONID=...;Path=/`), and `src/redaction.py:18/40` targets `JSESSIONID`.
3. This `netfunnel.js` is the shared KORAIL library (`TS_HOST nf.letskorail.com`); `srailSID` is a leftover config value the SRT app does not use.

Since `Cookie.get("srailSID")` returns `""` on the SRT app, the `if(b!="")` guard never fires and the **real** act_10 request never carries `user_data`. Our omission (`build_act10_url`) and the safety 7-param contract's rejection of `user_data` are therefore **faithful** to ground truth, not divergent. `srtgo` (battle-tested) likewise omits `user_data` and still obtains valid keys. **No bug.**

### Other non-bug observations (examined, deliberately not filed)

These are unfalsifiable or non-defect items surfaced as residual risk rather than bugs. They reproduce the conclusions of the prior reverify2/3/4 rounds.

- **`search-selectors` — `ARA0502P` station-map route** (`src/srt_mobile_api/client.py:156`, `payloads.py:52-55`, `safety.py:77`). **Unfalsifiable.** The literal `ARA0502P` and a `reqCode=2` request appear **nowhere** in apktool+jadx (grep-confirmed across `analysis/`). The `POP_REQ_STN_MAP=2` popCallback exists (`ara0101v.js:743-757`) but has **no** bundled call-site — the map popup opens from inside the server-rendered `ARA0501P` picker whose page JS is not bundled. The route was derived by analogy to `ARA0501P` and cannot be shown correct or wrong. This is the single highest-risk unverified read surface in the group; recommend a live capture to confirm or retire it.
- **`search-selectors` — station selector `sNowSel` hardcoded `'1'`** (`payloads.py:45`) vs the app's dynamic `'1'`(departure)/`'2'`(arrival) at `ara0101v.js:157`. **Non-bug:** the `POP_REQ_STN` popCallback (`ara0101v.js:685-699`) reads back `startStn*`/`arrivalStn*` and ignores `sNowSel`, so the returned station data is identical for `'1'` or `'2'`; `get_station_selector` is a headless page fetch with no dep-vs-arv tap concept.
- **`search-selectors` — passenger selector `isOrg` hardcoded `'2'`** (`payloads.py:77`) vs the app's `chk_grp_dv` toggle (`ara0101v.js:233`). **Non-bug:** the passenger popCallback (`ara0101v.js:782-805`) reads `obj.passenger1..5` and never reads `isOrg`; `'2'` is the individual-flow value the app posts.
- **`search-selectors` / `seat-timetable-fare` — `get_seat_page` `choiceSeatCount` default `'1'`** (`client.py:393/395`, `payloads.py:358`) vs the app's `lfn_getRsv('totPrnb')` (`ara1001l.js:1511`). **Non-bug:** `choiceSeatCount` is an exposed, safety-validated positive-integer param (`safety.py:58`); `'1'` matches the app's single-adult `totPrnb` default (`ara0101v.js:114`) and a caller reproduces the exact `totPrnb`. Read-only view page; divergence would arise only from caller misuse.
- **`search-selectors` — `search_ajax_payload` `dptTm1`** = full `departure_time` (`payloads.py:224`) vs `srtgo`'s hour-block `time[:2]+'0000'`. **Non-bug:** our code preserves the app's own invariant `dptTm==dptTm1` (both = selected hour-block radio value, `ara1001l.js:100/160-161`); `srtgo` is the outlier and the server accepts full precision. With default `departure_time='060000'` the values are identical anyway.
- **`seat-timetable-fare` — verification gaps (not bugs).** The `timetable.html`, `fare.html`, and `seat_selection_page.html` fixtures are **synthetic**; the HTML parsers (`parse_timetable_page`/`parse_fare_page` heuristic table+time+won regex, `parsers.py:299-357`; the `좌석선택` visible marker at `parsers.py:84`) cannot be validated against the real `arc02012`/`Ara12009`/`Ara13010` server HTML (server-rendered, absent from `analysis/`). `srtgo` implements no timetable/fare/seat-page feature, so it provides no cross-check.
- **`seat-timetable-fare` — `arc02011` (seat-inventory/seat-map) deliberately not implemented / not allowlisted** (documented scope decision). `get_seat_page` returns only the seat-selection HTML page, not parsed seat inventory. Not a divergence.
- **`notice-ticket` — decompile silence.** `grep` across `analysis/jadx/sources` + `analysis/apktool/smali` for `noticeList.do` / `MB0101000000` / `SUBJ` / `CREATE_DATE` / `IS_NOTICE` / `POST_NO` returns **zero** real hits (only `POST_NOTIFICATIONS` permission matches). The `pageId=MB0101000000`, the `noticeList[]` wrapper, and every notice-row field are attested **only** by a prior live capture (`docs/analysis/srt-app-api-library-spec-2026-07-09.md:256`), not by the static bundle. `ticketList.html` loads offline data from local storage via bridge, not the network (`analysis/apktool/assets/offline/sub/ticketList.html:38-72`).
- **`notice-ticket` — `atc14017` `pageNo` pagination** (LOW functional-uncertainty, not a proven bug). `client.py:122` always appends `?pageNo=<n>`, but the decompile attaches `pageNo` only to `atc14016` (`SRForegroundDialogActivity.java:31`; data-url at `ticketList.html:405`), while `atc14017` is loaded with **no** query string (`SRWebActivity.java:1592`). `pageNo=0` is verified good; whether `atc14017` honors `pageNo>0` is unproven — `get_ticket_list(page_no=N>0)` could silently return page 0. Not a proven wrong value. Recommend live capture before relying on ticket-list pagination.
- **`notice-ticket` — `atc14017` (our GET, HTML) vs `atc14016` (`srtgo` POST reservation list, `srtgo/srtgo/srt.py:95,1069`).** Both endpoints exist in the decompile, so per the audit rule (trust the decompile where `srtgo` differs) neither route is provably wrong; our `atc14017` landing mirrors the app's native WebView landing.
- **`notice-ticket` — `parsers.py:218` strict `type(POST_NO) is int`.** If the live API returned `POST_NO` as a numeric **string** (common in these Korean endpoints), a valid response would raise `SrtProtocolError`. Cannot be confirmed or refuted — the only sample (`notice_list.json`) is synthetic with `POST_NO=42` (int). Fragility, not a bug.

## Bottom line

No HIGH/MEDIUM/LOW provable divergence survived this pass. Both candidates raised were rejected on false or mis-cited ground-truth premises (the `srtgo` login POST sends no `X-Requested-With`; the SRT app never sets a `srailSID` cookie so the real act_10 request carries no `user_data`). All prior-round fixes remain verified, and the remaining residual risks are unfalsifiable static-analysis gaps — chiefly the `ARA0502P` station-map route and `atc14017` pagination — best retired by targeted live capture rather than code change.
