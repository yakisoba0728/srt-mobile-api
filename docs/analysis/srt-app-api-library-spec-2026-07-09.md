# SRT App API Library Spec

Date: 2026-07-09 KST
Last updated: 2026-07-15 KST
Scope: SRT Android app WebView APIs only  
Primary host: `https://app.srail.or.kr`  
Helper host: `https://nf.letskorail.com:443`

This document integrates the 20-way endpoint review behind the current
installable read-only library. Read-only sections describe usable contracts;
mutation-related requests, responses, and flows are retained only as historical,
non-implementable evidence and are not instructions for a future client.

No user credentials, cookies, NetFunnel keys, raw response bodies, or payment
tokens are stored here.

## 0. APK And Runtime Baseline

| Item | Value |
|---|---|
| APK file | `srt.apk` local artifact, not committed. |
| APK SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| APK size | `26,427,764` bytes |
| Package | `kr.co.srail.newapp` |
| Version | `2.0.41`, `versionCode=150` |
| SDK | `minSdk=18`, `targetSdk=35`, `compileSdk=35` |
| Runtime app UA suffix | `SRT-APP-Android V.2.0.41` |
| Manifest environment | `ENV=PRD` |
| Production WebView base | `https://app.srail.or.kr` |
| Development WebView base | `https://devapp.srail.or.kr` |
| Archive notes | No packaged `lib/*.so` was found in the APK tree, but Java paths reference native loaders for H2O/ERB, TransKey, and RAON/OnePass. |

Local reverse-engineering artifacts such as `build/apktool/`, `build/jadx/`,
and `build/*.txt` are generated evidence only. They are not required for using
this final spec and should stay out of git.

## 1. Scope Rules

| Class | Include in core library? | Rule |
|---|---:|---|
| `app.srail.or.kr` `.do` app endpoints | Read-only subset only | Only the current package's read routes are library surface; other app endpoints are evidence. |
| `nf.letskorail.com/ts.wseq` | Search helper only | The current library uses the `act_10` search gate; `act_19` remains non-implementable evidence. |
| `app.srail.co.kr/neo/...` native ticket route | Optional route alias | Found in native foreground notification flow. |
| `/srail-app/...` bundled/offline aliases | Optional/static | Present in assets; call only if a live route proves it is valid. |
| External Korail seatmap URL | No | Boundary for native WebView seatmap handoff, outside app API scope. |
| Real payment approval gateway | No | High-risk production payment flow. Only app ARD page entry was tested with invalid dummy state. |
| FIDO, push broker, mobile ID, fax, map/taxi apps | Optional integration modules | Native SDK/app handoff, not train booking business API. |

## 2. Evidence Levels

| Evidence | Meaning |
|---|---|
| Runtime success | Called against production app endpoint and returned expected app-level response. |
| Runtime rejected | Endpoint reached, but intentionally invalid payload was rejected. |
| Dummy page entry | Endpoint returned HTML with dummy reservation/payment-like state; not a real business success. |
| Static only | Found in APK/offline assets/native code, not runtime-called. |
| Helper | Needed to drive app flow, but not itself an SRT business endpoint. |
| Excluded | Deliberately outside app API scope or real-world side-effect boundary. |

## 3. Common HTTP Contract

| Item | Contract |
|---|---|
| Base URL | `https://app.srail.or.kr` for core app endpoints. |
| Method style | Mostly `POST` form-encoded for app Ajax/page transitions; some `GET` page loads. |
| Body format | `application/x-www-form-urlencoded`; current read-only calls send only their documented fields. Mutation forms are never constructed or forwarded. |
| Response types | Mixed `text/html`, JSON, and NetFunnel JavaScript snippets. |
| Session | Cookie-backed WebView session; keep one cookie jar per logged-in user/session. |
| User agent | App-like Android WebView UA with `SRT-APP-Android V.2.0.41` suffix was accepted. |
| Headers | Use normal WebView-style headers; Ajax calls generally include `Origin` and `X-Requested-With`. |
| Encoding | Treat response text as UTF-8 unless server declares otherwise. |
| Logging | Redact credentials, cookies, NetFunnel keys, PNRs, card-shaped values, and raw HTML by default. |

Native WebView settings observed statically:

| Setting | Observed behavior |
|---|---|
| JavaScript | Enabled. |
| DOM storage | Enabled. |
| Multiple windows | Enabled. |
| JavaScript window open | Enabled. |
| Mixed content | Allowed. |
| Third-party cookies | Allowed. |
| File URL universal/file access | Enabled in reviewed paths. |
| Safe Browsing | Disabled in manifest metadata. |
| SSL error | App can proceed after user confirmation. |

Routing caution: the initial PRD WebView URL is built from `app.srail.or.kr`,
but reviewed URL override logic does not prove a strict host allowlist for every
later HTTP(S) navigation. Treat `srbridge` exposure as tied to runtime page
trust, not only the initial base URL.

Evidence rule: page-entry endpoints and Ajax endpoints are distinct. Several
`.do` URLs return HTML pages containing forms or scripts, so a historical HTTP
200 observation does not establish a successful business operation or a library
interface.

## 4. Library Module Map

| Module | Responsibility |
|---|---|
| `SessionClient` | Cookie jar, base headers, login/logout/main/ticket page calls. |
| `NetFunnelClient` | Fetch and parse the read-only search `act_10` key; retry once on stale/missing-key app errors. `act_19` remains evidence-only. |
| `SearchClient` | Search page hydration, personal search, group search, pagination-safe parsing. |
| `SelectorClient` | Station/date/passenger/seat/train-group popup page contracts. |
| `TimetableFareClient` | Timetable and fare HTML calls plus tolerant parsers. |
| `SeatClient` | Read-only app-side seat-selection page parsing; no reservation-form construction. |
| `TicketClient` | Ticket/reservation list and static/native ticket route aliases. |
| `NativeBridge` | Optional interface for `srbridge`, push, biometric/FIDO, secure keyboard, external apps. |

Reservation, payment, cancellation, issuance, and other mutation endpoint facts
in this specification are historical, non-implementable evidence. No flag, no dry-run marker,
and no confirmation token authorizes mutation. Any future mutation interface
requires a separate safety design, new evidence, independent review, and explicit user authorization.

## 5. Recommended Core Models

### `SessionConfig`

| Field | Type | Notes |
|---|---|---|
| `base_url` | string | Default `https://app.srail.or.kr`. |
| `user_agent` | string | Include app suffix. |
| `device_id` | string | Sent to main page and native-like flows. |
| `cookie_jar` | object | Isolated per session. |
| `timeout` | number | HTTP timeout. |
| `tls_verify` | bool | Runtime script supported insecure mode only for local CA issues. |

### `LoginRequest`

| Field | Type | Notes |
|---|---|---|
| `srchDvCd` | string | Login id type. Runtime phone login used `3`. |
| `srchDvNm` | string | Login identifier; secret. |
| `hmpgPwdCphd` | string | Password; secret. |
| `check` | string | App form flag. |
| `auto` | string | Auto-login flag. |
| `login_referer` | string | Optional return page. |
| `deviceKey` | string | App/device key. |
| `page` | string | Optional app page field. |
| `customerYn` | string | App/server page field. |
| `ciUptYn` | string | App/server page field. |
| `dupInfoVal` | string | App/server page field. |

### `NetFunnelToken`

| Field | Type | Notes |
|---|---|---|
| `action` | enum | `act_10` for search, `act_19` for reservation. |
| `key` | string | Secret-like gate token; redact in logs. |
| `raw_type` | string | Example family `5101` / `5002`. |
| `code` | string | Parsed NetFunnel code. |
| `params` | map | Parsed response params. |

### `SearchPageState`

Hydrated from `GET /ara/selectListAra10007_n.do`. Store all hidden fields, not
only the documented ones, because the server-rendered form can change.

| Group | Important fields |
|---|---|
| Journey | `jobId`, `jrnyTpCd`, `jrnyCnt`, `grpDv`, `rtnDv`, `jrnySqno1`, `jrnySqno2`. |
| Train group | `trnGpCd1`, `trnGpCd2`, `trnGpNm1`, `trnGpNm2`, `stlbTrnClsfCd1`. |
| Stations | `dptRsStnCd1`, `dptRsStnCdNm1`, `arvRsStnCd1`, `arvRsStnCdNm1`. |
| Date/time | `dptDt1`, `dptTm1`, `arvDt1`, `arvTm1`, display fields such as `dptDtTmNm1`. |
| Passengers | `totPrnb`, `totPrnbNm`, `psgGridcnt`, `psgTpCd1..6`, `psgInfoPerPrnb1..6`, `infantCnt`. |
| Seat attrs | `rqSeatAttCd1`, `locSeatAttCd1`, `dirSeatAttCd1`, `seatAttNm1`, `seatAttCd`. |
| Gate | `netfunnelKey`, `adjStnScdlOfrFlg`, `dlayAcptFlg`. |
| Reservation handoff | `pnrNo`, `JRNYLIST_KEY`, `lumpStlTgtNo`, `tmpJobSqno1`, `tmpJobSqno2`, etc. |
| Seat slots | `seatNo1_1..9`, `seatNo2_1..9`, plus car/grid fields if present. |

### `TrainSearchRequest`

| Field | Notes |
|---|---|
| `chtnDvCd` | One-way/connection classification from app form. |
| `dptDt`, `dptDt1` | Departure date, `YYYYMMDD`. |
| `dptTm`, `dptTm1` | Departure time, `HHMMSS`. |
| `dptRsStnCd` | Departure station code. |
| `arvRsStnCd` | Arrival station code. |
| `stlbTrnClsfCd` | Train class filter. |
| `trnGpCd` | Train group filter. |
| `trnNo` | Optional train number filter. |
| `psgNum` | Total passenger count. |
| `seatAttCd` | Seat option code. |
| `arriveTime` | Optional arrival-time filter. |
| `tkDptDt`, `tkDptTm`, `tkTrnNo`, `tkTripChgFlg` | Ticket-change related fields. |
| `dlayTnumAplFlg` | Delay-related app flag. |
| `netfunnelKey` | Required fresh `act_10` key. |
| `disability` | Accessibility/disability flag. |
| `adjStnScdlOfrFlg` | Adjacent-station schedule offer flag. |

### `TrainSearchResponse`

| Field | Notes |
|---|---|
| `ErrorCode`, `ErrorMsg` | Personal-search top-level wrapper pair. |
| `ERROR_CODE`, `ERROR_MSG` | Group-search top-level wrapper pair. Exactly one complete observed pair is required; partial pairs, both pairs, and non-string values are protocol errors. A non-success wrapper is raised before dataset parsing. |
| `outDataSets.dsOutput0` | Result metadata. Can be array or object. |
| `outDataSets.dsOutput0.msgCd` | Runtime success: `IRG000000`. |
| `outDataSets.dsOutput0.strResult` | Runtime success: `SUCC`. |
| `outDataSets.dsOutput0.qryCnqeCnt` | Non-negative JSON integer in the retained runtime responses; strict ASCII decimal strings remain accepted for legacy compatibility. |
| `outDataSets.dsOutput0.fllwPgExt` | More-page flag. |
| `outDataSets.dsOutput1[]` | Train rows. Can be empty. |

The public `TrainSearchMetadata` retains the result code/status, normalized
non-negative query count, optional `Y`/`N` following-page flag, and repr-hidden message/raw
mapping. Search hydration may supply display station names only when the
request-context station code is present and exactly matches the response row's
station code. Missing or mismatched codes never invent a station name.

### `TrainRow`

| Field | Notes |
|---|---|
| `stlbTrnClsfCd` | Service class, selected SRT row used `17`. |
| `trnNo` | Train number; zero-pad to 5 digits for timetable/fare/seat follow-ups where needed. |
| `trnGpCd` | Train group, selected SRT row used `300`. |
| `trnClsfCd` | Train class code. |
| `runDt`, `dptDt`, `arvDt` | Date fields. |
| `dptRsStnCd`, `arvRsStnCd` | Station codes. |
| `dptRsStnNm`, `arvRsStnNm` | Optional response station names; otherwise the strictly code-matched hydrated request names may be used. |
| `dptTm`, `arvTm` | Time fields. |
| `dptStnConsOrdr`, `arvStnConsOrdr` | Station consist order. |
| `dptStnRunOrdr`, `arvStnRunOrdr` | Station run order. |
| `trnOrdrNo` | Non-negative JSON integer train order in retained runtime rows; strict ASCII decimal strings remain accepted for legacy compatibility. |
| `seatAttCd` | Seat attribute code. |
| `sprmRsvPsbStr`, `gnrmRsvPsbStr` | Special/general seat availability labels. |
| `sprmRsvPsbColor`, `gnrmRsvPsbColor` | UI color hints. |
| `sprmRsvPsbImg`, `gnrmRsvPsbImg` | UI image/status hints. |
| `trainDiscGenRt` | Discount/rate field. |
| `rcvdAmt` | Fare/amount field when present. |
| `stmpRsvPsbFlgCd` | Standing/reservation flag. |

The typed row also retains evidenced run/consist orders, current/expected delay
strings, general/special/wait/standing availability strings, received amount,
and discount rate without interpreting their display vocabularies.

## 6. Endpoint Matrix

### Session, Main, Ticket

| Evidence | Method | Endpoint | Request | Response and success rule |
|---|---:|---|---|---|
| Runtime success | GET | `/login/login.do` | No body. Keep cookies. | HTML login page, HTTP 200. |
| Runtime success | POST | `/apb/selectListApb01080_n.do` | `LoginRequest` form. | JSON `userMap.RTNCD=Y`; `userMap.MSG` user-facing message. |
| Static only | POST | `/srail-app/login/loginOut.do` | Bundled logout form; preserve hidden `login_referer` if present. | Runtime not called. |
| Runtime success | GET | `/main/main.do` | Query `deviceId`, optional `pushMsg`. | HTML app main page, HTTP 200. |
| Static only | GET | `/srail-app/main/main.do` | Static/offline alias found in bundled/native references. | Runtime not called; do not prefer over `/main/main.do`. |
| Runtime success | GET | `/ara/ara0101v.do` | No body after login. | HTML booking start page. |
| Runtime success | POST | `/main/noticeList.do` | `pageId=MB0101000000`. | JSON with `noticeList[]`; runtime returned 2 notices. |
| Runtime success | GET | `/atc/selectListAtc14017_n.do?pageNo=0` | Query `pageNo`. | HTML ticket/reservation list; before/after negative reservation checks were identical. |
| Static/native | GET | `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0` | Query `pageNo`. | Foreground notification/native ticket route candidate; runtime not called. |
| Static only | GET | `/srail-app/atc/selectListAtc14016_n.do?pageNo=0` | Query `pageNo`. | Offline marker/cached ticket route; runtime not called. |

### Popup And Selector Pages

These are HTML popup pages. Stable contract is the callback payload used by the
app JavaScript, not a fixed DOM parser.

| Evidence | Method | Endpoint | Request | Callback/response contract |
|---|---:|---|---|---|
| Runtime success | POST | `/common/ARA/ARA0501P/view.do` | `reqCode=1`, station names/codes, `sNowSel`, `chk_rtrp`, `page=ARA0101`, `boolRtrp`. | Station selector HTML; callback fields `startStnNm`, `startStnCd`, `arrivalStnNm`, `arrivalStnCd`. |
| Runtime success | POST | `/common/ARA/ARA0502P/view.do` | `reqCode=2`, `chk_rtrp`, `sNowSel`, `page`, `boolRtrp`. | Station map selector HTML; same station callback fields. |
| Static only | POST | `/common/ARA/ARA0401P/view.do` | `reqCode=3/4`, `selectDay`, `selectDt`. | Legacy/bundled date selector path. |
| Runtime success | POST | `/common/ARA/ARA0403P/view.do` | `reqCode=3`, `selectDay`, `selectDt=YYYYMMDD`, `selectTime=HH`. | Date/time selector HTML; callback `choiceDate`. |
| Runtime success | POST | `/common/ARA/ARA0901P/view.do` | `reqCode=6`, `isOrg`, `passenger1..6`, `totalPessnger`. | Passenger popup HTML; callback `passenger1..5`; preserve `totalPessnger` typo. |
| Runtime success | POST | `/common/ARA/ARA0701P/view.do` | `reqCode=5`, `rqSeatAttCd`, `locSeatAttCd`, `seatAttNm`. | Seat option HTML; callback `seatOption`, `seatPosition`, `seatOptionString`; direction defaults to `009`. |
| Runtime success | POST | `/common/ARA/ARA0201V/view.do` | `reqCode=7`, `trnGpCd`, `trnGpCdNm`. | Train group HTML; callback `trainOption`, `trainOptionNm`. |

Train-group mapping observed from app logic:

| User option | App value | Meaning |
|---|---|---|
| SRT | `300` | SRT only; maps to `stlbTrnClsfCd=17`. |
| KTX+SRT | `900` | Combined search; app/server normalization observed around `00`. |
| 전체 | `109` | All; app/server normalization observed around `05`. |

### Search And Availability

| Evidence | Method | Endpoint | Request | Response and success rule |
|---|---:|---|---|---|
| Helper | GET | `https://nf.letskorail.com:443/ts.wseq` | Query `opcode=5101`, `sid=service_1`, `aid=act_10`, `js=true`, timestamp. | JavaScript snippet containing key; inject as `netfunnelKey`. |
| Runtime success | GET | `/ara/selectListAra10007_n.do` | Query/form-like hydrated search state plus fresh `netfunnelKey`. | HTML result page containing `seatSearchForm`. This is hydration, not train-list JSON. |
| Runtime success | POST | `/ara/selectListAra10007_n.do` | `TrainSearchRequest` form with fresh `act_10` key. | JSON; success when `msgCd=IRG000000`, `strResult=SUCC`; train rows in `dsOutput1[]`. |
| Runtime success | POST | `/ara/selectListAra10082_n.do` | Same request family; group flow uses larger `psgNum`, app `grpDv=1`. | Same JSON shape as personal search; runtime group search returned 10 rows. |
| Expected failure | POST | `/ara/selectListAra10007_n.do` | Search form without fresh NetFunnel key. | App-level failure `NET000001`. Fetch a fresh `act_10` key and retry once. |

Search implementation notes:

| Concern | Rule |
|---|---|
| GET vs POST same URL | `GET /ara/selectListAra10007_n.do` hydrates/result page; `POST` performs Ajax search. |
| Pagination | `iter_train_search_pages(query, *, group=False, max_pages=10)` implements the static app `fn_search(sPagingDptTm)` contract. Existing search methods remain first-page-only. A continuation preserves the hydrated form/key and changes only `dptTm=last_row.dptTm[:5] + "1"` with `trnNo=""`; a bounded 2026-07-15 run observed two 10-row pages for both personal and group search. |
| Response shape | `dsOutput0` may be array or object; parser should normalize. |
| Empty results | HTTP 200 plus empty `dsOutput1[]` is a valid no-train result, not transport failure. |
| Pagination stops | Require exact `fllwPgExt=Y/N`; stop on `N`, an empty page, caller closure, or `max_pages`. Reject missing/invalid flags and repeated or non-progress cursors before another POST. |
| NetFunnel | Do not log the key. First-page search retains its full-flow one-refresh retry. A continuation `NET000001` refreshes key/hydration once and retries only that cursor. |

### Timetable And Fare

| Evidence | Method | Endpoint | Request | Response and parser rule |
|---|---:|---|---|---|
| Runtime success | POST | `/ara/selectListAra12009_n.do` | `stnCourseNm`, `trnSort`, `runDt`, zero-padded `trnNo` such as `00303`. | HTML timetable page. Parse table rows first; fallback to `HH:MM` regex. |
| Runtime success | POST | `/ara/selectListAra13010_n.do` | `stnCourseNm`, `trnSort`, `runDt`, `trnNo`, `chtnDvCd`, `dptRsStnCd1`, `arvRsStnCd1`, `runDt1`, `trnNo1`, `psgTpCd1..6`, `psgInfoPerPrnb1..6`, return-leg placeholders. | HTML fare page. Parse fare table first; store integer amount and raw label. |

Runtime fare examples from the selected train:

| Passenger/seat | Fare |
|---|---:|
| Adult special | `75700` |
| Adult general | `51900` |
| Child special | `49700` |
| Child general | `25900` |
| Senior special | `60100` |
| Senior general | `36300` |

### Mutual Verification

| Evidence | Method | Endpoint | Request | Response and use |
|---|---:|---|---|---|
| Runtime success | POST | `/ara/selectListAra10130_n.do` | Historical runtime smoke sent an empty form. | JSON `dsOutput0.msgCd=IRZ000008`, `strResult=SUCC`, `mutMrkVrfCd` present. The app used this value in some KorailTalk-marked paths; the library does not expose that mutation support. |

Do not auto-call the commented legacy `ara/selectListAra10h01.do` mutual path.

### Seat Selection

| Evidence | Method | Endpoint | Request | Response and contract |
|---|---:|---|---|---|
| Runtime success | POST | `/arc/selectListArc02012_n.do` | `reqCode=9`, `runDt`, `dptDt`, `trnNo`, `dptTm`, `trnGpCd`, `dptRsStnCd`, `arvRsStnCd`, `psrmClCd`, `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, `choiceSeatCount`. | HTML seat-selection page containing `좌석선택`. |
| Excluded | GET | `https://www.korail.com/ticket/search/list?...srtJob=seatmap` | Built by live page `choiceSeatWebView(...)`. | External Korail seatmap boundary; do not call in app API library core. |

Seat callback model:

| Field | Meaning |
|---|---|
| `scarSeatNo` | Selected seat number. |
| `scarSeatNm` | Display seat name. |
| `scarNo` | Car number. |
| `seatNo1_N` | Personal reservation seat slot fields. |
| `seatNo1` | Group ARD handoff field; different from `seatNo1_N`. |
| `scarNo1`, `scarGridcnt1` | Car/grid fields when present. |

### Reservation Endpoint Evidence (Non-Implementable)

The app contains reservation endpoints, and historical probes showed that a
valid call could create an unpaid reservation and hold live inventory. The
request and response details below are evidence only; they are not an
implementable library contract.

| Evidence | Method | Endpoint | Request | Response and success/failure rule |
|---|---:|---|---|---|
| Helper | GET | `https://nf.letskorail.com:443/ts.wseq` | `aid=act_19` for reservation. | The app injected the returned key into its reservation form. |
| Runtime rejected | POST | `/arc/selectListArc05013_n.do` | Serialized `rsvForm`, personal flow `grpDv=0`, selected train fields, passenger fields, seat fields, `mutMrkVrfCd`, fresh `act_19` key. | Invalid payloads reached endpoint. Zero-passenger retry returned `msgCd=WRP011002`, `strResult=FAIL`, `msgTxt=승객수 오류`. |
| Runtime rejected | POST | `/arc/selectListArc06014_n.do` | Group `rsvForm`, `grpDv=1`, group passenger count, selected train fields, fresh `act_19` key. | Invalid payloads reached endpoint. Zero-passenger retry returned `WRP011002`; malformed invalid train fields returned `ERROR_CODE=-1`. |

Observed personal reservation core request fields:

| Group | Fields |
|---|---|
| Journey | `jobId`, `jrnyTpCd`, `jrnyCnt`, `grpDv=0`, `rtnDv`, `jrnySqno1`. |
| Train | `stlbTrnClsfCd1`, `trnGpCd1`, `trnNo1`, `runDt1`, `dptDt1`, `dptTm1`, `arvDt1`, `arvTm1`. |
| Stations | `dptRsStnCd1`, `arvRsStnCd1`, `dptStnRunOrdr1`, `arvStnRunOrdr1`, `dptStnConsOrdr1`, `arvStnConsOrdr1`. |
| Seat | `psrmClCd1`, `seatAttCd1`, `scarNo1`, `seatNo1_1..9`. |
| Passenger | `totPrnb`, `psgGridcnt`, `psgTpCd1..6`, `psgInfoPerPrnb1..6`. |
| Gate | `netfunnelKey`, `mutMrkVrfCd`. |

Expected success response shape from app scripts:

| Map | Important fields |
|---|---|
| `resultMap[0]` | `strResult`, `msgCd`, `msgTxt`, `totRcvdAmt`, `tmpJobSqno1`. |
| `reservListMap[0]` | `pnrNo`, `JRNYLIST_KEY`, `arvDt`, `arvRsStnCd`, `arvTm`, `dlayAcptFlg`, `dptDt`, `dptRsStnCd`, `dptTm`, `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`, `trnNo`. |
| `trainListMap[0]` | `seatNo`, `scarNo`. |
| `commandMap[0]` | Echo/control fields used by follow-up pages. |

Observed app failure handling:

| Code/shape | Rule |
|---|---|
| `strResult=FAIL` | Surface `msgTxt` to caller. |
| `msgCd=S111` | App stored pending reservation parameters and redirected to login. |
| `msgCd=WRP011002` | Passenger count error. |
| `{}` | Malformed/insufficient payload; do not treat as success. |
| `ERROR_CODE=-1` | App/server rejection; do not treat as success. |

### ARD Payment/Reservation Detail Page Entry

These endpoints are page-entry handoffs after reservation success. Runtime tests
used dummy state only. HTTP 200 HTML here does not mean payment is possible or
approved.

| Evidence | Method | Endpoint | Request | Response and rule |
|---|---:|---|---|---|
| Dummy page entry | POST | `/ard/selectListArd02017_n.do` | Personal reservation handoff: `pnrNo`, `jrnySqno=1`, `JRNYLIST_KEY`, `arvDt`, `arvRsStnCd`, `arvTm`, `dlayAcptFlg`, `dptDt`, `dptRsStnCd`, `dptTm`, `jrnyTpCd`, `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`, `trnNo`. | HTML page, runtime dummy size about 84 KB. Page entry only. |
| Dummy page entry | POST | `/ard/selectListArd02018_n.do` | Group handoff: `pnrNo=-1`, `rcvdAmt`, `tmpJobSqno1`, `tmpJobSqno2=0`, `seatNo1`, `scarNo1`, plus common journey fields. | HTML page, runtime dummy size about 83 KB. Page entry only. |

These page-entry observations are historical and non-implementable. The library
does not construct their requests or implement card approval.

### Discount/Additional Detail

| Evidence | Method | Endpoint | Request | Response and rule |
|---|---:|---|---|---|
| Runtime failed | POST or jQuery Mobile page change | `/ata/selectListAta01032_n.do` | App script passes `pnrNo` from `commandMap`. Runtime dummy PNR was posted. | Runtime dummy call returned HTTP 500 app error page. Treat as valid-state-dependent, not standalone. |

Method caveat: offline script uses `$.mobile.changePage(...,{data:...})` without
an explicit `type:"post"`, so jQuery Mobile may send data as a query string.
Runtime testing used `POST`.

### Legacy And Static Candidates

| Evidence | Endpoint | Classification | Notes |
|---|---|---|---|
| Commented/static | `ara/selectListAra10h01.do` | Legacy | Historical mutual-verification/reservation-detail candidate; the library does not call it. |
| Static/native | `https://devapp.srail.or.kr/main/main.do` | Excluded | Development host reference. |
| Static/native | `https://devapp.srail.co.kr/neo/common/rest/JongURi/view.do` | Excluded | Development/legacy reference. |
| Static/native | `https://app.srail.co.kr/neo/main/main.do` | Excluded/candidate | Older host family; core runtime used `app.srail.or.kr`. |
| Static/native | `/error.html`, `file:///android_asset/offline/sub/error.html` | UI route | Error page home returns to main; not business API. |

## 7. Flow Contracts

### Login And Session Flow

1. `GET /login/login.do` to establish login page/session cookies.
2. `POST /apb/selectListApb01080_n.do` with `LoginRequest`.
3. Check JSON `userMap.RTNCD`.
4. `GET /main/main.do?deviceId=...` if the caller needs main-page session parity.
5. `GET /ara/ara0101v.do` before booking/search workflows.

Failure rules:

| Failure | Library behavior |
|---|---|
| HTTP error | Transport/server exception. |
| `userMap.RTNCD != Y` | Authentication failure with server message. |
| Missing `userMap` | Unexpected response schema. |

### Personal Search Flow

1. Get fresh NetFunnel `act_10` key.
2. `GET /ara/selectListAra10007_n.do` with search state and `netfunnelKey` to hydrate the search result page.
3. Parse/preserve `seatSearchForm` hidden fields.
4. `POST /ara/selectListAra10007_n.do` with `TrainSearchRequest`.
5. Normalize `dsOutput0` and `dsOutput1`.
6. For the opt-in iterator, yield the page without reordering or deduplication.
7. If `fllwPgExt=Y`, derive the next cursor from the last row, preserve the
   hydrated form and key, and POST the same route until a bounded stop condition.
8. Select a `TrainRow` only after checking availability labels/codes.

Observed selected runtime row:

| Field | Value |
|---|---|
| Train | SRT `303` |
| Train group | `300` |
| Service class | `17` |
| Run date | `20260710` |
| Departure | `0551` at `060000` |
| Arrival | `0020` at `083000` |
| General seat | Available |
| Special seat | Sold out |

### Group Search Flow

1. Build search state with `grpDv=1` and group passenger count.
2. Get fresh NetFunnel `act_10` key.
3. Hydrate through `GET /ara/selectListAra10007_n.do` and preserve form state.
4. `POST /ara/selectListAra10082_n.do`.
5. Parse with the same response model and optional bounded continuation rules as
   personal search; group continuations stay on Ara10082 with `grpDv=1`.

Group-specific rules:

| Rule | Notes |
|---|---|
| Passenger count | Group flow is for larger groups; runtime used 10 passengers. |
| Seat selection | App disables or constrains some personal seat options in group flow. |
| Historical reservation endpoint | App evidence mapped group state to `/arc/selectListArc06014_n.do`; this is not an implementation rule. |

### Timetable/Fare Flow

1. Take selected `TrainRow`.
2. Zero-pad `trnNo` to 5 digits where the page expects it.
3. Call timetable endpoint for stop sequence.
4. Call fare endpoint with passenger type/count fields.
5. Parse HTML defensively; keep raw labels with normalized integers.

### Seat Page Flow

1. Take selected `TrainRow`.
2. Call `/arc/selectListArc02012_n.do` with `reqCode=9`, class/car/seat fields.
3. Treat returned HTML as a seat-selection page.
4. If using the external live seatmap route, keep it outside core app API module.
5. Record callback-field mappings as historical evidence; do not construct a reservation form.

### Reservation Evidence Boundary

The observed state sequence, form fields, NetFunnel key, and response maps are
retained only so historical app behavior is not lost. The library does not
rehydrate, construct, validate, or submit reservation forms, and tests do not
invoke these endpoints with either valid or invalid payloads.

### Payment Detail Evidence Boundary

The ARD request fields and HTML results above document dummy historical probes.
The library does not build these page-entry requests, follow a reservation
success response into them, or contact a payment authorization gateway.

## 8. Hidden Native Libraries And Boundaries

The Android app is primarily a WebView shell around the app `.do` endpoints.
Native code and SDKs still matter for device identity, push, secure input,
biometric/FIDO, and external-app handoff.

### `srbridge`

JavaScript calls native as:

```text
window.srbridge.bridgeCall(action, JSON.stringify(params))
```

Relevant bridge action families:

| Family | Actions | Library treatment |
|---|---|---|
| Media/QR | `mkQRCode`, `mkQRCode2`, `takePicture`, `selectPicture`, `selectPictureByCode`, `getTakePicture`, `getTakeIdCard` | Optional native adapter. |
| Device/storage | `pkgVersion`, `getNetworkAddress`, `savePrfs`, `loadPrfs`, `getStorageItem`, `setStorageItem`, `removeStorageItem`, `writeLog` | Useful for parity; provide interface/stubs. |
| Auth/vendor | `showTransKey`, `snsLogin`, `regDevice`, `unRegDevice`, `easypay`, `allowedAuthnr`, `requestServiceRegist`, `requestServiceRelease`, `requestServiceAuth` | Optional; do not block core search library. |
| UI/external | `callExtApp`, `mobileFAX`, `mainShow`, `windowOpen`, `disableCapture`, `enableCapture`, `exitApp` | App shell features only. |

Important bridge details to preserve if a native parity layer is ever built:

| Action/area | Detail |
|---|---|
| `getNetworkAddress` | Callback `mac` is the uppercased Android ID, not a hardware MAC address. |
| `savePrfs` / `loadPrfs` | Uses `SRApp` SharedPreferences; offline ticket HTML cache key is `offTicketList`. |
| `getStorageItem` / `setStorageItem` / `removeStorageItem` | Uses `SRAIL` SharedPreferences; native offline ticket DTO cache key is `ticketListOffline`. |
| `showTransKey` | Secure-keypad flow can return plaintext data to JavaScript; do not log callback payloads. |
| FIDO callbacks | SDK result codes can differ from app bridge success code expectations; runtime confirmation is needed before relying on callbacks. |
| `easypay` | Confirmed static branch uses `shinhanfan` and a Shinhan app scheme; no real payment approval should be automated. |

### SDKs And Native Components

| Component | Role | Library decision |
|---|---|---|
| H2O push / `push.srail.co.kr:3101` | Push broker for registration, unregister, message fetch, and receipt. | Optional notification integration, not booking core. |
| FCM / install referrer / badge | App lifecycle and push. | Exclude from core. |
| TransKey / `KeySharpCrypto` | Secure keyboard. | Optional login/payment UI parity only. |
| RAON / `KSNative` | Security/auth native component. | Optional. |
| OnePass/FIDO references | Biometric/auth service under `https://fido.srail.co.kr`; visible subpaths include `/interfToken/processRequest.do`, `/fido/deviceUaf/processUafRequest.do`, `/fido/deviceUaf/processUafResponse.do`, `/interfDeviceBiz/processRequest.do`, `/interfBiz/processRequest.do`. | Optional auth module, not train search core. |
| Kakao/Naver/Daum/Taxi/Mobile ID/Fax/Rail Police | External app handoffs. | Exclude from core booking library. |
| ZXing, Glide, AndroidX, MaterialDrawer, AppIntro, ShortcutBadger | UI/general libraries. | Exclude from API client. |
| AppIron strings/resources | Security/resource hints; direct caller not confirmed. | Do not model until a live call path is found. |

Push notes:

| Item | Detail |
|---|---|
| H2O host/port | `push.srail.co.kr:3101`. |
| Token storage | FCM token is stored under `SRApp.TOKEN`. |
| User id derivation | Derived from Android ID with colon/hyphen removal and uppercasing. |
| Helper calls | `pushRegist`, `pushUnRegist`, `pushGetMsg`, `pushReceipt`. |
| Caveat | Static analysis found a possible FCM full-message fetch port/resource-id mismatch; not relevant to train search library core. |

External-app package visibility notes:

| Target | Note |
|---|---|
| `com.korail.talk` | Manifest query target. |
| `net.daum.android.map` | Manifest query target. |
| `com.kakao.taxi` | Manifest query target. |
| `com.RLP.railpolice` | Manifest query target. |
| `com.dho.mobilefax` | Manifest query target. |
| `kr.go.mobileid`, `kr.go.mobileid.tbe` | Manifest query targets; runtime mobile-id handler targets `kr.go.mobileid`. |
| `com.shcard.smartpay`, `com.eq4all.safe4all.one` | Runtime target candidates were seen, but manifest query coverage was not confirmed. Validate on Android 11+ before depending on package lookup. |

## 9. Implementation Guardrails

| Area | Rule |
|---|---|
| Form submission | Keep unknown hidden fields in a sidecar map and resend them unless explicitly overridden. |
| Date/time | Store raw SRT app strings (`YYYYMMDD`, `HHMMSS`) plus parsed convenience values. |
| Train number | Store raw and zero-padded variants. |
| Passenger fields | Preserve `psgTpCdN` and `psgInfoPerPrnbN`; popup typo `totalPessnger` is real. |
| Group vs personal | Separate request builders; do not flip only the endpoint URL. |
| HTML parsing | Prefer table/semantic selectors, then regex fallback; do not rely on byte sizes. |
| Business success | Check app-level JSON codes, not just HTTP 200. |
| Retry | Retry first-page NetFunnel flow once after `NET000001`; for continuation, refresh key/hydration once and retry only the failing cursor. |
| Redaction | Redact login id, password, cookies, PNR, card-like fields, NetFunnel key, raw response bodies. |
| Tests | Default tests cover offline login/search/selectors/timetable/fare/ticket fixtures and never invoke mutation endpoints. |

## 10. Current Verification Summary

| Area | Result |
|---|---|
| Runtime smoke | 25 HTTP steps completed. |
| Login | Success, app JSON `RTNCD=Y`. |
| Personal search | Success, app JSON `IRG000000`, 10 rows. |
| Group search | Success, app JSON `IRG000000`, 10 rows. |
| Selector pages | Station, map, date/time, passenger, seat option, train group all returned HTML. |
| Timetable/fare | Returned HTML and parsable values for selected train. |
| Seat-selection app page | Returned HTML containing `좌석선택`. |
| Mutual verification | Success, `IRZ000008`, mutual code present. |
| Reservation endpoints | Reached and intentionally rejected invalid payloads. |
| ARD page entry | Returned HTML with dummy state; not payment success. |
| ATA detail | Dummy PNR returned HTTP 500 app error. |
| Ticket list | Before/after negative reservation bodies matched. |
| Pagination offline contract | Personal/group sequencing, exact cursor, hydration/key reuse, metadata, bounds, non-progress, and continuation-only retry passed synthetic `MockTransport` tests. |
| Pagination live status | Bounded 2026-07-15 login succeeded; personal and group each returned two 10-row pages. Only fixed status/count summaries were retained. |

## 11. Open Gaps Before Building A Full Library

These gaps are documentary only and are not an implementation queue for
reservation, payment, or other mutation behavior.

| Gap | Why it matters |
|---|---|
| Full raw hidden form snapshots | Not retained; no reservation request builder is planned. |
| Valid reservation success response | Not captured by design; would create live inventory hold. |
| Real ARD page internals after valid reservation | Not captured; dummy page evidence is not payment behavior. |
| ATA detail valid-state behavior | Dummy PNR failed; no valid reservation context will be created. |
| Search pagination live verification | The bounded iterator implements the static app contract; a separately authorized read-only run is still needed to verify production continuation. |
| External seatmap callback | Current live page can hand off to external Korail seatmap; keep out of core unless separately scoped. |
| Native secure keyboard/FIDO parity | Not needed for basic HTTP login/search but may matter for app-identical UX. |

## 12. Source Documents

The earlier temporary catalog, runtime report, static APK notes, and deep-dive
notes were merged into this file. The repository now retains the installable
package source, offline tests and fixtures, implementation progress, approved
specifications and execution plans, the root README, and bounded smoke tooling.

| Retained file | Purpose |
|---|---|
| `docs/analysis/srt-app-api-library-spec-2026-07-09.md` | Final merged API/library specification. |
| `src/srt_mobile_api/` | Installable read-only package source. |
| `tests/` | Offline contract tests and sanitized synthetic fixtures. |
| `docs/IMPLEMENTATION_PROGRESS.md` | Current implementation and verification evidence. |
| `docs/superpowers/specs/` | Retained design decisions and completion status. |
| `docs/superpowers/plans/` | Retained implementation and review plans. |
| `scripts/srt_app_api_smoke.py` | Re-runnable smoke/negative test harness. |
| `README.md` | Package entry point, evidence map, and safety notes. |

## 13. Regenerating Static Evidence

If APK evidence has to be recreated, place the matching `srt.apk` at the
repository root and generate local artifacts outside git:

```bash
mkdir -p build
zipinfo -1 srt.apk | sort > build/apk-file-list.txt
apktool d -f srt.apk -o build/apktool
jadx -d build/jadx srt.apk
```

Then use `rg` against `build/apktool`, `build/jadx`, and this spec to compare
new evidence with the final contract. The `build/` directory and `srt.apk` are
ignored by git and can be deleted after the useful findings are merged.
