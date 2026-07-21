# Reference: `srtgo_plus` SRT booking logic (external project analysis)

**Purpose.** Extract the concrete request/response shapes of a *working* SRT
booking tool to unblock the mutation items our `RELEASE_GAP_PLAN.md` flagged as
"no static evidence." This is READ-ONLY source analysis of an external repo; no
code was run and no network call was made.

**Reference project.** `srtgo_plus` — a fork of the discontinued `srtgo`
(lapis42), maintained by "dion" (DionNam).
- Local clone: `/Users/yakisoba/Documents/GitHub/srtgo_plus`
- Commit analyzed: `354960197855b2ca5d2fe300f26d1b45bdbf66ab` ("Initial commit", 2026-03-23)
- Focus file: `srtgo/srt.py` (1261 lines) — the SRT client. Orchestration/CLI in
  `srtgo/srtgo.py`. `srtgo/__init__.py` is empty.
- All `srt.py:NNN` citations below are line numbers in that file.

---

## 0. License and reuse posture (READ THIS FIRST)

- **`srtgo_plus/LICENSE` = MIT License**, Copyright (c) 2023 DKim
  (`pyproject.toml:13` also declares `license = {text = "MIT License"}`).
- Its SRT module is itself derived from **`ryanking13/SRT` (MIT)** and the KTX
  module from **`carpedm20/korail2` (BSD)** — both permissive, both bundled into
  `LICENSE` as third-party notices (`README.md:80-83`, `LICENSE:27-79`).
- **Copyleft implication: none.** MIT/BSD are permissive, not copyleft. There is
  no GPL contamination risk.
- **Our posture regardless of license.** We treat this project as a reference for
  **factual API request shapes only** — endpoint paths, form-field names, fixed
  field values, response-key names, and the request sequence. Those are *facts
  about a third-party server's protocol*, not copyrightable expression, and are
  the only thing we lift. We must **not** copy substantial `srt.py` source
  verbatim (class bodies, method implementations, docstrings, constant tables) if
  our library's license differs from MIT. Re-implement independently from the
  documented field lists in this doc.
- **Non-commercial notice.** `README.md:7-8` asserts a non-commercial-use demand
  by the author. That is a usage request on *their* binary, separate from the MIT
  grant on the code; it does not restrict our independent re-implementation, but
  it signals the author's intent and is worth respecting in spirit.

---

## 1. Overview — what srtgo_plus is and its SRT approach

srtgo_plus is a terminal auto-booking assistant. For SRT it drives the **SRT
mobile app's hidden JSON API directly** — it does **not** drive the jQuery-Mobile
WebView site that our static APK analysis reverse-engineered. Concretely:

- **Single host, mobile JSON endpoints.** Everything hits
  `https://app.srail.or.kr:443` on `*_n.do` (and a couple of `.do`) paths that
  return **JSON**, not server-rendered HTML (`srt.py:88-103`). This is the same
  host our WebView analysis saw, but a *different code path* on the server: the
  native-app JSON API rather than the `#rsvForm`-serialize → HTML-payment-page
  flow the bundled JS uses.
- **TLS/JA3 impersonation as the anti-bot bypass.** It prefers
  `curl_cffi.Session(impersonate="chrome")` (`srt.py:2-7, 652-655`) so the TLS
  fingerprint matches a real Chrome/Android WebView. Falls back to `requests` if
  `curl_cffi` is missing.
- **Full lifecycle, all HTTP.** login → search → reserve (incl. standby/예약대기)
  → **card payment** → cancel → refund — every step is a plain
  `application/x-www-form-urlencoded` POST parsed as JSON. No SEED keypad, no PG
  redirect, no FIDO, no native bridge anywhere in the SRT path.

**Headline for us:** srtgo_plus is a *working existence proof* that SRT
reservation **and payment and cancel and refund** are all completable from a pure
Python HTTP client against the mobile JSON API — which is exactly the surface our
gap plan called WebView-blocked / capture-blocked. The blocker was that our APK
analysis only saw the WebView path; srtgo_plus reveals the parallel mobile-JSON
path.

---

## 2. Endpoint + host table

Base host constant: `SRT_MOBILE = "https://app.srail.or.kr:443"` (`srt.py:88`).
All endpoints defined in `API_ENDPOINTS` (`srt.py:89-103`).

| # | srtgo_plus role | Method | Path | `srt.py` def | Called at | Maps to our route / status |
|---|---|---|---|---|---|---|
| 1 | main (referer only) | — | `/main/main.do` | `:90` | login referer `:706` | our `get_main` GET `/main/main.do` ✓ allowlisted |
| 2 | **login** | POST | `/apb/selectListApb01080_n.do` | `:91` | `:712` | our allowlist POST `/apb/selectListApb01080_n.do` ✓ (analysis line 159) |
| 3 | logout | POST | `/login/loginOut.do` | `:92` | `:745` | NOT in our routes (we have GET `/login/login.do`); different path |
| 4 | **search** | POST | `/ara/selectListAra10007_n.do` | `:93` | `:822` | our `search_trains` GET+POST `/ara/selectListAra10007_n.do` ✓ |
| 5 | **reserve** (personal + standby) | POST | `/arc/selectListArc05013_n.do` | `:94` | `:999` | our EXCLUDED `reservation`; = gap-plan `arc05013`. **UNBLOCKED** |
| 6 | reservation list | POST | `/atc/selectListAtc14016_n.do` | `:95` | `:1069` | gap-plan **R3** (atc14016 variant of implemented atc14017); appears in app `SRForegroundDialogActivity.java:31` (analysis line 71) |
| 7 | ticket detail | POST | `/ard/selectListArd02019_n.do` | `:96` | `:1102` | NEW — not in our routes |
| 8 | **cancel** (unpaid 예약취소) | POST | `/ard/selectListArd02045_n.do` | `:97` | `:1140` | our EXCLUDED `cancellation`. **UNBLOCKED** |
| 9 | standby option set | POST | `/ata/selectListAta01135_n.do` | `:98` | `:1049` | NEW — 예약대기 SMS/좌석변경 동의 |
| 10 | **payment** (card) | POST | `/ata/selectListAta09036_n.do` | `:99` | `:1218` | our EXCLUDED `payment`. **UNBLOCKED (JSON, not the WebView ard02017/18 HTML)** |
| 11 | refund pre-info | POST | `/atc/getListAtc14087.do` | `:100` | `:1230` | NEW — feeds refund |
| 11r | refund referer | (header) | `/common/ATC/ATC0201L/view.do?pnrNo=` | `:101` | `:1228` | Referer string only |
| 12 | **refund** (paid 환불) | POST | `/atc/selectListAtc02063_n.do` | `:102` | `:1250` | our EXCLUDED `refund`. **UNBLOCKED** |
| NF | NetFunnel queue | GET | `https://nf.letskorail.com/ts.wseq` | `:583` | `:585` | our `act_10` helper ✓ — see §5 |

**Key reconciliation vs our APK analysis.** Our gap plan expected the *payment
entry* to be `ard02017`/`ard02018` (server-rendered HTML → PG). srtgo_plus never
touches those. Its payment is a **separate JSON endpoint `ata09036`** that takes
card fields directly. In srtgo_plus the `ard*` family is used for *ticket detail*
(`ard02019`) and *cancel* (`ard02045`) instead. So the two surfaces are genuinely
different server flows; srtgo_plus proves the JSON one exists and is complete.

---

## 3. Login / auth (`srt.py:673-731`)

- **Endpoint:** POST `/apb/selectListApb01080_n.do`.
- **ID type autodetection** (`srt.py:691-698`): email → `srchDvCd="2"`;
  phone (`\d{3}-\d{3,4}-\d{4}`) → `"3"` (hyphens stripped); else membership →
  `"1"`.
- **POST body (`srt.py:700-710`):**
  ```
  auto=Y, check=Y, page=menu,
  deviceKey=-,            # literally a hyphen — no real device key needed
  customerYn=,
  login_referer=https://app.srail.or.kr:443/main/main.do,
  srchDvCd=<1|2|3>,
  srchDvNm=<id>,
  hmpgPwdCphd=<password>  # PLAINTEXT despite the "Cphd" (cipher) suffix
  ```
- **Password / device-key encryption: NONE.** Despite the field name
  `hmpgPwdCphd`, the password is sent verbatim (`srt.py:709`). `deviceKey` is the
  constant `"-"` (`srt.py:705`). No hashing, no RSA, no device attestation. This
  matches our analysis (line 159: `srchDvCd, srchDvNm, hmpgPwdCphd, deviceKey`).
- **Session/cookies:** handled implicitly by the `curl_cffi`/`requests` session
  (`srt.py:652-656`); the login response Set-Cookie is reused for all subsequent
  calls. No manual JSESSIONID handling.
- **Error signalling by substring** on the raw body (`srt.py:715-720`):
  `"존재하지않는 회원입니다"`, `"비밀번호 오류"`, `"Your IP Address Blocked"`.
- **Success payload:** JSON `userMap` → `MB_CRD_NO` (membership no.),
  `CUST_NM` (name), `MBL_PHONE` (phone) (`srt.py:723-726`).

---

## 4. Reservation flow — the highest-value extraction

### 4.1 Endpoint and decision logic

Single reserve endpoint **`/arc/selectListArc05013_n.do`** for *both* personal and
standby; the mode is chosen by `jobId` (`srt.py:30-33`):
`PERSONAL="1101"`, `STANDBY="1102"`.

`reserve()` (`srt.py:840-884`) decides: if no seat available but standby possible
(`reserve_wait_possible_code >= 0`) → `reserve_standby` (jobId 1102) + then set
standby options; else → `_reserve(PERSONAL, …)` (jobId 1101). Group reservation
(`arc06014`, ≥10 pax) is **not implemented** by srtgo_plus.

### 4.2 The FULL reservation POST body (`_reserve`, `srt.py:962-997`)

This is the concrete `#rsvForm` our static analysis could not fully capture. Every
key below is posted to `arc05013`. Values are derived from the `SRTTrain` object
(a prior search result) plus passenger data — **nothing requires scraping a
server-rendered hidden form.**

Static base fields (`srt.py:962-988`):

| Key | Value / source | Notes |
|---|---|---|
| `jobId` | `1101` personal / `1102` standby | mode selector |
| `jrnyCnt` | `1` | |
| `jrnyTpCd` | `11` | journey type |
| `jrnySqno1` | `001` | |
| `stndFlg` | `N` | |
| `trnGpCd1` | `300` | leg-level train-group (SRT) |
| `trnGpCd` | `109` | top-level train-group |
| `grpDv` | `0` | 0=individual (1 would select arc06014) |
| `rtnDv` | `0` | one-way |
| `stlbTrnClsfCd1` | `train.train_code` (`17` for SRT) | |
| `dptRsStnCd1` | `train.dep_station_code` | e.g. `0551` 수서 |
| `dptRsStnCdNm1` | `train.dep_station_name` | **station NAME string** |
| `arvRsStnCd1` | `train.arr_station_code` | |
| `arvRsStnCdNm1` | `train.arr_station_name` | **station NAME string** |
| `dptDt1` | `train.dep_date` (YYYYMMDD) | |
| `dptTm1` | `train.dep_time` (HHMMSS) | |
| `arvTm1` | `train.arr_time` | |
| `trnNo1` | `f"{int(train.train_number):05d}"` | **5-digit zero-padded** |
| `runDt1` | `train.dep_date` | operation date |
| `dptStnConsOrdr1` | `train.dep_station_constitution_order` | from search field `dptStnConsOrdr` |
| `arvStnConsOrdr1` | `train.arr_station_constitution_order` | |
| `dptStnRunOrdr1` | `train.dep_station_run_order` | from search field `dptStnRunOrdr` |
| `arvStnRunOrdr1` | `train.arr_station_run_order` | |
| `mblPhone` | phone or `None` | standby notifications |
| `netfunnelKey` | `self._netfunnel.run()` | **act_10 key — see §5** |
| `reserveType` | `11` | **personal only** (`srt.py:990-991`) |

Passenger fields merged from `Passenger.get_passenger_dict()`
(`srt.py:179-204`, merged at `:993-997`):

| Key | Value | Notes |
|---|---|---|
| `totPrnb` | total passenger count | |
| `psgGridcnt` | number of passenger-type rows | |
| `locSeatAttCd1` | `000` any / `012` window / `013` aisle | `WINDOW_SEAT` map `srt.py:86` |
| `rqSeatAttCd1` | `015` | |
| `dirSeatAttCd1` | `009` | |
| `smkSeatAttCd1` | `000` | |
| `etcSeatAttCd1` | `000` | |
| `psrmClCd1` | `1` general / `2` special(특실) | from seat option |
| `psgTpCd{i}` | type code per row | `1`어른 `2`장애1~3 `3`장애4~6 `4`경로 `5`어린이 (`srt.py:207-235`) |
| `psgInfoPerPrnb{i}` | count per row | |

**Seat-selection fields (`seatNo1_*`, `scarNo1`) are NOT sent by srtgo_plus** — it
lets the server auto-assign seats. So the physical seat-pick loop (our `arc02011`
/ `popCallback` concern) is *optional*, not required to make a reservation.

`is_special_seat` is resolved from the `SeatType` enum + live availability
(`srt.py:955-960`): GENERAL_ONLY→일반, SPECIAL_ONLY→특실,
GENERAL_FIRST→특실 only if general unavailable, SPECIAL_FIRST→특실 if available.

### 4.3 Search request (needed to build the reserve body) (`srt.py:800-820`)

POST `ara10007` body: `chtnDvCd=1, dptDt, dptTm, dptDt1, dptTm1(=HH0000),
dptRsStnCd, arvRsStnCd, stlbTrnClsfCd=05, trnGpCd=109, trnNo="", psgNum,
seatAttCd=015, arriveTime=N, tkDptDt="", tkDptTm="", tkTrnNo="", tkTripChgFlg="",
dlayTnumAplFlg=Y, netfunnelKey=<act_10 key>`. Response trains parsed from
`outDataSets.dsOutput1`, filtered to `stlbTrnClsfCd == "17"` (SRT) (`srt.py:829-838`).

### 4.4 Multi-step sequence

```
NetFunnel act_10 (cached ≤48s)  → netfunnelKey          srt.py:542-568, 819
   ▼
search  POST ara10007  → SRTTrain[]                      srt.py:822-838
   ▼
reserve POST arc05013  (jobId 1101/1102, body §4.2)      srt.py:999
   │  parse {resultMap, reservListMap, trainListMap, commandMap}
   │  pnrNo = reservListMap[0]["pnrNo"]                   srt.py:1006
   ▼
get_reservations POST atc14016  → find matching pnrNo    srt.py:1008-1010
   ▼ (standby only) set options POST ata01135            srt.py:1014-1051
   ▼ (optional) pay_with_card POST ata09036              srt.py:1149-1225
```

### 4.5 Response parsing (`SRTResponseData`, `srt.py:366-411`)

- Envelope: `resultMap[0]` holds status; `strResult == "SUCC"|"FAIL"`,
  message in `msgTxt` (`srt.py:381-404`).
- Reserve success reads `reservListMap[0]["pnrNo"]` (`srt.py:1006`).
- **No explicit `S111` re-login handling in `srt.py`.** Session expiry is handled
  one layer up in `srtgo.py` by matching the message `"로그인 후 사용하십시오"` and
  re-logging in (`srtgo.py:732-739`). (Contrast our gap-plan §5.7 which wants an
  explicit `S111 → SrtSessionExpiredError` map — srtgo_plus does it by message
  substring, not `msgCd`.)

---

## 5. NetFunnel / queue (`NetFunnelHelper`, `srt.py:499-630`)

- **Host/path:** GET `https://nf.letskorail.com/ts.wseq` (`srt.py:583`),
  `verify=False` (`srt.py:585`).
- **Opcodes (`srt.py:505-509`):** `getTidchkEnter=5101` (start),
  `chkEnter=5002` (poll), `setComplete=5004` (complete).
- **Service/action:** `sid="service_1"`, **`aid="act_10"`** (`srt.py:603`).
- **`act_19` is NOT used.** srtgo_plus gates *both search and reservation* on the
  **same `act_10` key**. `search_train` and `_reserve` each call
  `self._netfunnel.run()` and inject the result as `netfunnelKey`
  (`srt.py:819, 987`). The key is cached for 48 s (`srt.py:539, 626-630`).
- **Handshake (`run()`, `srt.py:542-568`):** start (5101) → while status==`201`
  poll (5002) with `key`+`ttl=1` → complete (5004). Success statuses `200`
  (`WAIT_STATUS_PASS`) or `502` (`ALREADY_COMPLETED`) (`srt.py:501-503, 559`).
- **Param builder (`srt.py:591-609`):** `opcode, nfid=0,
  prefix="NetFunnel.gRtype=<opcode>;", js=true, <epoch-ms>=""`; for 5101/5002 add
  `sid=service_1, aid=act_10`; 5002 adds `key,ttl=1`; 5004 adds `key`.
- **Response parse (`srt.py:611-624`):** regex
  `NetFunnel.gControl.result='([^']+)'`, split `code:status:params`.
- **Headers (`srt.py:511-529`):** mimic the WebView —
  `X-Requested-With: kr.co.srail.newapp`, `Referer: https://app.srail.or.kr/`,
  `sec-ch-ua` Chromium/136, `Sec-Fetch-*`.

**Implication for us:** our gap plan assumed reservation needs a separate `act_19`
gate whose shape had to be captured live. srtgo_plus shows it does **not** — the
existing `act_10` key (which we already implement) is reused for reserve. This
removes a "capture-blocked" prerequisite.

---

## 6. PAYMENT — srtgo_plus DOES pay by card (JSON API)

`pay_with_card` (`srt.py:1149-1225`) performs a **complete card charge** via POST
`/ata/selectListAta09036_n.do` — wait, exact path `/ata/selectListAta09036_n.do`
(`srt.py:99`). No PG redirect, no SEED keypad, no FIDO, no native bridge.

- **Signature (`srt.py:1149-1158`):** `(reservation, number, password,
  validation_number, expire_date, installment=0, card_type="J")`.
  `card_type`: `J`=개인/personal (validation_number = birthday YYMMDD),
  `S`=법인/corporate (validation_number = 사업자등록번호).
- **POST body (`srt.py:1184-1216`):**

| Key | Value | Meaning |
|---|---|---|
| `stlDmnDt` | today YYYYMMDD | settlement request date |
| `mbCrdNo` | membership number | |
| `stlMnsSqno1` | `1` | payment-means seq |
| `ststlGridcnt` | `1` | |
| `totNewStlAmt` | `reservation.total_cost` | total to settle |
| `athnDvCd1` | `J` or `S` | auth division (card type) |
| `vanPwd1` | card password first 2 digits | |
| `crdVlidTrm1` | expiry `YYMM` | |
| `stlMnsCd1` | `02` | payment-means code = credit card |
| `rsvChgTno` | `0` | |
| `chgMcs` | `0` | |
| `ismtMnthNum1` | `installment` (0,2-12,24) | |
| `ctlDvCd` | `3102` | control division |
| `cgPsId` | `korail` | |
| `pnrNo` | `reservation.reservation_number` | |
| `totPrnb` | `reservation.seat_count` | |
| `mnsStlAmt1` | `reservation.total_cost` | amount on this means |
| `crdInpWayCd1` | `@` | card input method |
| `athnVal1` | `validation_number` (birthday / biz no.) | |
| `stlCrCrdNo1` | `number` (card PAN, no hyphens) | |
| `jrnyCnt` | `1` | |
| `strJobId` | `3102` | |
| `inrecmnsGridcnt` | `1` | |
| `dptTm` / `arvTm` | reservation times | |
| `dptStnConsOrdr2` / `arvStnConsOrdr2` | `000000` | |
| `trnGpCd` | `300` | |
| `pageNo` / `rowCnt` | `-` / `-` | |
| `pageUrl` | `` | |

- **Response (`srt.py:1220-1225`):** JSON; failure if
  `outDataSets.dsOutput0[0].strResult == "FAIL"` → raise with `msgTxt`.

**Verdict:** payment is **in scope and fully HTTP-replicable** in srtgo_plus — the
opposite of our gap plan's "WebView/PG/secure-keypad-blocked" conclusion, because
srtgo_plus uses the mobile JSON endpoint `ata09036`, not the WebView `ard02017/18`
HTML page. **This raises the stakes for our safety model:** a working direct card
charge is exactly what our `fake-card-only` / `never charge` guardrails exist to
prevent, and it is now demonstrably reachable from Python.

---

## 7. CANCEL and REFUND — both implemented

srtgo_plus distinguishes **cancel** (unpaid reservation, 예약취소) from **refund**
(paid/issued ticket, 환불); the CLI routes unpaid→cancel, paid→refund
(`srtgo.py:889-920`).

### 7.1 Cancel (`srt.py:1114-1147`)
- POST `/ard/selectListArd02045_n.do`.
- **Body (`srt.py:1138`):** `pnrNo=<reservation_number>, jrnyCnt=1, rsvChgTno=0`.
- Response: `SRTResponseData` envelope, success if `strResult=="SUCC"`.

### 7.2 Refund — two steps (`srt.py:1227-1257`)
1. **`reserve_info`** (`srt.py:1227-1236`): set header
   `Referer: /common/ATC/ATC0201L/view.do?pnrNo=<pnr>`, then POST
   `/atc/getListAtc14087.do` (no body). Returns `outDataSets.dsOutput1[0]` with
   fields `pnrNo, ogtkSaleDt, ogtkSaleWctNo, ogtkSaleSqno, ogtkRetPwd, buyPsNm`.
   (Note this response uses `{ErrorCode, ErrorMsg}` envelope, not `resultMap`.)
2. **`refund`** (`srt.py:1238-1257`): POST `/atc/selectListAtc02063_n.do` with:

| Key | Value (from step-1 info) |
|---|---|
| `pnr_no` | `pnrNo` (note underscore, unlike cancel's `pnrNo`) |
| `cnc_dmn_cont` | `"승차권 환불로 취소"` (cancel reason literal) |
| `saleDt` | `ogtkSaleDt` |
| `saleWctNo` | `ogtkSaleWctNo` |
| `saleSqno` | `ogtkSaleSqno` |
| `tkRetPwd` | `ogtkRetPwd` |
| `psgNm` | `buyPsNm` |

   Response: `SRTResponseData` envelope, success if `strResult=="SUCC"`.

**Verdict:** both cancel and refund are fully specified — the exact endpoints and
params our gap plan found **zero** static evidence for. Refund requires the
`atc14087` pre-info fetch first.

---

## 8. Anti-bot / headers / User-Agent (`srt.py:20-28, 511-529, 652-655`)

- **TLS impersonation:** `curl_cffi.Session(impersonate="chrome")`
  (`srt.py:653`) — the primary bypass; matches a real Chrome JA3/TLS fingerprint.
- **User-Agent (`srt.py:20-23`):** a full Android WebView string with app suffix
  `SRT-APP-Android V.2.0.38`. (Our client/analysis uses `V.2.0.41`; the suffix
  version differs — worth aligning or tolerating.)
- **Default headers (`srt.py:25-28`):** `User-Agent` + `Accept: application/json`.
- **NetFunnel headers (`srt.py:511-529`):** WebView-mimicking set incl.
  `X-Requested-With: kr.co.srail.newapp`, `Referer: https://app.srail.or.kr/`,
  `sec-ch-ua`, `Sec-Fetch-*`, `Accept-Encoding: gzip, deflate, br, zstd`.
- **Human-pacing:** the CLI retry loop sleeps a gamma-distributed ~3.8 s between
  reservation attempts (`srtgo.py:121-124, 803-807`) to dodge macro detection.
- **No request signing / nonce / body encryption** anywhere in the SRT path.

---

## 9. Gap-plan unblock map

Going item-by-item through the items `RELEASE_GAP_PLAN.md` marked
BLOCKED / capture-blocked:

| Gap-plan blocked item | srtgo_plus resolves? | Concrete finding |
|---|---|---|
| **`#rsvForm` hidden fields** (§3.4, §5.8) — "full hidden-field list absent from APK, must scrape live" | **RESOLVED** | The complete reserve body is the ~30 fields in §4.2 (`srt.py:962-997`). The fields our static `#rsvForm` analysis missed are just station-name strings (`dptRsStnCdNm1/arvRsStnCdNm1`), consist/run-order (`*StnConsOrdr1/*StnRunOrdr1`), `trnNo1` (5-digit), `runDt1`, `arvTm1`, `trnGpCd`, `grpDv=0`, `rtnDv=0`, `mblPhone`, `reserveType=11` — **all derivable from the search result, none server-scraped.** |
| **NetFunnel `act_19`** reserve gate (§3.4, §5.4) — "not in APK, must capture live" | **RESOLVED (does not exist as a separate gate)** | Reserve reuses the **`act_10`** key we already implement; `_reserve` injects `netfunnelKey=self._netfunnel.run()` (`srt.py:987`), same helper as search. Full 5101→5002→5004 handshake with `aid=act_10` (`srt.py:591-609`). No `act_19`. |
| **`arc05013` / `arc06014` reserve params** (§3.3) | **arc05013 RESOLVED; arc06014 NOT** | `arc05013` individual params fully given (§4.2). Standby uses the same endpoint via `jobId=1102`. **`arc06014` (group ≥10) is not implemented by srtgo_plus** — still needs capture for our group support. |
| **Payment** (§3.3, §3.5) — "ard02017/18 WebView/PG/keypad/FIDO-blocked, approval outside HTTP" | **RESOLVED via a different endpoint** | srtgo_plus pays through JSON **`/ata/selectListAta09036_n.do`** with plain card fields (§6, `srt.py:1149-1225`) — no PG/keypad/FIDO. Our gap plan's "payment not replicable" holds only for the *WebView `ard02017/18` path*; the mobile-JSON path **is** replicable. Field list captured in §6. |
| **Cancel** (§3.3) — "zero static evidence" | **RESOLVED** | POST **`/ard/selectListArd02045_n.do`**, body `pnrNo, jrnyCnt=1, rsvChgTno=0` (§7.1, `srt.py:1114-1147`). |
| **Refund** (§3.3) — "zero static evidence" | **RESOLVED** | Two-step: pre-info POST **`/atc/getListAtc14087.do`** (Referer-gated) → refund POST **`/atc/selectListAtc02063_n.do`** with `pnr_no, cnc_dmn_cont, saleDt, saleWctNo, saleSqno, tkRetPwd, psgNm` (§7.2, `srt.py:1227-1257`). |
| **Change (변경)** | **NOT** | srtgo_plus has no seat/train change endpoint. Still capture-blocked for us. |
| **`arc02011` physical seat inventory (R1/R5)** | **NOT** | srtgo_plus lets the server auto-assign seats; it never posts `seatNo1_*`/`scarNo1` and never calls a per-seat inventory endpoint. Our deferred seat-schema remains unresolved. |

### 9.1 Safety-model consequence (important)

This reference **strengthens the case for our fail-closed mutation model**, it does
not relax it. srtgo_plus demonstrates that reserve *and a real card charge* are
reachable from Python with no keypad/PG/FIDO barrier. Therefore our
`PAYMENT_ENTRY` tier must keep: fake-card-only (Luhn-invalid PAN enforced),
never-auto-submit, never-persist-card, and default dry-run — precisely because the
underlying `ata09036` call *would* charge a real card if fed real data. The "payment
is infeasible so it's self-safe" assumption in parts of the gap plan is **false**
for the mobile-JSON path and should be corrected.

### 9.2 Endpoints to add to our route registry (when mutation lands)

`arc05013` (RESERVE), `atc14016` (READ, R3), `ard02019` (READ, ticket detail),
`ard02045` (CANCEL), `ata01135` (RESERVE-adjacent, standby option), `ata09036`
(PAYMENT), `atc14087` (READ, refund pre-info), `atc02063` (CANCEL/REFUND),
`login/loginOut.do` (session). All on `app.srail.or.kr`. Re-implement field lists
independently from §3-§7; do not copy `srt.py` bodies.

---

## 10. Provenance / caveats

- All shapes above are **static reads of `srt.py`**; not verified against a live
  server in this analysis. srtgo_plus itself is a working tool (its README and the
  `ryanking13/SRT` lineage indicate the shapes are live-correct as of the app
  versions it targets, `SRT-APP-Android V.2.0.38`), but field values can drift
  with app updates — confirm against a live capture before shipping mutation.
- The mobile-JSON endpoints (`*_n.do`) are a *different server surface* from the
  WebView `#rsvForm`→`ard02017/18` flow our APK analysis documented. Both exist;
  srtgo_plus proves the JSON one is complete and HTTP-only.
- License: MIT (permissive, no copyleft). Reuse **facts only**; re-implement code.
</content>
</invoke>
