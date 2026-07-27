# SRT App — Definitive Full API Analysis

**App:** SRT (에스알 / 수서고속철도)
**Package:** `kr.co.srail.newapp`
**Version:** `2.0.41` (`versionCode=150`)
**Date:** 2026-07-20 KST
**Author:** FABLE
**Source of truth:** verified static reverse-engineering of the decompiled APK (`analysis/apktool/`, `analysis/jadx/`), cross-checked against the implemented read-only client in `src` and the prior runtime spec `docs/analysis/srt-app-api-library-spec-2026-07-09.md`.

## Overview

The SRT Android app is **not a native-API app**. It is a thin WebView shell
(`kr.co.srail.newapp.webview.SRWebActivity`) wrapping a server-rendered
jQuery-Mobile web application. All train-booking business logic lives in
bundled offline JavaScript under `assets/offline/js/`, and every business
endpoint is a URL string constructed in that JS as `contextPath + "/<domain>/…"`.
There are **zero Retrofit/OkHttp service interfaces** for the booking domain in
the decompiled Java.

Two surfaces therefore coexist:

1. **HTTP(S) `.do` endpoints** on `app.srail.or.kr` (PRD) — form-encoded POST /
   GET calls issued by jQuery `$.ajax` and jQuery-Mobile page transitions. No
   request signing, no payload encryption; TLS transport only; session carried
   by WebView cookies.
2. **A synchronous native JS bridge** named `srbridge`, an Android
   `@JavascriptInterface` exposing device/native capabilities (camera, QR,
   secure keypad, FIDO, push registration, storage, external-app handoff) to the
   web page. This is an in-process bridge, **not an HTTP API**.

This document catalogs both surfaces from verified findings only. Low-confidence
or unverifiable items are isolated in
[§9.1 Unverified / low-confidence](#91--unverified--low-confidence).

> **Naming caveat used throughout:** the JS variable `contextPath` is injected
> server-side by the hosting JSP and is **not defined anywhere in the bundled
> APK assets** (`grep` for `var contextPath` returns nothing). Absolute paths
> below are therefore written as `{contextPath}/…`; the host is resolved
> natively (see §1).

---

## 1. Network transport & hosts

### 1.1 Base URL resolution

The WebView base URL is resolved natively in `SRWebActivity.X0()`:

| Environment | Base URL | Selector |
|---|---|---|
| PRD (production) | `https://app.srail.or.kr` | `GlobalApplication.f8033g.equals("PRD")` |
| non-PRD (dev) | `https://devapp.srail.or.kr` | else branch |

Source: `analysis/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java:1577-1581`.
Environment (`PRD`/`DEV`) is read from the manifest `meta-data` key `ENV`
(`GlobalApplication.java:144`); the shipped manifest sets `ENV=PRD`.

**Initial load URL** is built in `X0()` as
`<base> + "/main/main.do?deviceId=<android_id>"`
(`SRWebActivity.java:1584-1592`); note it carries a `?deviceId=` query.
An alternate initial route `/atc/selectListAtc14017_n.do` is used when
`btnNo == "2"` (`SRWebActivity.java:1592`).

### 1.2 Legacy `/neo` host family

A legacy host with a `/neo` context path appears in decompiled Java (not only in
leftover debug assets):

| URL | Source |
|---|---|
| `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0` | `main/SRForegroundDialogActivity.java:31` |
| `https://app.srail.co.kr/neo/main/main.do` | `assets/dev.html:21` (debug asset only) |
| `https://devapp.srail.co.kr/neo/common/rest/JongURi/view.do` | `SRWebActivity.java:2055, :2068` |

These use the `srail.co.kr` host (not the booking host `srail.or.kr`) and are
unrelated to the reservation flow.

### 1.3 Transport & headers

| Item | Value | Source |
|---|---|---|
| Transport | HTTPS (TLS) only. No cert pinning found in the app package. | — |
| Cleartext | `android:usesCleartextTraffic="true"` — cleartext permitted app-wide | `AndroidManifest.xml:53` |
| Network security config | **None** — no `res/xml/network_security_config.xml` in the APK | — |
| Body format | `application/x-www-form-urlencoded`, produced by jQuery `$(form).serialize()` or inline object literals | `ara1001l.js:183, :1550` |
| Response types | Mixed JSON, `text/html` pages, and NetFUNNEL JS snippets | — |
| Session | WebView cookie jar; `CookieManager.setAcceptCookie(true)` + third-party cookies accepted | `SRWebActivity.java:1949-1952, :2665-2667`; flushed `:879` |
| User-Agent | Default WebView UA + suffix `SRT-APP-Android V.<versionName>` | `SRWebActivity.java:2642-2645` |
| Custom headers | **None added natively** — no `addRequestHeader`/`setRequestProperty` anywhere in `kr/co/srail/newapp` | — |

An unrelated **cleartext** integrity/anti-tamper endpoint is referenced in
resources: `http://iron.srail.co.kr/authCheck.call`
(`res/values/strings.xml:73`) — see §7.

### 1.4 Push / non-HTTP host

| Host:Port | Protocol | Source |
|---|---|---|
| `push.srail.co.kr:3101` | H2O SmartBroker proprietary TCP (`com.H2OSystech.SmartBrokerAPIs.ERBAPIs`), **not HTTP** | `res/values/strings.xml:178-179` (`h2o_ip`/`h2o_port`); `b6/a.java:53-93` |

### 1.5 FIDO host

| Host | Purpose | Source |
|---|---|---|
| `https://fido.srail.co.kr` | RaonSecure OnePass/FIDO UAF server | `SRWebActivity.java:2519` |

FIDO identity constants (verified literals): `siteId = SIT02SR0000000000000`,
`svcId = SVC01SIT02SR00000000` (`SRWebActivity.java:2517-2519`).

---

## 2. Auth & crypto

### 2.1 Authentication model

- **Session is WebView-cookie based**, not header-token based. There is no
  `Authorization` or `X-*` auth header anywhere in the app package. The only
  app-added request header is the User-Agent suffix (§1.3).
- **Search endpoints are callable without login.** No client-side auth gate
  precedes `selectListAra10007_n`/`Ara10082_n`
  (`ara1001l.js:180-222`).
- **Login is enforced downstream:**
  - Seat-map selection is gated client-side: aborts with
    "좌석선택은 로그인 후 이용 가능합니다" when
    `application.gds_userInfo.MB_CRD_NO == ""`, then calls `memberShipLogin()`
    (`ara1001l.js:1288-1306`). Non-member sessions (`USER_DV == "2"`) are
    force-cleared first (`ara1001l.js:1285-1287`).
  - The reserve call returns `resultMap[0].msgCd == "S111"` to signal
    "login required", after which the client redirects to `memberShipLogin()`
    (`ara1001l.js:1562-1573`).

### 2.2 Crypto / signing

- **No request signing, HMAC, nonce, timestamp, or payload encryption** exists
  on any booking endpoint. Transport is plain HTTPS.
- **`showTransKey`** (secure keypad) is the only cryptographic client feature:
  input is captured by a hardware-backed secure keypad (TouchEn/mTransKey) under
  **SEED** cipher and decrypted natively in `onActivityResult` via
  `com.softsecurity.transkey.h("SEED")`, returned to JS as `plainData`
  (`SRWebActivity.java:2352-2390`). Default secure-key bytes spell
  `MobileTransKey..` (`SRWebActivity.java:2170`).
- **FIDO/UAF** (RaonSecure OnePass) handles biometric auth for
  `allowedAuthnr` / `requestServiceRegist|Release|Auth` (§3.5).
- **mutMrkVrfCd** (상호검증값) from `selectListAra10130_n` is itself an
  anti-abuse handoff token for the KorailTalk cross-app flow — it is a value,
  not a transport-layer signature, and is **not attached** to search requests
  (`ara1001l.js:226-251`).

### 2.3 Login endpoint (cross-referenced — runtime-verified in prior spec)

The login/session endpoints below are **not part of this static analysis'
verified set**; they are documented with runtime evidence in
`srt-app-api-library-spec-2026-07-09.md` and implemented in `session.py`.
Included here for completeness and clearly attributed.

| Name | Method | Path | Key params | Response | Auth | Source |
|---|---|---|---|---|---|---|
| Login page | GET | `/login/login.do` | none | HTML login page | none | spec §6; `session.py:17` |
| Login submit | POST | `/apb/selectListApb01080_n.do` | `srchDvCd`, `srchDvNm`, `hmpgPwdCphd`, `deviceKey`, … | JSON `userMap.RTNCD=Y` | establishes session | spec §6; `session.py:19-35` |

---

## 3. Endpoint catalog grouped by service domain

Legend for **Auth** column: *none* = no client gate; *login* = login enforced
(client gate and/or `S111` server code); *implied* = requires an
owning-session but not gated in client code.

### 3.1 Session, Main & Ticket (cross-referenced from prior spec, runtime-verified there)

These are read routes verified at runtime in the prior spec and implemented in
`src`. They are not re-derived by this static analysis; the native app only
references `ara/ara0101v.do` as a back-button special case
(`SRWebActivity.java:2414`).

| Name | Method | Path | Key params | Response | Auth | Source |
|---|---|---|---|---|---|---|
| Main page | GET | `/main/main.do` | `deviceId=<android_id>` | HTML app main | login | `SRWebActivity.java:1584-1592`; `client.py:92` |
| Notice list | POST | `/main/noticeList.do` | `pageId=MB0101000000` | JSON `noticeList[]` | login | spec §6; `client.py:100-108` |
| Booking start page | GET | `/ara/ara0101v.do` | none | HTML booking form (hosts hidden forms) | login | `SRWebActivity.java:2414`; `client.py:97` |
| Ticket / reservation list | GET | `/atc/selectListAtc14017_n.do` | `pageNo` | HTML ticket list | login (implied) | spec §6; `client.py:120` |

### 3.2 Train search & availability (`ara`) — VERIFIED

Request body for both search endpoints is `$("#seatSearchForm").serialize()`
(urlencoded), populated indirectly by `lfn_setRsv(obj)` writing each key into a
hidden input by id (`main.html:549-554`), so **wire param names equal
hidden-input ids**. The form markup itself is server-rendered and absent from
the APK.

| Name | Method | Path | Key params | Response | Auth | Source |
|---|---|---|---|---|---|---|
| Train search (individual) | POST | `{contextPath}/ara/selectListAra10007_n.do` | `chtnDvCd`, `dptDt`, `dptTm`, `dptRsStnCd`, `arvRsStnCd`, `stlbTrnClsfCd`, `psgNum`, `seatAttCd`, `trnGpCd`, `trnNo`, `arriveTime="N"` | JSON `{ErrorCode,ErrorMsg,outDataSets:{dsOutput0[],dsOutput1[]}}` | none | `ara1001l.js:180, :182-208` |
| Train search (group 단체) | POST | `{contextPath}/ara/selectListAra10082_n.do` | identical form; selected when `grpDv=="1"`; requires ≥10 pax, forbids round-trip | same envelope | none | `ara1001l.js:177, :182-208`; `ara0101v.js:550-566` |
| Mutual-verification code | POST | `{contextPath}/ara/selectListAra10130_n.do` | **none** (no `data` key in `$.ajax`) | JSON `{outDataSets:{dsOutput0:{strResult,msgTxt,mutMrkVrfCd}}}` — `dsOutput0` read as **object**, not `[0]` | implied | `ara1001l.js:227-231, :233-242` |
| Timetable detail | POST | `{contextPath}/ara/selectListAra12009_n.do` | `runDt`, `trnNo`, `trnSort`, `stnCourseNm` | HTML page (jQuery-Mobile `pagecontainer("change")`) | none | `ara1001l.js:1180-1194` |
| Fare / pricing detail | POST | `{contextPath}/ara/selectListAra13010_n.do` | `chtnDvCd`, `dptRsStnCd1`, `arvRsStnCd1`, `runDt`, `trnNo`, `runDt1`, `trnNo1`, `trnSort`, `stnCourseNm`, `passenger1..5` (`dptRsStnCd2/arvRsStnCd2/runDt2/trnNo2` empty) | HTML page | none | `ara1001l.js:1205-1234` |
| Booking start (home) | GET (implied) | `{contextPath}/ara/ara0101v.do` | none (substring-matched natively for back button) | HTML search form page | none | `SRWebActivity.java:2414` |
| **[DEAD CODE]** legacy Nexacro gateway | (unknown) | `ara/selectListAra10h01.do` (relative — supplied as `sController`, never issued) | `svcid="search"`, `inds=["dsInput1=ds_hpg"]`, `outds=["ds_result=dsOutput0"]`; input dataset `ds_hpg{mutMrkVrfCd,pnrNo="",trgtCd="1",regUserId}` | never parsed | n/a | inside `/* */` comment `ara1001l.js:254-278` |

**Behavioral notes (verified):**

- **Individual vs group is a pure client-side branch** on hidden field `grpDv`
  (`ara1001l.js:176-181`, duplicated at `:1823-1829`).
- **Paging is time-cursor based, not offset based.** The next cursor is the last
  row's `dptTm` truncated to 5 chars + literal `"1"`
  (`sNextTm.substr(0,5)+"1"`, passed to `fn_search` at `ara1001l.js:1777`).
  End-of-page is signalled by `fllwPgExt == "N"` (read from the grid header
  dataset `ds_trInfo.getColumn(0,"fllwPgExt")` at `ara1001l.js:1768`) or an
  empty `dsOutput1[]`.
- **Round-trip is two sequential calls to the same endpoint.** `rtnDv=="1"`;
  the client tracks the leg via in-memory `fv_sRtnCd` (`"1"`=outbound,
  `"2"`=inbound), swaps `dptRsStnCd`/`arvRsStnCd` and substitutes
  `back_dptDt1`/`back_dptTm1` for the inbound leg (`ara1001l.js:113-118`). No
  server-side round-trip parameter exists on the search call.
- **Client-side time normalization:** if `dptDt` is today and `dptTm` is in the
  past, `dptTm` is silently rewritten to now (`ara1001l.js:145-148`). Station
  code is re-derived from the displayed station name right before the call
  (`ara1001l.js:133-139`).
- **NetFUNNEL is bundled but disabled in this build:** `netfunnel.js` (~87 KB)
  ships, but every `NetFUNNEL.SetService`/`BEGIN` call site in this domain is
  commented out and replaced by a direct `netfunnel_callback()`
  (`ara0101v.js:651-655`; `ara1001l.js:1734-1740`). (The prior spec's *runtime*
  evidence shows the **live server still requires** a fresh NetFUNNEL `act_10`
  key — `NET000001` on omission — a live-layer fact the bundled JS cannot show.)

### 3.3 Selector / popup pages (`common/ARA`) — VERIFIED

Each picker is a **server-rendered HTML page fetched by POST** via
`pagecontainer("change", url, {type:"POST", data:param})`; results return to the
opener through the global `popCallback(reqCode, obj)` dispatcher keyed by the
`POP_REQ_*` constants in `const.js:1-11`.

| Name | Method | Path | Key params | Callback fields | Auth | Source |
|---|---|---|---|---|---|---|
| Station picker (ARA0501P) | POST | `{contextPath}/common/ARA/ARA0501P/view.do` | `reqCode=1`, `sDptStnNm`, `sArvStnNm`, `sDptStnCd`, `sArvStnCd`, `sNowSel` | `{startStnNm,startStnCd,arrivalStnNm,arrivalStnCd}` | none | `ara0101v.js:158-168` |
| Date/time picker (ARA0401P) | POST | `{contextPath}/common/ARA/ARA0401P/view.do` | `reqCode=3` (가는) / `4` (오는), `selectDay`, `selectDt` | `{choiceDate}` (strips `-`) | none | `ara0101v.js:187-203` |
| Passenger picker (ARA0901P) | POST | `{contextPath}/common/ARA/ARA0901P/view.do` | `reqCode=6`, `isOrg`, `passenger1..5`, `totalPessnger` (typo preserved) | `{passenger1..5}` | none | `ara0101v.js:231-243, :479-490` |
| Seat-option picker (ARA0701P) | POST | `{contextPath}/common/ARA/ARA0701P/view.do` | `reqCode=5`, `rqSeatAttCd`, `locSeatAttCd`, `seatAttNm` | `{seatOption,seatPosition,seatOptionString}` | none | `ara0101v.js:253-263` |
| Train-type picker (ARA0201V) | POST | `{contextPath}/common/ARA/ARA0201V/view.do` | `reqCode=7`, `trnGpCd`, `trnGpCdNm` | `{trainOption,trainOptionNm}` | none | `ara0101v.js:273-280` |

> The call site for the **station-map picker (ARA0502P, `POP_REQ_STN_MAP=2`)**
> is *absent* from `ara0101v.js` in this build (verified). The implemented
> client nonetheless uses `/common/ARA/ARA0502P/view.do` (live-layer). Likewise
> the client uses `ARA0403P` for the date picker where the bundled JS uses
> `ARA0401P` — see §8.

### 3.4 Reservation, seat selection & payment handoff (`arc` / `ard` / `ata`) — VERIFIED (evidence only; not implementable)

All three ARC screen IDs (`ARC0201C`/`ARC0102C`/`ARC0103C`) are logical routing
IDs in a JS object `{app:"ARC", id, titletext, args}`
(`ara1001l.js:1289-1490`); only `ARC0201C` maps to a real URL.

| Name | Method | Path | Key params | Response | Auth | Source |
|---|---|---|---|---|---|---|
| Seat map / seat selection (ARC0201C) | POST | `{contextPath}/arc/selectListArc02012_n.do` | `reqCode` (9/10/11), `runDt`, `dptDt`, `trnNo`, `dptTm`, `trnGpCd="300"` (hard-coded, SRT-only), `dptRsStnCd`, `arvRsStnCd`, `psrmClCd`, `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, `choiceSeatCount` | HTML page; returns `{scarSeatNo,scarSeatNm,scarNo}` via `popCallback` | login | `ara1001l.js:1496-1520` |
| Create reservation (individual) | POST | `{contextPath}/arc/selectListArc05013_n.do` | `$("#rsvForm").serialize()`; 21 fields validated by `fn_validChk` (`jobId,jrnyTpCd,jrnyCnt,totPrnb,stndFlg,jrnySqno1,trnGpCd1,stlbTrnClsfCd1,dptDt1,dptTm1,dptRsStnCd1,arvRsStnCd1,psrmClCd1,smkSeatAttCd1,dirSeatAttCd1,locSeatAttCd1,psgInfoPerPrnb1,etcSeatAttCd1,rqSeatAttCd1,psgGridcnt,psgTpCd1`) | JSON `{resultMap[],reservListMap[],trainListMap[],commandMap[]}` | login (`S111` redirect) | `ara1001l.js:1547, :1549-1621` |
| Create reservation (group 단체) | POST | `{contextPath}/arc/selectListArc06014_n.do` | same `#rsvForm`; selected purely by `grpDv=="1"` | same envelope; group has no `pnrNo` | login (`S111`) | `ara1001l.js:1544, :1549-1621` |
| Payment / detail handoff (individual) | POST (form submit) | `{contextPath}/ard/selectListArd02017_n.do` | `#rsvForm` retargeted: `pnrNo`, `jrnySqno=1`, `JRNYLIST_KEY`, `arvDt/arvRsStnCd/arvTm`, `dlayAcptFlg`, `dptDt/dptRsStnCd/dptTm`, `jrnyTpCd`, `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`, `trnNo` + all remaining rsvForm fields | HTML page | login (implied) | `ara1001l.js:1608` |
| Payment / detail handoff (group) | POST (form submit) | `{contextPath}/ard/selectListArd02018_n.do` | `pnrNo=-1` (hard), `rcvdAmt`, `tmpJobSqno1`, `tmpJobSqno2=0`, `seatNo1`, `scarNo1` + shared journey fields | HTML page | login (implied) | `ara1001l.js:1599` |
| Discount detail (ARC0102C → 할인 상세) | GET | `{contextPath}/ata/selectListAta01032_n.do` | `pnrNo=${commandMap.pnrNo}` (unresolved JSP EL shipped in JS — proves server-rendering) | HTML page | implied | `arc/arc0102c.js:33-37` |

**Behavioral notes (verified):**

- The **reserve response envelope is a 4-array JSON**
  `{resultMap:[],reservListMap:[],trainListMap:[],commandMap:[]}`, each read as
  `[0]` (`ara1001l.js:1560, :1577-1579`) — structurally different from the
  search `{ErrorCode,ErrorMsg,outDataSets}` envelope in the same file.
- **`jobId` (조정구분코드)** carried in the reserve body: `1101`=개인예약,
  `1102`=예약대기 (waitlist, when the general-cabin image is the "waiting"
  sprite), `1103`=시트맵예약 (`ara1001l.js:1434-1450`).
- **Group reservations receive no `pnrNo`** — client hard-sets `pnrNo=-1` and
  forwards `tmpJobSqno1`/`totRcvdAmt`/`seatNo`/`scarNo` to `ard02018`
  (`ara1001l.js:1597-1605`).
- **`trnGpCd` is hard-coded `"300"`** for the seat-selection request with the
  explicit comment "좌석선택은 SRT만 가능하기때문에 무조건 300을 셋팅한다"
  (`ara1001l.js:1504`).
- **Seat selection is not a JSON API** — it loads a full HTML page via
  `pagecontainer("change", …, {type:"POST"})` and returns via `popCallback`
  (`ara1001l.js:1514-1520`; `ara0101v.js:866-893`).

> These reservation/payment endpoints are **evidence only**. They match the
> prior spec's runtime probes (arc05013 zero-passenger → `WRP011002`/`FAIL`;
> ard02017/ard02018 ~84 KB/83 KB dummy HTML). They are deliberately **not
> implemented** in `src` (§8).

### 3.5 Native JS bridge — `srbridge` (device/native capability API) — VERIFIED

**Not an HTTP API.** `srbridge` is an Android WebView
`@JavascriptInterface` registered at `SRWebActivity.java:2677` via
`W.addJavascriptInterface(new y(this, jVar), "srbridge")`. It exposes **exactly
two** `@JavascriptInterface` methods:

- `bridgeCall(String action, String jsonParam)` — a single string-keyed
  dispatcher (`SRWebActivity.java:1052-1190`) routing **30 distinct action
  strings** to 24 obfuscated private handlers (action names are *not*
  obfuscated; handler method names ARE R8-renamed).
- `exitApp()` (`SRWebActivity.java:1192-1196`) — calls `Activity.finish()`.

**Callback marshalling (three paths):**

1. **Standard** (`T()` → inner `c.run`, `SRWebActivity.java:514-529`):
   `runOnUiThread` → `WebView.evaluateJavascript("bridgeCallBack(<quoted-json>)")`
   with envelope `{action,resultCode,data[,image]}`. JS dispatcher at
   `bridge.js:150`. `resultCode==1` = success (FIDO uses `1200` ok / `9`
   immediate-error); other values dropped by JS.
2. **Named-string** (`I0()`/inner `d`, `:551-569`): calls
   `<callbackName>('{"resultCode":..,"data":..}')` where `callbackName` comes
   from the param JSON — used by `loadPrfs`.
3. **Named-int** (`J0()`/inner `e`, `:586-589`): calls
   `<callbackName>(<resultCode>)` (bare int) — used by `savePrfs`.

The reverse direction is `getDataBridge` (native → JS): native calls
`W.loadUrl("javascript:getDataBridge('<json>')")` to hand external-app deep-link
data into the page (`SRWebActivity.java:2004-2022`).

Permission-gated actions route through `V(String[] permissions)`
(`SRWebActivity.java:1493`); on grant, `c1()` (`:2196-2220`) redispatches by the
stored action string.

| Action | Handler | Params (JSON) | Result | Auth / permission | Source |
|---|---|---|---|---|---|
| `mkQRCode` / `mkQRCode2` | `B0()` | `{data:String, width:int}` | `data:{imgData:"data:image/png;base64, <…>"}` (label says PNG but bytes are JPEG q=50) | none | `SRWebActivity.java:1059,1185,1210-1240` |
| `takePicture` | `d1()` | `{}` | `data:{imgData}`; cached to SRApp `getTakePicture` | runtime `CAMERA` | `:1060-1062,1687-1704,2251-2262` |
| `selectPicture` | `R0()` | `{}` | `data:{imgData}` | `READ_MEDIA_IMAGES`(SDK≥33)/`WRITE_EXTERNAL_STORAGE` | `:1064,1409-1420,2264-2285` |
| `selectPictureByCode` | `S0()` | `{code:int}` | `data:{imgData,code,filename}` | media/storage | `:1064,1422-1437,2286-2311` |
| `getTakePicture` | `o0()` | ignored | `data:{imgData}` from cache (JS routes to `bridgeCallBackLeft`) | none | `:1065-1067,1905-1917` |
| `getTakeIdCard` | `o0()` | ignored | `data:{imgData}` (same handler; action string echoed) | none | `:1097-1099,1905-1917` |
| `showTransKey` | `a1()` | `{keyType,title,hint,maxLength,minLength,useAllDelete,useCursor,keydata,disableSymbol,language}` | success `data:{plainData}`; cancel `data:{errorMsg}` | none; SEED secure keypad | `:1069-1071,2145-2186,2352-2390` |
| `pkgVersion` | `H0()` | ignored | `data:{pkgVersion:versionName}` | none | `:1073-1075,1308-1320` |
| `getNetworkAddress` | `j0()` | ignored | `data:{mac:<uppercased android_id, :,- stripped>, ip:<dotted-quad>}` | none | `:1077-1079,1836-1856` |
| `snsLogin` | `b1()` | `{type:"G"|"K"}` | success `data:{id,type}`; fail `data:{msg}` | Google Sign-In / Kakao SDK | `:1081-1083,2188-2194,2315-2348` |
| `callExtApp` | `U()` | `{pkgName,viewName,values}` | only when target NOT installed: `data:{pkgName,viewName}` then opens `market://` | none | `:1085-1087,1444-1490` |
| `savePrfs` | `Q0()` | `{prfsKey,values,callback}` | named-int callback `<callback>(<resultCode>)` (SRApp prefs) | none | `:1089-1091,1393-1407` |
| `loadPrfs` | `y0()` | `{prfsKey,callback}` | named-string callback `<callback>('{resultCode,data}')`; `data`=`JSONArray(value)` unless `callback=="offTicketListCallback"` | none | `:1093-1095,1990-1995` |
| `regDevice` | `K0()` → `b6.a` | jsonParam parsed but unused | native `ERBAPIs.pushRegist(push.srail.co.kr,3101,userID=android_id,token=FCM,pkg,timeout=30)` → int; **no JS callback** | android_id identity | `:1101-1103,1330-1338`; `b6/a.java:123-126` |
| `unRegDevice` | `e1()` → `b6.a` | unused | native `ERBAPIs.pushUnRegist(...)` → int; clears USER_ID/USERID; no JS callback | android_id identity | `:1105-1107,1706-1714`; `b6/a.java:105-107` |
| `mobileFAX` | `C0()` | `{image:"<meta>,<base64 JPEG>"}` | no callback; writes `<time>.jpg` and `ACTION_SEND` to `com.dho.mobilefax` | media/storage | `:1109-1111,1242-1270,2079-2117` |
| `getStorageItem` | `n0()` | `{key, defaultValue?, pageId?}` | `data:{key,value,pageId}` (SRAIL prefs) | none | `:1113-1115,1872-1902` |
| `setStorageItem` | `W0()` | `{key,value,pageId?}` | `data:{key,value,pageId}`; also auto-stores appId/deviceId at startup | none | `:1117-1119,1542-1570,2522-2523` |
| `removeStorageItem` | `M0()` | `{key,pageId?}` | `data:{key,pageId}` (SRAIL prefs) | none | `:1121-1123,1340-1366` |
| `writeLog` | `h1()` | `{type,msg}` | `data:{}` — **DEV build only** (`GlobalApplication.f8033g=="DEV"`) | none; DEV only | `:1125-1131,1780-1801` |
| `easypay` | `d0()` | `{type:"shinhanfan"}` | no callback; VIEW Intent to Shinhan app / Play Store | none | `:1132-1134,1658-1685` |
| `mainShow` | `A0()` | ignored | no callback; hides splash overlay | none | `:1136-1138,1203-1207` |
| `windowOpen` | `g1()` | `{url}` (tolerant of `{data:…}` wrapper) | `data:{url}` (opens new WebView window) | none | `:1140-1155,1763-1770` |
| `disableCapture` | inline Runnable | ignored | no callback; sets `FLAG_SECURE` (8192) | none | `:1156-1158,1033-1035` |
| `enableCapture` | inline Runnable | ignored | no callback; clears `FLAG_SECURE` | none | `:1160-1162,1043-1045` |
| `allowedAuthnr` | `f0()` | `{aaidList:String[]}` | Handler `10001` → `data:{resultMsg,isSupported}` (`resultCode<1200=ok`) | `READ_PHONE_NUMBERS`(SDK≥30)/`READ_PHONE_STATE`; FIDO | `:1163-1166,1716-1740,794-807` |
| `requestServiceRegist` | `g0(…,20001)` | `{trId, …}` | Handler `20001` → `data:{resultMsg,requestParam}` | FIDO register | `:1168-1170,1742-1761,809-814` |
| `requestServiceRelease` | `g0(…,30001)` | `{trId, …}` | Handler `30001` → `data:{resultMsg,requestParam}` | FIDO release | `:1171-1173,809-830` |
| `requestServiceAuth` | `g0(…,40001)` | `{trId, …}` | Handler `40001` → `data:{resultMsg,requestParam}` | FIDO auth | `:1175-1177,823-830` |
| `getDataBridge` (native→JS) | `G0()` | `{PARAM, path, toKrailFlag:"1"}` | consumed by page; no native return | none | `:2004-2022` |
| `exitApp` (direct method) | — | none | `Activity.finish()` | none | `:1192-1196` |

---

## 4. Data models

### 4.1 Search / reservation session state — `gds_rsv` (`AraRsvState`)

The hidden-input state bag backing `#seatSearchForm` and `#rsvForm`. Canonical
init at `ara0101v.js:84-152`; extended at `ara1001l.js:1438-1468`. Selected
fields:

> **CORRECTED 2026-07-27.** The `psgTpCd` table below was wrong in both places
> it appeared: it read `2=어린이, 3=경로, 4=중증장애, 5=경증장애`, which swaps
> 2↔5 and 3↔4 against `commCode.js:54-88` (`1 어른`, `2 장애 1~3급`,
> `3 장애 4~6급`, `4 만 65세이상`, `5 만4~12세`). **The CODE was always right**
> — `models.py` maps `psgTpCd 5` to 어린이 — so this was a correction trap: a
> reader who "fixed" the code to match this document would have booked child
> fares into 장애인 seats. Two earlier audits flagged it and neither edit
> landed, which is why it is called out here rather than quietly amended.

| Field | Meaning / decode | Source |
|---|---|---|
| `jobId` | 조정구분코드: 1101=개인예약, 1102=예약대기, 1103=시트맵예약 | `ara0101v.js:85` |
| `jrnyTpCd` | 여정유형코드: 11=편도, 14=환승편도 | `ara0101v.js:86` |
| `grpDv` | 단체구분: 0=개인, 1=단체 (selects arc05013 vs arc06014) | `ara0101v.js:88` |
| `rtnDv` | 왕복구분: 0=편도, 1=왕복 | `ara0101v.js:89` |
| `chtnDvCd` | 직통환승구분: 1=직통, 2=환승 (derived `jrnyTpCd=="11"?1:2`) | `ara1001l.js:98` |
| `stlbTrnClsfCd1` | 역무차종별코드: 17=SRT, 05=전체, 00=KTX(+SRT) | `ara0101v.js:90` |
| `trnGpCd1` | 열차그룹코드: 300=SRT, 900=KTX+SRT, 109=전체 | `ara0101v.js:93` |
| `dptRsStnCd1`/`arvRsStnCd1` | 출발/도착역코드 (defaults 0551=수서, 0020=부산) | `ara0101v.js:96,98` |
| `dptDt1`/`dptTm1` | 출발일자(yyyyMMdd)/시각(HHmmss) | `ara0101v.js:101-102` |
| `back_dptDt1`/`back_dptTm1` | 오는열차(inbound) 출발일자/시각 | `ara0101v.js:105-106` |
| `totPrnb` | 총인원수 (also sent as `choiceSeatCount`) | `ara0101v.js:109` |
| `psgTpCd1..5` | 승객유형: 1=어른,2=장애 1~3급,3=장애 4~6급,4=만 65세이상,5=만4~12세(어린이) | `commCode.js:54-88` |
| `psgInfoPerPrnb1..5` | 승객정보당인원수 | `ara0101v.js:114-122` |
| `rqSeatAttCd1/2` | 요구좌석속성: 015=일반, 021=휠체어, 028=전동휠체어 | `ara0101v.js:127,134` |
| `smkSeatAttCd*`=`000`, `dirSeatAttCd*`=`009`, `locSeatAttCd*`=`000`, `etcSeatAttCd*`=`000` | 좌석속성 defaults | `ara0101v.js:124-135` |
| `psrmClCd1` | 객실등급코드: 1=일반실, 2=특실 | `ara1001l.js:1452` |
| `dptStnRunOrdr1`/`arvStnRunOrdr1`, `dptStnConsOrdr1`/`arvStnConsOrdr1` | 운행/구성 순서 | `ara1001l.js:1453-1456` |
| `go_baseDsXml`/`go_seatDsXml` | round-trip outbound `reservListMap`/`trainListMap` cache | `ara0101v.js:138-139`; written `ara1001l.js:1583-1584` |
| `seatNo1_1..N`, `scarNo1/2`, `scarGridcnt1/2` | seat-map-derived per-seat labels/car/grid | `ara0101v.js:872-882` |

### 4.2 `AraSearchResponse` (search envelope)

| Field | Meaning | Source |
|---|---|---|
| `ErrorCode` | -1 = error (→ alert + `lfn_goBack()`) | `ara1001l.js:190-193` |
| `ErrorMsg` | error message | `ara1001l.js:191` |
| `outDataSets.dsOutput0[]` → `AraSearchHeader` | header row (read as `[0]`) | `ara1001l.js:198` |
| `outDataSets.dsOutput1[]` → `AraTrainItem` | train result rows | `ara1001l.js:199` |

**`AraSearchHeader` (`dsOutput0[0]`):** `strResult` ("FAIL" = business error),
`msgTxt`, `fllwPgExt` ("N" = no further page)
(`ara1001l.js:198-205, :1873`).

### 4.3 `AraTrainItem` (`dsOutput1[]` row) — selected fields

Server fields: `trnNo`, `stlbTrnClsfCd`, `trnClsfCd` (sent as `trnSort`),
`trnGpCd`, `chtnDvCd`, `dptRsStnCd`/`arvRsStnCd`, `dptDt`/`dptTm`,
`arvDt`/`arvTm`, `runDt`, `dptStnConsOrdr`/`arvStnConsOrdr`,
`dptStnRunOrdr`/`arvStnRunOrdr`, `gnrmRsvPsbStr`/`gnrmRsvPsbImg`/`gnrmRsvPsbColor`
(일반실 status), `sprmRsvPsbStr`/`sprmRsvPsbImg`/`sprmRsvPsbColor` (특실 status),
`trainDiscGenRt` (조기예매 할인율 %), `rcvdAmt` (영수운임), `stmpRsvPsbFlgCd`
("YY" enables seat selection). Client-added-after-render fields (**not from
server**): `timeTable`, `payTable`, `seatSelect`, `doReserv`.
Source: `ara1001l.js:385-460, :1146-1149, :1443-1467`.

### 4.4 Reservation response models (evidence)

- **`ReserveResponse`** (`arc05013`/`arc06014`):
  `{resultMap[], reservListMap[], trainListMap[], commandMap[]}`, each read as
  `[0]` (`ara1001l.js:1557-1579`).
- **`ReserveResultMap[0]`:** `strResult` ("FAIL"), `msgCd` ("S111"=re-login),
  `msgTxt`, `totRcvdAmt`, `tmpJobSqno1` (`ara1001l.js:1560-1602`).
- **`ReservListMap[0]`:** `pnrNo` (individual only), `JRNYLIST_KEY`, `arvDt`,
  `arvRsStnCd`, `arvTm`, `dlayAcptFlg`, `dptDt`, `dptRsStnCd`, `dptTm`,
  `lumpStlTgtNo`, `proyStlTgtFlg`, `stlbTrnClsfCd`, `totSeatNum`, `trnGpCd`,
  `trnNo` (`ara1001l.js:1609-1626`).
- **`TrainListMap[0]`:** `seatNo`, `scarNo` (`ara1001l.js:1604-1605`).
- **`SeatSelectResult`** (from seat map to `popCallback`): `scarSeatNo`
  ("2,7,10"), `scarSeatNm` ("1B,2C,3B"), `scarNo` (`ara0101v.js:866-893`).
- **`MutMrkVrfCdResponse`:** `outDataSets.dsOutput0.{strResult,msgTxt,mutMrkVrfCd}`
  — `dsOutput0` read as an object, not `[0]` (`ara1001l.js:233-242`).

### 4.5 `UserInfo` (`application.gds_userInfo`)

`MB_CRD_NO` (회원카드번호; empty = not logged in), `USER_DV` ("2"=비회원),
`CUST_MG_NO` (고객관리번호), `ABRD_RS_STN_CD` / `GOFF_RS_STN_CD` (default
승/하차역). Source: `ara0101v.js:52-62`; `ara1001l.js:1288, :1316-1318`.

### 4.6 `POP_REQ_*` navigation constants (`const.js:1-11`)

`1`=STN, `2`=STN_MAP, `3`=DPT_DT, `4`=ARV_DT, `5`=SEAT, `6`=PASSENGER,
`7`=TRN_GRP, `8`=PAYTABLE, `9`=SEATSELECT_DPT_ONEWAY, `10`=SEATSELECT_GO_BACK,
`11`=SEATSELECT_GO_BACK_DONE.

### 4.7 srbridge envelopes

`BridgeCallbackEnvelope` `{action, resultCode, data, image?}` (`image` added
only when `data.imgData != null`) — `SRWebActivity.java:516-523`. Per-action
model fields are enumerated inline in §3.5.

### 4.8 Domain constant decodes (verified reference)

`jrnyTpCd` 11=편도/14=환승 · `chtnDvCd` 1=직통/2=환승 · `rtnDv` 0=편도/1=왕복 ·
`grpDv` 0=개인/1=단체 · `jobId` 1101/1102/1103 · `trnGpCd` 300=SRT/900=KTX+SRT/109=전체 ·
`stlbTrnClsfCd` 00=KTX/05=전체/07·10=KTX-산천/17=SRT (full table `main.html:626-640`) ·
`psrmClCd` 1=일반실/2=특실 · `rqSeatAttCd` 015=일반/021=휠체어/028=전동휠체어 ·
`psgTpCd` 1=어른/2=장애 1~3급/3=장애 4~6급/4=만 65세이상/5=만4~12세(어린이) · default stations 0551=수서, 0020=부산.

---

## 5. Local storage

Storage is split across **two** Android `SharedPreferences` stores:

| Store | Bridge actions | Notes | Source |
|---|---|---|---|
| `SRAIL` | `getStorageItem` / `setStorageItem` / `removeStorageItem` | Web-facing key/value; startup auto-injects `appId` + `deviceId` | `SRWebActivity.java:1348,1550,1880,2522-2523` |
| `SRApp` (via `c6.d`) | `savePrfs` / `loadPrfs`; image cache key `getTakePicture` | Also holds FCM `TOKEN`, `USERID`; H2O `USER_ID` cleared on unRegDevice | `c6/d.java:24`; `SRWebActivity.java:1907` |

The web app also uses **DOM `localStorage`** (WebView DOM storage enabled). Note
the security leak in §7: on reserve `S111`, the full serialized `rsvForm` is
written to `localStorage['userReservation']`.

---

## 6. WebView & URL schemes

- **WebView host:** `SRWebActivity`; JS enabled, DOM storage enabled, multiple
  windows enabled, mixed content allowed, third-party cookies allowed. (Static
  settings corroborated in prior spec §3.)
- **Bridge registration:** `addJavascriptInterface(new y(…), "srbridge")`
  (`SRWebActivity.java:2677`).
- **External-app / URL-scheme handoffs** via `callExtApp` (§3.5) and dedicated
  actions:
  - `com.RLP.railpolice` → `krailwaypolice://crime.report?<values>`
    (`SRWebActivity.java:1444-1490`).
  - `easypay` → `shinhan-sr-ansimclick-srt://` scheme or
    `market://…com.shcard.smartpay` (`SRWebActivity.java:1658-1685`).
  - `mobileFAX` → `ACTION_SEND` to `com.dho.mobilefax`.
  - `snsLogin` → Google Sign-In intent (req 9001) / Kakao (req 201).
- **Manifest external-package query targets** (verified in prior spec §8):
  `com.korail.talk`, `net.daum.android.map`, `com.kakao.taxi`,
  `com.RLP.railpolice`, `com.dho.mobilefax`, `kr.go.mobileid[.tbe]`.

---

## 7. Security & anti-tamper

| Finding | Detail | Source |
|---|---|---|
| No cert pinning | None found in the app package | — |
| Cleartext permitted | `usesCleartextTraffic="true"`; no network-security-config | `AndroidManifest.xml:53` |
| Cleartext integrity endpoint | `http://iron.srail.co.kr/authCheck.call` (AppIron) | `res/values/strings.xml:73` |
| Screenshot control | `disableCapture`/`enableCapture` toggle `FLAG_SECURE` (8192) | `SRWebActivity.java:1033-1045` |
| Secure keypad | `showTransKey` SEED-encrypted; **plaintext `plainData` returned to JS** — do not log | `SRWebActivity.java:2352-2390` |
| **Privacy leak (reserve S111)** | On `msgCd=="S111"` the full serialized `rsvForm` (journey + passenger composition) is written to `localStorage['userReservation']` **and** dumped via `console.log(param)` and raw `alert(param)` — leftover debug code shipped in production | `ara1001l.js:1565-1571` |
| Java obfuscation | App package retains readable class names (`SRWebActivity`) but all methods/fields are R8-renamed to 1–2 letters; helper libs under `c6`, `f7`, `y5`. Domain logic is plaintext JS, so obfuscation does not impede analysis | — |
| FIDO / biometric | RaonSecure OnePass/FIDO UAF against `https://fido.srail.co.kr`; `siteId=SIT02SR0000000000000`, `svcId=SVC01SIT02SR00000000` | `SRWebActivity.java:2517-2519` |

---

## 8. Coverage vs implemented client (`src`)

The `src/srt_mobile_api` package is a **pure server-side, read-only HTTP
client**. Its allowlist (`safety.py: READ_ONLY_ROUTES`) is the authority on what
is and is not implemented.

### 8.1 Implemented (in `READ_ONLY_ROUTES` / client methods)

| Endpoint | Client reference |
|---|---|
| `GET /login/login.do` | `session.py:17` |
| `POST /apb/selectListApb01080_n.do` | `session.py:19` |
| `GET /main/main.do` | `client.py:92` |
| `GET /ara/ara0101v.do` | `client.py:97` |
| `POST /main/noticeList.do` | `client.py:100-108` |
| `GET /atc/selectListAtc14017_n.do` | `client.py:120` |
| `GET`+`POST /ara/selectListAra10007_n.do` | `client.py:229, :263` |
| `POST /ara/selectListAra10082_n.do` (group) | `client.py:244` |
| `POST /ara/selectListAra10130_n.do` (empty `{}` body — matches static "no data key") | `client.py:207-209` |
| `POST /ara/selectListAra12009_n.do` (timetable) | `client.py:399` |
| `POST /ara/selectListAra13010_n.do` (fare) | `client.py:411` |
| `POST /arc/selectListArc02012_n.do` (seat map, read-only, field-locked in `safety.py:94-115`) | `client.py:390` |
| `POST /common/ARA/ARA0501P/view.do` (station) | `client.py:146` |
| `POST /common/ARA/ARA0502P/view.do` (station map) | `client.py:154` |
| `POST /common/ARA/ARA0403P/view.do` (date) | `client.py:162` |
| `POST /common/ARA/ARA0901P/view.do` (passenger) | `client.py:170` |
| `POST /common/ARA/ARA0701P/view.do` (seat option) | `client.py:184` |
| `POST /common/ARA/ARA0201V/view.do` (train group) | `client.py:200` |
| `GET https://nf.letskorail.com:443/ts.wseq` (NetFUNNEL `act_10` helper) | `safety.py:77` |

### 8.2 NOT implemented (by design — read-only library boundary)

| Endpoint | Reason |
|---|---|
| `POST /arc/selectListArc05013_n.do` (reserve, individual) | Mutation — excluded |
| `POST /arc/selectListArc06014_n.do` (reserve, group) | Mutation — excluded |
| `POST /ard/selectListArd02017_n.do` (payment individual) | Payment handoff — excluded |
| `POST /ard/selectListArd02018_n.do` (payment group) | Payment handoff — excluded |
| `GET /ata/selectListAta01032_n.do` (discount detail) | State-dependent; prior spec runtime = HTTP 500 with dummy PNR |
| `ara/selectListAra10h01.do` (dead Nexacro gateway) | Dead code / never issued |
| NetFUNNEL `act_19` (reservation gate) | Excluded (`EXCLUDED_API_DOMAINS`, `safety.py:180-192`) |
| Entire `srbridge` surface (30 actions) | In-process Android bridge, not an HTTP API — **zero hits** for `srbridge`/`bridgeCall`/`mkQRCode`/`showTransKey`/`OnePass`/`fido.srail` in `src` |

### 8.3 Layer divergences (both correct for their layer)

| Divergence | Bundled JS (this analysis) | Implemented client / live layer |
|---|---|---|
| Date picker | `ARA0401P` (`ara0101v.js:203`) | `ARA0403P` (`client.py:162`) — prior spec labels ARA0401P "legacy/bundled" |
| Station-map picker | call site absent from `ara0101v.js` | `ARA0502P` added (`client.py:154`) |
| NetFUNNEL | `BEGIN` commented out in bundled JS | live server still gates on fresh `act_10` key (`NET000001`) |

---

## 9. Discrepancies & open questions

### 9.1 NEW vs already-documented

**Already documented** in `srt-app-api-library-spec-2026-07-09.md` (with runtime
detail this static pass cannot see): the search/reserve/payment endpoint URLs,
runtime success codes (`msgCd=IRG000000`, `strResult=SUCC`), mutual-verification
(`IRZ000008`), the reserve/payment param sets, seat-callback fields, the
`srbridge` action families (spec §8), the PRD/DEV bases, and the UA suffix. **No
contradictions** were found against that spec.

**NEW in this analysis** (not in the prior endpoint-centric docs):

1. The obfuscated srbridge handler mapping (30 actions → 24 handlers) and the
   **three** callback marshalling paths (`T`/`bridgeCallBack`, `I0`, `J0`).
2. Per-action srbridge request/response field models (§3.5) and the
   SRApp-vs-SRAIL storage split (§5).
3. Exact H2O push host:port `push.srail.co.kr:3101` and FIDO
   `siteId`/`svcId`/OnePass request codes (`20001`/`30001`/`40001`,
   `resultCode 1200`).
4. `getDataBridge` reverse (native→JS) direction.
5. The dead Nexacro gateway `ara/selectListAra10h01.do`.
6. The exact time-cursor paging formula (`substr(0,5)+"1"`) and round-trip leg
   swapping via `fv_sRtnCd`.
7. The `S111` `localStorage['userReservation']` + `alert(param)` payload leak.
8. `savePrfs`/`loadPrfs` (omitted from prior spec) and `mkQRCode` field keys.

### 9.2 Corrections folded into this document (superseding raw finding text)

- **srbridge action count:** the dispatcher routes **30** distinct action
  strings (prior "~29"), mapped to 24 obfuscated handlers.
- **`pnrDataSave`/`pnrDataLoad`:** these live in the **current `bridge.js`**
  (iOS `WebViewJavascriptBridge` path, `bridge.js:127-142`), *not* in
  `bridge_old.js`. The substantive claim stands: the Android `bridgeCall`
  dispatcher does **not** implement them.
- **`mkQRCode` output:** payload prefix is the literal `"data:image/png;base64, "`
  (trailing space) but the bytes are **JPEG** compressed at quality 50
  (`SRWebActivity.java:1229`) despite the `image/png` label.
- **`ARC0103C` dispatch:** `fn_goPage` has **no `ARC0103C` branch** (only
  `ARC0201C`/`ARC0102C`). `ARC0103C` passed to `fn_goPage` is a **no-op**; the
  return-leg reserve is actually reached via `popCallback`
  (`POP_REQ_SEATSELECT_GO_BACK`=10 / `_DONE`=11 → `fn_callReserv()`,
  `ara0101v.js:887,891`). On the non-seat "예약하기" return path this is a latent
  no-op bug.
- **`/neo` host** appears in decompiled Java (`SRWebActivity.java:2055,:2068`),
  not only in `assets/dev.html:21`.
- **Latent JS bug:** `fn_scheduleList` references undeclared `sPagingYn` at
  `ara1001l.js:1850, :1863`, and `:1873` reads `dsOutput0.fllwPgExt` outside its
  success-callback scope (a second latent `ReferenceError`).

### 9.3 ⚠️ Unverified / low-confidence

The following could **not** be confirmed from the APK and must not be treated as
fact:

- **Literal value of `{contextPath}`** — injected server-side; absent from all
  bundled assets. Absolute paths cannot be asserted beyond `<base>/{contextPath}/…`.
- **Server-side response field *values*** for any endpoint (e.g. concrete
  `mutMrkVrfCd`, PNR formats, HTML page internals) — outside the APK. The
  runtime values in the prior spec (e.g. `IRG000000`, `IRZ000008`, fare amounts)
  come from that spec's live probes, not from this static pass.
- **The full `#seatSearchForm` / `#rsvForm` field list** — the form markup is
  server-rendered JSP and not in the APK. Only the fields the client explicitly
  writes/validates are enumerable (§3.2, §3.4).
- **`snsLogin` Kakao launch path** — the Google branch (`type=="G"`, req 9001)
  is present in `b1()`; the Kakao result is handled at req 201 (`type=="K"`) but
  **no bridge branch launches Kakao** in this decompile.
- **Whether `regDevice`/`unRegDevice` succeed at runtime** — they issue a
  proprietary H2O TCP call returning an int with no JS callback; success cannot
  be observed statically.

### 9.4 Open questions

- Does the live server enforce the same 30-action set, or are some srbridge
  actions dead on the current web app? (Static: all 30 are wired.)
- Does `ata/selectListAta01032_n.do` ever return a valid page with a real PNR?
  (Prior spec: HTTP 500 with a dummy PNR.)
- Are the `ARA0401P` (bundled) vs `ARA0403P` (live) date-picker paths both
  currently served, or is `ARA0401P` fully retired server-side?

---

## Appendix — Primary source files

| File | Role |
|---|---|
| `analysis/jadx/sources/kr/co/srail/newapp/webview/SRWebActivity.java` | WebView host, srbridge dispatcher, base-URL resolution |
| `analysis/apktool/assets/offline/js/ara/ara1001l.js` | Search / reserve / paging controller |
| `analysis/apktool/assets/offline/js/ara/ara0101v.js` | Search-form controller, pickers, `gds_rsv` init, `popCallback` |
| `analysis/apktool/assets/offline/js/arc/arc0102c.js` | ARC0102C reservation-detail page script |
| `analysis/apktool/assets/offline/js/common/const.js` | `POP_REQ_*` constants |
| `analysis/apktool/assets/offline/js/common/bridge.js` | JS-side bridge caller / `bridgeCallBack` |
| `analysis/apktool/assets/offline/sub/main.html` | `lfn_setRsv`/`lfn_getRsv`, station helpers, code tables |
| `analysis/.../b6/a.java`, `c6/d.java` | H2O push AsyncTask; SRApp prefs helper |
| `res/values/strings.xml` | `h2o_ip`/`h2o_port`, AppIron integrity URL |
| `AndroidManifest.xml` | cleartext flag, package query targets |
| `docs/analysis/srt-app-api-library-spec-2026-07-09.md` | Prior runtime-verified spec (cross-referenced) |
| `src/srt_mobile_api/{client,session,safety}.py` | Implemented read-only client + route allowlist |
