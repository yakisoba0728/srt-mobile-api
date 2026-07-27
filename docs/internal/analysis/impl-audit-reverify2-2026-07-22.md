# SRT Client Implementation Audit — Re-verify (Pass 2) — 2026-07-22

**Target:** `kr.co.srail.newapp` v2.0.41 (SRT mobile app)
**Subject:** `srt-mobile-api` read-only client vs. the decompiled ground truth
**Author:** FABLE
**Date:** 2026-07-22

## Overview

This is the second re-verification pass over where our read-only SRT client
diverges from the decompiled v2.0.41 app ("ground truth"). Ground truth is, in
priority order: the bundled offline JS/HTML under
`analysis/apktool/assets/offline/`, the jadx/smali native decompile, and — where
the app source is server-rendered or absent from the bundle — the battle-tested
`srtgo` reference client and prior settled cross-validation docs. Live-API
captures override decompile-usage arguments where they exist.

Every candidate finding was **adversarially verified** against those sources.
**Only findings that survived verification are listed as bugs.** Candidates that
were rejected (unconfirmable, or provably non-defects) are documented, with
reasons, in the *Rejected / non-bugs* section and are **not** counted as real
defects.

Headline results this pass:

- **No auth-session divergences** are provable. The two `login.do` payload
  candidates (`check`/`auto` and `page`/`login_referer`) were **rejected**: our
  empty values faithfully match the app's own server-rendered login form
  defaults, and the fields only steer session-persistence / post-login redirect,
  not authentication.
- **No notice-ticket divergences.** The notice list is entirely absent from the
  decompile, so nothing there is provable; route/params/headers on the ticket
  path match the decompile and prior capture.
- **No netfunnel-transport-safety divergences.** The `act_10` (`5101`) contract,
  transport headers, UA/hosts/deviceKey, and the read-only route allowlist are
  correct; the lone candidate (`ARA0502P` station-map selector) was **rejected**
  as unfalsifiable — the map-open request shape is genuinely absent from ground
  truth, so it can be neither confirmed nor refuted.
- The **4 surviving bugs** are all in the **search** and **seat/timetable/fare**
  builders/parsers: two Medium (search success-classification + an invalid
  `infant` head-count field) and two Low (`stnCourseNm` value + missing
  `Referer` header). None is High.

### Totals

| Severity | Count |
| --- | --- |
| High | 0 |
| Medium | 2 |
| Low | 2 |
| **Total verified bugs** | **4** |

Rejected / unconfirmable candidates: **3** (2 auth-session login-payload, 1
netfunnel station-map selector). Groups audited: auth-session, search-selectors,
seat-timetable-fare, notice-ticket, netfunnel-transport-safety.

All `src/…`, `analysis/…`, `safety.py`, `payloads.py`, `parsers.py` paths are
relative to the `srt-mobile-api` repo root (where this doc lives). Cross-repo
citations to `srtgo/…` are the external reference client.

## Prioritized bug table (High → Low)

| # | Severity | Area | Our ref | Ground-truth ref | Description | Fix |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | **Medium** | search response parser (success classification) | `src/srt_mobile_api/parsers.py:842` | `analysis/apktool/assets/offline/js/ara/ara1001l.js:206` (+ srtgo `srt.py:391-401`) | `parse_train_search_response` gates success on `code != "IRG000000" or status != "SUCC"` and raises `SrtAppError` otherwise. Ground truth: the app treats a search as successful whenever `dsOutput0.strResult != "FAIL"` and **never inspects `msgCd`**; srtgo agrees, keying success solely on `strResult` (SUCC/FAIL). Requiring `msgCd == "IRG000000"` is stricter than **both** ground-truth sources, so any legitimate non-`FAIL` response carrying a different success/warning `msgCd` would be rejected and its real `dsOutput1` train rows discarded. All bundled fixtures happen to use `IRG000000`, which masks this. | Gate success on `strResult` only (`status == "SUCC"`, or `strResult != "FAIL"` to fully match the app), keeping the `NET000001` NetFunnel special-case; treat `msgCd` as informational rather than requiring the exact `"IRG000000"` value. |
| B2 | **Medium** | passenger head-count fields (search + passenger selector) | `src/srt_mobile_api/models.py:42` (field decl `:18`) | `analysis/apktool/assets/offline/js/ara/ara0101v.js:35` (`getPsgTotCnt` sums `psgInfoPerPrnb1..5`) | `PassengerCounts.total` sums an `infant` field that has **no SRT passenger type**. All head-count fields derive from `total()`: `totPrnb`/`totPrnbNm` (`payloads.py:189-190`), `psgNum` (`payloads.py:232`), `totalPessnger` (`payloads.py:82`). But the `psgTpCd`/`psgInfoPerPrnb` type grid (and `psgGridcnt`) excludes infant (only `PASSENGER_TYPE_CODES` 1..5 are packed). The app invariant is `totPrnb == sum(psgInfoPerPrnb1..5)` **always**, because `getPsgTotCnt()` sums exactly those hidden inputs. With `infant>0` the client breaks that invariant: `PassengerCounts(adult=1, infant=1)` emits `totPrnb`/`totalPessnger=2` while the type grid sums to 1; worse, `PassengerCounts(infant=1)` passes validation and yields `totPrnb=1` with `psgGridcnt=0` and an all-zero grid — a request the app can never produce. The field is publicly exported and `live.py:165` wires `SRT_INFANT_COUNT` into it, so this is reachable on the live search path. | Since SRT has no infant type (`psgTpCd` is 1..5 only), either reject `infant>0` in `PassengerCounts.__post_init__` or remove the `infant` field entirely (and drop it from `total()`, the `sum>=1` check, and `live.py`'s `SRT_INFANT_COUNT`). Head-count fields must always equal the sum of the emitted `psgInfoPerPrnb` slots. |
| B3 | Low | timetable + fare `stnCourseNm` value | `src/srt_mobile_api/payloads.py:347-349` (used at `:354` `timetable_payload`, `:365` `fare_payload`) | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1185` (timetable) & `:1218` (fare) | The app always builds `stnCourseNm` as `getStnNameByCd(dptRsStnCd) + "-" + getStnNameByCd(arvRsStnCd)` — a dash-joined pair of station **names** resolved from codes via a static client-side table — so it is never empty and always contains the dash. Our `_station_course` instead joins `train.departure_station_name`/`arrival_station_name`, filtering out empties. Those names come from the search row's `dptRsStnNm`/`arvRsStnNm` (which the real `dsOutput1` does **not** carry — the app resolves names from codes, and the sample fixture rows have no such fields) or the request-context fallback (`parsers.py:781-784`, only when the caller passed a name differing from the code). So when a search is issued with station **codes only**, our `stnCourseNm` is emitted **empty**; with only one name known it is emitted with no `-` separator. Almost certainly a display-only echo (the fare request also carries `dptRsStnCd1`/`arvRsStnCd1` codes the server actually computes from, and the timetable is keyed by `trnNo`+`runDt`), hence Low, but a provable value mismatch versus the app. | Match the app: always emit `dptName + "-" + arvName`, resolving names from a code→name table (`getStnNameByCd` equivalent, from `stationInfo.js`) rather than depending on names carried on `TrainSummary`, so the `-` and both names are always present. If a name is unresolvable, fall back to the code rather than dropping the segment. |
| B4 | Low | `get_timetable`/`get_fare` missing `Referer` header | `src/srt_mobile_api/client.py:405-409` (`get_timetable`) & `:418-422` (`get_fare`) | `analysis/apktool/assets/offline/js/ara/ara1001l.js:1188-1194` (timetable) & `:1228-1234` (fare) | `get_seat_page` and `get_mutual_verification` defensively set a `Referer` header (the search-results page), but `get_timetable` and `get_fare` call `http.post_form` **without** a `referer=` argument, so no `Referer` header is sent. In the app both timetable and fare are triggered by `$.mobile.pageContainer.pagecontainer('change', ...)` from the search-results page (`ara1001l`, served at `/ara/selectListAra10007_n.do`), so the actual requests carry that page as `Referer`. Our client sends none. Low severity because these read endpoints do not appear to enforce `Referer`, but it is a divergence in what is sent — and inconsistent with our own seat/mutual code paths. | Pass `referer=f"{self.config.base_url}/ara/selectListAra10007_n.do"` to the `post_form` calls in `get_timetable` and `get_fare`, mirroring `get_seat_page` and `get_mutual_verification`. |

## Bug details

### B1 — Medium — search success gate over-requires `msgCd == "IRG000000"`

- **Our ref:** `src/srt_mobile_api/parsers.py:842`
- **Ground truth:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:206`; secondary `srtgo/srt.py:391-401`

The app's search-result handler classifies purely on `dsOutput0.strResult`
(`SUCC`/`FAIL`) and never reads `msgCd`. srtgo does the same. Our parser adds an
extra equality requirement `code == "IRG000000"`, so a legitimate non-`FAIL`
response carrying any other success/warning code would be raised as `SrtAppError`
and its `dsOutput1` train rows dropped. Every bundled fixture uses `IRG000000`,
so tests never exercise the divergence. Keep the `NET000001` NetFunnel-retry
special-case; drop the `msgCd` value requirement.

### B2 — Medium — `infant` head-count breaks `totPrnb == sum(psgInfoPerPrnb1..5)`

- **Our ref:** `src/srt_mobile_api/models.py:42` (field declared `:18`)
- **Ground truth:** `analysis/apktool/assets/offline/js/ara/ara0101v.js:35`

SRT's passenger picker has exactly five types (`psgTpCd` 1..5); there is no
infant type. Because our head-count fields all derive from `total()` while the
type grid packs only types 1..5, any `infant>0` composition emits a `totPrnb` /
`totalPessnger` / `psgNum` that exceeds the grid sum — an invariant the app
guarantees via `getPsgTotCnt()`. `PassengerCounts(infant=1)` is the worst case: a
head-count of 1 with an all-zero grid and `psgGridcnt=0`, a request the app can
never build. Reachable live via `live.py:165` (`SRT_INFANT_COUNT`). Fix by
rejecting `infant>0` or removing the field outright.

### B3 — Low — `stnCourseNm` emitted empty / dash-less on code-only searches

- **Our ref:** `src/srt_mobile_api/payloads.py:347-349` (consumed at `:354`, `:365`)
- **Ground truth:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:1185` (timetable), `:1218` (fare)

The app resolves station **names from codes** client-side and always produces
`name-"-"-name`. Our builder depends on names carried on the `TrainSummary`,
which the real `dsOutput1` does not supply, so a code-only search yields an empty
`stnCourseNm` (or a dash-less single name). Very likely a display-only echo (the
fare/timetable requests key on codes and `trnNo`+`runDt`), so Low, but a provable
value divergence. Resolve names from a static code→name table with a code
fallback.

### B4 — Low — `Referer` header omitted on `get_timetable` / `get_fare`

- **Our ref:** `src/srt_mobile_api/client.py:405-409` (`get_timetable`), `:418-422` (`get_fare`)
- **Ground truth:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:1188-1194` (timetable), `:1228-1234` (fare)

Both requests originate from the search-results page in the app, so the real
requests carry `/ara/selectListAra10007_n.do` as `Referer`. Our client sends no
`Referer` on these two calls, unlike its own `get_seat_page` /
`get_mutual_verification`. Endpoints do not appear to enforce it, hence Low; pass
the same `referer=` to match.

## Verified correct (no divergence found)

The following were checked and confirmed **faithful to ground truth** — not bugs:

**auth-session (all confirmed, or deliberate design):**

- `deviceKey` stub `"0123456789ABCDEF"` (`config.py:19`, `session.py:53`) vs
  srtgo `"-"` (`srt.py:704`): server-unvalidated at login and user-overridable;
  the app's real source is `ANDROID_ID` (`SRWebActivity`), and srtgo proves a
  stub authenticates.
- `ciUptYn=""` / `dupInfoVal=""` (`session.py:56-57`): appear in neither the
  decompile nor srtgo but are empty-valued → harmless additive.
- `Origin` + `X-Requested-With: XMLHttpRequest` on the login POST
  (`http.py:187-188`): additive vs srtgo; endpoint returns JSON regardless.
- Login POST `Referer=<base>/login/login.do` (`session.py:60`): faithful (the
  form is rendered on `login.do`); harmless.
- Logout (`client.py:81-82`) only clears local cookies and does **not** POST
  `/login/loginOut.do`: deliberate read-only design, not a wire divergence.

**seat-timetable-fare:** builders/parsers/models are well-aligned with the
decompile — routes and param **names** are all correct, and `arc02012` (not
`arc02011`) is confirmed. Only the two Low value/robustness divergences (B3, B4)
were found.

**notice-ticket:** the ticket route (`/atc/selectListAtc14017_n.do`) and method
match the decompile; `atc14017?pageNo=0` returning the list is confirmed by prior
runtime capture (`srt-app-api-library-spec-2026-07-09.md:257`). Our HTML-text
`atc14017` approach (vs srtgo's structured `atc14016` JSON) mirrors the app's
native WebView landing (`btnNo=='2'`) — expected, not a defect.

**netfunnel-transport-safety:** the `act_10` (`5101`) getTid contract, transport
headers, UA/hosts/deviceKey, and the 20-route read-only allowlist are correct;
`js=yes` (vs srtgo's `js=true`) is handled correctly on our side; the client's
act_10-only handshake relying on `NET000001` retry (`client.py:271-301`) matches
the expected "only act_10 remains" design.

## Rejected / non-bugs

### Adversarially rejected candidates (not defects)

- **login `check=""`/`auto=""`** (`session.py:49-50`) vs srtgo `"Y"`/`"Y"`
  (`srt.py:701-702`) — **REJECTED.** The divergence is real but non-defective.
  The decompiled app's own login form
  (`analysis/apktool/assets/offline/sub/main.html:724-725`) hard-codes
  `<input name=check value="">` and `<input name=auto value="">` as defaults —
  the exact empty values our client sends. `check`/`auto` are the keep-signed-in
  / auto-login checkbox flags; empty is the legitimate default-submit state and
  controls only session persistence, not session creation. srtgo's `"Y"`/`"Y"`
  reflect a persistence-enabled capture, not an auth requirement. Not wrong.
- **login `page=""`/`login_referer=""`** (`session.py:51,54`) vs srtgo
  `page="menu"`/`login_referer=main.do` (`srt.py:703,706`) — **REJECTED.**
  `login_referer` defaults to `value=""` in the app's real form
  (`main.html:726`) and there is **no `page` field at all** in that form, so our
  empty values are faithful to the app. Both fields only steer the server's
  post-login redirect target and are not required to authenticate. Our client
  ignores any redirect anyway, doing its own `GET /main/main.do?deviceId=...`
  (`session.py:68`) and `GET /ara/ara0101v.do` (`session.py:73`) after login, so
  these fields have zero effect on our flow. Not wrong.
- **`ARA0502P` station-map selector route + payload** (`safety.py:77`,
  `client.py:153-159` `get_station_map_selector`, `payloads.py:48`
  `station_map_selector_payload`) — **REJECTED (unfalsifiable).** All of the
  finding's facts check out: `"ARA0502P"` appears **nowhere** in the entire
  decompile (jadx sources+resources, apktool smali+assets, raw/base); the
  evidenced set of `/common/ARA/` popup endpoints is exactly five (`ARA0201V`,
  `ARA0401P`, `ARA0501P`, `ARA0701P`, `ARA0901P`); `POP_REQ_STN_MAP=2`
  (`const.js:2`) exists only as a **result-handler** callback
  (`ara0101v.js:743`), never as a request builder; and our
  `{reqCode:'2', sNowSel:'1'}` payload is derived by analogy to `ARA0501P`, not
  from evidence. **However**, the map feature genuinely exists (map button
  images, the `POP_REQ_STN_MAP` constant, the result callback), and the map popup
  is a nested sub-view of `ARA0501P` whose page JS is **not** in the offline
  bundle — so ground truth is *silent* on the map-open request shape. It neither
  confirms nor contradicts `ARA0502P` or `{reqCode:2, sNowSel:1}`. Absence of
  evidence is not a demonstrated divergence; allowlisting an unevidenced
  read-only route is a faithfulness/capture-to-confirm concern, not a
  safety-boundary breach (the allowlist stays deny-by-default; mutation/payment
  routes remain excluded). A valid hardening flag — capture a live trace, or mark
  it explicitly unverified and mirror `ARA0501P`'s context fields — but **not a
  confirmed bug**. (This mirrors the adjudication already recorded in
  `impl-audit-reverify-2026-07-22.md:154-164`.)

### Non-bug observations (unprovable, or invalid-input-only)

**search-selectors:**

- `sNowSel` hardcoded `"1"` (`payloads.py:44`): the app varies it (`"1"`
  departure / `"2"` arrival, `ara0101v.js:157`); we only expose the
  departure-variant, a legitimate app request. Cosmetic.
- `group_search_ajax_payload` clamps `psgNum` to `max(total,10)`
  (`payloads.py:258`) vs the app's raw `totPrnb` (`ara1001l.js:104,165`):
  identical on the valid group path (≥10); diverges only for an invalid
  <10-passenger group the app blocks at the UI.
- `dptTm1` set to the full `query.departure_time` (`payloads.py:227`) vs srtgo's
  hour-aligned `time[:2]+"0000"` (`srt.py:805`): only matters for a
  non-hour-aligned `departure_time`, and `dptTm` (not `dptTm1`) drives the time
  filter, so server impact is inconclusive.

**seat-timetable-fare:**

- `parse_mutual_verification_response` requires `msgCd` to be a non-`None` string
  (`parsers.py:419,423-426`) though the app (`ara1001l.js:232-241`) never reads
  `msgCd`; the documented Ara10130 `dsOutput0`
  (`full-api-analysis-2026-07-20.md:195,426`) is `{strResult,msgTxt,mutMrkVrfCd}`
  with no `msgCd`. If the live response omits `msgCd`, our parser rejects a valid
  `SUCC` — but the standard envelope elsewhere carries `msgCd`, so omission can't
  be proven.
- `parse_seat_selection_page` requires the literal marker `좌석선택`
  (`parsers.py:171-183`); the `arc02012` page is server-rendered and absent from
  the APK assets, so the marker is unverifiable.
- `seat_page_payload` uses the train row's `seatAttCd` whereas the app sends
  `rqSeatAttCd1` (the search-requested seat attr, default `'015'`,
  `ara0101v.js:132`); both equal `'015'` in fixtures, so no observed divergence.
- `get_seat_page` default `choiceSeatCount='1'` and `get_fare` default all-adult
  `PassengerCounts` differ from the app's search-time `totPrnb`/`psgInfoPerPrnb`:
  a caller-responsibility default, not a builder bug.

**notice-ticket (all unprovable — the notice list is absent from the decompile):**

- The notice list is **entirely absent** from the decompiled app: grep for
  `noticeList` / `noticeList.do` / `MB0101` / `POST_NO` / `CREATE_DATE` /
  `IS_NOTICE` / `IS_MAIN` / `SUBJ` across `analysis/apktool/assets` and
  `analysis/jadx/sources` returns **zero** hits. So `/main/noticeList.do`
  (`client.py:105`), `pageId=MB0101000000` (`client.py:106`), the
  `ErrorCode`/`ErrorMsg`/`noticeList` wrapper (`parsers.py:189-199`), and every
  notice row field originate from prior live capture, not the decompile — a
  divergence there is unprovable.
- Latent risk: the notice parser hard-requires `POST_NO` to be a JSON int
  (`parsers.py:218`) and six named string fields present-and-string on every row
  (`parsers.py:201-217`). The only fixture is synthetic. A real response with
  `POST_NO` as a numeric string, or any nulled/omitted field, would raise
  `SrtProtocolError` and reject the whole list. Flag for live capture.
- Ticket `pageNo` nuance: the decompile attaches no query string to `atc14017`
  (`SRWebActivity.java:1592`); `pageNo` appears only with `atc14016`. Our client
  sends `atc14017?pageNo=0`. Route+method match; the extra `pageNo` is unattested
  in the decompile but confirmed harmless by prior capture. Corollary: whether
  `atc14017` actually paginates by `pageNo` is unknown, so
  `get_ticket_list(page_no=N>0)` could silently return page 0.
- Our `get_ticket_list` returns `HtmlPage.text` only (no structured ticket
  fields): a capability gap vs srtgo's `reservListMap`, not a correctness bug —
  our HTML `atc14017` approach mirrors the app's native WebView landing.

**netfunnel-transport-safety:**

- The client hydrates search state via `GET /ara/selectListAra10007_n.do`
  (`client.py:231`); the app's evidenced hydration source is
  `GET /ara/ara0101v.do` (the app only ever POSTs `Ara10007`). The GET is not
  app-evidenced but cannot be shown to fail (the endpoint may accept GET).
- `POST /main/noticeList.do` is not in the offline JS bundle (live-traffic-only
  per prior docs) — plausible, unprovable.
- The UA omits the `; wv)` WebView token and `Build/` segment of a real Android
  WebView UA; these are device-variable and not gated by these read endpoints.
- By design the client performs only the act_10 (`5101`) getTid and passes that
  `netfunnelKey` to search, rather than srtgo's full `5002`/`5004` handshake,
  relying on `NET000001` retry — matches the "only act_10 remains" expectation.

## Ground-truth caveats & residual risks

The ground-truth rule is *trust the decompile*; where the app source is
server-rendered or absent from the offline bundle, srtgo is the only working wire
reference and some items are simply **unverifiable**.

- **Server-rendered login (`login.do`).** The actual `check`/`auto`/`page`/
  `login_referer` values **and** the JSON success envelope (`RTNCD`/`MSG`) are
  server-rendered and absent from the offline APK bundle (jadx+apktool), so they
  cannot be confirmed from the decompile. srtgo is the only working wire
  reference. `impl-audit-reverify-2026-07-22.md:101-106` already flags this and
  recommends a **live smoke test**.
- **Login success gate (one-way risk, not filed as a bug).** Our code requires
  `userMap.RTNCD == "Y"` (`session.py:65`), but srtgo never reads `RTNCD` — it
  treats login as success when no Korean error substring is present and reads
  `userMap.MB_CRD_NO`/`CUST_NM`/`MBL_PHONE` (`srtgo/srt.py:715-726`). If a real
  success response ever omits `RTNCD`, our login would false-negative (raise
  `SrtAuthError` on success). Docs claim `RTNCD=Y` from prior runtime capture, so
  likely fine, but it is a one-way risk.
- **Error-message source (message-only).** On failed login we read `userMap.MSG`
  (`session.py:66`) whereas srtgo reads top-level `r.json()['MSG']`
  (`srt.py:716,718`). Affects only the human-readable message, not pass/fail. Our
  fixtures nest `MSG` inside `userMap`, but that fixture is self-authored.
- **IP-block path (edge case).** `Your IP Address Blocked` is returned as **plain
  text** and handled via `r.text` in srtgo (`srt.py:719-720`); our
  JSON-expecting `post_form` would raise `SrtProtocolError` ("body was not valid
  JSON") rather than a clean auth error.
- **`ARA0502P` map selector.** The only allowlisted read route with no decompiled
  support; see the rejected-candidates note above. Recommended action: capture a
  live trace to confirm the endpoint and payload, or mark
  `get_station_map_selector` explicitly unverified and mirror `ARA0501P`'s
  station-context fields (`sDptStnNm`/`sArvStnNm`/`sDptStnCd`/`sArvStnCd`).

### Recommended next steps

1. Fix **B1** and **B2** (Medium) — both are provable against bundled JS and both
   are reachable on the live search path.
2. Fix **B3** and **B4** (Low) as faithfulness/robustness cleanups.
3. Run a **live login smoke test** to settle the rejected auth-session items and
   the `RTNCD`/`MSG`/IP-block residual risks.
4. Capture a **live station-map trace** to confirm or retire `ARA0502P`.

---

*Not re-reported: `docs/analysis/impl-audit-2026-07-22.md` is stale — its B1
(ARA0403P route + safety), B4 (passenger ordering), and B11 (station extra
fields) are already fixed in the current source.*
