# SRT Audit — Slice: 열차조회 · 역 · 운임 (Train Search / Stations / Fare)

Scope owner: this pass. Repo: `srt-mobile-api`. Library root:
`src/srt_mobile_api/`. App evidence root: `analysis/` (apktool authoritative
for constants/branches, jadx for readability). Prior-audit cross-reference:
`docs/analysis/impl-audit-2026-07-22.md` + 5 reverify passes +
`docs/IMPLEMENTATION_PROGRESS.md` + `docs/VERIFICATION.md` (2026-07-26 live
capture). This pass explicitly avoided re-deriving what those already settled
and re-verified; it instead re-confirmed the settled state at each point that
touches my slice and searched the parts those passes did not name.

## Method

1. Read the merged spec (`docs/analysis/srt-app-api-library-spec-2026-07-09.md`)
   for the target contract shape.
2. Diffed `stations.py` against `stationInfo.js` programmatically (full
   code/name comparison, not sampling).
3. Read `exceptStation.js` (named explicitly in my brief) and grepped the
   whole bundle for its consumer — none found.
4. Read `ara0101v.js` (booking form defaults, popup triggers, `btn_inquiry`
   client-side guards) and `ara1001l.js` (`fn_search`, its `oData`, the
   mutual/timetable/fare builders) end to end for the request shapes in scope.
5. Read `payloads.py`, `parsers.py`, `models.py`, `stations.py`, and the
   relevant slice of `client.py` end to end, cross-checking each field against
   the app source line the code's own comments cite (not just trusting the
   comment — the app lines were opened independently for the items below).
6. Cross-checked `commCode.js`'s `stlbTrnClsfCd`/`trnGpCd` code tables against
   `TRAIN_GROUP_OPTIONS`.
7. Checked prior-audit bug tables (B1–B13 across 6 docs) against the CURRENT
   code to confirm they are fixed, not to re-file them.

## Extracted app surface vs. library — summary table

"App evidence" cites are `file:line`; apktool paths are relative to
`analysis/apktool/assets/offline/`. "Status" is my classification for THIS
pass, not a re-statement of prior audits.

| # | Feature / endpoint | App evidence | Library counterpart | Status |
|---|---|---|---|---|
| 1 | Station code→name table (344 codes) | `js/stationInfo.js:29-433` (`stationList`, both SRT and korail groups) | `stations.py:STATION_NAMES_BY_CODE`, `station_name_by_code()` | **Match** — full programmatic diff: 344/344 codes present, 0 name mismatches, 0 extras either direction |
| 2 | `getStnNameByCd` semantics (unknown code → `""`) | `sub/main.html:613-621` (per `stations.py` docstring, not independently re-opened this pass) | `stations.py:361-369` | Match (per prior audits + docstring citation) |
| 3 | Adjacent-station exclusion table (`excpStationList`, 19 pairs) + `getStationFlag(cd1,cd2)` | `js/exceptStation.js:18-51` | **none** — no reference anywhere in `src/` or `docs/analysis/` | **Missing** (S2-01) |
| 4 | Search request `oData` (11 fields: `chtnDvCd,dptDt,dptTm,dptRsStnCd,arvRsStnCd,stlbTrnClsfCd,psgNum,seatAttCd,arriveTime,trnGpCd,trnNo`) | `js/ara/ara1001l.js:98-165` | `payloads.search_ajax_payload` | Match |
| 5 | 직통/환승 derivation (`chtnDvCd = jrnyTpCd=="11" ? "1" : "2"`) | `ara1001l.js:98` | `payloads.py:98-104`, `SEARCH_CONNECTION_DIRECT/TRANSFER` | Match |
| 6 | Search URL selection by `grpDv` alone (Ara10007 vs Ara10082); connection type does not change the path | `ara1001l.js:174-181` | `client._prepare_search:552` | Match |
| 7 | Group search min-party guard (`totPrnb>=10` else alert, no send) | `ara0101v.js:549-554` | `payloads.group_search_ajax_payload:670-674` raises `ValueError` | Match |
| 8 | Personal search max-party guard (`totPrnb<=9` else alert "10매 이상은 단체예약입니다", no send) | `ara0101v.js:559-563` | **none** — `search_trains`/`search_ajax_payload` accept any `passengers.total` | **Missing** (S2-04, low) |
| 9 | Same-station guard (`dptStn.text()==arvStn.text()` else alert, no send) | `ara0101v.js:566-569` | **none** — `TrainSearchQuery.__post_init__` (`models.py:216-224`) checks non-empty + date/time format + `train_group_code` membership only | **Missing** (S2-03) |
| 10 | Train-group code table (`300`→SRT/`17`, `900`→KTX+SRT/`00`, `109`→전체/`05`) | `commCode.js:186-274` (`trnGpCd`/`stlbTrnClsfCd` groups, `rmk:"main"` on 300/900/109) | `payloads.TRAIN_GROUP_OPTIONS` | Match (independently re-verified against `commCode.js`, not just the prior spec doc) |
| 11 | Passenger compaction (`psgTpCd`/`psgInfoPerPrnb`, non-zero types packed contiguous, 유아 folded into 어린이 count + separate `infantCnt`, 청소년 as `psgTpCd6`) | `ara0101v.js:824-836`, `commCode.js` (`psgTpCd` 1-5), live 2026-07-26 echo capture (`IMPLEMENTATION_PROGRESS.md:1694-1715`) | `payloads._passenger_slot_counts/_compact_passenger_slots/_passenger_fields`, `models.PassengerCounts` | Match — confirms prior audit's B1/B2 (2026-07-22) were fixed and since live-reverified (2026-07-26), superseding that audit's conclusion |
| 12 | `psgGridcnt` = distinct filled-type count, not head count | `ara0101v.js:826-836` (`idx-1`) | `payloads._distinct_passenger_type_count` | Match — confirms prior B12/B1 fixed |
| 13 | Hydration GET `grpDv` reflects the group checkbox's `lfn_setRsv` BEFORE navigating to the Ara10007 result/hydrate page | `ara0101v.js:522` (`lfn_setRsv({"grpDv": checked?"1":"0"})`, set before `btn_inquiry`/`fn_moveSearchPage` navigates) | `payloads.search_page_payload:554` hardcodes `"grpDv": "0"` unconditionally, regardless of `group=` | **Incorrect** (S2-02, low — proven harmless by the 2026-07-26 live group-search capture, which returned 10 rows successfully through this exact code path) |
| 14 | NetFunnel helper (`act_10`), single bounded retry on `NET000001` | `common/netfunnel.js`, `ara1001l.js` | `client._search_with_retry`, `netfunnel.py` | Match (out of my slice's authority — netfunnel/safety is a separate reviewer's area per the task split, only cross-checked at the call boundary) |
| 15 | Selector endpoints in scope: station (ARA0501P), station-map (ARA0502P), seat-option (ARA0701P), train-group (ARA0201V) | `ara0101v.js:150-260` | `client.get_station_selector/get_station_map_selector/get_seat_option_selector/get_train_group_selector` + `payloads.py` builders | Match |
| 16 | `dsOutput0` metadata (`msgCd`,`strResult`,`msgTxt`,`qryCnqeCnt`,`fllwPgExt`) | `ara1001l.js:190-210` | `parsers._parse_search_metadata` → `TrainSearchMetadata` | Match, incl. non-negative-int-or-ASCII-digit-string tolerance for `qryCnqeCnt` |
| 17 | Search top-level wrapper (`ErrorCode`/`ErrorMsg` personal, `ERROR_CODE`/`ERROR_MSG` group) | `ara1001l.js:190-193` (`ErrorCode==-1`) | `parsers._normalize_search_wrapper`, `parse_train_search_response:2392-2394` | Match; see note under Findings (considered, not filed) |
| 18 | `dsOutput1` row columns (~35 identified: `trnNo,trnGpCd,stlbTrnClsfCd,trnClsfCd,runDt,dptDt,dptTm,arvDt,arvTm,dptRsStnCd,arvRsStnCd,dptRsStnNm,arvRsStnNm,dptStnRunOrdr,arvStnRunOrdr,dptStnConsOrdr,arvStnConsOrdr,seatAttCd,runTm/trnRunTm,trnRunOrdr/trnOrdrNo,ocurDlayTnum,expnDptDlayTnum,gnrmRsvPsbStr,sprmRsvPsbStr,rsvWaitPsbCd,stmpRsvPsbFlgCd,*CdNm x4,rcvdAmt,trainDiscGenRt,rcvdFare,trnCpsCd1-5,gnrmBkclDcntRt,sprmBkclDcntRt`) | `ara1001l.js` row consumers + spec §5 `TrainRow` + live 2026-07-26 capture | `parsers._parse_search_train_rows` → `models.TrainSummary` | Match — all typed, `raw=row` also preserved |
| 19 | `*RsvPsbImg` / `*RsvPsbColor` (UI icon/color hints) | `ara1001l.js:26-38` (`S_IMG_*`, `S_COL_*` constants), spec §5 lists them as `TrainRow` fields | Not promoted to typed `TrainSummary` fields; reachable only via `TrainSummary.raw["gnrmRsvPsbImg"]` etc. `payloads._standby_row_image` reads it from `.raw` (documented, deliberate) | **Partial** (S2-05, info/low — data is not lost, just not surfaced on the typed model the spec itself describes) |
| 20 | Timetable request (Ara12009: `stnCourseNm,trnSort,runDt,trnNo`), `trnNo` zero-padded to 5 | `ara1001l.js:1176-1185`, live-corrected 2026-07-26 (`trnSort` = display name via `getStlbTrnClsfCdNm`, not `trnClsfCd`) | `payloads.timetable_payload`, `_train_sort`, `_station_course` (`train_no.zfill(5)`) | Match — independently re-verified zero-padding and `stnCourseNm` construction against `ara1001l.js:1176-1185` this pass |
| 21 | Fare request (Ara13010: `stnCourseNm,trnSort,runDt/runDt1,trnNo/trnNo1,chtnDvCd,dptRsStnCd1,arvRsStnCd1,dptRsStnCd2/arvRsStnCd2/runDt2/trnNo2 blank,psgTpCd1-6,psgInfoPerPrnb1-6`) | `ara1001l.js:1203-1234`, live-corrected 2026-07-26 (was sending `passenger1..5`, now correct `psgTpCd*`) | `payloads.fare_payload` | Match — confirms prior B3/B5/B6 (2022-07-22 audits) fixed and live-reverified |
| 22 | Fare response parsing — reads only the FIRST fare-bearing `<table>`, discarding the transfer page's unpopulated second-leg placeholder table (`0원` rows with real-looking labels) | Live-captured 2026-07-26 fare page (`trainPayInfo1`/`trainPayInfo22`), documented in `parsers.parse_fare_page` docstring | `parsers.parse_fare_page:1035-1101` | Match — deliberate, well-evidenced; confirmed correct this pass by reading the parser directly (not just trusting the docstring) |
| 23 | Timetable response parsing — station name is NOT in the HTML, only a per-row `<script>getStationNameByCode('CODE')</script>`; resolved via the same static `stations.py` table | Live-captured 2026-07-26 (`stationNm_N` cell empty/unclosed) | `parsers.parse_timetable_page`, `_TimetableTableParser` | Match |
| 24 | 환승 (transfer) search: same endpoint, `chtnDvCd` only delta; response is ONE ROW PER LEG, paired by shared `trnOrdrNo` | `ara1001l.js:98,159,1206`; live-confirmed 2026-07-26 pairing (동대구→광주송정, `trnOrdrNo` 1-3) | `payloads.search_ajax_payload(transfer=True)`, `parsers.pair_transfer_itineraries`, `models.TransferItinerary` | Match — construction validates connection point, leg order (time), distinctness |
| 25 | Fare/get_fare has no dedicated two-leg transfer method | `ara1001l.js` fare form has `dptRsStnCd2` etc. slots, live page renders a second table when populated | `client.get_fare(train, passengers)` takes one `TrainSummary`; caller must call it twice (once per leg) for a transfer itinerary | Not filed — `TransferItinerary.legs` each are full independent `TrainSummary`s and `fare_payload` derives leg-1 fields from whichever train is passed, so two calls reproduce the same per-leg fares; reasonable API shape, not a protocol gap |
| 26 | Pagination (`fn_search(sPagingDptTm)`, cursor = `dptTm[:5]+"1"`, `trnNo=""`, `fllwPgExt` gate) | `ara1001l.js:65-95` | `client.iter_train_search_pages`, `payloads.search_continuation_payload`, `parsers.parse_search_has_following_page` | Match (per prior audits; only spot-checked this pass, not the primary target) |

## Findings

### S2-01 — `exceptStation.js` adjacent-station exclusion list has no library counterpart

- **Category:** missing (severity: low — enforcement by the real server is
  unproven, see below)
- **App evidence:** `analysis/apktool/assets/offline/js/exceptStation.js:18-51`.
  The app ships a 19-pair `excpStationList` (수서↔동탄, 동탄↔지제, 지제↔천안아산,
  천안아산↔오송, 오송↔대전, 김천구미↔동대구, 동대구↔신경주, 신경주↔울산, 울산↔부산,
  오송↔공주(코드상 0020=부산, see quirk below), 익산↔정읍, 정읍↔광주송정, 광주송정↔나주,
  광주송정↔목포, 나주↔목포) plus `getStationFlag(cd1,cd2)`, which returns `false`
  (disallowed) when a pair is in the list in either order.
- **Library evidence:** no hit for `exceptStation`, `getStationFlag`, or
  `excpStation` anywhere under `src/srt_mobile_api/` or `docs/analysis/`.
  `stations.py` implements only `STATION_NAMES_BY_CODE`/`station_name_by_code`.
  `TrainSearchQuery.__post_init__` (`models.py:216-224`) validates non-empty
  codes, `YYYYMMDD`/`HHMMSS` format, and `train_group_code` membership — it does
  not check the departure/arrival pair against any exclusion table.
- **Detail:** if this list is enforced anywhere in the real booking flow, a
  caller could construct a `TrainSearchQuery` for a disallowed adjacent pair
  (e.g. 수서→동탄) that the app itself would never let a user submit, and get
  an unpredictable server response instead of a clear client-side rejection.
  **I could not find the call site for `getStationFlag` anywhere in the
  bundle** (`grep` across all of `analysis/apktool/assets/offline/` returns
  only the function's own definition, line 41) — the function is defined but
  provably unreferenced in every file this repo has. That means I cannot show
  the app enforces it at all, let alone that the server does independently of
  the client. This is reported as a gap in the library's validation surface
  relative to app-shipped data, not as a proven functional defect — treat the
  severity as low and the enforcement question as genuinely open.
- **Suggested fix:** either (a) capture a live search against one of the 19
  excluded pairs to determine actual server behavior, then decide whether to
  add a pre-flight check mirroring `getStationFlag`, or (b) if left
  unimplemented, note the gap explicitly in `stations.py`'s module docstring
  so a future reader doesn't assume the app-shipped table has no purpose.

**Info, not a finding — app-side data quirk in `exceptStation.js`:** several
entries carry a station CODE that does not match its own NAME label, e.g. line
31 `exceptStn_cd1:"0297"` (오송, correct) paired with `exceptSstn_cd2:"0020"`
labelled `exceptStn_nm2:"공주"` — but `0020` is 부산 (0514 is 공주) per
`stationInfo.js` itself. Lines 35-36 similarly carry `exceptStn_cd1:"0033"`
(정읍) mislabelled `exceptStn_nm1:"광주송정"`. This is a defect in the app's own
shipped asset, not in `stations.py` (which correctly maps every code to its
real name per the diff in table row 1). Noted so nobody "fixes" `stations.py`
to match the app's mislabeled data.

### S2-02 — Group-search hydration GET always sends `grpDv="0"`, even for a group search

- **Category:** incorrect (severity: low — functionally unproven to matter;
  live evidence shows the current code path already works)
- **App evidence:** `analysis/apktool/assets/offline/js/ara/ara0101v.js:522`
  — the 단체(group) checkbox handler runs `lfn_setRsv({"grpDv": $(this).is(":checked") ? "1" : "0"})`
  against the shared reservation state BEFORE `btn_inquiry` navigates to
  `GET /ara/selectListAra10007_n.do` (the hydration/result page). The
  navigation serializes that state, so a real group search's hydration GET
  carries `grpDv=1`.
- **Library evidence:** `src/srt_mobile_api/payloads.py:554`
  (`search_page_payload`) hardcodes `"grpDv": "0"` unconditionally; the
  function takes no `group` parameter. `src/srt_mobile_api/client.py:540-560`
  (`_prepare_search`) calls `_hydrate_search(query, key, transfer=transfer)`
  with no group flag, then separately builds the POST body via
  `group_search_ajax_payload`, which DOES correctly force `payload["grpDv"]="1"`
  (`payloads.py:676`) — but only on the POST, after hydration already happened
  with `grpDv="0"`.
- **Detail:** the actual search POST body is correct (`grpDv=1`, correct URL
  `Ara10082`), which is why the 2026-07-25/26 live group-search runs recorded
  in the spec (`srt-app-api-library-spec-2026-07-09.md:622`, "Group search:
  Success, app JSON IRG000000, 10 rows") succeeded through this exact code
  path — this divergence has already been exercised live without failing.
  What's wrong is the fidelity of the intermediate hydration step to the
  app's actual navigation state, which could matter if the server's rendered
  hidden-field defaults differ between a `grpDv=0` and `grpDv=1` hydration
  (e.g. a different NetFunnel service id, different default seat/passenger
  hidden fields) that then get carried into the POST via `hydrated_fields`.
  No evidence either way beyond the successful live run already on record.
- **Suggested fix:** thread a `group: bool` parameter through
  `search_page_payload`/`_hydrate_search` and set `"grpDv"` accordingly, for
  request-shape fidelity, even though no live failure is currently on record.

### S2-03 — No same-station (departure == arrival) validation

- **Category:** missing (severity: low)
- **App evidence:** `analysis/apktool/assets/offline/js/ara/ara0101v.js:566-569`
  — `btn_inquiry`'s handler: `if ($("#btn_dpt_stn").text() == $("#btn_arv_stn").text()) { srtAlertBoxDivShow("알림","출발역과 도착역이 같습니다.",...); return; }`,
  blocking submission before any request is sent.
- **Library evidence:** `src/srt_mobile_api/models.py:216-224`
  (`TrainSearchQuery.__post_init__`) checks only that both codes are non-empty
  and that date/time strings are well-formed; it never compares
  `departure_station_code` to `arrival_station_code`.
- **Detail:** a caller can construct `TrainSearchQuery(departure_station_code="0001", arrival_station_code="0001", ...)`
  without any error, and `search_trains`/`search_ajax_payload` will send it.
  Real-server behavior for this case is unverified (not captured live), so
  the concrete failure mode (empty result vs. a distinct app error vs.
  something else) is unknown — reported as a missing pre-flight guard the app
  demonstrably has, not as a proven wrong-answer bug.
- **Suggested fix:** raise `ValueError` in `TrainSearchQuery.__post_init__`
  when the two codes are equal, mirroring the app's own guard.

### S2-04 — No personal-search max-party guard (app blocks `totPrnb>9` outside group mode)

- **Category:** missing (severity: low)
- **App evidence:** `analysis/apktool/assets/offline/js/ara/ara0101v.js:559-563`
  — the same `btn_inquiry` handler, non-group branch: `if (lfn_getRsv("totPrnb") > 9) { srtAlertBoxDivShow("알림","10매 이상은 단체예약입니다...",...); return; }`.
  This is the exact symmetric counterpart of the group-mode `totPrnb<10` guard
  that IS implemented (`payloads.GROUP_MIN_PARTY_SIZE`,
  `group_search_ajax_payload:670-674`).
- **Library evidence:** `search_trains`/`search_ajax_payload` place no upper
  bound on `PassengerCounts.total` for a non-group `TrainSearchQuery`.
- **Detail:** a caller can request a 15-passenger personal (non-group) search
  and the library will send it, something the app's own UI refuses to submit.
  Unverified whether the server enforces this itself; likely a pure
  client-side UX nudge toward the group flow, so functional impact is
  probably nil, but it is a concrete, evidenced asymmetry with the
  already-implemented group-side check.
- **Suggested fix:** either raise (mirroring the app exactly) or at minimum
  document the asymmetry next to `GROUP_MIN_PARTY_SIZE`.

### S2-05 — `*RsvPsbImg` / `*RsvPsbColor` fields not promoted to `TrainSummary`

- **Category:** partial (severity: info/low)
- **App evidence:** `analysis/apktool/assets/offline/js/ara/ara1001l.js:26-38`
  defines `S_IMG_SOUT/PSBL/PSBLK/PSBL_S/PSBL_SK/WAIT/WAIT_S` and
  `S_COL_PSBL/PSBLK/PSBLE/WAIT`, consumed by `fn_postSearch` to color/iconify
  each row's general/special-seat cells. `docs/analysis/srt-app-api-library-spec-2026-07-09.md:229-230`
  lists `sprmRsvPsbImg/gnrmRsvPsbImg/sprmRsvPsbColor/gnrmRsvPsbColor` as
  intended `TrainRow` fields.
- **Library evidence:** `parsers._parse_search_train_rows` (`parsers.py:2430-2582`)
  does not read any of these four keys into typed `TrainSummary` attributes.
  They remain reachable only via `TrainSummary.raw["gnrmRsvPsbImg"]` etc.
  `payloads._standby_row_image` (`payloads.py:1123-1131`) confirms this is
  deliberate — it explicitly reads from `.raw` with a comment that promoting
  a "UI asset name" to a typed field was judged not worth it.
- **Detail:** not a data-loss bug (`raw=row` is always preserved, and the
  string-label fields `general_seat_availability`/`special_seat_availability`
  cover the human-readable availability text), but it is a gap relative to
  the field list the project's own spec document describes for `TrainRow`.
  A caller wanting to reproduce the app's exact icon/color per row (rather
  than just the availability string) has to reach into `.raw` themselves.
- **Suggested fix:** none required if the raw-dict access pattern is the
  intended contract; if the spec document's field list is meant to be
  authoritative, either promote the four fields or amend the spec.

## Verified correct (not filed as bugs, listed for completeness)

- Station table: full 344/344 code/name match, `station_name_by_code` unknown
  → `""` semantics correct.
- `TRAIN_GROUP_OPTIONS` (`300`/`900`/`109` → name + `stlbTrnClsfCd`)
  independently re-verified against `commCode.js`'s `trnGpCd`/`stlbTrnClsfCd`
  tables (not just the prior spec doc) — exact match.
- Passenger compaction, 유아 fold + `infantCnt`, 청소년 `psgTpCd6` — confirms
  prior-audit bugs (2026-07-22 B1/B2/B4/B5 in the 07-22 audit numbering) are
  fixed and were since independently re-verified against a 2026-07-26 live
  echo capture, which supersedes the offline-only conclusion those 07-22
  audits were working from.
- `fare_payload`/`timetable_payload`: `trnNo` zero-padded to 5 digits,
  `stnCourseNm` built as `getStnNameByCd(dpt)+"-"+getStnNameByCd(arv)`,
  `trnSort` sourced from `stlbTrnClsfCd` via `getStlbTrnClsfCdNm` (not the
  absent `trnClsfCd`) — all independently re-verified against
  `ara1001l.js:1176-1185` / `:1203-1234` this pass, not merely trusted from
  the code's own comments.
- `parse_fare_page` correctly reads only the first fare-bearing table,
  avoiding the transfer page's unpopulated placeholder second-leg rows
  (`0원` rows with real-looking labels) — read and confirmed directly.
- `parse_timetable_page` correctly resolves station names from a per-row
  inline-script code via the shared static table, rather than mis-parsing the
  time-placeholder `-` cell as a name.
- Transfer search/pairing: same-endpoint `chtnDvCd` delta, one-row-per-leg
  response, `trnOrdrNo` grouping, `TransferItinerary` connection/order/
  distinctness validation — internally consistent, matches the documented
  2026-07-26 live capture.
- Search response wrapper (`ErrorCode`/`ErrorMsg` vs `ERROR_CODE`/`ERROR_MSG`,
  exactly one required) matches app + spec. **Considered, not filed:** the
  success set `wrapper_code in {"","0"}` is stricter than the app's literal
  `ErrorCode==-1` check (any non–`-1` value, including hypothetical unseen
  codes, would let the app proceed to `dsOutput0.strResult`, while the
  library raises `SrtAppError` for anything outside `{"","0"}`). No live
  evidence the server ever emits such a value exists either way, and the
  strict rule is stated as an intentional design in the spec document itself
  — not filed as a finding.
- Selector endpoints (station/station-map/seat-option/train-group) in scope:
  route, method, and field sets match `ara0101v.js`.
- `Ara10131` (공공할인 search) is correctly registered in
  `safety.READ_ONLY_ROUTES` (`safety.py:356`) — checked because the constant
  definition and the registration are far apart in the file and looked
  suspicious at first read; confirmed both exist.

## Explicitly out of scope / not re-litigated

- Reservation, payment, cancellation, refund payload/response shapes — a
  different reviewer's slice per the task split; only touched where a search
  concept (station pair, passenger compaction, transfer pairing) is shared.
- NetFunnel wire-format internals (`5101` parsing, `js=yes` vs `js=true`) —
  the 2026-07-22 reverify docs already fixed and closed this; only the call
  boundary (`_search_with_retry`) was checked from my side.
- Group booking (mutation) — explicitly removed from this library per
  `docs/IMPLEMENTATION_PROGRESS.md`; group SEARCH (read-only) is in scope and
  covered above.
- 단체(group) reservation — out of scope (mutation, and explicitly a
  documented removed feature, not a library gap).

## Counting basis for the structured summary

"App functions extracted" is counted at field/endpoint/table granularity
across the rows in the summary table above, using each table row's own
sub-count where the row bundles multiple items (e.g. row 1 = 344 station
codes, row 3 = 19 exclusion pairs, row 18 = ~35 row columns, row 4/21 = their
own field counts). This yields:

- Station codes: 344 (344 implemented)
- Exclusion pairs: 19 (0 implemented)
- Search request core fields (row 4): 11 (11 implemented)
- Search request extended/passenger fields (rows 11-12, 16-17): ~15 field
  concepts (15 implemented)
- Client-side pre-flight guards (rows 7-9): 3 (1 implemented — group min;
  2 missing — same-station, personal max)
- Hydration fidelity (row 13): 1 (0 — incorrect)
- Selector endpoints (row 15): 4 (4 implemented)
- Timetable fields (row 20): 4 (4 implemented)
- Fare fields (row 21): ~20 (20 implemented)
- `dsOutput0` metadata (row 16): 5 (5 implemented)
- `dsOutput1` row columns (rows 18-19): 39 identified, 35 promoted to typed
  fields + 4 raw-only (partial)
- Transfer pairing (row 24): counted as 1 mechanism (implemented)

Total extracted ≈ 464 (344 + 19 + 11 + 15 + 3 + 1 + 4 + 4 + 20 + 5 + 39 - the
1 double-counted transfer mechanism folded into rows already counted... see
note). Implemented ≈ 438. These are reasoned counts at the granularity shown
above, not a precise machine count — treat the ratio (~94%) as the useful
signal, not the exact integers.
