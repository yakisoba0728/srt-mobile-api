# SRT Client Implementation Audit — Re-verify Pass 3

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Client under audit:** `srt-mobile-api` (read-only Python client)
**Date:** 2026-07-22
**Author:** FABLE
**Scope:** Divergences between our read-only client and the decompiled ground truth (apktool/jadx bundle), cross-checked against the battle-tested `srtgo` / `srtgo_plus` wire references.

## Overview

This pass re-verifies candidate divergences across five subsystem groups: `auth-session`, `search-selectors`, `seat-timetable-fare`, `notice-ticket`, and `netfunnel-transport-safety`. Each candidate was adversarially verified against both the decompile and the available wire references; only findings that survived verification are reported here as real bugs.

**Result: 3 provable divergences, all LOW severity.** No high- or medium-severity provable divergence survived verification. Two of the three live in `auth-session` (login form field value + failure-message parsing); one in `netfunnel` (an over-broad success-code set). Every previously-flagged bug in `search-selectors`, `seat-timetable-fare`, and `notice-ticket` was either already fixed or rejected on verification (see the Rejected / non-bugs section).

| Metric | Count |
| --- | --- |
| High | 0 |
| Medium | 0 |
| Low | 3 |
| Rejected (non-bugs) | 4 |

## Prioritized bug table

Sorted High → Low. Includes only findings the verifier did **not** reject.

| Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- |
| Low | login `deviceKey` field value | `src/srt_mobile_api/session.py:53` (also `config.py:19` `device_key` default) | `srtgo/srtgo/srt.py:704-705`; `docs/analysis/ref-srtgo_plus.md:119-122` | We send `config.device_key` (default `"0123456789ABCDEF"`, an ANDROID_ID-format value) as the login form's `deviceKey`. Both wire refs send the constant `"-"` for this server-rendered field; `deviceKey` appears nowhere in the decompile, so these are the only evidence and they agree. The ANDROID_ID value belongs on `/main/main.do?deviceId=` (`SRWebActivity.java:1582-1584`), not here. Wrong param value vs. the only evidence; a static fake device key is worse than the neutral `"-"` for any device-based anti-abuse gate. | Send a literal `deviceKey="-"` in the login POST; do not use `config.device_key` here. Keep `config.device_key` only for the `/main/main.do?deviceId=` query. |
| Low | failed-login error message parsing | `src/srt_mobile_api/session.py:62-66` | `srtgo/srtgo/srt.py:716,718`; `docs/analysis/ref-srtgo_plus.md:126` | On failure we read the server message from `user_map.get("MSG")` (nested in `userMap`), but the wire ref reads `MSG` at the **top level** (`r.json()["MSG"]`). Our nested read yields `None`, so we drop the real Korean message and emit generic "SRT login failed". Worse: if a failure response omits `userMap` entirely (srtgo's failure path never touches it), our earlier guard raises `SrtProtocolError("...missing userMap")` — wrong exception type on a normal wrong-password attempt. | Read the message from the top level first (`response.get("MSG")`), fall back to `userMap.MSG`. Treat an auth failure as `SrtAuthError` even when `userMap` is absent, not `SrtProtocolError`. |
| Low | `netfunnel.py` success codes | `src/srt_mobile_api/netfunnel.py:18` | `analysis/apktool/assets/offline/js/common/netfunnel.js:84` | `SUCCESS_CODES = {"200","502"}` treats `kTsErrorAComplete=502` as a NetFunnel success, but we only issue `getTidChkEnter` (opcode 5101). That reply is dispatched via `RTYPE_GET_TID_CHK_ENTER -> RTYPE_CHK_ENTER -> _showResultChkEnter()`, whose switch fires success only for `kSuccess=200` (and bypass 300 / ipblock-overflow 302); `502` falls to the default → `onError`. `502`-as-success only holds for `setComplete` (5004), which we never issue. Conversely `kTsBypass=300`, a pass, is missing. Latent, not crashing (fresh getTid returns `(5002,200)`), but the success set is provably inconsistent with the app's own chkEnter classifier. | Narrow `SUCCESS_CODES` to `{"200"}` for the getTid/chkEnter parse and fix the comment. If tolerating a bypassing server, add `"300"` (kTsBypass) — not `"502"` (a setComplete-only code that never occurs on a fresh getTid). |

## Detailed findings

### LOW — login `deviceKey` field value (`auth-session`)

- **Our ref:** `src/srt_mobile_api/session.py:53` (also `config.py:19` `device_key` default)
- **Ground-truth ref:** `srtgo/srtgo/srt.py:704-705`; `docs/analysis/ref-srtgo_plus.md:119-122`

Our client sends `config.device_key` (default `"0123456789ABCDEF"`, an ANDROID_ID-format value) as the login form's `deviceKey` field. Both wire references for this server-rendered field send the constant `"-"`: srtgo (`data["deviceKey"] = "-"`) and srtgo_plus, which explicitly states "deviceKey is the constant '-'". The ANDROID_ID value legitimately belongs on the `/main/main.do?deviceId=` query param (decompile `SRWebActivity.java:1582-1584` reads `Settings.Secure` ANDROID_ID), **not** on the login `deviceKey` field. Our client conflates the two by reusing one config value for both. `deviceKey` appears nowhere in the decompile, so srtgo/srtgo_plus are the only wire evidence and they agree on `"-"`. Likely harmless (server probably ignores it) but it is a wrong param value vs. the only evidence, and sending a static obviously-fake device key on every login is worse than the neutral `"-"` for any device-based anti-abuse gate.

**Suggested fix:** Send a literal `deviceKey="-"` in the login POST (do not use `config.device_key` here). Keep `config.device_key` only for the `/main/main.do?deviceId=` query, which correctly carries an ANDROID_ID-format value.

### LOW — failed-login error message parsing (`auth-session`)

- **Our ref:** `src/srt_mobile_api/session.py:62-66`
- **Ground-truth ref:** `srtgo/srtgo/srt.py:716,718`; `docs/analysis/ref-srtgo_plus.md:126`

On login failure our client reads the server message from `user_map.get("MSG")` (nested inside `userMap`). The wire reference reads `MSG` at the **top level** of the JSON: srtgo does `r.json()["MSG"]` for both the non-existent-member and password-error cases, sibling to the top-level `userMap` it reads for success. Because `MSG` is top-level per the only wire evidence, our nested read yields `None` on a real failure, so we fall back to the generic "SRT login failed" and lose the real Korean server message. Worse, if a failure response omits `userMap` entirely (srtgo's failure path never touches `userMap`), our earlier guard raises `SrtProtocolError("SRT login response missing userMap")` instead of an `SrtAuthError`, giving the wrong exception type on a normal wrong-password attempt.

**Suggested fix:** On failure, read the message from the top-level response first (`response.get("MSG")`) and only fall back to `userMap.MSG`. Treat an auth failure as `SrtAuthError` even when `userMap` is absent, rather than raising `SrtProtocolError`.

### LOW — `netfunnel.py` success codes (`netfunnel-transport-safety`)

- **Our ref:** `src/srt_mobile_api/netfunnel.py:18`
- **Ground-truth ref:** `analysis/apktool/assets/offline/js/common/netfunnel.js:84`

`SUCCESS_CODES = {"200","502"}` treats `kTsErrorAComplete=502` as a NetFunnel success. Our client only performs `getTidChkEnter` (opcode 5101, `aid=act_10`) and parses that response. In the app, a `getTidChkEnter` reply is dispatched by `netfunnel.js` as: `getReqType()==RTYPE_GET_TID_CHK_ENTER -> setReqType(RTYPE_CHK_ENTER) -> _showResultChkEnter()`. That handler's switch only fires onSuccess/pass for `kSuccess=200` (and `kTsBypass=300`, ipblock-overflow `302`); `kTsErrorAComplete=502` falls into the default branch which fires onError. So `502` is an ERROR for the response type we actually parse. `502`-as-success only holds for the `setComplete` (5004) step, which our read-only client never issues (confirmed by srtgo `run()`: `status in (WAIT_STATUS_PASS, ALREADY_COMPLETED)` is applied only to the `_complete()` result). The inline comment ("kSuccess=200, kTsErrorAComplete=502") mis-attributes `setComplete` semantics to the getTid/chkEnter parse. Conversely `kTsBypass=300`, which `_showResultChkEnter` treats as a pass, is absent from `SUCCESS_CODES`. Latent rather than crashing: a fresh `getTidChkEnter` (nfid=0, new tid) will not return "already complete", and the confirmed live response for this endpoint is `(5002,200)`; but the code's success set is provably inconsistent with the app's own chkEnter classifier.

**Suggested fix:** Narrow `SUCCESS_CODES` to `{"200"}` (kSuccess) for the getTidChkEnter/chkEnter parse and correct the comment; if a bypassing NetFunnel server should be tolerated, add `"300"` (kTsBypass) rather than `"502"` (which is a setComplete-only success and never occurs on a fresh getTid).

## Verified correct

The following were confirmed to match the decompiled ground truth during this pass and require no change:

- **`auth-session` — UA-space and S111 session-expiry fixes.** Verified correct (`docs/analysis/impl-audit-reverify-2026-07-22.md:26`). The prior audit (`impl-audit-reverify2-2026-07-22.md:26`) concluded "no provable auth-session divergences"; the two bugs above are the residual provable divergences, both low-impact.
- **`search-selectors` — group is in very good shape.** Every previously-flagged bug here has been FIXED and now matches ground truth: the ARA0403P wrong-date route + safety misclassification, the phantom `selectTime` field, and the station `chk_rtrp`/`page`/`boolRtrp` extras. No high/medium provable divergence found.
- **`seat-timetable-fare` — builders carefully aligned with the decompiled JS.** No hard route/method/param-name bugs; many builders cite exact JS line numbers. Ground truth used: `ara1001l.js`, `ara0101v.js`, `commCode.js`, `common/const.js`, `sub/main.html`, cross-validation docs, and test fixtures.
- **`netfunnel-transport-safety` — netfunnel/transport/config/safety contracts otherwise match the decompiled app.** Only the one low/latent success-code divergence above was provable.

## Rejected / non-bugs

Four candidate findings were opened, fact-checked, and rejected on verification. Their factual claims were accurate, but none met the "our code is really wrong vs ground truth" bar:

- **`search-selectors` — station selector `sNowSel` hardcoded to `"1"`** (`payloads.py:45` vs `ara0101v.js:157`). Rejected as harmless cosmetic divergence. `"1"` is a value the app itself legitimately posts (its `btn_dpt_stn` branch); `sNowSel` is a pure UI-focus hint for the server-rendered ARA0501P picker, and its `POP_REQ_STN` popCallback (`ara0101v.js:685-699`) reads back both `startStn*`/`arrivalStn*` and ignores `sNowSel`, so returned data is identical for `"1"` or `"2"`. `get_station_selector()` is a headless page fetch with no departure-vs-arrival tap concept. The finding itself rates it low, concedes "both values are valid", and its fix is an optional-param/doc enhancement.
- **`seat-timetable-fare` — `parse_mutual_verification_response` requires `dsOutput0.msgCd` string** (`parsers.py:419` vs `ara1001l.js:234`). Rejected. The app never reads `msgCd`, but requiring it is a deliberate module-wide framing-validation convention shared by the search parser (`parsers.py:835`) and reservation parser (`parsers.py:530`) on the same `_n.do`/`dsOutput0` server framework that reliably emits `msgCd` (IRZ000008 present in every fixture). "App never reads msgCd" conflates field-reads with wire format; the client validates framing, not read-parity. Finder concedes server omission is "not fully provable" — over-strict-in-theory only.
- **`seat-timetable-fare` — `get_seat_page` defaults `seat_count="1"`** (`client.py:393` vs `ara1001l.js:1511`). Rejected. The app sends `choiceSeatCount=totPrnb` (total passenger count) while our default is `"1"`, but `seat_count` maps directly to `choiceSeatCount` and is an exposed/documented/validated parameter (`payloads.py:306-309,338`), so the exact `totPrnb` value is reproducible by the caller. The `"1"` default matches the app's own `totPrnb` default (`ara0101v.js:114`) and mirrors `get_fare`'s single-adult default (`client.py:421`). Divergence arises only from caller misuse, not from the client emitting something the app wouldn't — a stateless-design characteristic, not a correctness bug.
- **`notice-ticket` — `get_ticket_list` sends `pageNo` to route 14017 instead of 14016** (`client.py:122`). Rejected as MEDIUM candidate. Decompile facts are accurate (`SRForegroundDialogActivity.java:31` opens `14016?pageNo=0`; `SRWebActivity.java:1592` opens 14017 with no params), but they don't make our code wrong, and a live runtime capture refutes the premise: `docs/analysis/srt-app-api-library-spec-2026-07-09.md:257` records `GET /atc/selectListAtc14017_n.do?pageNo=0` succeeding on the real server. 14017 is a deliberate documented route choice (`RELEASE_GAP_PLAN.md:153/726` labels atc14016 as deferred gap-plan item R3, "HTML only"). "Structured JSON lives at 14016" is a capability-scope gap, not a correctness bug. The only real kernel — whether `page_no=N>0` actually paginates on 14017 — is UNPROVEN and already tracked in `impl-audit-reverify2-2026-07-22.md:254-259`.

## Unverifiable residual risks (not bugs — recommend live capture)

Kept OUT of the bug list because the offline APK bundle lacks the server-rendered ground truth; correctness cannot be pinned to the decompile. Listed for awareness / smoke-test targeting:

- **`auth-session` login field values** `check=''`/`auto=''`/`page=''`/`login_referer=''` (`session.py:46-51`) vs srtgo `'Y'`/`'Y'`/`'menu'`/main.do URL (`srt.py:701-706`). The bundled form's `value=''` are HTML defaults populated by JS at submit, not proof of transmitted values. Likely harmless (JSESSIONID still set) — recommend a live login smoke test.
- **`auth-session` RTNCD success gate.** `session.py:65` requires `userMap.RTNCD=='Y'`; srtgo never reads RTNCD. If a real success response omits it, our login false-negatives. One-way risk; docs claim a prior runtime capture showed `userMap.RTNCD=Y`.
- **`auth-session` IP-block path.** "Your IP Address Blocked" is returned as plain text (`srt.py:719-720`); our login uses `post_form` with a JSON `Accept`, so a plain-text body would raise `SrtProtocolError` instead of a clean auth error. Edge case.
- **`auth-session` extra login fields** `customerYn`/`ciUptYn`/`dupInfoVal` (`session.py:55-57`) absent from both the offline bundle and srtgo (which sends only `customerYn`); harmless extras but unverified. Also the HTTP `Referer` header on the login POST (`session.py:60`, `/login/login.do`) vs srtgo's `login_referer` FORM field (main.do), and `X-Requested-With: XMLHttpRequest` added by `post_form` (`http.py:188`) despite the bundled form being `data-ajax='false'` — all harmless (endpoint returns JSON regardless), all unprovable statically.
- **`search-selectors` ARA0502P station-map selector** (`client.py:156`, `payloads.py:52-55`, `safety.py:77`). The route `/common/ARA/ARA0502P/view.do` and `{reqCode:"2", sNowSel:"1"}` payload appear NOWHERE in apktool/jadx; the map popup opens from inside the server-rendered ARA0501P picker whose page JS is not bundled. Derived by analogy — cannot be proven correct or wrong. Keep explicitly documented as unverified; ideally confirm/retire via live capture.
- **`search-selectors` `dptTm1`** (`payloads.py:186,226`) set to full `query.departure_time`, whereas the app's `dptTm1` is the hour-boundary radio value (`ara0101v.js:579-583`) and srtgo rounds to `time[:2]+"0000"` (`srt.py:805`). The primary filter `dptTm` carries the full time in all three impls, so `dptTm1` only diverges for sub-hour values with no known functional effect. Note, not a bug.
- **`notice-ticket` notice list** (`/main/noticeList.do`, pageId `MB0101000000`, row fields `IS_MAIN`/`PAGE_ID`/`BODY`/`POST_NO`/`CREATE_DATE`/`IS_NOTICE`/`SUBJ`) appears nowhere in `analysis/` (main.do server-rendered, JS not bundled) and srtgo has no notice feature; the fixture is synthetic. Latent risk: `parse_notice_list_response` (`parsers.py:218-222`) hard-requires `POST_NO` to be a Python int; many SRT JSON endpoints return numeric fields as strings, which would raise `SrtProtocolError` — unconfirmable from available evidence.
- **`netfunnel` missing `setComplete`(5004)/`chkEnter`(5002).** Our `netfunnel.py` builds only 5101 — an intentional documented single-getTid design. `netfunnel.js:70` (`MP_REQONLYLIMIT=10`) shows getTidChkEnter-without-setComplete is permitted (client-side cap 10), so omitting setComplete is a slot-leak robustness risk over many searches, not a per-request divergence. Also: `reqCode` allowlist pins `'9'` only (`safety.py`) while the app also sends round-trip seat requests with `reqCode=10` (we only issue one-way, so not a send-divergence, just a stricter allowlist); and srtgo sends `X-Requested-With: kr.co.srail.newapp` + `Sec-Fetch-*` headers on the netfunnel GET (`srt.py:521-525`) which we omit (server tolerance unknown).

## Cross-impl divergence (not a bug against the app)

- **`search-selectors` train-class filtering.** srtgo filters search rows to `stlbTrnClsfCd=="17"` (SRT only, `srt.py:834`) while our parser returns all `dsOutput1` rows — a deliberate read-only design choice for a client whose default `train_group_code` is `"900"` (KTX+SRT). The app itself renders all returned rows.
