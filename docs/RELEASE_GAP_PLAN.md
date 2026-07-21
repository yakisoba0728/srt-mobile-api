# SRT Mobile API — Release Gap Analysis & Phased Plan (Read-only → Full Mutation)

**Target library:** `srt-mobile-api` (`src/srt_mobile_api/`)
**App under analysis:** `kr.co.srail.newapp` v2.0.41 (`versionCode=150`) — WebView shell over a
jQuery-Mobile web app on `app.srail.or.kr`.
**Date:** 2026-07-21 KST
**Scope of this document:** PLANNING ONLY. No code is changed and no live request is
made here. This plan drives a later implementation that extends the current
read-only client to full mutation (reservation / seat / payment / refund /
cancel / change).

**Primary sources cross-referenced**

- Authoritative static analysis: `docs/analysis/full-api-analysis-2026-07-20.md`
- **External working-tool reference (added 2026-07-21):** `docs/analysis/ref-srtgo_plus.md`
  — analysis of `srtgo`/`srtgo_plus` (`srtgo/srt.py`), a pure-Python tool that
  completes SRT reserve/pay/cancel/refund over the **mobile JSON API**. This
  reverses several verdicts below; see the marked `UPDATE (2026-07-21)` notes and
  `## Revision 2026-07-21` near the end.
- **Cross-validation vs OUR decompile (added 2026-07-21):** `docs/analysis/cross-validation-2026-07-21.md`
  — reconciles srtgo endpoint-by-endpoint against OUR decompiled v2.0.41 bundle
  (the ground truth). It **walks back** the srtgo-optimistic payment/cancel/refund
  verdicts (those endpoints are **0-hit across all 21,673 files** in our bundle)
  while **confirming** reserve (`arc05013`) and NetFunnel `act_10`. See the
  `UPDATE 2 (2026-07-21)` notes and `## Revision 2 (2026-07-21)` near the end.
- Prior runtime spec: `docs/analysis/srt-app-api-library-spec-2026-07-09.md`
- Decompiled app: `analysis/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java`
- Bundled web JS (the real request shapes): `analysis/apktool/assets/offline/js/ara/ara1001l.js`,
  `.../ara/ara0101v.js`, `.../arc/arc0102c.js`, `.../common/const.js`,
  `.../common/netfunnel.js`
- Current client: `src/srt_mobile_api/{client,safety,payloads,parsers,models,http,session,netfunnel,config,live,errors,redaction}.py`
- Progress/notes: `docs/IMPLEMENTATION_PROGRESS.md`, `CHANGELOG.md`, `README.md`, `SECURITY.md`

> **Feasibility headline (read this first).** SRT booking is browser/WebView-driven.
> The **reservation-create** call (`arc05013`/`arc06014`) is a plain form-encoded
> `$.ajax` POST and is *cleanly replicable* in Python once two live-only inputs are
> captured. **Payment is not.** The payment step is a server-rendered HTML page
> (`ard02017`/`ard02018`) that hosts a PG/EasyPay redirect, a SEED secure keypad,
> and optional FIDO — none reachable from a pure Python HTTP client.
> **Refund/cancel/change have ZERO static evidence anywhere in the APK** (verified
> below) and are fully blocked on live request-shape capture. The plan is honest
> about each boundary per section.
>
> **⚠️ UPDATE (2026-07-21, srtgo/srtgo_plus reference — KEY REVERSAL).** The headline
> above is correct *only for the WebView `#rsvForm`→`ard02017/18` HTML surface* our
> APK analysis saw. A **parallel mobile JSON API** on the same host
> (`app.srail.or.kr`) exists and completes the **entire** lifecycle over pure HTTP —
> reserve **and payment and cancel and refund** — with **no PG redirect, no SEED
> keypad, no FIDO, no native bridge**. Payment goes through a *different* JSON
> endpoint (`/ata/selectListAta09036_n.do` with plain card fields), not the WebView
> `ard02017/18` page. Cancel and refund have their own JSON endpoints too. So
> "payment is not replicable" and "cancel/refund have zero evidence" are **false for
> the mobile-JSON path**. Evidence: `srtgo/srt.py` (see `docs/analysis/ref-srtgo_plus.md`).
> The still-genuine gaps are seat-designation/change and group (`arc06014`) — srtgo
> does not implement those either. Corrections are inlined below and summarized in
> `## Revision 2026-07-21`.
>
> **⚠️ UPDATE 2 (2026-07-21, cross-validation vs decompiled v2.0.41 — PAYMENT WALK-BACK).**
> The "KEY REVERSAL" above was **over-optimistic for OUR version.** Cross-validating
> srtgo against OUR decompiled v2.0.41 bundle
> (`docs/analysis/cross-validation-2026-07-21.md`) found the mobile-JSON
> payment/cancel/refund endpoints `Ata09036` / `Ard02045` / `Atc02063` (plus standby
> `Ata01135`, reserve-info `getListAtc14087`, ticket-info `Ard02019`) are **0-hit
> across all 21,673 files** in our bundle — attested **only by srtgo's live runs**
> (possibly a different/newer app version). OUR app's real payment path IS the
> `ard02017/18` **WebView** page gated by **TransKey (SEED secure keypad) + FIDO +
> AppGuard**. So for OUR v2.0.41, **payment / cancel / refund are NOT statically
> confirmable** and revert to "**needs a live v2.0.41 capture**" (srtgo's shapes =
> starting hypothesis, not confirmed fact). **RESERVATION (`arc05013`, NetFunnel
> `act_10`) remains CONFIRMED present** in our app and stays feasible. See
> `## Revision 2 (2026-07-21)`.

---

## 1. Current State

### 1.1 What the client is today

The package is a **pure server-side, read-only HTTP client**. The route allowlist
in `safety.py` is the single authority on what can be sent.

- **Route count:** exactly **20** allowlisted routes (`safety.py:56-79`,
  `READ_ONLY_ROUTES`). 19 on `app.srail.or.kr` + 1 NetFunnel `act_10` helper on
  `nf.letskorail.com` (`GET /ts.wseq`, `safety.py:77`).
- **Read client methods (`client.py`):** `get_main` (`:90`), `get_booking_page`
  (`:95`), `get_notice_list`/`get_typed_notice_list` (`:110`,`:114`),
  `get_ticket_list` (`:118`), the six selector reads
  `get_station_selector`/`get_station_map_selector`/`get_date_selector`/`get_passenger_selector`/`get_seat_option_selector`/`get_train_group_selector`
  (`:137`-`:203`), `get_mutual_verification` (`:205`), `search_trains`/`search_group_trains`
  (`:278`,`:282`), `iter_train_search_pages` (`:372`), `get_seat_page` (`:387`),
  `get_timetable` (`:396`), `get_fare` (`:405`). Session: `login`/`clear_session`/`logout`
  (`client.py:73-80`, `session.py:14`).
- **HTTP verbs used:** GET + form POST only. All POSTs are
  `application/x-www-form-urlencoded` (`http.py:186`). No signing, nonce, or
  payload encryption anywhere (matches analysis §2.2).

### 1.2 Read-only safety model (the premise that mutation breaks)

- Every outbound request passes through `assert_read_only_request(request, config)`
  (`http.py:106` → `safety.py:118`). If the `(method, host_kind, path)` triple is
  not in the `READ_ONLY_ROUTES` frozenset, it raises `SrtProtocolError`
  (`safety.py:144-148`).
- `SrtConfig.__post_init__` pins canonical HTTPS origins and rejects anything else
  (`config.py:23-49`); `assert_read_only_request` re-checks the origins
  (`safety.py:119-120`).
- The one authenticated write-shaped read — the seat-map page
  `POST /arc/selectListArc02012_n.do` — is **field-locked**: exactly 13 named
  fields, fixed values (`reqCode=9`, `trnGpCd=300`, `psrmClCd=1`, `choiceSeatCount=1`),
  digit patterns, and no query string (`safety.py:19-53`, `:94-115`).
- `EXCLUDED_API_DOMAINS` (`safety.py:180-192`) names the deliberately-excluded
  surfaces conceptually: `reservation`, `netfunnel-act-19`, `ard-payment-entry`,
  `payment`, `refund`, `cancellation`, `ata-detail`, `native-bridge`,
  `external-seatmap`. These are documentation, not an enforcement path.
- `SAFETY_STATEMENTS` (`safety.py:194-198`) codify: no credential/cookie/key/PNR/card
  persistence; "do not implement real card approval in the core client."
- Strong PII redaction already exists (`redaction.py`): sensitive-key masking,
  `CARD_RE` (`redaction.py:39`), `JSESSIONID`, NetFunnel keys, PNR/journey keys, etc.

### 1.3 Only a reservation RESPONSE PARSER exists — no request layer

- `parse_reservation_attempt_response(data)` (`parsers.py:507-625`) parses the
  4-array reserve envelope `{resultMap, reservListMap, trainListMap, commandMap}`
  from **caller-supplied JSON only**. It performs **no I/O**, adds no route, and is
  exported as a pure offline helper (`__init__.py:32,51`).
- Typed evidence-only models exist: `ReservationAttemptResult`, `ReservationRecord`,
  `ReservationTrain` (`models.py:139-177`), all repr-safe.
- There is **no reservation request builder, no reserve/pay/cancel route, no
  NetFunnel `act_19` flow, and no mutation client method** (confirmed by
  `IMPLEMENTATION_PROGRESS.md:21-26,98-103`).

### 1.4 Note: no `crypto.py`

The task brief references `src/srt_mobile_api/crypto.py`; **that file does not
exist** in the package (verified). The client has no crypto module because the
app's only cryptographic client features (SEED secure keypad, FIDO/UAF) are
**native**, not HTTP, and are out of scope for a pure-Python client (analysis
§2.2). This matters for the payment section: there is nothing to port.

- **pyproject:** `version = "0.2.0"`, `Development Status :: 3 - Alpha`,
  description "…read APIs", keyword `"read-only"` (`pyproject.toml:7-11`).

---

## 2. Read-only Gaps (read endpoints not yet implemented)

The static/JS surface contains read endpoints and read-flows the client does not
yet cover. Listed as *route → purpose → source ref → why unimplemented*.

| # | Route / feature | Purpose | Source ref | Why unimplemented |
|---|---|---|---|---|
| R1 | `POST /arc/selectListArc02011_n.do` | **Physical seat-inventory JSON** (the real per-car/per-seat availability feed behind the seat-selection page) | `tests/fixtures/seat_page_schema_v2_evidence.json:200-222` (inline `jquery_ajax` POST → `/arc/selectListArc02011_n.do`); `IMPLEMENTATION_PROGRESS.md:71-75,337-344` | **Deferred physical-seat schema.** No stable iterable seat/car source or availability vocabulary has been captured yet; response grammar unknown; not allowlisted. Requires live capture. **⚠️ UPDATE 2 (2026-07-21, cross-val): `arc02011` is a PHANTOM — 0 hits across our entire decompile (the only `02011` match is an incidental AES T-table substring). The real seat endpoint is `arc02012` (`/arc/selectListArc02012_n.do`), which returns an HTML seat page, NOT a JSON inventory feed; the only structured output is the `popCallback` `{scarSeatNo,scarSeatNm,scarNo}` tuple (`ara0101v.js:868`). This "seat-inventory JSON" is mis-modelled and must be reframed (§Rev 2).** |
| R2 | `GET /ata/selectListAta01032_n.do` | Discount / fare detail for a booked PNR | `arc/arc0102c.js:33-37` (`data:"pnrNo=${commandMap.pnrNo}"` — unresolved JSP EL) | State-dependent: needs a real PNR; prior spec runtime = HTTP 500 with dummy PNR. Server-rendered HTML, no closed parser. |
| R3 | `GET /atc/selectListAtc14016_n.do` (incl. legacy `/neo`) | Alternate ticket/reservation list (the `btnNo` variant of the implemented `atc14017`) | `SRForegroundDialogActivity.java:31`; `SRWebActivity.java:1592`; analysis §1.2 | Adjacent variant of the already-implemented `atc14017` read; low value, HTML only. |
| R4 | Round-trip (왕복) search flow | Two sequential search calls to the same endpoint with leg swap (`rtnDv=1`, `fv_sRtnCd` 1→2, `back_dptDt1`/`back_dptTm1`) | `ara1001l.js:113-118`; analysis §3.2 | Client only issues one-way searches (`payloads.search_page_payload` fixes `rtnDv="0"`, `jrnyCnt="1"`, `search_page_payload:130-170`). No return-leg state machine. |
| R5 | Typed physical-seat model over the seat page | Turn `SeatSelectionPage` (opaque HTML) into typed cars/seats/availability | `models.py:186` (`SeatSelectionPage` is just `HtmlPage`); `IMPLEMENTATION_PROGRESS.md:337-344` | Blocked until R1 response evidence proves a stable schema (**Rev 2: `arc02011` is a phantom; the real seat endpoint is `arc02012` and returns HTML, not a JSON inventory feed**). |
| R6 | Date picker return-leg (`reqCode=4`, ARA0401P) | "오는열차 출발일시" return-date selection | `ara0101v.js:193-199` | Client's `get_date_selector` only issues the outbound `reqCode=3` path (and via ARA0403P — see §5.1). |

> **Excluded, not a gap:** `ara/selectListAra10h01.do` (dead Nexacro gateway inside
> a `/* */` comment, never issued — `ara1001l.js:254-278`). Do **not** implement.

**Count:** 5 unimplemented read surfaces (R1–R4, R6) + 1 blocked typed-seat model
(R5); 1 dead-code alias explicitly excluded.

---

## 3. Mutation Additions (the full mutation surface)

All request shapes below are read directly from the bundled JS. Every mutation
`.do` literal in the APK was enumerated; the complete set is: `arc02012`,
`arc05013`, `arc06014`, `ard02017`, `ard02018`, `ata01032` (plus the read
`ara*` search/timetable/fare and the dead `ara10h01`). **There is no `cancel`,
`refund`, or `change` endpoint literal anywhere in the bundled JS or in the
decompiled Java** — verified by exhaustive `.do` enumeration across
`analysis/apktool/assets/offline/js/{ara,arc}` and `analysis/jadx/sources`.

> **UPDATE (2026-07-21, srtgo ref).** The "no cancel/refund/change literal in the
> APK" finding still holds *for the WebView bundle* — but it does **not** mean these
> operations are unreachable. The SRT **native mobile JSON API** (a distinct server
> surface the WebView bundle does not use) exposes concrete endpoints for cancel,
> refund and payment that srtgo/srtgo_plus drives directly. They are absent from our
> APK JS only because the WebView never calls them; the native app path does. New
> mobile-JSON endpoints confirmed in `srt.py` (`docs/analysis/ref-srtgo_plus.md`):
> - **reserve** `/arc/selectListArc05013_n.do` — `jobId=1101` personal, `1102`
>   standby/예약대기 (`srt.py:94`, body `srt.py:962-997`);
> - **payment (card)** `/ata/selectListAta09036_n.do` — plain card fields, no PG
>   (`srt.py:99`, body `srt.py:1184-1216`);
> - **cancel (unpaid, 예약취소)** `/ard/selectListArd02045_n.do` (`srt.py:97`, body
>   `srt.py:1138`);
> - **refund (paid, 환불)** 2-step `/atc/getListAtc14087.do` →
>   `/atc/selectListAtc02063_n.do` (`srt.py:100,102`, `srt.py:1227-1257`).
>
> *Change (변경)* and *group reserve* (`arc06014`) are still unimplemented by srtgo,
> so those two remain genuine capture-blocked gaps.
>
> **⚠️ UPDATE 2 (2026-07-21, cross-validation).** The three mobile-JSON endpoints
> asserted just above — `Ata09036` (payment), `Ard02045` (cancel),
> `getListAtc14087`→`Atc02063` (refund), plus `Ata01135` and `Ard02019` — are
> **0-hit across all 21,673 files** in OUR v2.0.41 decompile. They are attested only
> by srtgo's live runs, so for our version they are **NOT confirmed** and revert to
> capture-blocked. Only **reserve `arc05013`** (with `jobId 1101/1102`) and its
> **`act_10`** gate are actually present in our bundle. See `## Revision 2 (2026-07-21)`.

### 3.1 Response envelopes

- **Reserve envelope (4 arrays), each read as `[0]`:**
  `{resultMap[], reservListMap[], trainListMap[], commandMap[]}`
  (`ara1001l.js:1560,1577-1579`; models in `parsers.py:507-625`).
  - `resultMap[0]`: `strResult` ("FAIL"=business error), `msgCd` ("S111"=re-login),
    `msgTxt`, `totRcvdAmt`, `tmpJobSqno1` (`ara1001l.js:1560-1602`).
  - `reservListMap[0]`: `pnrNo` (individual only), `JRNYLIST_KEY`, `arvDt`,
    `arvRsStnCd`, `arvTm`, `dlayAcptFlg`, `dptDt`, `dptRsStnCd`, `dptTm`,
    `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`,
    `trnNo` (`ara1001l.js:1612-1626`).
  - `trainListMap[0]`: `seatNo`, `scarNo` (`ara1001l.js:1604-1605`).
- **Search / read envelope (for contrast):** `{ErrorCode, ErrorMsg,
  outDataSets:{dsOutput0[], dsOutput1[]}}` (`ara1001l.js:190-199`) — structurally
  different from reserve, in the same file.
- **Payment (`ard*`) response:** a full server-rendered **HTML page** (~84 KB /
  ~83 KB in prior runtime probes), not JSON. *(This describes the WebView entry
  page only.)*
- **UPDATE (2026-07-21):** the mobile-JSON payment endpoint `ata09036` returns
  **JSON**, not HTML — success/failure read from
  `outDataSets.dsOutput0[0].strResult` (`srt.py:1220-1225`). Cancel/refund return
  the standard `SRTResponseData` envelope (`strResult == "SUCC"|"FAIL"`,
  `srt.py:366-411`); refund pre-info (`atc14087`) uses an `{ErrorCode, ErrorMsg}`
  envelope instead.
- **⚠️ UPDATE 2 (2026-07-21, cross-validation):** these envelope shapes describe
  **srtgo's** live responses only — `ata09036`, cancel `ard02045`, refund
  `atc14087`/`atc02063` are **0-hit in OUR v2.0.41 bundle** and cannot be verified
  from our code. The only response envelope actually confirmed in our app is the
  reserve 4-array JSON (`arc05013`). Treat the payment/cancel/refund envelopes as
  unconfirmed hypotheses (`docs/analysis/cross-validation-2026-07-21.md` §3–§4).

### 3.2 The multi-step happy-path flow

```
search (ara10007 / ara10082, group)                        [READ — implemented]
   │  select train + cabin class → lfn_setRsv(gds_rsv)      ara1001l.js:1427-1470
   ▼
[optional] seat map (arc02012, reqCode 9/10/11) → HTML page ara1001l.js:1495-1520
   │  user picks seats in WebView DOM → popCallback           ara0101v.js:866-894
   │  yields {scarSeatNo,scarSeatNm,scarNo} → gds_rsv seatNo* ara0101v.js:869-882
   ▼
reserve (arc05013 individual / arc06014 group)  $.ajax POST  ara1001l.js:1541-1560
   │  body = $("#rsvForm").serialize(); 21 fields validated   ara1001l.js:1649-1701
   │  → resultMap/reservListMap/trainListMap/commandMap
   │  (S111 ⇒ re-login; else pnrNo / tmpJobSqno1 obtained)
   ▼
payment entry (ard02017 individual / ard02018 group)         ara1001l.js:1596-1646
   │  #rsvForm RETARGETED (frm.action=…), frm.submit()  ← FORM POST, not ajax
   │  returns server-rendered HTML PAYMENT PAGE (PG/EasyPay)
   ▼
PG / EasyPay approval  (WebView + native srbridge `easypay`) SRWebActivity.java:1658-1685
   │  Shinhan app scheme / SEED secure keypad / FIDO
   ▼
confirm / ticket issued  (state persists → atc ticket list)
```

Cancel / refund / change: **no static path exists.** They live in the `atc`
ticket-management server-rendered pages (`atc14016`/`atc14017`) whose mutation
request shapes are not in the APK.

### 3.3 Endpoint-by-endpoint mutation catalog

| Route | Method | Params (as posted by bundled JS) | Response | JS source | Replicability |
|---|---|---|---|---|---|
| `/arc/selectListArc02012_n.do` (seat map) | POST | `reqCode`(9/10/11), `runDt`, `dptDt`, `trnNo`, `dptTm`, `trnGpCd="300"` (hard-coded SRT-only), `dptRsStnCd`, `arvRsStnCd`, `psrmClCd`, `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, `choiceSeatCount` | HTML page; seat pick returns `{scarSeatNo,scarSeatNm,scarNo}` via `popCallback` | `ara1001l.js:1498-1520`; `ara0101v.js:866-894` | **Partial.** POST is replicable (already allowlisted read-only for `reqCode=9`). The *actual per-seat selection* is DOM/WebView interaction; the only machine-readable output is the `popCallback` tuple, **not** a separate JSON feed (see R1: `arc02011` is a phantom; the real endpoint is this `arc02012`, HTML). |
| `/arc/selectListArc05013_n.do` (reserve, individual) | POST | `$("#rsvForm").serialize()`; 21 fields validated by `fn_validChk`: `jobId, jrnyTpCd, jrnyCnt, totPrnb, stndFlg, jrnySqno1, trnGpCd1, stlbTrnClsfCd1, dptDt1, dptTm1, dptRsStnCd1, arvRsStnCd1, psrmClCd1, smkSeatAttCd1, dirSeatAttCd1, locSeatAttCd1, psgInfoPerPrnb1, etcSeatAttCd1, rqSeatAttCd1, psgGridcnt, psgTpCd1` (+ seat fields `seatNo1_*`, `scarNo1`) | 4-array JSON envelope (§3.1) | `ara1001l.js:1547,1550,1649-1701` | **Cleanly replicable via direct POST.** ~~*iff* the full `#rsvForm` field set and the live NetFunnel `act_19` key are captured~~ → **UPDATE (2026-07-21): both prerequisites RESOLVED.** srtgo posts the complete ~30-field body (`srt.py:962-997`, jobId `1101`/`1102`; seat fields omitted → server auto-assigns) and gates on the **`act_10`** key we already implement — **not** `act_19` (`srt.py:987`). No live `#rsvForm` scrape and no new gate needed. |
| `/arc/selectListArc06014_n.do` (reserve, group) | POST | same `#rsvForm`; selected purely by `grpDv=="1"`; ≥10 pax; group receives **no `pnrNo`** | same envelope | `ara1001l.js:1542-1544,1597-1605` | Same as `arc05013`. |
| `/ard/selectListArd02017_n.do` (payment entry, individual) | **POST (form submit)** | `#rsvForm` retargeted: `pnrNo`=reservListMap.pnrNo, `jrnySqno=1`, `JRNYLIST_KEY`, `arvDt/arvRsStnCd/arvTm`, `dlayAcptFlg`, `dptDt/dptRsStnCd/dptTm`, `jrnyTpCd`, `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`, `trnNo` + all remaining rsvForm fields | **HTML payment page** (~84 KB) | `ara1001l.js:1606-1626,1642-1646` | **WebView/PG-dependent — for THIS endpoint only.** A Python client can POST it and inspect the returned HTML, but this page *is* the WebView payment UI (PG redirect + secure keypad); approval cannot complete here. **UPDATE (2026-07-21): payment is NOT infeasible overall** — the mobile app pays via a *different* JSON endpoint, `ata09036` (new row below), which charges a card over plain HTTP with no PG/keypad/FIDO. `ard02017/18` is simply not the route the native app uses to pay. **⚠️ UPDATE 2 (cross-val): `ata09036` is 0-hit in OUR v2.0.41 bundle; OUR real payment path IS this `ard02017/18` WebView page + TransKey keypad + FIDO + AppGuard — payment reverts to needs-live-capture (§Rev 2).** |
| `/ard/selectListArd02018_n.do` (payment entry, group) | **POST (form submit)** | `pnrNo=-1` (hard), `rcvdAmt`=resultMap.totRcvdAmt, `tmpJobSqno1`, `tmpJobSqno2=0`, `seatNo1`=trainListMap.seatNo, `scarNo1`=trainListMap.scarNo + shared journey fields | HTML payment page (~83 KB) | `ara1001l.js:1596-1605` | Same WebView/PG dependency. |
| `/ata/selectListAta01032_n.do` (discount detail) | GET | `pnrNo=${commandMap.pnrNo}` (JSP EL, server-rendered) | HTML page | `arc/arc0102c.js:33-37` | Read-but-state-dependent (needs a real PNR). Not a mutation, listed for flow completeness. |
| **cancel / refund / change** | **unknown** | **no static evidence in APK** | unknown | — (absent) | ~~**Blocked on live capture.**~~ **UPDATE (2026-07-21): cancel & refund RESOLVED via mobile-JSON API** (rows below); **change (변경) still capture-blocked** (srtgo has no change endpoint either). **⚠️ UPDATE 2 (cross-val): cancel `ard02045` & refund `atc14087`/`atc02063` are 0-hit in OUR bundle — srtgo-attested only; all three revert to needs-live-capture (§Rev 2).** |
| **`/ata/selectListAta09036_n.do` (payment, card)** — mobile-JSON *(NEW, 2026-07-21)* | POST | `stlCrCrdNo1`(PAN, no hyphens), `crdVlidTrm1`(expiry YYMM), `vanPwd1`(pw first 2 digits), `athnVal1`(birthday YYMMDD / biz-no), `athnDvCd1`(`J` personal / `S` corp), `ismtMnthNum1`(installment), `stlMnsCd1="02"`(credit card), `crdInpWayCd1="@"`, `totNewStlAmt`/`mnsStlAmt1`(=total_cost), `pnrNo`, `mbCrdNo`, `ctlDvCd="3102"`, `cgPsId="korail"`, `trnGpCd="300"`, `jrnyCnt="1"` … | **JSON** (`dsOutput0[0].strResult`) | `srt.py:99`, body `srt.py:1184-1216`, resp `srt.py:1220-1225` | **Fully HTTP-replicable — NO PG/keypad/FIDO.** Real card charge over plain form-POST. **This is the opposite of the `ard02017/18` verdict** and is exactly what the §4 safety guardrails must block. **⚠️ UPDATE 2 (cross-val): `ata09036` is 0-hit across all 21,673 files in OUR v2.0.41 bundle — srtgo-attested only (maybe a different/newer app); UNCONFIRMED for our version, needs live capture (§Rev 2).** |
| **`/ard/selectListArd02045_n.do` (cancel, 예약취소)** — mobile-JSON *(NEW, 2026-07-21)* | POST | `pnrNo`, `jrnyCnt="1"`, `rsvChgTno="0"` | `SRTResponseData` (SUCC/FAIL) | `srt.py:97`, body `srt.py:1138` | **Fully replicable.** Unpaid-reservation cancel. **⚠️ UPDATE 2 (cross-val): `ard02045` 0-hit in OUR bundle — srtgo-attested only; needs live capture (§Rev 2).** |
| **`/atc/getListAtc14087.do` → `/atc/selectListAtc02063_n.do` (refund, 환불)** — mobile-JSON, 2-step *(NEW, 2026-07-21)* | POST | step 1 (Referer `/common/ATC/ATC0201L/view.do?pnrNo=<pnr>`, no body) → returns `ogtkSaleDt, ogtkSaleWctNo, ogtkSaleSqno, ogtkRetPwd, buyPsNm`; step 2 body: `pnr_no`(underscore!), `cnc_dmn_cont="승차권 환불로 취소"`, `saleDt, saleWctNo, saleSqno, tkRetPwd, psgNm` | step 1 `{ErrorCode,ErrorMsg}`; step 2 `SRTResponseData` | `srt.py:100,101,102`, `srt.py:1227-1257` | **Fully replicable.** Paid/issued-ticket refund; needs the pre-info fetch first. **⚠️ UPDATE 2 (cross-val): `getListAtc14087`/`atc02063` 0-hit in OUR bundle — srtgo-attested only; needs live capture (§Rev 2).** |

### 3.4 Prerequisites for mutation

- **Authenticated cookie session.** Login is enforced downstream: seat selection
  aborts when `MB_CRD_NO==""` (`ara1001l.js:1288-1306`); reserve returns
  `resultMap[0].msgCd=="S111"` to force re-login (`ara1001l.js:1565-1571`). The
  client already establishes the WebView cookie session in `session.py:14-52`.
- **NetFunnel.** Bundled JS has the queue **disabled** — every
  `NetFUNNEL.SetService/BEGIN` is commented out and replaced by a direct
  `netfunnel_callback()` (`ara0101v.js:651-655`; `ara1001l.js:1734-1740`,`:1746-1754`).
  But the **live server still gates** search on a fresh `act_10` key (`NET000001`
  on omission — implemented at `netfunnel.py:18`, `client.py:218-224`). ~~The
  reservation path is expected to gate on a separate **`act_19`** key… must be
  captured live before `arc05013` can succeed.~~
  **UPDATE (2026-07-21, srtgo ref): there is NO separate `act_19` gate.** srtgo
  reserves by injecting `netfunnelKey=self._netfunnel.run()` into the `arc05013`
  body — the **same `act_10` helper it uses for search** (`aid="act_10"`,
  `srt.py:603`; reserve injects it at `srt.py:987`; search at `srt.py:819`). The key
  is cached ≤48 s and reused. **We already implement `act_10`, so no new gate is
  needed and this prerequisite is removed.**
- **Device / UA.** UA suffix `SRT-APP-Android V.2.0.41` (`config.py:5-9`;
  `SRWebActivity.java:2642-2645`); `deviceKey`/`deviceId` (`config.py:19`).
  **UPDATE (2026-07-21):** srtgo's mobile-JSON path sends `deviceKey="-"` (a literal
  hyphen — no real device key/attestation) and a UA suffix `V.2.0.38`
  (`srt.py:20-23,705`). No device attestation is required for the JSON API.
- **Login needs NO encryption.** **UPDATE (2026-07-21):** despite the field name
  `hmpgPwdCphd` (the `Cphd` = "cipher" suffix), srtgo sends the password
  **plaintext/verbatim** — no hashing, no RSA, no device attestation
  (`srt.py:700-731`, esp. `:709` `hmpgPwdCphd=srt_pw` and `:705` `deviceKey="-"`).
  Any assumption that SRT login requires client-side encryption is wrong; the SEED
  keypad/FIDO in §1.4 apply to the *WebView payment/keypad UI*, not to login or to
  the mobile-JSON auth endpoint `apb01080`.
- **Anti-bot: TLS/JA3 impersonation is required.** **UPDATE (2026-07-21):** srtgo
  prefers `curl_cffi.Session(impersonate="chrome")` so its TLS/JA3 fingerprint
  matches a real Chrome/Android WebView (`srt.py:2-7,652-655`), falling back to
  `requests` only if `curl_cffi` is absent. To exercise the mobile-JSON endpoints
  reliably our client will likely need the same browser-impersonation transport
  (e.g. `curl_cffi`); a plain `requests`/`httpx` client may be JA3-fingerprinted and
  blocked. There is **no request signing, nonce, or body encryption** anywhere in
  the SRT path (`srt.py:380`).
- **Hidden / server-rendered form fields.** The full `#rsvForm` / `#seatSearchForm`
  markup is server-rendered JSP and **absent from the APK** (analysis §9.3). Only
  the ~21 validated + seat fields are enumerable statically; the remaining hidden
  inputs ~~must be scraped from the live booking page~~.
  **UPDATE (2026-07-21, srtgo ref): RESOLVED — no live scrape needed.** The complete
  reserve body (~30 fields) is known statically from `srt.py:962-997`; every field
  our `#rsvForm` analysis missed is **derived from the search-result train object**
  (`dptRsStnCdNm1`/`arvRsStnCdNm1` station-name strings, `*StnConsOrdr1`/`*StnRunOrdr1`
  consist/run orders, `trnNo1` 5-digit zero-padded, `runDt1`, `arvTm1`, `trnGpCd=109`
  / `trnGpCd1=300`, `grpDv=0`, `rtnDv=0`, `mblPhone`, `reserveType=11` personal-only)
  plus `Passenger.get_passenger_dict()` rows (`srt.py:179-204`) — **none of it is
  scraped from a server-rendered hidden form.** Seat fields (`seatNo1_*`, `scarNo1`)
  are simply **not sent** by srtgo; the server auto-assigns.

### 3.5 Replicable vs WebView/PG/native-blocked (explicit separation)

> **UPDATE (2026-07-21, srtgo ref): this whole trichotomy is re-drawn.** The buckets
> below were computed from the **WebView surface only**. On the **mobile-JSON
> surface** srtgo proves that reserve + payment + cancel + refund are *all* cleanly
> HTTP-replicable. The corrected classification is:
>
> - **Cleanly replicable via direct mobile-JSON POST (pure HTTP):** reserve
>   `arc05013` (`jobId 1101/1102`), **card payment `ata09036`**, cancel `ard02045`,
>   refund `atc14087`→`atc02063`, standby-option `ata01135`, ticket-detail
>   `ard02019`. All shown working in `srt.py` with `act_10` + `curl_cffi`.
> - **Still WebView/native-blocked (unchanged, but no longer on the critical path
>   for payment):** the `ard02017/18` *HTML* payment page, its PG/EasyPay redirect,
>   SEED keypad, FIDO — these are a *parallel* flow the native app does not use to
>   pay, so they no longer block a working payment implementation.
> - **Still genuinely capture-/support-blocked:** *change (변경)* (no srtgo endpoint),
>   *group reserve `arc06014`* (srtgo does personal `arc05013` only), *designated
>   physical-seat selection & the `arc02011` seat-inventory schema* (srtgo lets the
>   server auto-assign and never posts `seatNo1_*`/`scarNo1`).

> **⚠️ UPDATE 2 (2026-07-21, cross-validation) — the re-draw above is walked back for
> OUR version.** srtgo's payment/cancel/refund endpoints (`ata09036`, `ard02045`,
> `atc14087`→`atc02063`, plus `ata01135`, `ard02019`) are **0-hit across all 21,673
> files** in OUR v2.0.41 bundle, so for our app they are **NOT** "cleanly replicable"
> — they revert to **capture-blocked / needs-live-capture** (srtgo shapes = hypothesis).
> The only mutation endpoints actually present in our bundle are **reserve `arc05013`
> / group `arc06014`** and **seat-map `arc02012` (HTML)** with the **`act_10`** gate.
> So the corrected buckets are: **replicable & confirmed in-bundle:** reserve
> `arc05013` (`jobId 1101/1102`) + `act_10`. **WebView/native-blocked (OUR real
> payment path):** `ard02017/18` + TransKey keypad + FIDO + AppGuard. **Capture-
> blocked (srtgo-attested only, unconfirmed for v2.0.41):** payment, cancel, refund,
> change, group reserve `arc06014`, and the `arc02012` HTML seat page. See
> `## Revision 2 (2026-07-21)`.

The original WebView-surface classification is retained below for reference, with the
reversed items struck:

- **Cleanly replicable via direct `.do` POST**
  - `arc05013` / `arc06014` reserve-create (produces a real held reservation / PNR).
  - `arc02012` seat-map POST (already allowlisted for `reqCode=9`; extend to 10/11).
  - Reserve response parsing (already exists: `parse_reservation_attempt_response`).
  - **+ (2026-07-21)** `ata09036` payment, `ard02045` cancel, `atc14087`→`atc02063`
    refund — see §3.3 new rows.
- **WebView / PG / secure-keypad / native-blocked (NOT cleanly replicable)**
  - ~~`ard02017` / `ard02018` payment **completion**~~ — the *HTML page* still hosts
    PG/keypad, **but payment overall is replicable via `ata09036` JSON**, so this is
    no longer a blocker (§6/§3.3).
  - EasyPay / Shinhan handoff — `srbridge` `easypay` native action + external app
    scheme `shinhan-sr-ansimclick-srt://` (`SRWebActivity.java:1658-1685`). Native,
    not HTTP. *(Not on the srtgo payment path.)*
  - SEED secure keypad (`showTransKey`, `SRWebActivity.java:2352-2390`) and FIDO/UAF
    (`https://fido.srail.co.kr`, `SRWebActivity.java:2517-2519`) — native only.
    *(Not on the srtgo payment path.)*
  - Physical per-seat pick — DOM interaction on the `arc02012` page → `popCallback`.
    **Still blocked** (srtgo auto-assigns; genuine gap).
- **Blocked on live request-shape capture (no static evidence)**
  - ~~Cancel / refund~~ **RESOLVED** via mobile-JSON (`ard02045`; `atc14087`→`atc02063`).
    **Change (변경) still capture-blocked** (no srtgo endpoint).
  - ~~Full `#rsvForm` hidden-field list~~ **RESOLVED** (`srt.py:962-997`, §3.4).
  - ~~NetFunnel `act_19` reservation gate~~ **RESOLVED — does not exist; reuse
    `act_10`** (`srt.py:987`, §3.4/§5.4).
  - `ard` payment-page field grammar — moot (payment goes via `ata09036`).
  - **`arc02011` physical-seat inventory schema — still unresolved** (srtgo does not
    cover it; R1/R5 remain deferred).

**Mutation surface count:** ~~5~~ **the WebView surface has 5 statically-evidenced
`.do` routes**; **the mobile-JSON surface (srtgo) adds `ata09036`, `ard02045`,
`atc14087`, `atc02063`, `ata01135`, `ard02019`, plus reuses `arc05013`.** Corrected
verdict: **reserve, payment, cancel, and refund are ALL cleanly replicable over pure
HTTP via the mobile-JSON API**; only **change, group-reserve (`arc06014`), and
designated-seat selection** remain capture-/support-blocked.

---

## 4. Safety-model Redesign

Adding mutation invalidates the premise that "every allowed route is read-only."
The redesign keeps the current guarantees for read traffic bit-for-bit and adds a
**tiered, capability-gated, fail-closed** policy for mutation.

> **⚠️ UPDATE (2026-07-21, srtgo ref) — the safety model is now MANDATORY, not
> aspirational.** The earlier draft could lean on "payment completion is infeasible
> from pure Python, so it is self-safe." **That assumption is false.** srtgo's
> `ata09036` JSON endpoint performs a **real card charge over plain HTTP** with no
> PG/keypad/FIDO barrier (`srt.py:1149-1225`) — fed real card data, it *would*
> charge. Likewise `arc05013` creates a real (billable) reservation and `ard02045`
> really cancels. Therefore every guardrail below is **required**, not optional:
> (1) **fake-card-only** (Luhn-invalid PAN enforced — the only thing standing between
> a test and a real charge), (2) **default dry-run**, (3) **never auto-submit** the
> charge, (4) **never persist** card/PNR/credential, and (5) **auto-cancel** every
> test reservation. Nothing about the mobile-JSON surface is "self-safe."
>
> **⚠️ UPDATE 2 (2026-07-21, cross-validation).** For OUR v2.0.41 the `ata09036`
> charge path is **srtgo-attested only** (0-hit in our bundle) — our confirmed
> billable action is **reserve `arc05013`**, and payment is the WebView `ard02017/18`
> page. The guardrails above stay **mandatory as a precaution**: if srtgo's `ata09036`
> shape is ever wired up on a live capture, it would charge, so fake-card-only +
> dry-run + never-persist + auto-cancel must be in place *before* any such attempt.

**One-line approach:** *replace the single `READ_ONLY_ROUTES` allowlist with a
tiered route policy — READ is always on; RESERVE / PAYMENT / CANCEL each require
explicit typed consent, default to dry-run, route card data only through a
fake-card-only path that can never reach PG approval, persist no card/PNR, and
auto-cancel test reservations.*

### 4.1 Concrete `safety.py` restructuring

1. **Route classification.** Introduce `class RouteClass(Enum): READ, RESERVE,
   PAYMENT_ENTRY, CANCEL`. Keep `READ_ONLY_ROUTES` unchanged (20 routes) as the
   READ tier. Add a parallel `MUTATION_ROUTES: dict[ReadOnlyRoute, RouteClass]`
   registry (`arc05013`/`arc06014`→RESERVE, `ard02017`/`ard02018`→PAYMENT_ENTRY,
   cancel/refund→CANCEL once captured).
2. **Policy-parameterized gate.** Generalize to
   `assert_request(request, config, policy)`. `policy` is a frozen object listing
   which `RouteClass`es are permitted this call. **Default policy = READ only**, so
   `assert_read_only_request` becomes `assert_request(..., READ_ONLY_POLICY)` and
   all existing read tests stay green with zero behavior change. Anything not in an
   enabled tier still raises `SrtProtocolError` (fail-closed).
3. **Explicit, non-boolean opt-in.** Mutation is never enabled by an env var or a
   bare `True`. `SrtClient` gains `enable_mutations(policy: MutationPolicy)` where
   `MutationPolicy` must be constructed with named intent flags
   (`allow_reserve`, `allow_payment_entry`, `allow_cancel`). No default enables
   payment.
4. **Confirmation gate per call.** Each mutating method requires a **typed consent
   token**, not a bool — e.g. `client.reserve(req, consent=ReserveConsent(...))`,
   `client.pay(..., consent=PaymentConsent(fake_card=FakeCard(...)))`. A plain
   `confirm=True` is rejected. This prevents accidental fire.
5. **Dry-run default.** `reserve()`/`pay()` default to `dry_run=True`: build the
   payload, run it through `assert_request`, and **return the prepared request for
   inspection without sending**. A live send requires `dry_run=False` *and* the
   consent token *and* an enabled policy tier.
6. **Fake-card-only payment path.** A `FakeCard` type rejects any PAN that (a)
   passes Luhn or (b) matches a real-BIN prefix table — only structurally-invalid
   test numbers are accepted. The payment method **never auto-submits** the
   `ard`-returned HTML, never follows the PG redirect, and cannot invoke the
   native `easypay` bridge. Card values are **never stored** and never logged
   (extend `redaction.py SENSITIVE_KEYS` with `cardNo`, `pan`, `expiry`, `cvc`,
   `authNo`, `easypay*`, `rcvdAmt`-adjacent). The path is *structurally incapable*
   of charging.
7. **Auto-cancel of test reservations.** Provide a
   `reserve_for_test(...)` context manager that yields the PNR and **guarantees a
   cleanup attempt on exit**. Until the cancel endpoint is captured (§3.5), cleanup
   emits a loud, explicit warning and the live reserve test is gated behind an
   additional `SRT_ALLOW_TEST_RESERVATION=1` env flag plus manual-cleanup
   acknowledgement.
8. **Permanent exclusions stay excluded.** Keep `EXCLUDED_API_DOMAINS`
   (`safety.py:180-192`) but split its meaning: `native-bridge`/`external-seatmap`
   (`easypay`, Shinhan scheme, SEED keypad, FIDO, korail seatmap) are **permanently
   non-implementable** and never gated on; `reservation`/`cancellation`/`refund`
   move to the opt-in mutation tiers.
   **UPDATE (2026-07-21):** `payment` must **also move to an opt-in tier**, not stay
   in the "permanently non-implementable" bucket — the mobile-JSON `ata09036` charge
   *is* implementable (§6). What stays permanently excluded is only the WebView
   `ard02017/18` PG page and the native bridges. Because the `PAYMENT_ENTRY` tier can
   now actually charge, its fake-card-only + dry-run guardrails are load-bearing, not
   documentation.
   **⚠️ UPDATE 2 (2026-07-21, cross-validation):** `ata09036` is **0-hit in OUR
   v2.0.41 bundle** — it is srtgo-attested only, so for our version the *confirmed*
   payment surface is the WebView `ard02017/18` page (TransKey keypad + FIDO +
   AppGuard). Keep the `PAYMENT_ENTRY` opt-in tier + guardrails scaffolded, but treat
   an `ata09036` implementation as gated behind a live-capture confirmation, not a
   settled fact.
9. **PII redaction extension.** `redaction.py` already masks PNR/journey/NetFunnel
   keys and cards; add the card/easypay/auth keys above and confirm reserve/pay
   request+response bodies are redacted in every error path (`errors.py` already
   redacts messages).

### 4.2 Invariants the redesign must preserve

- With no `MutationPolicy`, the client behaves exactly as 0.2.0 (20 read routes,
  same tests).
- No code path can send a `PAYMENT_ENTRY` request that carries a Luhn-valid PAN.
- No credential, cookie, NetFunnel key, PNR, or card value is written to disk,
  fixtures, or logs (`SECURITY.md`, `.gitignore:8-9` keep `.env` out of git).

---

## 5. Correctness & Bugs (client vs decompiled/JS truth)

Each item cites both sides. Several are "correct for their layer" per analysis
§8.3 but must be reconciled before mutation relies on them.

1. **Date picker path + params diverge (ARA0403P vs ARA0401P).**
   Client posts `/common/ARA/ARA0403P/view.do` with `reqCode=3, selectDay,
   selectDt, selectTime=hour` (`client.py:159-165`; `payloads.py:54-69`). Bundled
   JS posts `/common/ARA/ARA0401P/view.do` with `reqCode=3(가는)/4(오는),
   selectDay, selectDt` and **no `selectTime`** (`ara0101v.js:187-203`). Two
   divergences: (a) different picker id, (b) client adds a `selectTime` field the
   JS never sends, and (c) the `reqCode=4` return-date path is unimplemented.
   Confirm the live server still serves ARA0403P and whether `selectTime` is
   accepted/ignored.
2. **ARA0502P station-map has no static request-shape evidence.**
   Client posts `/common/ARA/ARA0502P/view.do` with `reqCode=2` + `chk_rtrp,
   sNowSel, page, boolRtrp` (`client.py:151-157`; `payloads.py:44-51`). The
   call site is **absent from `ara0101v.js`** in this build (analysis §3.3 note,
   §8.3). This route's payload is inferred/live-only — flag for live confirmation,
   not JS-verifiable.
3. **Station selector sends 3 fields the JS omits.**
   Client `station_selector_payload` adds `chk_rtrp="false"`, `page="ARA0101"`,
   `boolRtrp="false"` (`payloads.py:31-41`). Bundled JS sends only `reqCode,
   sDptStnNm, sArvStnNm, sDptStnCd, sArvStnCd, sNowSel` (`ara0101v.js:158-165`).
   Extra fields are live-inferred; verify they are harmless.
4. **NetFunnel `act_10` implemented; ~~`act_19` reserve-gate missing~~ — reserve
   reuses `act_10`.**
   Client implements only `act_10` (`netfunnel.py:18`; `safety.py:155-177`
   act_10 contract). Bundled `netfunnel.js` references `act_10` only (line 17);
   `act_19` does not appear. ~~For reserve, the `act_19` request shape is a
   live-only fact to capture.~~
   **UPDATE (2026-07-21, srtgo ref):** `act_19` **does not exist as a separate gate**
   — srtgo gates *both* search and reserve on the **same `act_10` key** (`aid="act_10"`,
   `srt.py:603`; reserve injects `netfunnelKey=self._netfunnel.run()` at
   `srt.py:987`). The handshake is `getTidchkEnter=5101` → poll `chkEnter=5002`
   (while status `201`) → `setComplete=5004`, success statuses **`200` or `502`**
   (`srt.py:501-509,542-568`). So the `act_19` capture prerequisite is removed, and
   the `(5002,200)` success pair is confirmed (with `502`=already-completed as an
   additional pass). `EXCLUDED_API_DOMAINS`'s `netfunnel-act-19`
   (`safety.py:182`) entry can be retired.
5. **Seat-page read cannot express 특실 or multi-seat, and only `reqCode=9`.**
   Client hard-codes `psrmClCd="1"` (일반실) and `choiceSeatCount="1"`
   (`payloads.py:286,296`; `safety.py:37-42`) and only `reqCode=9`. Bundled JS uses
   `psrmClCd=lfn_getRsv("psrmClCd1")` (can be `2`=특실) and
   `choiceSeatCount=lfn_getRsv("totPrnb")` (can be >1) and `reqCode` 9/10/11
   (`ara1001l.js:1499,1507,1511`; `const.js:9-11`). The read is therefore a
   one-way, single-general-seat special case. Reservation needs the full range.
6. **`trnGpCd` hard-coded `"300"` — correct, keep.**
   Client fixes `trnGpCd="300"` (`payloads.py:275`; `safety.py:38`); JS does the
   same with the explicit "SRT만 가능…무조건 300" comment (`ara1001l.js:1504`).
   Verified consistent.
7. **Reserve parser does not distinguish `S111` re-login.**
   `parse_reservation_attempt_response` raises a generic `SrtAppError` for any
   `strResult!="SUCC"` and treats `msgCd=="WRP011002"` as failure
   (`parsers.py:538-539`). Bundled JS treats `strResult=="FAIL"` + `msgCd=="S111"`
   as **session-expired → `memberShipLogin()`** (`ara1001l.js:1562-1571`). When
   wired to a live route, `S111` should map to `SrtSessionExpiredError`, not a
   generic app error, so session recovery works.
   **UPDATE (2026-07-21, srtgo ref):** srtgo's mobile-JSON path does **not** key on
   `msgCd=="S111"`; `srt.py` has no explicit re-login map, and the orchestration
   layer detects expiry by the **message substring `"로그인 후 사용하십시오"**` and
   re-logs in (`srtgo.py:732-739`). So on the JSON surface, session-expiry detection
   may be message-substring-based rather than an `S111` `msgCd` — support both when
   wiring the live route.
8. **`S111` privacy leak to be avoided in our client.**
   The web app, on `S111`, writes the full serialized `rsvForm` to
   `localStorage['userReservation']` and `alert(param)` (`ara1001l.js:1565-1571`).
   Our client must **never** persist or log the reserve body (already covered by
   redaction; add explicit test). Documentation-only for us, but relevant.
9. **Passenger selector `isOrg` is fixed, JS derives it.**
   Client sends `isOrg="2"` always (`payloads.py:75`); JS sets
   `isOrg = chk_grp_dv ? "1" : "2"` (`ara0101v.js:233`). Group booking needs
   `isOrg="1"`. Minor, matters for group mutation.
10. **`config.py` User-Agent has an EXTRA SPACE (client bug — being fixed separately).**
   OUR `config.py` inserts a space before `SRT-APP-Android` so the wire UA ends
   `…Mobile Safari/537.36 SRT-APP-Android V.2.0.41`. Neither the real app (which
   concatenates the suffix with **no** separator, `SRWebActivity.java:2645`) nor srtgo
   (`srt.py:22`) emits that space (`docs/analysis/cross-validation-2026-07-21.md` §6;
   `config.py:7-8`, sent verbatim via `http.py`). A fidelity bug that could be
   fingerprinted. *(Source fix tracked separately — not changed by this doc edit.)*
11. **`safety.py` carries a stale `netfunnel-act-19` reference (client bug — being fixed
   separately).** `EXCLUDED_API_DOMAINS` still lists `netfunnel-act-19`
   (`safety.py:183`) for a gate that **does not exist** — `act_19` is 0-hit across the
   whole decompile and reserve reuses `act_10` (§5.4 above;
   `docs/analysis/cross-validation-2026-07-21.md` §2/§6). Retire the label.
   *(Source fix tracked separately — not changed by this doc edit.)*

---

## 6. Testing Strategy

### 6.1 Offline fixtures (add under `tests/fixtures/`)

Existing relevant fixtures: `reservation_attempt_success.json`,
`reservation_attempt_passenger_failure.json`, `seat_page_schema_v2_evidence.json`,
search/selector HTML. Add (all synthetic or sanitized, **zero PII/card/PNR**):

- `reserve_individual_success.json` — 4-array envelope with a synthetic `pnrNo`.
- `reserve_group_success.json` — group variant (no `pnrNo`, has `tmpJobSqno1`).
- `reserve_s111_relogin.json` — `resultMap[0].strResult="FAIL", msgCd="S111"`
  → asserts `SrtSessionExpiredError` (fix from §5.7).
- `reserve_business_fail.json` — `WRP011002`/other FAIL → `SrtAppError`.
- `payment_entry_individual.html` / `payment_entry_group.html` — sanitized
  `ard02017`/`ard02018` HTML shells (structure only, no card/PG secrets) to lock
  "we return HTML, never auto-submit."
- `seat_inventory_arc02012.json` — the R1 seat data, **once captured and
  sanitized**, to design the deferred physical-seat schema. **⚠️ Rev 2: `arc02011`
  is a phantom; the real endpoint is `arc02012`, which returns HTML (no JSON
  inventory feed) — the only structured output is the `popCallback` tuple.**
- ~~`netfunnel_act19.js`~~ — **removed: `act_19` does not exist; reserve reuses the
  `act_10` key already implemented (§5.4, §Rev 2).**
- `roundtrip_search_leg1.json` / `_leg2.json` — return-leg search sequence.
- `ata01032_discount.html` — discount detail page (if a real PNR ever yields 200).

### 6.2 Live-smoke plan (staged, opt-in, cleanup-mandatory)

- **Stage A — read-only live (already exists).** `run_live_smoke`
  (`live.py:94-149`) with `SRT_MOBILE_API_LIVE=1` + `.env` credentials (the stored
  phone login). No state change. Extend to capture (not persist) the R1
  `arc02012` seat-page shape into a sanitized fixture under a bounded evidence
  script (mirror `scripts/capture_seat_layout_evidence.py`). **⚠️ Rev 2: `arc02011`
  and `act_19` were both phantoms — the seat endpoint is `arc02012` (HTML) and
  reserve reuses `act_10`, so neither needs a separate capture.**
- **Stage B — reserve live (state change).** Gated behind `MutationPolicy(allow_reserve=True)`
  + `SRT_ALLOW_TEST_RESERVATION=1` + typed `ReserveConsent`. Flow: login → search →
  build `#rsvForm` from live hydration + gds_rsv → `act_10` → `arc05013` → assert a
  `pnrNo` comes back → **immediately run cleanup**. Because cancel is not yet
  captured (§3.5), cleanup is a loud manual-cancel warning until Phase 4 lands the
  cancel endpoint; the test must fail loudly if a PNR is left dangling.
- **Stage C — payment live with FAKE card.** Gated behind
  `MutationPolicy(allow_payment_entry=True)` + `PaymentConsent(FakeCard(...))`.
  Realistically this can only POST `ard02017` and inspect the returned HTML; a
  fake (Luhn-invalid) PAN cannot be entered into the PG/secure-keypad, so the
  expected result is a rejected/again-rendered payment page and **no charge**. The
  test documents the WebView/PG boundary rather than completing payment. Any test
  reservation from Stage B/C must be cancelled/cleaned up.
- **Stage D — cancel/refund live.** Only after the request shapes are captured
  (Phase 4). Validates that Stage B/C reservations can be programmatically removed.

### 6.3 Regression guardrails

- A boundary test asserting the READ tier is still exactly 20 routes with no
  policy, and that every mutation route raises without an enabled tier.
- A test asserting `pay()` rejects any Luhn-valid PAN.
- A redaction test asserting reserve/pay bodies never appear in error text.

---

## 7. Release Readiness

- **Version.** `0.2.0` → **`0.3.0`** when the reserve tier lands (opt-in, still
  `Development Status :: 3 - Alpha`). Reserve is a major behavioral expansion but
  gated; a `1.0.0` should wait until the payment feasibility question (§8, P3) is
  resolved and documented. Bump `Development Status` to `4 - Beta` only when
  reserve+cancel are round-trip-tested live.
- **pyproject (`pyproject.toml`).** Change `description` off "read APIs"; drop or
  qualify the `"read-only"` keyword (`:8-11`). Consider an optional extra marker
  for mutation-enabled installs (packaging unchanged otherwise; keep `py.typed`).
- **CHANGELOG.** One entry per phase; **explicitly state**: mutation is opt-in and
  dry-run by default; payment is fake-card-only and cannot complete approval;
  cancel/refund shapes were captured live, not derived from the APK.
- **Docs.** `README.md` currently states read-only scope and the six-selector read
  surface (`README.md:34-71`). Rewrite `## Scope` / `## Safety`; add a
  `docs/MUTATIONS.md` with the §3 catalog, the §4 safety model, and a prominent
  "what is NOT replicable (WebView/PG/native)" box. Update
  `docs/IMPLEMENTATION_PROGRESS.md` counters (currently "20 routes / mutation
  excluded", `:101-103,326-335`).
- **SECURITY.md.** Currently says the package "intentionally excludes reservation,
  payment, cancellation, refund, seat holding or selection." Rewrite to: mutation
  is opt-in + dry-run default; payment is fake-card-only and never charges; card
  data is never persisted; test reservations are auto-cancelled; PG approval,
  `easypay`, secure keypad, and FIDO remain permanently out of scope.
- **Public API surface (`__init__.py`).** Add (gated) `reserve`, `select_seat`,
  `pay`, `cancel`/`refund`; new types `MutationPolicy`, `ReserveConsent`,
  `PaymentConsent`, `FakeCard`, `ReserveRequest`, `PaymentEntryPage`; keep the
  existing offline `parse_reservation_attempt_response` and wire it to the reserve
  route parser. Everything mutation is absent from the default surface until a
  policy is enabled.
- **Security review.** Run a dedicated review of `safety.py`/`redaction.py` before
  each of P2/P3/P4 ships.
- **LICENSE (added 2026-07-21).** Our library currently has **no `LICENSE` file** —
  **add one** before shipping mutation (and before referencing external code shapes).
  The `srtgo`/`srtgo_plus` reference is **MIT** (its bundled `SRT` dep is MIT,
  `korail2` is BSD-3 — all permissive, no copyleft). We may reference the **factual
  request shapes** (endpoint paths, field names, fixed values, request sequence) — those
  are facts about a third-party server's protocol, not copyrightable expression — but
  we must **NOT copy `srt.py` source verbatim** (class/method bodies, docstrings,
  constant tables). Re-implement every field list independently from the documented
  §3-§7 in `docs/analysis/ref-srtgo_plus.md`. srtgo's README also states a
  non-commercial-use *request* (separate from the MIT grant); worth respecting in
  spirit though it does not bind our independent re-implementation.

---

## 8. Phased Roadmap

Risk legend: **Low** / **Med** / **High**. "🔒 capture-blocked" = cannot start
until a live request/response shape is recorded and sanitized.

### P0 — Safety-model foundation (no new routes) — risk: **Med**

- [ ] Add `RouteClass` + `MutationPolicy`; refactor `assert_read_only_request` into
      `assert_request(request, config, policy)` with `READ_ONLY_POLICY` default
      (`safety.py`). Keep the 20-route READ tier byte-identical.
- [ ] Add typed consent objects (`ReserveConsent`/`PaymentConsent`/`FakeCard`) and
      a dry-run scaffold that returns prepared requests without sending.
- [ ] Extend `redaction.py SENSITIVE_KEYS` with card/easypay/auth keys; add tests.
- [ ] Regression: READ tier still 20 routes with no policy; all 0.2.0 tests green.
- *Not blocked.* Ships without changing any live behavior.

### P1 — Read-only completion + seat schema — risk: **Low–Med**

- [ ] Round-trip (왕복) search state machine (R4): `rtnDv=1`, leg swap, `back_*`
      fields (`ara1001l.js:113-118`).
- [ ] Return-date picker `reqCode=4` path (R6, §5.1); reconcile ARA0403P/ARA0401P
      + `selectTime` divergence.
- [ ] Generalize seat-page read: allow `psrmClCd=2` (특실), `choiceSeatCount>1`,
      `reqCode` 10/11 (§5.5) — relax the field-lock accordingly.
- [ ] `atc14016` ticket-list variant (R3).
- [ ] 🔒 **Capture + type the `arc02012` seat page (R1/R5)** → design the deferred
      physical-seat schema. **Blocked on live capture.** **⚠️ Rev 2: `arc02011` is a
      phantom; the real endpoint is `arc02012`, which returns HTML (no JSON inventory
      feed) — reframe the deferred schema around the `popCallback` tuple.**

### P2 — Reservation (`arc05013`) POST layer — risk: **Med** *(was High; unblocked 2026-07-21)*

- [ ] Build the reserve body from a `ReserveRequest`/search-result model — **the full
      ~30-field `arc05013` body is now known statically** (`srt.py:962-997`;
      §3.4/§4.2 of the ref). `jobId=1101` personal / `1102` standby; seat fields
      omitted (server auto-assigns). Independently re-implement the field list; do
      not copy `srt.py`.
- [ ] Wire `parse_reservation_attempt_response` to the real route; read `pnrNo` from
      `reservListMap[0]`. Map `S111` → `SrtSessionExpiredError` **and** support the
      message-substring session-expiry path srtgo uses (§5.7).
- [ ] Reuse the existing **`act_10`** NetFunnel key for reserve (no `act_19`) — §5.4.
- [ ] RESERVE tier + dry-run default + `ReserveConsent`.
- [ ] ~~🔒 Blocked on capturing `#rsvForm` hidden fields + `act_19`.~~ **UNBLOCKED
      (2026-07-21):** both were resolved statically from srtgo (§3.4). Only remaining
      live steps: a Stage-B live smoke with mandatory cleanup, and — if group support
      is wanted — 🔒 **capturing `arc06014` (group ≥10 pax), which srtgo does NOT
      implement.** Individual reserve needs no further capture.

### P3 — Payment path — risk: **High** *(reframed 2026-07-21; re-corrected — payment UNCONFIRMED for OUR v2.0.41)*

> **UPDATE (2026-07-21, srtgo ref).** The old "feasibility spike / probably
> infeasible" framing is **wrong** for the mobile-JSON surface. Payment is a plain
> JSON POST to **`/ata/selectListAta09036_n.do`** with card fields and **no
> PG/keypad/FIDO** (`srt.py:1149-1225`, §6 of ref). The risk here is therefore **not
> feasibility** but **safety**: a working charge path makes the fake-card-only /
> dry-run guardrails load-bearing (§4).
>
> **⚠️ UPDATE 2 (2026-07-21, cross-validation).** `ata09036` is **0-hit in OUR
> v2.0.41 bundle** — it is srtgo-attested only, possibly a different/newer app. For
> OUR version payment is **NOT statically confirmed**: the real in-app path is the
> `ard02017/18` WebView page (TransKey keypad + FIDO + AppGuard). So P3 is **back to
> capture-blocked** — treat the `ata09036` shape as a hypothesis to verify with a
> live v2.0.41 capture before implementing, not a resolved route.

- [ ] Implement the `ata09036` JSON payment POST → parse `dsOutput0[0].strResult`
      (never auto-submit; default dry-run). Body fields per §3.3 new row /
      `srt.py:1184-1216`. Independently re-implement; do not copy `srt.py`.
- [ ] Fake-card-only `pay()`; assert it can **never** send a Luhn-valid PAN — this is
      the sole barrier between a test and a real charge.
- [ ] Keep the `ard02017/18` WebView HTML page **out of scope** (parallel flow the
      native app does not use to pay); do not fake a completion through it.
- [ ] ~~🔒 Blocked on capturing the `ard` page grammar.~~ **UNBLOCKED:** the JSON
      payment field list is known (§3.3). Remaining live step: Stage-C smoke with a
      **fake (Luhn-invalid) card → expected FAIL, no charge**; never feed a real PAN.

### P4 — Refund / cancel / change — risk: **High** *(re-corrected 2026-07-21: cancel/refund UNCONFIRMED for OUR v2.0.41)*

> **⚠️ UPDATE 2 (2026-07-21, cross-validation).** Cancel `ard02045`, refund
> `getListAtc14087`→`atc02063`, plus `ata01135`/`ard02019` are **0-hit across all
> 21,673 files** in OUR v2.0.41 bundle — srtgo-attested only. So P4 is **back to
> capture-blocked for our version**: srtgo's shapes are a starting hypothesis, and a
> live v2.0.41 capture is still required before implementing cancel/refund (change
> was always capture-blocked).

- [ ] ~~🔒 First capture the cancel/refund/change shapes — ZERO static evidence.~~
      **UPDATE (2026-07-21): cancel & refund shapes are known** from srtgo's
      mobile-JSON path (§3.3 new rows):
      - **cancel** POST `/ard/selectListArd02045_n.do`, body `pnrNo, jrnyCnt=1,
        rsvChgTno=0` (`srt.py:1114-1147`);
      - **refund** 2-step `/atc/getListAtc14087.do` → `/atc/selectListAtc02063_n.do`
        (`srt.py:1227-1257`).
      Independently re-implement; do not copy `srt.py`.
- [ ] Implement CANCEL tier + auto-cancel test harness (`reserve_for_test`) — now
      backed by a **real** cancel endpoint, so Stage-B cleanup no longer needs a
      manual-cancel warning.
- [ ] 🔒 **Change (변경) is still capture-blocked** — srtgo has no seat/train change
      endpoint; its shape must still be recorded live before implementation.
- [ ] Stage-D live validation: Stage-B reservations can be removed programmatically
      (cancel if unpaid, refund if paid — srtgo routes unpaid→cancel, paid→refund).

### P5 — Release prep — risk: **Low**

- [ ] Version bump (0.3.0 for reserve; hold 1.0.0 on payment outcome).
- [ ] CHANGELOG, README `## Scope`/`## Safety` rewrite, `docs/MUTATIONS.md`,
      SECURITY.md rewrite, pyproject `description`/keyword fix.
- [ ] Finalize public API surface (`__init__.py`) with gated mutation exports.
- [ ] Dedicated security review of `safety.py`/`redaction.py`; packaging + isolated
      wheel-import gate (mirror the existing `scripts/verify_distribution.py`).

### Phase dependency summary

Original (WebView-surface) blocker map, with items resolved by the 2026-07-21 srtgo
reference struck through:

```
P0 ──► P1 ──► P2 ──► P3 ──► P4 ──► P5
        │      │      │      │
        │      │      │      └─ cancel/refund shapes  ✅ RESOLVED (mobile-JSON); 🔒 change still blocked
        │      │      └──────── payment  ✅ RESOLVED via ata09036 JSON (no PG/keypad/FIDO)
        │      └─────────────── #rsvForm fields ✅ + NetFunnel act_19 ✅ (reuse act_10) — RESOLVED
        └────────────────────── 🔒 arc02011 seat-inventory JSON (deferred seat schema) — STILL blocked
```

**Capture-blocked phases (corrected 2026-07-21):** only a few genuine live items
remain — 🔒 **`arc02011` seat-inventory schema** (P1/R1/R5), 🔒 **`arc06014` group
reserve** (P2), and 🔒 **change/변경** (P4). Individual reserve, payment, cancel, and
refund are now **derivable statically** from srtgo (`docs/analysis/ref-srtgo_plus.md`)
and need only a confirmatory live smoke, not a shape-capture, before implementation.
P0 and P5 are not blocked.

> **⚠️ UPDATE 2 (2026-07-21, cross-validation) — this summary is corrected.** Only
> **individual reserve `arc05013`** (`jobId 1101/1102`, `act_10` gate) is
> statically confirmed in OUR v2.0.41 bundle. **Payment (`ata09036`), cancel
> (`ard02045`), and refund (`atc14087`→`atc02063`) are 0-hit** in our bundle
> (srtgo-attested only) and are therefore **still capture-blocked** for our version,
> NOT "derivable statically." The `arc02011` seat schema is a **phantom** — the real
> endpoint is `arc02012` (HTML). Corrected capture-blocked list: 🔒 **payment /
> cancel / refund** (P3/P4, live v2.0.41 capture), 🔒 **`arc02012` HTML seat page**
> (P1/R1/R5), 🔒 **`arc06014` group reserve** (P2), 🔒 **change/변경** (P4). See
> `## Revision 2 (2026-07-21)`.

---

## Revision 2026-07-21 — srtgo/srtgo_plus reference findings

> **⚠️ SUPERSEDED IN PART by `## Revision 2 (2026-07-21)` below.** The
> payment/cancel/refund optimism in this section (endpoints `Ata09036`, `Ard02045`,
> `getListAtc14087`→`Atc02063`) is **walked back**: cross-validation found all of
> them **0-hit in OUR v2.0.41 bundle**, so they are srtgo-attested only and revert to
> needs-live-capture. The reserve (`arc05013`) + `act_10` findings here **stand**.

Static analysis of the external tool **`srtgo`/`srtgo_plus`** (`srtgo/srt.py`;
full write-up in **`docs/analysis/ref-srtgo_plus.md`**) reversed several verdicts in
this plan. srtgo drives SRT's **native mobile JSON API** on `app.srail.or.kr` — a
*different server surface* from the WebView `#rsvForm`→`ard02017/18` HTML flow our
APK analysis documented — and completes the **entire** lifecycle over pure HTTP.

**Key reversal — payment.** The plan assumed SRT payment was WebView/PG/secure-
keypad/FIDO-bound and infeasible in pure Python. **False for the mobile-JSON path.**
srtgo pays by a plain form-POST to **`/ata/selectListAta09036_n.do`** with card
fields (`stlCrCrdNo1`, `crdVlidTrm1`, `vanPwd1`, `athnVal1`, `athnDvCd1`,
`ismtMnthNum1`, `stlMnsCd1=02`, `crdInpWayCd1=@`, …) and **no PG/keypad/FIDO**
(`srt.py:1149-1225`). It performs a **real card charge**.

**Endpoints unblocked (statically derivable; no live shape-capture needed):**

- **Reserve** `/arc/selectListArc05013_n.do` — `jobId 1101` personal / `1102`
  standby; full ~30-field body at `srt.py:962-997`. The `#rsvForm` hidden-field
  concern is **resolved** (all fields derive from the search result; no server
  scrape).
- **Reserve gate** reuses **NetFunnel `act_10`** (same key as search), **not**
  `act_19` — no new gate to build (`srt.py:987`).
- **Payment** `/ata/selectListAta09036_n.do` — pure HTTP card charge (above).
- **Cancel** (unpaid) `/ard/selectListArd02045_n.do` — body `pnrNo, jrnyCnt=1,
  rsvChgTno=0` (`srt.py:1114-1147`).
- **Refund** (paid) 2-step `/atc/getListAtc14087.do` →
  `/atc/selectListAtc02063_n.do` (`srt.py:1227-1257`).

**Other corrections:**

- **Login needs no encryption** — password is sent **plaintext** despite the
  `hmpgPwdCphd` field name; `deviceKey="-"` (`srt.py:700-731`).
- **Anti-bot** — the JSON API is JA3-fingerprinted; srtgo uses
  `curl_cffi`/`impersonate="chrome"` (`srt.py:652-655`). Our client will likely need
  browser/TLS impersonation. No request signing/nonce/body-encryption anywhere.
- **Safety model reinforced** — because `ata09036` really charges and `arc05013`
  really books, fake-card-only + dry-run + never-persist + auto-cancel are now
  **mandatory, not optional** (§4). `payment` moves from "permanently
  non-implementable" to an opt-in mutation tier.

**Remaining genuine gaps (srtgo does NOT cover these either):**

- **Designated physical-seat selection & change** — srtgo lets the server
  auto-assign (never posts `seatNo1_*`/`scarNo1`).
- **`arc02011` physical-seat inventory schema** (R1/R5) — still deferred.
- **Group reservation `arc06014`** (≥10 pax) — srtgo implements personal
  `arc05013` only.
- **Change (변경)** — no srtgo endpoint; still capture-blocked.

**License / reuse.** srtgo is **MIT** (deps: `SRT` MIT, `korail2` BSD-3 — all
permissive, no copyleft). We reference **factual request shapes only** and must
**re-implement independently** (no verbatim `srt.py`). Our library has **no LICENSE
file** — recommend adding one (see §7).

*Sections corrected inline (search "UPDATE (2026-07-21)"):* feasibility headline,
§3 intro, §3.1, §3.3 (table + 4 new rows), §3.4, §3.5, §4 (+item 8), §5.4, §5.7,
§7 (LICENSE), §8 (P2/P3/P4 + dependency map).

---

## Revision 2 (2026-07-21) — cross-validation vs decompiled v2.0.41

Cross-validating **srtgo against OUR own decompiled v2.0.41 bundle** — the ground
truth — corrects the srtgo-optimistic verdicts in `## Revision 2026-07-21` above.
Full report: **`docs/analysis/cross-validation-2026-07-21.md`**. srtgo was checked
endpoint-by-endpoint against `analysis/apktool` (smali + assets), `analysis/jadx`
(Java), and OUR `src/`. Inline `UPDATE 2 (2026-07-21)` notes carry the same
corrections at each point they change a verdict.

### 1. PAYMENT / CANCEL / REFUND — walk-back (most important)

The earlier Revision claimed SRT payment/cancel/refund are feasible via a pure-JSON
mobile API (`Ata09036` / `Ard02045` / `Atc02063`). **That is UNCONFIRMED for OUR
version.** These endpoints — plus standby-option `Ata01135`, reserve-info
`getListAtc14087`, and ticket-info `Ard02019` — are **0-hit across all 21,673 files**
in our v2.0.41 bundle (`cross-validation-2026-07-21.md` §3–§4; classes.dex, smali,
jadx, and bundled JS all return zero). They are attested **only by srtgo's live
runs**, possibly against a different/newer app version.

OUR app's actual payment path is the **`ard02017` / `ard02018` WebView page** gated by
**TransKey (SEED secure keypad)** + **RaonSecure FIDO** + **AppGuard/appiron**
(`cross-validation-2026-07-21.md` §3; `ara1001l.js:1599,1608`;
`SRWebActivity.java:2352-2390,2517-2519`). The only `Ata####` payment endpoint
actually present in the bundle is **`Ata01032`** (discount / payable-card-company
page), **not `Ata09036`** (`arc0102c.js:34`).

**Verdict for OUR v2.0.41:** payment / cancel / refund are **NOT statically
confirmable** and revert to "**needs a live v2.0.41 capture**" — srtgo's request
shapes are a **starting hypothesis, not confirmed fact**. §3.3/§3.5 rows, §4 (item 8
+ mandate note), and the P3/P4 roadmap are corrected inline accordingly.

**Still confirmed feasible:** **RESERVATION `Arc05013`** (`jobId 1101` personal /
`1102` standby) and its **NetFunnel `act_10`** gate ARE present in our app
(`cross-validation-2026-07-21.md` §1–§2; `ara1001l.js:1547`; `netfunnel.js:16-17`).
Individual reserve stays feasible; only payment/cancel/refund walk back.

### 2. OUR-own phantoms corrected

- **`act_19` does not exist** — only `act_10` is in the bundle (3× `act_10`, 0×
  `act_19` across apktool assets); reserve reuses the same `act_10` key
  (`cross-validation-2026-07-21.md` §2, §6). Already corrected in this plan's body
  (§3.4, §3.5, §5.4, P2); residual test/roadmap references (§6.1, §6.2, dependency
  map) now fixed too.
- **Seat-inventory endpoint is `arc02012`, not `arc02011`.** `arc02011` is a phantom
  (0 hits; the only `02011` match is an incidental AES T-table substring). The real
  endpoint `/arc/selectListArc02012_n.do` returns an **HTML seat page, NOT a JSON
  inventory feed**; the only machine-readable output is the `popCallback`
  `{scarSeatNo:'2,7,10', scarSeatNm:'1B,2C,3B', scarNo:1}` tuple
  (`cross-validation-2026-07-21.md` §5; `ara0101v.js:868`). R1/R5's deferred
  "seat-inventory JSON schema" is mis-modelled and must be reframed.

### 3. Newly-found hidden surface (extends §2/§3/§5)

- **Alternate host `app.srail.co.kr/neo`** serves the same `_n.do` JSON (dev variant
  `devapp.srail.co.kr/neo`), which srtgo never models
  (`cross-validation-2026-07-21.md` §1; `SRForegroundDialogActivity.java:31`).
- **Full group / seat-map branch** (srtgo is individual-only): group search
  **`Ara10082`** (`ara1001l.js:177`), group reserve **`Arc06014`** (`:1544`, by
  `grpDv=='1'`, ≥10 pax, round-trip forbidden), group payment-entry **`Ard02018`**
  (`:1599`, `pnrNo=-1`, `tmpJobSqno1/2`), seat-map **`Arc02012`** (`reqCode` 9/10/11),
  **`jobId '1103'`** 시트맵예약 (`:1436`), and Korail-interop verification
  **`Ara10130`** returning `mutMrkVrfCd` (`:229`)
  (`cross-validation-2026-07-21.md` §2, §5).
- **Complete bundled inventory = EXACTLY 14 `_n.do` endpoints:** `apb01080`,
  `ara10007`, `ara10082`, `ara10130`, `ara12009`, `ara13010`, `arc02012`, `arc05013`,
  `arc06014`, `ard02017`, `ard02018`, `ata01032`, `atc14016`, `atc14017`
  (`cross-validation-2026-07-21.md` §5). `Ard02019`, `Ard02045`, `Ata09036`,
  `Ata01135`, `Atc02063`, `getListAtc14087` are all ABSENT (runtime-only).
- **Uncaptured native secrets** (not in §7): hardcoded Google/Firebase API keys
  (Firebase project `<SRT-APP-FIREBASE-PROJECT-REDACTED>`), Kakao and Facebook app keys, and an
  `android_id`/MAC/IP device fingerprint feeding `push.srail.co.kr:3101`
  (`cross-validation-2026-07-21.md` §5; `strings.xml`; `SRWebActivity.java:1841-1851`).
  *(Key values intentionally NOT reproduced in this plan.)*

### 4. OUR-own client fidelity bugs (being fixed separately — see §5 items 10–11)

- **`config.py` User-Agent has an EXTRA SPACE** before `SRT-APP-Android` that neither
  the real app (no separator, `SRWebActivity.java:2645`) nor srtgo (`srt.py:22`)
  emits (`cross-validation-2026-07-21.md` §6; `config.py:7-8`).
- **`safety.py` carries a stale `netfunnel-act-19`** exclusion label
  (`EXCLUDED_API_DOMAINS`, `safety.py:183`) for a gate that does not exist; retire it.
- *(Both source fixes are tracked separately — this doc edit does not touch code.)*

### 5. Net effect on the plan

srtgo remains a **correct model of the individual reserve flow** for v2.0.41 (login,
search, reserve, tickets, `act_10` all match). But payment/cancel/refund are the
**largest remaining verification gap** for our version — treat srtgo's shapes as
hypotheses to confirm with a live v2.0.41 capture, not as resolved. The corrected
capture-blocked list is: 🔒 **payment** (WebView `ard02017/18`, or an unconfirmed
`ata09036`), 🔒 **cancel**, 🔒 **refund**, 🔒 **change (변경)**, 🔒 **group reserve
`arc06014`**, and 🔒 **designated-seat / the `arc02012` HTML seat page**. Confirmed and
implementable now: **individual reserve `arc05013`** with the existing `act_10` gate.

---

## Appendix — Key file:line index

| Fact | Client side | JS / decompiled side |
|---|---|---|
| Read allowlist (20 routes) | `safety.py:56-79` | — |
| Read-only gate | `http.py:106`; `safety.py:118-177` | — |
| Seat-page field lock | `safety.py:94-115`; `payloads.py:265-297` | `ara1001l.js:1498-1520` |
| Reserve response parser (offline only) | `parsers.py:507-625`; `models.py:139-177` | `ara1001l.js:1557-1626` |
| Reserve create routes | *(absent)* | `ara1001l.js:1544,1547`; **mobile-JSON: `arc05013` `srt.py:94`, body `:962-997`** |
| Payment entry (WebView HTML) | *(absent)* | `ara1001l.js:1599,1608` |
| **Payment (mobile-JSON card charge)** *(2026-07-21)* | *(absent)* | **`ata09036` `srt.py:99`, body `:1184-1216`** |
| Seat inventory JSON (deferred schema) | *(absent)* | `seat_page_schema_v2_evidence.json:200-222` |
| NetFunnel act_10 | `netfunnel.py:18`; `client.py:218-224` | `netfunnel.js:17` |
| NetFunnel act_19 / BEGIN disabled | *(absent)* | `ara0101v.js:651-655`; `ara1001l.js:1734-1740` — **NB: no act_19 gate; reserve reuses `act_10` `srt.py:987,603`** |
| Date picker divergence | `client.py:159-165`; `payloads.py:54-69` | `ara0101v.js:187-203` |
| Station-map picker (no static evidence) | `client.py:151-157`; `payloads.py:44-51` | *(call site absent, `ara0101v.js`)* |
| Seat pick / popCallback | *(WebView)* | `ara0101v.js:866-894`; `const.js:9-11` |
| EasyPay / secure keypad / FIDO | *(native, out of scope)* | `SRWebActivity.java:1658-1685,2352-2390,2517-2519` |
| Cancel / refund / change | *(absent)* | WebView: *(no static evidence)*; **mobile-JSON (2026-07-21): cancel `ard02045` `srt.py:1114-1147`, refund `atc14087`→`atc02063` `srt.py:1227-1257`; change still absent**|
| Login (no encryption) | `config.py` | **plaintext pw `hmpgPwdCphd`, `deviceKey="-"` `srt.py:700-731`** |
| Anti-bot TLS/JA3 impersonation | *(absent — likely `curl_cffi`)* | **`srt.py:652-655` `impersonate="chrome"`** |
