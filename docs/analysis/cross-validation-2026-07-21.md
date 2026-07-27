# SRT App v2.0.41 — Cross-Validation Report

**Date:** 2026-07-21
**App:** `kr.co.srail.newapp` v2.0.41 (versionCode 150)
**Authors:** FABLE
**Scope:** Reconcile the **srtgo** reference implementation (`srtgo/srt.py`) against **OUR** independent decompilation of the v2.0.41 APK (`analysis/apktool` smali+assets, `analysis/jadx` Java) and OUR own client (`src/`).

## Overview

srtgo is a working, live-tested Python client for the SRT hidden mobile-JSON API. This report checks, endpoint-by-endpoint and field-by-field, whether srtgo's assumptions hold against what is actually shipped in our v2.0.41 offline bundle and native layer, and records what our decompile reveals that srtgo never saw.

**Verification model.** Every claim below is tagged:

- ✅ **Confirmed** — the same fact is present on *both* sides (srtgo source line **and** our decompiled artifact).
- ⚠️ **Correction / discrepancy** — the two sides diverge, or one of OUR own prior docs was wrong.
- 🔀 **Version drift** — same intent, different value across srtgo (targets live) vs our offline snapshot vs our client.
- 🆕 **Newly-found hidden** — present in our v2.0.41 decompile, absent from srtgo.
- ❓ **Disputed / low-confidence** — could not be line-verified, or a citation was found imprecise. Substance noted separately.

> **On the `<SRT-APP-…-REDACTED>` placeholders below.** The SR app ships several
> third-party vendor credentials hardcoded in its own resources — Google/Firebase
> API keys, a Firebase project id, a GCM/FCM sender number, and Kakao and Facebook
> app ids — and finding them there is part of what this report records. The
> **finding** is kept in full: the field name, the file and the line number are all
> still here, so the claim stays checkable by anyone who decompiles the same APK.
> The **values** are not. They are SR's credentials, not ours, and this repository
> is public; republishing them would hand out working keys to no analytical end.
> Every one of them was rewritten out of this repository's git history and replaced
> with a `<SRT-APP-…-REDACTED>` placeholder naming which key it stood for. Nothing
> here was a secret of SRT's *API* — none of these keys is used by anything this
> library does.

> **Status note (2026-07-25) — a snapshot, plus one gap it named that has since
> been closed.** This report is a static cross-validation dated 2026-07-21 and is
> left as written; every 0-hit finding in it still holds, because they are facts
> about our offline bundle and no bundle changed. What has changed is that the
> live capture it repeatedly called for **was performed for cancel** on
> 2026-07-25: one operator-run reserve->cancel round trip against the real server
> released a real unpaid hold — reserve (`Arc05013`) `strResult=SUCC` /
> `msgCd=IRR000018`, cancel (`Ard02045`, body `pnrNo`/`jrnyCnt="1"`/
> `rsvChgTno="0"`) `strResult=SUCC` / `msgCd=IRG000000` — and the ticket list held
> no trace of it afterwards. So `Ard02045` is still ABSENT from our decompile
> **and** now confirmed on the live server for our app version; the two statements
> are about different evidence and both are true. The run covered ONE
> single-journey, one-adult, general-seat reservation. **Standby (`Ata01135`) and
> ticket-info (`Ard02019`) were NOT captured and remain attested only by srtgo.**
>
> **✅ Update (2026-07-26) — payment and refund were captured too.** Same shape of
> result, same day-later pattern, and again the 0-hit findings below are unchanged
> facts about the offline bundle. A free probe first: a fake card and a
> non-existent PNR drew proper business envelopes from both routes rather than
> 404s — `Atc14087` returned `msgCd=WRT300005` / "조회자료가 없습니다.",
> `Ata09036` returned `strResult=FAIL` / `msgCd=WRT100170` — which established that
> both exist on v2.0.41 without spending anything. Then one real round trip:
> 수서→동탄, one adult, 7,500 KRW, payment `strResult=SUCC` / `msgCd=IRT000000`,
> two-step refund `strResult=SUCC` / `msgCd=IRT200277`, account verified empty
> afterwards from a separate session. It also settled §4's `tkRetPwd` / `psgNm`
> prefix-drift question: srtgo's step-2 spellings are the ones the server takes,
> and the bare `retPwd` / `buyPsNm` forms in our offline ticket store really were
> a local cache vocabulary rather than an API schema. So `Ata09036`,
> `Atc14087` and `Atc02063` are still ABSENT from our decompile **and** now
> confirmed on the live server; both statements are about different evidence.
> Scope: one single-journey, one-adult, general-seat ticket on one personal card
> in one lump sum. See
> `docs/IMPLEMENTATION_PROGRESS.md` ("Live Reserve->Cancel Verification") and
> `CHANGELOG.md` (Unreleased); the resolution is also noted at §4, at "Net changes"
> #2 and at "Remaining open questions" #1.

**Headline result.** The hidden `_n.do` JSON API srtgo targets is unambiguously **real** in our v2.0.41 bundle: login, search, reserve, tickets, and the NetFunnel queue all match on host, path, field names, and response envelope. The material divergences are (a) six endpoints (payment, cancel, refund, standby-option, reserve-info, ticket-info) that are **server-rendered and simply not shipped** in the offline bundle, so they are unverifiable from our static code and attested only by srtgo's live runs; (b) an **alternate host** `app.srail.co.kr/neo/` srtgo never models; and (c) a whole **group / seat-map reservation branch** srtgo has no analogue for.

---

## 1. Hidden JSON API (base architecture)

### ✅ Confirmed

- **Base host + initial route.** srtgo `SRT_MOBILE='https://app.srail.or.kr:443'` (`srt.py:88`) and `main='/main/main.do'` (`srt.py:90`) match OUR PRD host `Z='https://app.srail.or.kr'` (`SRWebActivity.java:1578`) and initial URL `Y=Z+'/main/main.do?deviceId='+...` (`SRWebActivity.java:1584`).
- **Login endpoint + fields.** srtgo `/apb/selectListApb01080_n.do` (`srt.py:91`) == OUR `main.html:721` `<form action="../apb/selectListApb01080_n.do" method="POST">`. Field names `srchDvCd/srchDvNm/login_referer/hmpgPwdCphd` (srtgo `srt.py:706-709`) == hidden inputs `main.html:722-727`. srtgo reads JSON `userMap` (`srt.py:723`), proving the endpoint returns JSON.
- **Search is a pure-JSON XHR** (not a form nav). srtgo `/ara/selectListAra10007_n.do` (`srt.py:93`) == OUR `ara1001l.js:180`, called via `$.ajax({type:'POST', dataType:'json'})` (`ara1001l.js:185-189`); response read as `data.outDataSets.dsOutput1` (`ara1001l.js:198-199`) == srtgo `parser.get_all()['outDataSets']['dsOutput1']` (`srt.py:833`). Train-class filter matches: srtgo posts `stlbTrnClsfCd='05'` then filters `=='17'` (`srt.py:808,834`) == OUR comment `stlbTrnClsfCd (05:전체, 17:SRT)` (`ara1001l.js:103`).
- **Reserve is a pure-JSON XHR.** srtgo `/arc/selectListArc05013_n.do` (`srt.py:94`) == OUR `ara1001l.js:1547`, `$.ajax({type:'POST',dataType:'json'})` (`ara1001l.js:1552-1556`). Response envelope matches exactly: srtgo reads `resultMap[0]` + `reservListMap[0]['pnrNo']` (`srt.py:382,1006`) == OUR `data.resultMap[0]`/`data.reservListMap[0]`/`data.trainListMap[0]`/`data.commandMap[0]` (`ara1001l.js:1560,1577-1579`).
- **RESERVE_JOBID codes.** srtgo `PERSONAL='1101'`, `STANDBY='1102'` (`srt.py:31-32`) == OUR `ara0101v.js:90` comment `1101:개인예약,1102:예약대기,1103:시트맵예약` + runtime assignment `ara1001l.js:1445` (1101) / `:1448` (1102).
- **Tickets endpoint + param.** srtgo `/atc/selectListAtc14016_n.do` with `pageNo:'0'` (`srt.py:95,1069`) == OUR `ticketList.html:405` `data-url="/srail-app/atc/selectListAtc14016_n.do?pageNo=0"` AND native `SRForegroundDialogActivity.java:31` `SRWebActivity.z0('https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0')`.
- **NetFunnel queue system.** srtgo `NetFunnelHelper`: host `nf.letskorail.com`, path `/ts.wseq`, opcodes `5101/5002/5004`, `sid=service_1`, `aid=act_10` (`srt.py:505-509,583,603`) == OUR `netfunnel.js:12` `nf.letskorail.com`, `:15` `ts.wseq`, `:16` `service_1`, `:17` `act_10`, `:84` opcodes `5101/5002/5004`. OUR own client also encodes this: `config.py:11` `NETFUNNEL_ORIGIN='https://nf.letskorail.com:443'`.

### ⚠️ Corrections / discrepancies

- **`ticket_info` endpoint DIVERGES.** srtgo uses `/ard/selectListArd02019_n.do` (`srt.py:96`). **Ard02019 does not appear anywhere** in our decompiled assets/smali/jadx. OUR bundled JS instead uses **Ard02017** (individual, `ara1001l.js:1608`) and **Ard02018** (group, `ara1001l.js:1599`) — but those are the reserve→detail/payment handoff, submitted as `frm.action=...` **FORM navigations** to HTML pages, not the JSON `ticket_info` call. Ard02019 is server-only and unverifiable from our offline decompile.
- **Payment/cancel/refund/standby-option/reserve-info are ABSENT from our decompile.** srtgo `Ata09036` payment (`srt.py:99`), `Ard02045` cancel (`srt.py:97`), `Atc02063` refund (`srt.py:102`), `Ata01135` standby_option (`srt.py:98`), `getListAtc14087.do` reserve_info (`srt.py:100`) — grep across all of `analysis/apktool` and `analysis/jadx` returns **ZERO** hits. They live only in server-rendered pages not shipped offline; their request shapes cannot be confirmed against v2.0.41 from our code — only srtgo's live-tested shapes attest. (Adjacent `Ata01032` discount-detail exists at `arc0102c.js:34` but is a different function.)
- **Host assumption is incomplete in srtgo.** srtgo treats `app.srail.or.kr` as the sole host. OUR app also serves the same `_n.do` JSON from a **second host** `app.srail.co.kr/neo/` (`SRForegroundDialogActivity.java:31`; `dev.html:21`) and a dev variant `devapp.srail.co.kr/neo/` (`SRWebActivity.java:2055,2068`). srtgo misses the alternate host entirely.
- **NetFunnel is stubbed/commented-out in our OFFLINE bundle**, contradicting srtgo's active handshake. srtgo fetches a key and injects `netfunnelKey` into search & reserve bodies (`srt.py:819,987`). In OUR `ara1001l.js:1734-1739` the `NetFUNNEL.SetService/BEGIN` calls are commented out and `netfunnel_callback()` jumps straight to `fn_search()`; the search `oData` (`ara1001l.js:158-170`) has no `netfunnelKey`. This is a stale offline-snapshot artifact — the live server JS and OUR own client (`payloads.py:166` sends `netfunnelKey`) do use it — but taken literally the offline JS diverges from srtgo.

### 🔀 Version drift

- **App version:** srtgo hardcodes UA suffix `SRT-APP-Android V.2.0.38` (`srt.py:22`); OUR app is v2.0.41 (UA suffix built natively as `SRT-APP-Android V.<versionName>`, `SRWebActivity.java` ~2642-2645). 3-patch drift.
- **contextPath prefix:** OUR cached `ticketList.html:405` uses legacy `/srail-app/atc/selectListAtc14016_n.do`; srtgo (live) uses host-root `/atc/selectListAtc14016_n.do` (`srt.py:95`). The `/srail-app` context path is a stale value baked into the offline asset.
- **NetFunnel activation:** stubbed in offline `ara1001l.js:1734-1739` vs active in srtgo (`srt.py:819,987`) and in OUR live-targeting client (`payloads.py:166`). The offline bundle predates/omits the netfunnel wiring the live 2.0.41 server serves.

### 🆕 Newly-found hidden (srtgo missed)

- **`jobId '1103'` = 시트맵예약** (seat-map reservation) — `ara1001l.js:1436`, `ara0101v.js:90`. srtgo only knows 1101/1102.
- **Alternate initial route `/atc/selectListAtc14017_n.do`** — `SRWebActivity.X0()` sets the main URL to Atc14017 when launch mode `=='2'` (`SRWebActivity.java:1592`). Sibling of Atc14016; OUR own client targets Atc14017.
- **Seat-selection JSON endpoint `/arc/selectListArc02012_n.do`** (`ara1001l.js:1515`) returns seat data (`scarSeatNo`/`scarNo`) via `popCallback`. srtgo has no seat API at all.
- **Anti-abuse mutual-verification token `/ara/selectListAra10130_n.do`** returning `mutMrkVrfCd` (`ara1001l.js:229-241`) — no srtgo equivalent.
- **Group (단체) endpoint family** branched on `grpDv=='1'`: search `Ara10082` (`ara1001l.js:177`), reserve `Arc06014` (`ara1001l.js:1544`), detail `Ard02018` (`ara1001l.js:1599`). srtgo is individual-only.
- **Timetable `/ara/selectListAra12009_n.do`** (`ara1001l.js:1189`), **fare `/ara/selectListAra13010_n.do`** (`ara1001l.js:1229`), **discount-detail `/ata/selectListAta01032_n.do`** (`arc0102c.js:34`) — none in srtgo.
- **Extra native hosts/services:** `devapp.srail.co.kr/neo/common/rest/JongURi/view.do` (`SRWebActivity.java:2055,2068`) and FIDO biometric endpoint `https://fido.srail.co.kr` (`SRWebActivity.java:2519`).

### OUR-version exact values

- PRD host `https://app.srail.or.kr` | dev host `https://devapp.srail.or.kr` (`SRWebActivity.java:1578-1580`)
- Alternate host `https://app.srail.co.kr/neo` (`SRForegroundDialogActivity.java:31`)
- Initial URL `/main/main.do?deviceId=<android_id>` (`SRWebActivity.java:1584`)
- Login form fields: `srchDvCd, srchDvNm, check, auto, login_referer, hmpgPwdCphd` (`main.html:722-727`)
- Tickets: `/atc/selectListAtc14016_n.do?pageNo=0` (`ticketList.html:405`)
- **Present-in-decompile `_n.do` set (v2.0.41):** Apb01080 (login), Ara10007 (search), Ara10082 (group search), Ara10130 (verify), Ara12009 (timetable), Ara13010 (fare), Arc05013 (reserve), Arc06014 (group reserve), Arc02012 (seatmap), Ard02017/Ard02018 (detail handoff), Ata01032 (discount), Atc14016/Atc14017 (ticket list).
- **ABSENT:** Ard02019, Ard02045, Ata09036, Ata01135, Atc02063, getListAtc14087.

### ❓ Disputed / low-confidence

- **Not line-verified (peripheral refs only):** srtgo function-body ranges for the ABSENT endpoints — `srt.py:1102-1112` (ticket_info), `:1140-1147` (cancel), `:1184-1225` (payment), `:1238-1257` (refund). The endpoint **constants** at `srt.py:96-102` were verified directly; the function bodies were not opened. Irrelevant to the offline-verifiability conclusion (these codes are 0-hit in our decompile).
- **Not opened:** the analysis doc cited in sourceRefs (`full-api-analysis-2026-07-20.md:47-73, :159-261`). Secondary reference; every primary source it summarizes was verified directly.
- **Minor attribution slips (substance stands):**
  - The camelCase names `getTidchkEnter/chkEnter/setComplete` are **not** literally on `netfunnel.js:84` — they are srtgo's `OP_CODE` dict keys (`srt.py:506-508`). `netfunnel.js:84` declares the same numeric opcodes under `RTYPE_` names (`RTYPE_GET_TID_CHK_ENTER=5101`, `RTYPE_CHK_ENTER=5002`, `RTYPE_SET_COMPLETE=5004`). Opcodes match; only naming was conflated.
  - srtgo's `SRT_MOBILE` literal is `https://app.srail.or.kr:443` (explicit `:443`); OUR `Z` is `https://app.srail.or.kr` (no port). Same host, not byte-identical.
  - Login-field range `srt.py:703-709` is loose — line 703 is `'page':'menu'`; the 4 named fields sit at `srt.py:706-709`. srtgo's login body carries extra keys (`page, deviceKey, customerYn`) absent from `main.html`; `main.html` additionally exposes `check`/`auto`. The 4 asserted names match, but the two field-sets are not identical. `main.html:721` also carries `id='form'` and `data-ajax='false'`.

---

## 2. Reservation

### ✅ Confirmed

- **Endpoint match.** srtgo POSTs individual reservations to `/arc/selectListArc05013_n.do` (`srt.py:94,999`) — identical to OUR app, which sets `url='/arc/selectListArc05013_n.do'` for `grpDv!='1'` and POSTs `$('#rsvForm').serialize()` (`ara1001l.js:1547,:1550-1554`).
- **jobId 1101/1102.** srtgo `RESERVE_JOBID={PERSONAL:'1101',STANDBY:'1102'}` (`srt.py:30-33,963`) matches OUR seed `jobId='1101'` (`ara0101v.js:90`) and `fn_moveRsv`, which defaults `sJobId='1101'` and sets `'1102'` when the general-cabin image is the 예약대기 image `grd_WF_Waiting_S` (`ara1001l.js:1445-1448`).
- **All 21 `fn_validChk`-required rsvForm fields are present in srtgo's body:** `jobId, jrnyTpCd, jrnyCnt, totPrnb, stndFlg, jrnySqno1, trnGpCd1, stlbTrnClsfCd1, dptDt1, dptTm1, dptRsStnCd1, arvRsStnCd1, psrmClCd1, smkSeatAttCd1, dirSeatAttCd1, locSeatAttCd1, psgInfoPerPrnb1, etcSeatAttCd1, rqSeatAttCd1, psgGridcnt, psgTpCd1` (OUR `ara1001l.js:1675-1697`), all supplied by srtgo base body + `get_passenger_dict` (`srt.py:962-997 + :189-204`).
- **NetFunnel `act_10` reuse (not `act_19`).** srtgo uses ONE shared `NetFunnelHelper` (48 s cache), `aid='act_10'` (`srt.py:603`), for BOTH search (`srt.py:819`) and `_reserve` (`srt.py:987`). OUR `netfunnel.js:16-17` defines only `TS_ACTION_ID='act_10'`; the only `NetFUNNEL.SetService` references anywhere are `act_10` and are commented out (`ara1001l.js:1737`, `ara0101v.js:652`). OUR client mirrors it: `src/netfunnel.py:18-23 build_act10_url`.
- **Response envelope.** srtgo reads `reservListMap[0]['pnrNo']` (`srt.py:1006`) from the 4-array JSON — the same envelope OUR `fn_callReserv` consumes (`ara1001l.js:1560,1577-1579`) and OUR parser validates all four containers (`parsers.py:518-555`).
- **Seat-attr + cabin defaults.** srtgo `get_passenger_dict` sends `rqSeatAttCd1='015', dirSeatAttCd1='009', smkSeatAttCd1='000', etcSeatAttCd1='000', locSeatAttCd1=WINDOW_SEAT (000/012/013), psrmClCd1='2' special/'1' general` (`srt.py:192-197`) — identical to OUR `gds_rsv` seed (`ara0101v.js:129-133`) and OUR `psrmClCd 1=일반실/2=특실` mapping (`ara1001l.js:1431-1432`).
- **Static reserve fields.** srtgo `jrnyCnt='1', jrnyTpCd='11', jrnySqno1='001', stndFlg='N', grpDv='0', rtnDv='0'` (`srt.py:964-971`) match OUR seed values (`ara0101v.js:91-97`).

### ⚠️ Corrections / discrepancies

- **`act_19` is a phantom.** The "reservation NetFunnel gate `act_19`" claim in OUR older docs (`srt-app-api-library-spec-2026-07-09.md:358-360`; `full-api-analysis-2026-07-20.md:548`; label `netfunnel-act-19` in `safety.py:183`) has **NO basis in code** — grep for `act_19` across ALL decompiled artifacts (jadx Java+resources, smali, apktool JS, raw/base) returns **ZERO** hits. Only `act_10` exists. srtgo confirms reservation reuses `act_10` (`srt.py:987,603`). Already corrected in `docs/RELEASE_GAP_PLAN.md` (2026-07-21, `:254-256,471-482`) but still stale in the two analysis docs above.
- **`mblPhone` sent by srtgo, absent from OUR code.** srtgo puts `'mblPhone': mblPhone` in the reserve body (`srt.py:986`; populated only for standby, dropped for personal). `mblPhone` does not appear anywhere in our decompile (jadx/smali/apktool/raw all empty). Either a server-rendered JSP hidden input we cannot see, or an srtgo-empirical field.
- **`reserveType='11'` sent by srtgo (personal only), absent from OUR code.** srtgo adds `data['reserveType']='11'` when `jobId==PERSONAL` (`srt.py:990-991`). Not in any decompiled artifact. Same status as `mblPhone`.

### 🔀 Version drift

- srtgo posts a **trimmed ~34-field body**; OUR app posts the **full** `$('#rsvForm').serialize()` (dozens of hidden inputs). srtgo omits `arvDt1` (sends only `arvTm1`) though OUR `fn_moveRsv` sets `arvDt1=item.arvDt` (`ara1001l.js:1464`); omits all leg-2 fields (`jrnySqno2, trnGpCd2/trnGpNm2, dptRsStnCd2, arvRsStnCd2, dptTm2, back_dptDt1/back_dptTm1`), `totPrnbNm`, `seatAttNm1/2`, and per-index passenger seat-attr slots 2..5 — all present in OUR seed (`ara0101v.js:120-144`). Server tolerates the trimmed body.
- **Seat fields:** srtgo sends NO `seatNo1_*/scarNo1` fields (server auto-assigns). OUR app carries `seatNo1_1..9/seatNo2_*` and, on success, backfills `frm.seatNo1/frm.scarNo1` from `trainListMap` for the group payment handoff (`ara1001l.js:1604-1605`).
- **`trnGpCd` (unsuffixed)** hardcoded `'109'` in srtgo body (`srt.py:969`). In OUR v2.0.41 the unsuffixed `trnGpCd` is a **search**-ajax field, not a reserve field; the reserve field is `trnGpCd1`, which `fn_moveRsv` sets to `item.trnGpCd='300'` for SRT (`ara1001l.js:1440`). Both send `trnGpCd1='300'`; the extra `trnGpCd='109'` is an srtgo leftover the server ignores.
- **`get_passenger_dict` divergence:** srtgo only writes `*1`-suffixed seat-attr fields regardless of passenger count (`srt.py:192-197`), whereas the upstream SRT library writes them per index (`SRT/SRT/passenger.py:86-96`) and OUR app carries `...1` and `...2` slots (`ara0101v.js:129-141`). Internal to the two Python impls; both satisfy the server.

### 🆕 Newly-found hidden (srtgo missed)

- **OUR src client does not implement reservation at all.** `client.py` has no reserve/`arc05013` method (methods stop at `get_seat_page, get_fare, get_timetable` — `client.py:387-405`); `payloads.py` has no reservation body builder. Only the response PARSER exists (`parse_reservation_attempt_response`, `parsers.py:507-625`). So on OUR side reservation is parser-only — no request path — while srtgo is a full working reserve.
- **Group reserve `/arc/selectListArc06014_n.do`,** selected purely by `grpDv=='1'` (`ara1001l.js:1544`), `pnrNo` hard-set to `-1`, payment handoff to `/ard/selectListArd02018_n.do` (`ara1001l.js:1597-1605`). srtgo has neither.
- **`jobId '1103'` 시트맵예약** via the ARC0201C seat-select flow (`ara1001l.js:1436`). srtgo only implements 1101/1102.
- **`mutMrkVrfCd` (상호검증값):** required only for Korail-interop (KTX) reservations, fetched via `/ara/selectListAra10130_n.do` and routed through the native `fn_foKorailApp` bridge (`ara1001l.js:241,1334-1389`) — NOT the arc05013 path. A whole v2.0.41 reservation branch srtgo (SRT-only) has no analogue for.
- **S111 privacy leak (client behavior):** on `resultMap.msgCd=='S111'` the full serialized `rsvForm` (journey + passenger composition) is written to `localStorage['userReservation']` AND dumped via `console.log(param)` and raw `alert(param)` before redirecting to `memberShipLogin()` (`ara1001l.js:1565-1571`). Leftover production debug; srtgo does not replicate.
- **Two-phase rsvForm reuse:** after a successful arc05013 reserve, OUR app RE-TARGETS the same `document.forms['rsvForm']` to the payment page `/ard/selectListArd02017_n.do` (individual), backfilling `pnrNo, jrnySqno=1, JRNYLIST_KEY, arvDt/arvRsStnCd/arvTm, dlayAcptFlg, dptDt/dptRsStnCd/dptTm, jrnyTpCd, lumpStlTgtNo, proyStlTgtFlg, stlbTrnClsfCd, totSeatNum, trnGpCd, trnNo` from `reservListMap` (`ara1001l.js:1596-1626`). srtgo instead skips this and calls `get_reservations()` to locate the ticket by `pnrNo` (`srt.py:1008-1012`).

### OUR-version exact values

- Endpoint (individual): `{contextPath}/arc/selectListArc05013_n.do`; (group): `/arc/selectListArc06014_n.do` (`ara1001l.js:1544,1547`)
- jobId: default `'1101'` (개인예약); `'1102'` (예약대기) when `gnrmRsvPsbImg==IMAGE::grd_WF_Waiting_S.png`; `'1103'` (시트맵예약) on ARC0201C path (`ara1001l.js:1436,1445-1448`)
- Seed statics (`ara0101v.js:90-98`): `jrnyTpCd='11', jrnyCnt='1', grpDv='0', rtnDv='0', stndFlg='N', jrnySqno1='001'`; seed `trnGpCd1='109'` & `stlbTrnClsfCd1='05'` are OVERWRITTEN at reserve time by `fn_moveRsv` to `item.trnGpCd` (`'300'` SRT) and `item.stlbTrnClsfCd` (`'17'` SRT) (`ara1001l.js:1439-1440`)
- Seat-attr defaults (`ara0101v.js:129-134`): `smkSeatAttCd1='000', dirSeatAttCd1='009', locSeatAttCd1='000', rqSeatAttCd1='015', etcSeatAttCd1='000', seatAttNm1='일반/기본'`
- `psrmClCd1`: `'1'`=일반실 / `'2'`=특실 (`ara1001l.js:1431-1432`)
- Train fields set by `fn_moveRsv` (`ara1001l.js:1453-1468`): `psrmClCd1, dptStnConsOrdr1, arvStnConsOrdr1, dptStnRunOrdr1, arvStnRunOrdr1, runDt1, trnNo1 (via lfn_getTrNoData), dptDt1, dptTm1, arvDt1, arvTm1, dptRsStnCd1, arvRsStnCd1`
- NetFunnel: `sid='service_1', aid='act_10'` (`netfunnel.js:16-17`); `NetFUNNEL.BEGIN` commented out in `fn_callReserv` (`ara1001l.js:1734-1740`)
- `gds_rsv/rsvForm` is a shared hidden-input bag: `lfn_setRsv(obj)` does `$('#'+key).val(obj[key])`, `lfn_getRsv(key)=$('#'+key).val()` (`main.html:549-567`); the reserve POST = `$('#rsvForm').serialize()` of every named hidden input.

### ❓ Disputed / low-confidence

- **Provenance note (not an error):** `fn_moveRsv` assigns `trnGpCd1=item.trnGpCd` and `stlbTrnClsfCd1=item.stlbTrnClsfCd` from **runtime** search-result data (`ara1001l.js:1439-1440`), NOT literals. The `300/17` SRT values appear only as seed comments (`ara0101v.js:85,95,98`) and srtgo hardcodes (`srt.py:968,972`). The value-match is comment/srtgo-inferred, not literal in `fn_moveRsv`.
- **Citation offset (`mutMrkVrfCd`):** the request URL is at `ara1001l.js:229`, not `:241`; line 241 is where `mutMrkVrfCd` is EXTRACTED from the response. Substance correct.
- **Scope note (jobId default):** `fn_moveRsv`'s `1101`-default/`1102`-for-waiting logic (`ara1001l.js:1445-1448`) only runs in the ARC0102C branch (guard at `:1437`); the ARC0201C path sets `1103` first (`:1436`). "default 1101" is path-scoped.
- **Seed-coverage note:** srtgo's `WINDOW_SEAT` yields `000/012/013` (`srt.py:86`); OUR seed carries only the default `locSeatAttCd1='000'` (`ara0101v.js:131`). The `012/013` variants are runtime-set, so "identical to OUR seed defaults" holds only for the `000` default.

---

## 3. Payment

### ✅ Confirmed

- **WebView payment-ENTRY route matches.** srtgo's ref doc characterizes the app's WebView payment as `/ard/selectListArd02017_n.do` (individual) and `/ard/selectListArd02018_n.do` (group) [`ref-srtgo_plus.md:394`]. OUR app does exactly this: `ara1001l.js:1608` sets `frm.action=contextPath+'/ard/selectListArd02017_n.do'` (individual), `:1599` sets `'/ard/selectListArd02018_n.do'` (group), then submits the form as a full-page WebView navigation. Both sides agree the real in-app payment path is the ard02017/18 WebView page.
- srtgo's own field-list header confirms these are "plain card fields" posted **outside** the WebView (`srt.py:1184-1216`); nothing in OUR app contradicts that srtgo does this against the server — but it is **NOT** a path v2.0.41 exercises (see corrections).
- **PG/keypad/FIDO security stack** that srtgo's doc says gates ard02017/18 is really present: RaonSecure FIDO (smali `com/raonsecure`, `com/raon/fido`; host `fido.srail.co.kr` in dex strings), TransKey SEED secure keypad (smali `com/softsecurity/transkey`), AppGuard/appiron (`assets/appiron`, `iron.srail.co.kr`).

### ⚠️ Corrections / discrepancies

- **CENTRAL DISCREPANCY: srtgo's payment endpoint `/ata/selectListAta09036_n.do` (`srt.py:99`) DOES NOT EXIST in v2.0.41.** 0 occurrences of `ata09036`/`09036`/`selectListAta09036` in: `base.apk` `classes.dex` (strings scan = 0), apktool smali (0), jadx Java (0), and all bundled web assets (0). It appears ONLY in our own docs (`RELEASE_GAP_PLAN.md`, `ref-srtgo_plus.md`). srtgo pays via a JSON endpoint our app never references.
- **srtgo's card fields are all absent** from OUR app: `stlCrCrdNo1, vanPwd1, crdVlidTrm1, athnVal1, athnDvCd1, ismtMnthNum1, stlMnsCd1, crdInpWayCd1` (`srt.py:1190-1204`) = 0 hits across classes.dex/smali/jadx/JS. OUR app has no plain-card-field JSON payment code at all.
- **OUR own docs overreach:** `RELEASE_GAP_PLAN.md:~160` asserts the native app path calls `ata09036`. This is **unsupported** by our decompiled code — `classes.dex` has zero references to `ata09036` or any card field. For v2.0.41 the original "ard02017/18 WebView/PG/keypad/FIDO-blocked" conclusion is the correct description; `ata09036` is not an in-app fact for our version.
- **Answer to the critical question:** **NO** — from OUR v2.0.41 code we CANNOT confirm Ata09036 exists or is reachable without WebView/PG/keypad/FIDO. It is entirely absent. Its "reachability" rests only on srtgo being a working impl against the live server (an external/server-side fact). So for OUR app "WebView/PG-blocked" is right; "payment resolved via ata09036" is right only as a statement about srtgo/the server.
- **Host/path drift within payment:** srtgo posts to bare-path `https://app.srail.or.kr:443/ata/...` (`srt.py:88-99`). OUR neo API endpoints carry a `/neo/` context path on `app.srail.co.kr` (dex strings: `https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do`, `/neo/main/main.do`). srtgo's bare `/ata/`,`/ard/` paths do not match our `/neo/`-prefixed surface.

### 🔀 Version drift

- **Payment endpoint surface differs by client/version:** srtgo targets a mobile-JSON `ata09036` card-charge endpoint (`srt.py:99`) with Korail-flavored constants (`cgPsId='korail', ctlDvCd/strJobId='3102', trnGpCd='300'`, `srt.py:1197-1212`); OUR v2.0.41 drives a WebView server-rendered page via ard02017/18 (`ara1001l.js:1599,1608`). srtgo's ata09036 is likely a legacy or different-client endpoint not wired into v2.0.41 client code.
- **Host + context-path drift:** srtgo `https://app.srail.or.kr:443` no context prefix (`srt.py:88`); OUR v2.0.41 uses `app.srail.co.kr/neo/...` for neo API plus `app.srail.or.kr` for main. Whichever host serves ard02017/18 is injected at runtime via `contextPath`, not statically defined in bundled JS.

### 🆕 Newly-found hidden (srtgo missed)

- **`/ata/selectListAta01032_n.do`** — a payment-related WebView sub-page srtgo has no equivalent for. Invoked via jQuery Mobile `changePage` (`arc0102c.js:34`) from the "결제 가능 카드사" / discount button (`btn_dcnt`, `arc0102c.js:33`), data `pnrNo=${commandMap.pnrNo}` (`arc0102c.js:35`). This is the ONLY "Ata####" payment endpoint actually present in v2.0.41 — and it is **Ata01032, not Ata09036**.
- **Group payment entry ard02018** with fields srtgo never models: `pnrNo=-1, rcvdAmt=resultMap.totRcvdAmt, tmpJobSqno1=resultMap.tmpJobSqno1, tmpJobSqno2=0, seatNo1=trainListMap.seatNo, scarNo1=trainListMap.scarNo` (`ara1001l.js:1599-1605`).
- **The full WebView payment-security stack** srtgo abstracts away is bundled and gates ard02017/18: TransKey SEED (`com/softsecurity/transkey`), RaonSecure FIDO + OMS ASM (`com/raon/fido`, `com/raonsecure`; `fido.srail.co.kr`), AppGuard/appiron (`assets/appiron`, `iron.srail.co.kr/authCheck.call`). srtgo's plain-HTTP ata09036 bypasses all of this — precisely why it is not the v2.0.41 in-app route.
- **`arc0102c.js`** is a dedicated payment-step client page (card-company selection UI, `form_onload/setEvent`) with no counterpart in srtgo's pure-HTTP model.

### OUR-version exact values

- Payment entry (individual): full-page POST of form `rsvForm` to `contextPath+'/ard/selectListArd02017_n.do'` with `frm.pnrNo=reservListMap.pnrNo` (`ara1001l.js:1596,1608-1609`)
- Payment entry (group): POST to `contextPath+'/ard/selectListArd02018_n.do'` with `pnrNo=-1, rcvdAmt=resultMap.totRcvdAmt, tmpJobSqno1=resultMap.tmpJobSqno1, tmpJobSqno2=0, seatNo1=trainListMap.seatNo, scarNo1=trainListMap.scarNo` (`ara1001l.js:1599-1605`)
- Shared payment-entry form fields (`ara1001l.js:1611-1626`): `jrnySqno=1, JRNYLIST_KEY, arvDt, arvRsStnCd, arvTm, dlayAcptFlg, dptDt, dptRsStnCd, dptTm, jrnyTpCd (14=transfer/11=direct), lumpStlTgtNo, proyStlTgtFlg, stlbTrnClsfCd, totSeatNum, trnGpCd, trnNo`
- Payable-card-company / discount page: `contextPath+'/ata/selectListAta01032_n.do'`, data `pnrNo=${commandMap.pnrNo}` (`arc0102c.js:34-35`)
- Hosts in v2.0.41 bundle: `app.srail.co.kr/neo/` (neo API), `app.srail.or.kr` (main), `fido.srail.co.kr` (FIDO), `iron.srail.co.kr` (AppGuard)
- **Ata09036 and card fields ABSENT** — 0 occurrences in classes.dex, smali, jadx, bundled JS.

### ❓ Disputed / low-confidence

- **Misattributed submit-line:** `confirmed[0]`/sourceRefs cite `frm.submit at ara1001l.js:1645` as the submit that navigates the ard02017/18-actioned form. This is wrong: line 1645 submits `document.forms['passDetailPayStepFrm']` (set at 1644) — a **different** form from `rsvForm` (line 1596) that receives the ard02017/18 action at 1599/1608. The `rsvForm`'s own submit runs through `fn_gotoRsvPage` (referenced at 1629/1633) which is **not defined in any bundled offline JS** (grep = only the two call-sites, zero definition); `rsvForm` is otherwise only `.serialize()`'d at `:1550`. So "then submits the form at :1645" is not verifiable as stated. The higher-level conclusion (ard02017/18 is the v2.0.41 WebView payment entry, action assigned at 1599/1608) stands. `RELEASE_GAP_PLAN.md:235` carries the same imprecise `1642-1646` citation.
- **Host-location labels imprecise (substance unaffected, all hosts DO exist in bundle):** `iron.srail.co.kr/authCheck.call` lives in `analysis/raw/base/resources.arsc` and `apktool/res/values/strings.xml`, NOT dex; `app.srail.co.kr/neo/main/main.do` is in `apktool/assets/dev.html`; the full path `app.srail.or.kr/main/main.do` is in `apktool/assets/offline/sub/error.html`. Only bare `app.srail.or.kr` (classes.dex + `SRWebActivity.smali`), `app.srail.co.kr/neo/atc/selectListAtc14016_n.do`, `app.srail.co.kr/neo/common/rest/JongURi/view.do`, and `fido.srail.co.kr` are genuine classes.dex strings.
- srtgo side re-confirmed verbatim: `SRT_MOBILE` base `srt.py:88`, payment endpoint `srt.py:99`, card fields `srt.py:1190-1212`, POST `:1218`. No correction to srtgo side.

---

## 4. Cancel / Refund

### ✅ Confirmed

- **Architecture match.** srtgo's mobile-JSON `_n.do` surface is real in our app. OUR WebView loads these endpoints from host base `https://app.srail.co.kr/neo/` (`SRForegroundDialogActivity$a.smali:47` = `.../neo/atc/selectListAtc14016_n.do`), the same `_n.do` family srtgo posts to (`srt.py:88,95`). So the cancel/refund `_n.do` pages are served at RUNTIME from this host — consistent with why they are not bundled.
- **Cancel family confirmed.** The `/ard/selectListArd02xxx_n.do` series srtgo's cancel (`Ard02045`, `srt.py:97`) belongs to exists in our app — Ard02017 (개인) and Ard02018 (단체) reserve-result actions at `ara1001l.js:1608` and `:1599`, both posting `frm.pnrNo.value` (`:1609,:1600`). srtgo's ticket_info Ard02019 (`srt.py:96`) is the adjacent number in the same series.
- **Cancel param `jrnyCnt="1"`** confirmed: OUR app hard-codes `"jrnyCnt":"1"` at `ara0101v.js:92` (여정건수), matching srtgo cancel body `{"pnrNo":..., "jrnyCnt":"1", "rsvChgTno":"0"}` (`srt.py:1138`).
- **`pnrNo` present natively and in JS:** `webview/b.java:651-652` (`cVar2.get("pnrNo")`), `b.smali:145` (`const-string "pnrNo"`), reserve form `ara1001l.js:1609` — matches srtgo (`srt.py:1138,1199`).
- **Refund input vocabulary confirmed in NATIVE code.** The exact fields srtgo posts to refund (`srt.py:1243-1248`: `saleDt/saleWctNo/saleSqno/tkRetPwd/psgNm`) are all extracted by OUR native offline-ticket adapter `webview/b.java:606-652` and `b.smali:145-185`: `saleWctNo`(`b.smali:185`), `saleDt`(`:177`), `saleSqno`(`:169`), `retPwd`(`:161`), `buyPsNm`(`:153`/psgNm), `pnrNo`(`:145`). This is the data feeding a refund.
- **Refund pre-info family confirmed.** srtgo refund pre-info `Atc14087` (`srt.py:100`) and refund `Atc02063` (`srt.py:102`) share the `/atc/...` family present in our app as ticket-list `Atc14016` (`ticketList.html:405`, `SRForegroundDialogActivity$a.smali:47`) and `Atc14017` (`SRWebActivity.smali:4257`).

### ⚠️ Corrections / discrepancies

- **Re-confirmed absence (our static bundle proves none of it).** The three cancel/refund endpoints are DEFINITIVELY ABSENT from v2.0.41 — **0 hits across all 21,673 files** even grepping the exact paths: `selectListArd02045`=0, `getListAtc14087`=0, `selectListAtc02063`=0. These are runtime server-rendered WebView pages, never bundled. **✅ Resolution note (2026-07-25):** this absence is unchanged and still correct — but the missing evidence was obtained live for **cancel only**. `selectListArd02045` with `pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"` released a real unpaid hold on the live server (`strResult=SUCC`, `msgCd=IRG000000`, `msgTxt="정상처리되었습니다"`), which also settles the two bullets below for cancel: `rsvChgTno="0"` was accepted on the wire, and `jrnyCnt="1"` was accepted for a single-journey hold (multi-leg untested). **✅ Resolution note (2026-07-26):** `getListAtc14087` and `selectListAtc02063` were then exercised too, and the same split applies — still 0-hit in the bundle, now confirmed live. Step 1 answered a non-existent PNR with `msgCd=WRT300005` / "조회자료가 없습니다." and then returned a real ticket's identity; step 2 refunded it (`strResult=SUCC`, `msgCd=IRT200277`) with srtgo's `pnr_no`/`cnc_dmn_cont`/`saleDt`/`saleWctNo`/`saleSqno`/`tkRetPwd`/`psgNm` body, and the account was empty afterwards.
- **Cancel param `rsvChgTno="0"`** (srtgo `srt.py:1138`) is ABSENT from our app (0 files). Cannot corroborate from static assets; would appear only at runtime.
- **Refund step-2 underscore params `pnr_no` and `cnc_dmn_cont`** (srtgo `srt.py:1241-1242`) are ABSENT (0 files). OUR native store uses camelCase `pnrNo` (`b.smali:145`), never the underscore form — the underscore style is anomalous vs the rest of the API and unverifiable from our bundle.
- **Refund reason literal `"승차권 환불로 취소"`** (srtgo `srt.py:1242`) is ABSENT (0 files). OUR `commCode.js:1423-1471` has refund STATUS codes (`반환접수신청/접수반환완료/반환/로칼반환`) but not that exact client-supplied demand-reason string.

### 🔀 Version drift

- **Refund field-name prefix drift:** srtgo's `reserve_info` (getListAtc14087) returns `ogtk`-prefixed fields and remaps them — `ogtkSaleDt/ogtkSaleWctNo/ogtkSaleSqno/ogtkRetPwd` (`srt.py:1243-1246`), posting the password as `tkRetPwd`. OUR v2.0.41 offline store uses the BARE forms `saleDt/saleWctNo/saleSqno/retPwd` (`b.java:639-646`, `b.smali:161-185`) — no `ogtk`/`tk` prefix. The prefix appears specific to the atc14087 response shape.
- **Host drift:** srtgo `https://app.srail.or.kr:443` (`srt.py:88`); OUR app WebView loads the same `_n.do` pages from `https://app.srail.co.kr/neo/` (`SRForegroundDialogActivity$a.smali:47`).

### 🆕 Newly-found hidden (srtgo missed)

- **OUR app stores ALL refund-relevant ticket data OFFLINE** in SharedPreferences key `ticketListOffline` (`b.java:613`), parsed by a native BaseAdapter (`webview/b.java f()`), whereas srtgo fetches it live via reserve_info. Cached fields include `pbpAcepTgtFlg` (`b.java:657`) — a refund/standby eligibility flag srtgo never references.
- **Individual vs group split:** `Ard02017` for 개인 (pnrNo only, `ara1001l.js:1608-1609`) and `Ard02018` for 단체 (extra `tmpJobSqno1/tmpJobSqno2/seatNo1/scarNo1/rcvdAmt`, `ara1001l.js:1599-1605`). srtgo has no group path; it only reserves via arc05013 (`srt.py:94`).
- **Second ticket-list variant `Atc14017`** loaded natively (`SRWebActivity.smali:4257`) alongside `Atc14016`; srtgo only knows Atc14016 (`srt.py:95`).

### OUR-version exact values

- Cancel endpoint value: NONE bundled (absent). Runtime host base = `https://app.srail.co.kr/neo/` (`SRForegroundDialogActivity$a.smali:47`)
- `jrnyCnt = "1"` (`ara0101v.js:92`) — matches srtgo cancel value
- Refund/ticket field names stored locally (un-prefixed camelCase): `pnrNo, buyPsNm, retPwd, saleSqno, saleDt, saleWctNo` (`b.smali:145,153,161,169,177,185`)
- SharedPreferences cache key = `ticketListOffline` (`b.java:613`)
- Reserve family present: reserve `Arc05013`(개인) + `Arc06014`; reserve-result `Ard02017`(개인)/`Ard02018`(단체); ticket list `Atc14016`/`Atc14017`. Cancel `Ard02045`, refund `Atc14087`/`Atc02063`, ticket_info `Ard02019`, standby `Ata01135`, payment `Ata09036` = **all ABSENT (runtime-only)**.

### ❓ Disputed / low-confidence

- **Swapped endpoint→line mapping in `confirmed[]` (INTERNAL inconsistency only).** The confirmed bullet as originally worded implied `Ard02017=1599, Ard02018=1608`. **ACTUAL code:** `ara1001l.js:1599` = `/ard/selectListArd02018_n.do` (단체/group), `ara1001l.js:1608` = `/ard/selectListArd02017_n.do` (개인/individual). i.e. **Ard02018=1599, Ard02017=1608** — corrected in the ✅ list above. The finding's own sourceRefs and newHidden state the correct mapping; only the one confirmed bullet transposed them. Substance unaffected — both endpoints exist and both post `frm.pnrNo.value` (1600, 1609).
- **Nuance on "both post `frm.pnrNo.value`":** literally true, but the GROUP path (Ard02018, line 1600) posts `frm.pnrNo.value = -1` — a placeholder, not a real reservation number. Only the individual path (Ard02017, line 1609) posts a real `pnrNo` (`reservListMap.pnrNo`). So the group reserve-result is NOT direct evidence of a pnrNo-keyed cancel/refund body.
- **Naming imprecision:** `reserve_info getListAtc14087` uses the `getList-` prefix and has **NO `_n` suffix**, unlike `selectListAtc14016_n.do`/`selectListAtc02063_n.do`. It shares the `/atc/` path but not the `selectList...._n.do` convention. Existence/inference unaffected; only the "family" wording is loose.

---

## 5. Uncovered hidden capabilities (group / seat-map / native secrets)

### ✅ Confirmed

- **GROUP RESERVE (arc06014) exists and is srtgo-uncovered.** OUR app branches to `/arc/selectListArc06014_n.do` purely on `grpDv=='1'` (`ara1001l.js:1542-1547`); srtgo hardcodes `grpDv:'0'` (`srt.py:970`), so it only ever hits arc05013. srtgo's own doc admits arc06014 not implemented (`ref-srtgo_plus.md:144`).
- **TICKET CHANGE (변경) is genuinely uncovered by both.** srtgo has no change method — its only "change" token is the reserve-time option `isAgreeClassChange→psrmClChgFlg` (`srt.py:1044`), which is "accept seat-class substitution", not ticket re-issue. OUR decompiled app likewise contains no change endpoint (grep of `analysis/apktool` + `analysis/jadx` yields only the 14 reservation-flow `*_n.do` endpoints).
- **DESIGNATED SEAT SELECTION is uncovered by srtgo.** srtgo never sends physical seat fields; forces auto-assign defaults `rqSeatAttCd1:'015', dirSeatAttCd1:'009', locSeatAttCd1` window-only (`srt.py:189-196`). OUR app implements a real seat-pick: `popCallback` writes `seatNo1_1..N, scarNo1, scarGridcnt1` (and `scarNo2/scarGridcnt2` for return) into rsvForm before posting arc05013/arc06014 (`ara0101v.js:866-882`).
- **Individual arc05013 params match OUR schema:** `jrnyTpCd '11', stndFlg 'N', jrnySqno1, trnGpCd1 '300', psrmClCd1, psgTpCd*/psgInfoPerPrnb*, totPrnb, psgGridcnt` (srtgo `srt.py:962-997`) align with `fn_validChk` and the seat-option setter (`ara1001l.js:1652-1697`; `ara0101v.js:770-779`).
- **srtgo `RESERVE_JOBID PERSONAL=1101/STANDBY=1102`** (`srt.py:30-33`) consistent with OUR jobId-driven reserve (`ara1001l.js:1652` reads jobId as first required field; both individual and standby POST to the same arc05013 endpoint).

### ⚠️ Corrections / discrepancies

- **`arc02011` DOES NOT EXIST in v2.0.41 — anywhere.** Exhaustive grep across `analysis/apktool` (JS, smali, res), `analysis/jadx`, `analysis/raw`, `analysis/splits` returns ZERO hits for `02011_n`/`arc02011` (the only `02011` match is an incidental substring in the AESFastEngine T-table constant, `jadx/.../AESFastEngine.java:45`). The real seat endpoint is **arc02012** (`/arc/selectListArc02012_n.do`), which returns an **HTML seat page, NOT a JSON "seat-inventory" feed**. OUR own docs (`RELEASE_GAP_PLAN.md`, `ref-srtgo_plus.md`) repeatedly call the deferred schema "arc02011 seat-inventory JSON" — that identifier is a **phantom** for this version and should read arc02012 (HTML). This corrects OUR analysis, not srtgo (which covers neither).
- **The "physical-seat inventory JSON" schema our docs treat as a blocked capture target is mis-modelled.** Statically, arc02012 is a server-rendered page reached via `pagecontainer('change')` and the ONLY machine-readable output is the `popCallback` tuple `{scarSeatNo:'2,7,10', scarSeatNm:'1B,2C,3B', scarNo:1}` (`ara0101v.js:868`). There is no evidence in the APK of a separate JSON inventory endpoint — the full car/seat grid is inside the arc02012 HTML/DOM and cannot be typed from static assets.

### 🔀 Version drift

- **`ticket_info` code differs across three references AND our app:** srtgo maps `ticket_info→/ard/selectListArd02019_n.do` (`srt.py:96`); the upstream SRT lib maps it to `/ard/selectListArd02017_n.do` (`SRT/SRT/constants.py:63`); OUR v2.0.41 uses `/ard/selectListArd02017_n.do` as the individual payment/detail handoff (`ara1001l.js:1608`). srtgo drifted to 02019 while OUR app + SRT lib stay on 02017.
- **Initial-route drift:** srtgo/SRT hit main + apb01080 login only; OUR app additionally wires an alternate landing route `/atc/selectListAtc14017_n.do` (a second ticket-list variant, distinct from srtgo's `tickets=atc14016`) triggered natively when `btnNo=='2'` (`SRWebActivity.java:1592`). srtgo has no atc14017 (`srt.py:88-102` lists only atc14016).

### 🆕 Newly-found hidden (srtgo missed)

- **GROUP SEARCH `/ara/selectListAra10082_n.do`** — srtgo only knows individual `/ara/selectListAra10007_n.do` (`srt.py:93`). OUR app selects Ara10082 whenever `grpDv=='1'`, in BOTH initial search and scroll-paging re-query (`ara1001l.js:175-181` and `1822-1829`).
- **GROUP PAYMENT-ENTRY `/ard/selectListArd02018_n.do`,** structurally different from individual ard02017: group submits `pnrNo=-1 (hard), rcvdAmt=totRcvdAmt, tmpJobSqno1 (from reserve response), tmpJobSqno2=0, seatNo1=trainListMap.seatNo, scarNo1=trainListMap.scarNo` (`ara1001l.js:1597-1605`). srtgo has neither ard02018 nor this tmpJobSqno-based handoff.
- **GROUP business rules (hidden validation):** group requires `totPrnb >= 10` (`단체예약은 10매 이상`), group FORBIDS round-trip (`단체는 왕복 예약이 불가능`), and >9 pax MUST use group (`ara0101v.js:549-568`). `grpDv` default `'0'` (`ara0101v.js:93`), toggled at `:522`.
- **SEAT-DESIGNATION `/arc/selectListArc02012_n.do` with `reqCode` semantics decoded:** `9`=seat-designate one-way, `10`=round-trip outbound, `11`=round-trip done (`const.js:9-11` `POP_REQ_SEATSELECT_DPT_ONEWAY/GO_BACK/GO_BACK_DONE`; consumed at `ara1001l.js:1496-1520`). `trnGpCd` hard-coded `'300'` because seat pick is SRT-only. srtgo omits this endpoint.
- **Group reservation disables seat designation:** the seat-select affordance is gated by `grpDv != '1'` (`ara1001l.js:1101`), so group is auto-assign only — a rule neither srtgo nor OUR client models.
- **Extra reservation-flow endpoints srtgo lacks:** `ara10130` mutual-verification returning `mutMrkVrfCd` as `dsOutput0` (`ara1001l.js:227-242`), `ara12009` timetable detail (`ara1001l.js:1189`), `ara13010` fare/pricing detail (`ara1001l.js:1229`), `ata01032` discount detail GET with JSP EL `pnrNo=${commandMap.pnrNo}` (`arc0102c.js:33-37`). srtgo has none (`srt.py:88-102`).
- **Hardcoded Firebase/Google keys (NOT in our doc §7):** `google_api_key` and `google_crash_reporting_api_key` hold **one and the same** key (`strings.xml:171,174` — written here as the single placeholder `<SRT-APP-GOOGLE-API-KEY-REDACTED>`, and that they are equal is the finding); `sr_gcm_api_key` (`strings.xml:492`) is a **SECOND, DIFFERENT** Google API key, distinct from the first — it is `<SRT-APP-GCM-API-KEY-REDACTED>` here precisely so the two do not blur together; `google_app_id` (`:172`); `firebase_database_url https://<SRT-APP-FIREBASE-PROJECT-REDACTED>.firebaseio.com` (`:162`), `google_storage_bucket <SRT-APP-FIREBASE-PROJECT-REDACTED>.appspot.com` (`:176`) and `project_id` (`:469`), all three naming the same Firebase project. srtgo has no native layer. *(Values withheld — see the note at the top of this report.)*
- **Social-login app keys hardcoded:** `kakao_app_key` (`strings.xml:242`) and `facebook_app_id` (`:158`). One GCM/FCM sender/project number is stored three times over, as `gcm_defaultSenderId`, `google_project_id` and `sr_gcm_id` (`:164,175,493`) — all three the same value, which is why one placeholder `<SRT-APP-GCM-SENDER-ID-REDACTED>` stands for all of them. *(Values withheld — see the note at the top of this report.)*
- **Device fingerprinting for H2O push registration:** `android_id` is re-read, `:` and `-` stripped and upper-cased, used as a pseudo-`macAddress` alongside the real WiFi MAC (`getMacAddress` on SDK≤22, else `/sys wlan0` read) and the IPv4 address (`SRWebActivity.java:1841-1851`). Feeds the proprietary `push.srail.co.kr:3101` H2O SmartBroker channel (`b6/a.java`). Separate from the `deviceId=android_id` already noted for main.do.

### OUR-version exact values

- Group reserve: POST `{contextPath}/arc/selectListArc06014_n.do` (by `grpDv=='1'`), body = full `#rsvForm` serialize (`ara1001l.js:1544,1550`)
- Group search: POST `{contextPath}/ara/selectListAra10082_n.do` (`ara1001l.js:177,1825`)
- Group payment-entry: POST `{contextPath}/ard/selectListArd02018_n.do` with `pnrNo=-1, tmpJobSqno2=0, tmpJobSqno1/seatNo1/scarNo1` from reserve response (`ara1001l.js:1599-1605`)
- Seat-map: POST `{contextPath}/arc/selectListArc02012_n.do`; `trnGpCd` hard `'300'`; `reqCode` 9=oneway/10=round-out/11=round-done; params `runDt, dptDt, trnNo, dptTm, dptRsStnCd, arvRsStnCd, psrmClCd, seatAttCd, dptStnRunOrdr, arvStnRunOrdr, choiceSeatCount` (`ara1001l.js:1498-1520`)
- Seat-pick rsvForm fields: `seatNo1_1..seatNo1_N, scarNo1, scarGridcnt1, scarNo2, scarGridcnt2` (`ara0101v.js:870-879`)
- `grpDv`: 0=individual, 1=group; group threshold `totPrnb>=10`; group round-trip forbidden (`ara0101v.js:93,549-568`)
- Individual payment-entry: `/ard/selectListArd02017_n.do` with `pnrNo=reservListMap.pnrNo` (`ara1001l.js:1608-1609`)
- Firebase/Google, values withheld — the entries are `api_key`, `sr_gcm_api_key`, `app_id`, the sender number and the project id, at `strings.xml:171,492,172,164,469` in that order
- `kakao_app_key` and `facebook_app_id`, values withheld (`strings.xml:242,158`)
- **Full bundled endpoint inventory = EXACTLY 14 `*_n.do`:** apb01080, ara10007, ara10082, ara10130, ara12009, ara13010, arc02012, arc05013, arc06014, ard02017, ard02018, ata01032, atc14016, atc14017.

### ❓ Disputed / low-confidence

- **Minor precision (not material):** `ara10130` returns `mutMrkVrfCd` nested as `data.outDataSets.dsOutput0` (then `dsOutput0.mutMrkVrfCd`), verified `ara1001l.js:231-241` — one level deeper than "bare object dsOutput0". Field/value right.
- **Minor precision (not material):** the 14-endpoint inventory is EXACTLY 14 and TRUE, but the split is: 11 in `offline/js` modules; `apb01080` + `atc14016` appear only in `offline/sub/*.html`; **`atc14017` appears ONLY in native decompiled Java** (`SRWebActivity.java:1592`), never in any bundled JS/HTML asset — so "bundled" is loose for atc14017.

---

## 6. Transport & Auth

### ✅ Confirmed

- **NetFunnel `act_10`.** srtgo hardcodes `sid=service_1 / aid=act_10` (`srt.py:603`, OP_CODE `srt.py:505-509`). OUR `netfunnel.js:16-17` (`TS_SERVICE_ID='service_1'`, `TS_ACTION_ID='act_10'`) and both call sites `ara0101v.js:652` & `ara1001l.js:1737` (commented `SetService("service_1","act_10")`). OUR client mirrors it: `netfunnel.py:18-23` & `safety.py:163-164`.
- **NetFunnel opcodes.** srtgo `5101/5002/5004` (`srt.py:505-509`). OUR `netfunnel.js:84` `RTYPE_GET_TID_CHK_ENTER=5101, RTYPE_CHK_ENTER=5002, RTYPE_SET_COMPLETE=5004`; success codes `kSuccess=200/kContinue=201/kTsErrorAComplete=502` match srtgo `WAIT_STATUS_PASS/FAIL/ALREADY_COMPLETED` (`srt.py:501-503`).
- **NetFunnel `nfid=0`.** srtgo `srt.py:596`. OUR `netfunnel.js` initializes `this.id=0` (used as `&nfid=`).
- **NetFunnel host/transport.** srtgo GET `https://nf.letskorail.com/ts.wseq` (`srt.py:583`). OUR `netfunnel.js:11-15` `TS_HOST='nf.letskorail.com', TS_PORT=443, TS_PROTO='https', TS_QUERY='ts.wseq'`; `config.py:11 NETFUNNEL_ORIGIN='https://nf.letskorail.com:443'`.
- **Plaintext password despite `hmpgPwdCphd` (cipher) suffix.** srtgo sends `srt_pw` verbatim in `hmpgPwdCphd` (`srt.py:709`). OUR `session.py:26` sends password verbatim. APK shows NO client-side login encryption (no RSA/CryptoJS/SHA for login); `main.html:727` `hmpgPwdCphd` is a plain hidden input populated by `$("#key").val(obj[key])` (`main.html:549-554`). Secure keypad returns plaintext `plainData` to JS before submit (`SRWebActivity.java:2352-2390`).
- **Login endpoint path.** srtgo `/apb/selectListApb01080_n.do` (`srt.py:91`). OUR `main.html:721` `<form action="../apb/selectListApb01080_n.do" method=POST>`; `session.py:19` POST same; `safety.py:59` allowlists it.
- **UA suffix format (no space before suffix).** srtgo UA ends `...Mobile Safari/537.36SRT-APP-Android V.2.0.38` with NO space (`srt.py:20-23`). OUR `SRWebActivity.java:2642-2645` builds `getUserAgentString() + "SRT-APP-Android V." + versionName`, concatenated directly onto the WebView UA (ends `Safari/537.36`) with no separator → `537.36SRT-APP-Android V.2.0.41`.
- **`X-Requested-With=kr.co.srail.newapp` for NetFunnel** = the app package. srtgo NetFunnel DEFAULT_HEADERS (`srt.py:521`). OUR `AndroidManifest.xml:2` `package="kr.co.srail.newapp"`.
- **No certificate pinning.** OUR APK: zero `networkSecurityConfig` (grep = 0), `android:usesCleartextTraffic="true"` (`AndroidManifest.xml:53`), and `onReceivedSslError` shows a user "proceed" dialog (`SRWebActivity.java:415-421`) rather than pinning.
- **`act_19` does NOT exist as a separate reservation gate — reserve reuses `act_10`.** srtgo `_reserve` injects `netfunnelKey=self._netfunnel.run()` (same act_10 helper, `srt.py:987/819`). OUR bundled assets contain ONLY act_10 (grep across apktool/assets: 3× act_10, 0× act_19).

### ⚠️ Corrections / discrepancies

- **UA extra-space drift (OUR client is the outlier).** Real app concatenates the suffix with NO space (`SRWebActivity.java:2645`) and srtgo matches (`srt.py:22`). BUT OUR `config.py` inserts a space (literal ends `Mobile Safari/537.36 ` then `SRT-APP-Android V.2.0.41` → `...537.36 SRT-APP-Android...`). `http.py` sends `config.user_agent` verbatim, so OUR wire UA has an extra space neither the app nor srtgo emits.
- **`deviceKey` value discrepancy.** srtgo hardcodes `deviceKey='-'` (`srt.py:704`); OUR `config.py:19` uses fixed `'0123456789ABCDEF'` (`session.py:27`). Real app uses a device-specific identifier (`Settings.Secure` ANDROID_ID and OnePass `GetDeviceID`). Both srtgo's `'-'` and our stub work because the server does not strictly validate `deviceKey` for login.
- **`act_19` assumption in OUR client is outdated.** `safety.py:183` `EXCLUDED_API_DOMAINS` still lists `netfunnel-act-19` and doc line 548 lists an `act_19 reservation gate`, but working srtgo proves reservation reuses the act_10 key (`srt.py:987`) and no act_19 exists (0 hits in APK). Harmless (reserve is excluded from our read-only client) but the premise is wrong.
- **Login form field-set/value discrepancy (both work → server lenient).** srtgo sends `auto=Y, check=Y, page=menu, login_referer=main.do, deviceKey=-`, no `ciUptYn/dupInfoVal` (`srt.py:700-710`). OUR `session.py:20-31` sends `auto='', check='', page='', login_referer='', deviceKey=fixed`, PLUS `ciUptYn='', dupInfoVal=''`. The bundled form (`main.html:722-727`) only has 6 fields; `deviceKey/page/customerYn` are added by the server-rendered login.do JS, absent from the APK.

### 🔀 Version drift

- **App version:** srtgo UA suffix `V.2.0.38` (`srt.py:22`); OUR app `V.2.0.41` (`apktool.yml:10-11` versionName 2.0.41 / versionCode 150) and OUR `config.py:8` uses `V.2.0.41`. Suffix is dynamic from `packageInfo.versionName` (`SRWebActivity.java:1772-1774`), so it drifts every release.
- **NetFunnel `js` param:** real bundled `netfunnel.js` emits `&js=yes` in every request builder; BUT srtgo (`srt.py:598`) AND OUR client (`netfunnel.py:22`, `safety.py:164`) both use `js=true`. Both accepted by the server, but the app's real value is `yes` not `true`.
- **Base UA (device/Chrome) is not app-controlled and differs everywhere:** srtgo Android 15 / SM-S912N / Chrome 136 (`srt.py:20-22`); OURS Android 14 / Pixel 7 / Chrome 126 (`config.py:5-9`); real app uses the runtime device WebView UA (`getUserAgentString()`, `SRWebActivity.java:2642`). Only the `SRT-APP-Android V.<ver>` suffix is guaranteed by the app.

### 🆕 Newly-found hidden (srtgo missed)

- **TWO distinct `X-Requested-With` values — srtgo captures only one.** The app's data/API POSTs use jQuery `$.ajax dataType:'json'` (`ara1001l.js:185-189, 1552-1556, 1833-1834`); jQuery auto-adds `X-Requested-With: XMLHttpRequest` for same-origin XHR. So API calls send `XMLHttpRequest` while NetFunnel script loads send the package name `kr.co.srail.newapp`. srtgo's main session omits `X-Requested-With` entirely (`srt.py:25-28`) and only sets the package name on NetFunnel (`srt.py:521`). OUR `http.py:188` correctly sends `X-Requested-With: XMLHttpRequest` on API POSTs — closer to the app than srtgo.
- **Accept header fidelity:** the app's jQuery JSON calls send `application/json, text/javascript, */*; q=0.01`. OUR `session.py:33` uses exactly that; srtgo uses only `application/json` (`srt.py:27`). OUR value is the more faithful one.
- **SSL-error bypass is available in-app (weaker than no-pin):** `onReceivedSslError` pops a 계속(proceed)/취소(cancel) dialog (`SRWebActivity.java:415-421`) letting a user override an invalid cert — srtgo/ref does not note this.
- **`main.do` carries a SEPARATE device identifier:** `/main/main.do?deviceId=<ANDROID_ID>` (`SRWebActivity.java:1582-1584`), distinct from login's `deviceKey`. OUR `client.py:92` passes `deviceId=config.device_key`; srtgo's main endpoint (`srt.py:90`) sends no deviceId at all.
- **Login `deviceKey`'s true source is native OnePass/FIDO:** `OnePassManager.GetDeviceID(this)` injected into WebView JS as `{key:'deviceId'}` (`SRWebActivity.java:2520-2523`) against `fido.srail.co.kr` (siteId `SIT02SR0000000000000`). srtgo (`'-'`) and we (stub) both replace this.
- **Client-side NetFunnel is DISABLED in this build:** `NetFUNNEL.BEGIN` is commented out and `netfunnel_callback()` is called directly (`ara1001l.js:1735-1748`, `ara0101v.js:651-655`), so the WebView sends no NetFunnel handshake for search — the act_10 gate is enforced live server-side only. srtgo reimplements the full `5101→5002→5004` handshake natively to satisfy that gate.

### OUR-version exact values

- `versionName = 2.0.41, versionCode = 150` (`apktool.yml:10-11`)
- UA suffix `SRT-APP-Android V.2.0.41` appended with NO space onto the device WebView UA (`SRWebActivity.java:2642-2645`)
- WebView / NetFunnel `X-Requested-With = kr.co.srail.newapp` (`AndroidManifest.xml:2`); API-POST `X-Requested-With = XMLHttpRequest` (jQuery, `ara1001l.js:185-189`)
- NetFunnel: `sid=service_1, aid=act_10`, opcodes `5101/5002/5004`, `nfid=0`, host `nf.letskorail.com:443`, query `ts.wseq`, `js=yes` (`netfunnel.js:11-17,84`; `this.id=0`)
- Login: POST `/apb/selectListApb01080_n.do` with `hmpgPwdCphd = PLAINTEXT` password; `deviceKey = device ANDROID_ID-derived / OnePass GetDeviceID` (our stub `0123456789ABCDEF`, srtgo `-`)
- Transport: HTTPS only, NO cert pinning, NO `network_security_config`, `android:usesCleartextTraffic=true` (`AndroidManifest.xml:53`); SSL errors user-bypassable (`SRWebActivity.java:415-421`)
- `main.do` device param: `/main/main.do?deviceId=<Settings.Secure.ANDROID_ID>` (`SRWebActivity.java:1582-1584`)

### ❓ Disputed / low-confidence

- **`deviceKey` source mis-citation (SRWebActivity.java:1845) — VERIFIED FALSE.** The correction attributed the login-form `deviceKey` to "Settings.Secure ANDROID_ID uppercased-hex (SRWebActivity.java:1845)". Actually line 1845's uppercased android_id is stored as `map.put("mac", upperCase)` (line 1853, logged `## macAddress:` at 1850) and returned to JS as the **MAC-address** value, NOT deviceKey. The bundled login form (`main.html:722-727`) has NO deviceKey field, so the login deviceKey's true source is set by the server-rendered login.do JS and is **not determinable from the APK**. The two device IDs that ARE in the APK are unrelated: `main.do?deviceId=` uses RAW android_id (`SRWebActivity.java:1582-1584`, not uppercased); `OnePassManager.GetDeviceID` is injected as a variable literally named `deviceId` not `deviceKey` (`2521-2523`). The core discrepancy (srtgo `'-'` vs our stub `0123456789ABCDEF` vs a real device value) stands; only the line-1845 provenance is wrong.
- **`X-Requested-With=kr.co.srail.newapp` for NetFunnel is an INFERENCE, not observed.** grep for `X-Requested-With`/`setRequestProperty` across decompiled `kr/co/srail/` = ZERO — the app never sets it in code. Presumed the Android WebView default package-name injection, but NetFunnel is DISABLED in this build so the WebView emits no NetFunnel request here at all. The package name IS confirmed (`AndroidManifest.xml:2`) and srtgo hardcodes it (`srt.py:521`); the "two distinct X-Requested-With values" claim is a reasonable jQuery/WebView-behavior inference, not statically provable.
- **Line-label drifts (substance confirmed):** the reserve/search netfunnelKey citation "`srt.py:987/819`" is off — `srt.py:987` IS reserve (posts to `reserve` at `:999`), but `srt.py:819` is the SEARCH request (posts to `search_schedule` at `:822`). Both call the same `self._netfunnel.run()` act_10 helper, so "reserve reuses act_10, no act_19" is CONFIRMED. UA extra-space split is at `config.py` lines 7-8 (not 8-9); `http.py` sends `config.user_agent` at line 40 (not `:41`). srtgo `login_referer` is the FULL url `https://app.srail.or.kr:443/main/main.do` (`srt.py:706`), not literally `main.do`; srtgo defines `main.do` (`srt.py:90`) but never GETs it — it is only the `login_referer` string.

---

## Net changes to our understanding

1. **The hidden mobile-JSON API is real and well-matched.** Login (Apb01080), search (Ara10007), reserve (Arc05013), tickets (Atc14016), and the NetFunnel `act_10` queue all match srtgo on host, path, field names, and response envelope. srtgo is a **correct model of the individual flow** for v2.0.41.
2. **Six endpoints are server-rendered and NOT in our bundle** (payment Ata09036, cancel Ard02045, refund Atc02063, standby-option Ata01135, reserve-info getListAtc14087, ticket-info Ard02019) — 0 hits across all 21,673 files. For v2.0.41 they are **attested only by srtgo's live runs**, not by our static code. This is the largest remaining verification gap. **✅ Resolution note (2026-07-25): one of the six is closed.** Cancel `Ard02045` was exercised against the live server in a reserve->cancel round trip (`SUCC`/`IRG000000`, single-journey one-adult hold), so it is now attested by a run of **ours** as well; it remains 0-hit in the bundle. **✅ Resolution note (2026-07-26): three more are closed.** Payment `Ata09036`, reserve-info `getListAtc14087` and refund `Atc02063` were exercised against the live server in a probe-then-real-round-trip (`SUCC`/`IRT000000` for the charge, `SUCC`/`IRT200277` for the refund, 7,500 KRW, one adult, refunded and confirmed gone). All three remain 0-hit in the bundle. Standby `Ata01135` and ticket-info `Ard02019` are untouched, and the gap stands for those two.
3. **`ata09036` is not the v2.0.41 in-app payment route.** v2.0.41 pays via the **ard02017/18 WebView page** gated by TransKey + RaonSecure FIDO + AppGuard. The only `Ata####` payment endpoint actually present is **Ata01032** (discount / payable-card-company page), not Ata09036. OUR `RELEASE_GAP_PLAN.md` overreach on this is corrected.
4. **srtgo misses a whole group / seat-map branch:** group search (Ara10082), group reserve (Arc06014), group payment (Ard02018), seat-map select (Arc02012), plus jobId `1103` (시트맵예약) and Korail-interop `mutMrkVrfCd` (Ara10130). Full bundled inventory = **exactly 14 `_n.do` endpoints**.
5. **srtgo misses the alternate host** `app.srail.co.kr/neo/` (and dev `devapp.srail.co.kr/neo/`) which serves the same `_n.do` JSON.
6. **Two of OUR own prior beliefs were phantoms and are now retired:** `act_19` reservation gate (only `act_10` exists) and `arc02011` seat-inventory JSON (the real endpoint is `arc02012`, and it returns HTML, not a JSON inventory feed).
7. **Two OUR-client fidelity bugs surfaced:** an **extra space** in the UA before `SRT-APP-Android` (`config.py:7-8`) that neither the app nor srtgo emits, and a stale `netfunnel-act-19` exclusion in `safety.py:183`.
8. **Native-layer secrets our doc §7 omitted:** two distinct Google/Firebase API keys, `google_app_id`, a `firebase_database_url` / `google_storage_bucket` / `project_id` trio naming one Firebase project, Kakao and Facebook app keys, and an android_id/MAC/IP fingerprint feeding `push.srail.co.kr:3101`. Field names and `strings.xml` lines are in §5; the values are withheld (see the note at the top of this report).

## Remaining open questions (need a live v2.0.41 capture)

1. **Can the request shapes for the six absent endpoints** (payment Ata09036, cancel Ard02045, refund Atc02063, standby Ata01135, reserve-info getListAtc14087, ticket-info Ard02019) be confirmed for v2.0.41? Absent from our decompile; only srtgo attests. **Biggest gap.** **✅ Answered for cancel (2026-07-25):** yes for `Ard02045` — the live server accepted `pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"` and released a real hold (`SUCC`/`IRG000000`) for our app version, in a single-journey one-adult round trip. Question 4 below (is `netfunnelKey` mandatory for `arc05013`?) is **not** answered: our reserve always sends an `act_10` key and the run therefore never tested omitting it. **✅ Also answered for payment, reserve-info and refund (2026-07-26):** yes for `Ata09036`, `getListAtc14087` and `Atc02063` — the live server accepted srtgo's shapes for all three, charging and then refunding a real 7,500 KRW ticket. Standby `Ata01135` and ticket-info `Ard02019` are still open.
2. `reserve_info` uses `getListAtc14087.do` — NO `_n` suffix, `getList-` prefix, `.do` GET-style servlet (`srt.py:100`), unlike the `selectList...._n.do` family. Different servlet lineage? Not in our decompile to cross-check.
3. **Are `mblPhone` and `reserveType` real hidden inputs** in the server-rendered JSP `#rsvForm`, or srtgo-only fields the server silently accepts? Unresolvable from our offline assets.
4. **Is `netfunnelKey` mandatory for `arc05013` reserve**, or only for search? OUR `fn_callReserv` has NO netfunnel call and `BEGIN` is commented; srtgo sends a fresh act_10 key defensively (`srt.py:987`). Whether the live server rejects reserve without it is unverified.
5. **Does the live 2.0.41 server still return `NET000001` on a missing `netfunnelKey` for search?** The bundled JS bypasses NetFunnel, so only the prior runtime spec attests the live gate.
6. **Do both hosts (`app.srail.or.kr` and `app.srail.co.kr/neo`) serve byte-identical `_n.do` JSON,** or is co.kr/neo a staging/OPR mirror? `dev.html` labels the co.kr/neo main as "OPR PAGE".
7. **Runtime cancel/refund param style:** does OUR app's runtime WebView post `rsvChgTno` and the underscore params `pnr_no`/`cnc_dmn_cont` as srtgo does, or the camelCase `pnrNo` seen locally? Where is the `ogtk`→bare field prefix stripped? Is the refund reason `"승차권 환불로 취소"` client-supplied or server-defaulted?
8. **Ticket-CHANGE (변경) flow** is entirely server-rendered — which domain/code does the app POST to? Requires live capture; srtgo lacks change too.
9. **`arc02012` request→response body** returns an HTML seat page, so the full per-car/per-seat availability grid is only in the DOM; needs live capture to type. The `{scarSeatNo,scarSeatNm,scarNo}` popCallback tuple is the ONLY structured output visible statically.
10. **`arc06014` group response shape** is only inferable from setter code (`resultMap.tmpJobSqno1, totRcvdAmt, trainListMap.seatNo/scarNo`, no pnrNo) — needs one live group reservation to confirm the envelope differs from arc05013's `reservListMap[0].pnrNo`.
11. **Does app.srail.or.kr enforce TLS/JA3(JA4) fingerprinting?** srtgo relies on `curl_cffi impersonate='chrome'` (`srt.py:653`); OUR client uses plain httpx with no impersonation (`http.py:37`). Not answerable from the APK; if the WAF fingerprints, our httpx client could be blocked while srtgo passes.
12. **Is any `deviceKey` accepted for ALL flows, or only login?** Both srtgo `'-'` and our stub work for login; the app supplies a real ANDROID_ID/OnePass id — untested elsewhere.
13. **Which of the two Google API keys** (`AIzaSyA2Qx...` vs `AIzaSyDDnq...`) is live/current for FCM vs Maps/crash? Both Android-restricted, low severity.
