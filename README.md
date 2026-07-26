# srt-mobile-api

This repository provides an installable read-only-by-default Python package for
the evidenced SRT Android app WebView API surface. Nothing is transmitted
without an explicit, per-category `MutationConsent` with `dry_run=False`: by
default the client transmits only login/read requests, and a mutation method
returns a redacted `MutationPreview` of the exact form that would be POSTed.

Five consent-gated mutation methods exist: `reserve`, `reserve_transfer`,
`cancel`, `pay_with_card` and `refund`, across **four** consent categories —
`reserve_transfer` is the 환승 half of `reserve` on the *same* endpoint, so it
rides the existing `reserve` category. All preview by default and all transmit
when given an explicit `dry_run=False` consent for their category. Each CATEGORY is live-enabled because a live run answered its own
wire format, and for nothing else:

| method | verified | server's answer |
| --- | --- | --- |
| `reserve` | 2026-07-25 | `SUCC` / `IRR000018` |
| `cancel` | 2026-07-25 | `SUCC` / `IRG000000` |
| `pay_with_card` | 2026-07-26 | `SUCC` / `IRT000000` |
| `refund` | 2026-07-26 | `SUCC` / `IRT200277` |

A live `reserve` creates a **real unpaid hold on a real account**, which the
caller then owns; a live `pay_with_card` **moves real money**; a live `refund`
really returns a ticket. The 2026-07-25 round trip covered one adult, one
journey, a general seat, one train, and left no trace of the reservation in the
ticket list. The 2026-07-26 round trip covered 수서→동탄 (`0551`→`0552`, the
shortest SRT hop), 2026-08-09, train 315, one adult, 7,500 KRW: paid, then
refunded, then confirmed gone from a separate session. Nothing broader is
claimed — see "Card payment" and "Refund" below for what those runs did *not*
settle. In particular the two reservation VARIANTS — standby (`jobId=1102`) and
the round trip (`rtnDv=1`) — are **bundle-evidenced and not live-verified**; see
"Reservation variants" below. A third variant, 단체 (group), was implemented and
then **removed on 2026-07-26** once a live probe showed what its endpoint
actually returns; see "단체 (group) booking: removed" below.

Which mutations may reach the network at all is enforced at the transport
layer, by two different mechanisms which are worth keeping distinct:

- the read-only send path refuses all four mutation routes **by allowlist** —
  they are deliberately not in `READ_ONLY_ROUTES`, so `assert_read_only_request`
  rejects them;
- `post_mutation_form`, the only method that can send a state-changing request,
  refuses every category outside `safety.SRT_LIVE_MUTATION_CATEGORIES`, which
  holds **exactly `{"reserve", "cancel", "payment", "refund"}`** — the four a
  live run has answered. A fifth is rejected however permissive the caller's
  consent is, and that refusal, not the presence or absence of a client method,
  is what holds the line. It separately refuses a `dry_run=True` consent, so a
  preview can never be transmitted either. `_send_mutation_request`, the
  function that actually calls `send`, re-asserts the same membership, the route
  allowlist and the route/category binding, so a consent for one category can
  never be aimed at another's route.
- separately, and stated on the request **body** rather than on the route,
  `assert_no_card_secrets` lets a PAN, card PIN, expiry or cardholder birthdate
  travel **only** as a `payment`. That guard mattered less while `payment` was
  shut; now that it is open it is the only thing keeping a hand-assembled card
  form off a read route, off the `reserve` and `cancel` routes, and out of the
  private send boundary under a non-payment category.

`reserve` and `cancel` were enabled together because they are the two halves of
one reversible operation: reserve creates an unpaid hold, cancel releases one
(from a hold object or a bare PNR string). Enabling reserve alone would mean a
crash mid-flow strands a real reservation with no programmatic way out. Opening
that gate was a decision about **recoverability, not evidence** — it is what
made the operator-run reserve->cancel round trip possible, and that round trip
has since been run twice (2026-07-25 and 2026-07-26, see below). `payment` and
`refund` were opened on the same principle a day later: a charge and its
reversal, verified as one round trip so nothing could be stranded paid. Adding a
**fifth** category would require live-verifying its own wire format first, which
is the only thing membership in that set has ever meant. The retained APK
specification and smoke tooling remain the evidence context for that package.

The reviewed safety boundary contains 25 routes on the read side, plus 4
mutation routes, one per consent category. It was 5 until 2026-07-26: the 단체
reservation endpoint `arc/selectListArc06014_n.do` was **unregistered** when
group booking was removed, because a route no client method can reach must not
stay transmittable. The 23rd read is the 좌석배치도
`arc/selectListArc02011_n.do`, live-confirmed 2026-07-26. The integrated 0.2.0 gate
recorded `587 passed, 1 deselected` (historical); after the additive
reservation-attempt response parser, the consent-gated reserve mutation
surface, the transport-layer live-mutation gate, the consent-gated cancel
surface, the two-category live enablement, the operator scripts, the
reservation-list read, the NetFunnel queue protocol, the error taxonomy, the
real-card acknowledgement gate, the consent-gated card-payment and refund
surfaces, the four-category live enablement, the bundle-evidenced
reservation variants (standby, round trip), the 환승 (transfer)
search and reservation, the 좌석배치도 (seat grid) read and the 좌석지정
(seat-designated) reservation
landed — and after 단체 (group) booking was removed again, and after the
할인 (discount) code tables, the 할인쿠폰 read and the 공공할인 read —
the current offline suite at HEAD is
`1497 passed, 1 deselected`. The deselected case is the
explicitly opted-in live-service test.

Internal editable installation and offline verification:

```bash
python -m pip install -e ".[test]"
PYTHONPATH="$PWD/src" pytest -q -m "not live"
```

The `-m "not live"` filter is the offline gate used by CI
(`.github/workflows/ci.yml`) and by [docs/RELEASE.md](docs/RELEASE.md); it
deselects the live-service test, which additionally requires an explicit
`SRT_MOBILE_API_LIVE=1` opt-in.

Release and handling documents:

- [docs/RELEASE.md](docs/RELEASE.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)

The final merged library-oriented specification is:

- `docs/analysis/srt-app-api-library-spec-2026-07-09.md`

The reusable read-only smoke runner is:

- `scripts/srt_app_api_smoke.py`

### Live read-surface capture (operator-run)

`scripts/capture_live_read_surface.py` drives the public read surface once
against the real server and writes every RAW response to disk **before** it is
parsed, so a parser that raises still leaves its evidence behind. It sends
nothing that changes state: every call goes through the read-only allowlist,
which rejects all four mutation routes by construction.

```bash
SRT_MOBILE_API_LIVE=1 SRT_LIVE_READ_CAPTURE=1 \
SRT_LIVE_CAPTURE_DIR=/path/outside/this/repo \
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... SRT_TEST_DATE=YYYYMMDD \
python3 scripts/capture_live_read_surface.py
```

Three opt-ins, all explicit. `SRT_LIVE_CAPTURE_DIR` has no default and is
**refused inside this repository**: raw captures carry the account's ticket
history, member id and session ids, and must never be committed. Requests are
spaced by `SRT_LIVE_CAPTURE_PACE_SECONDS` (default 2.5s, floor 1s) because
NetFunnel queueing sits in front of search and macro-shaped traffic risks an IP
ban; `SRT_LIVE_CAPTURE_STEPS` runs a named subset so a follow-up pass need not
repeat the whole ~34-request walk. Everything it prints is redacted and the
password is never printed.

**Run on 2026-07-26**, 21 of 22 steps reached across two routes. It is what
produced the live-response findings recorded through this README: the
login-redirect page that made an expired session read as an empty ticket list,
the fare page's placeholder transfer leg (three phantom `0원` fares under real
labels), the timetable whose station names are not in the markup at all, the
sold-out seat page's error shell, the JSON nulls the search rows really carry,
and the live page's own JavaScript refuting our `trnSort` and fare passenger
field names. The one step that did not complete was the deliberate empty-window
search, which the server answers `strResult=FAIL` / `WRG000000` /
"조회 결과가 없습니다." — the server telling the truth, not a parser fault.

### Live reserve->cancel verification (operator-run)

Two scripts exist for the live run that confirms the reserve and cancel wire
shapes. **The round trip has been run twice — 2026-07-25 and 2026-07-26 — and
passed both times**, returning the identical codes on each (reserve
`SUCC`/`IRR000018` "결제하지 않으면 예약이 취소됩니다.", cancel `SUCC`/`IRG000000`
"정상처리되었습니다", no trace left in the ticket list) — see the verification
section above for scope and limits. Both scripts create or release real
reservations on a real account, so re-running either one is a real state change,
not a test.

`scripts/verify_reserve_cancel_roundtrip.py` performs the round trip: login,
search, pick one train that actually has a seat, reserve one adult, print the
PNR, cancel it immediately, then re-read the ticket list to confirm nothing
remains. It requires **two** explicit opt-ins, so it can never fire from an
ordinary live smoke run:

```bash
SRT_MOBILE_API_LIVE=1 SRT_LIVE_MUTATION=1 \
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... SRT_TEST_DATE=YYYYMMDD \
python3 scripts/verify_reserve_cancel_roundtrip.py
```

It reads the same journey variables as the live smoke runner
(`SRT_DEPARTURE_STATION_CODE`, `SRT_ARRIVAL_STATION_CODE`, `SRT_DEPARTURE_TIME`,
the station names and passenger counts), through that module's own helpers. It
refuses to proceed if no train is reservable, prints the raw `strResult`/`msgCd`
for both operations, and exits non-zero on any failure. Everything after a
successful reserve is wrapped so that a failed cancel is retried and, if that
also fails, the PNR is printed in a banner together with the exact recovery
command.

`scripts/recover_hold.py` is that recovery command — it cancels one hold given
nothing but its PNR:

```bash
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py <PNR>
```

It exits 0 only when the server reports the hold released, and reprints the PNR
in a banner on every other outcome. Neither script ever prints the password.

When the PNR *itself* is what was lost, `--list` enumerates the account's
reservations instead of cancelling anything:

```bash
SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py --list
```

`--list` is a pure read (`SrtClient.get_reservations`) and constructs no consent
at all, so it cannot cancel, reserve, pay or refund. It closed a hole in the
recovery path shaped exactly like the path's own worst case: the tool for a lost
hold used to require you to already know the hold's identity.

### Reservation list read

`SrtClient.get_reservations(page_no=0)` POSTs `/atc/selectListAtc14016_n.do`
with `pageNo` and returns an `SrtReservationListResult` of typed
`SrtReservationSummary` rows — the only read that ENUMERATES reservations.
`get_ticket_list` is a different read: it GETs the neighbouring
`/atc/selectListAtc14017_n.do` page and returns HTML.

**Live-verified on 2026-07-26, for the EMPTY case only.** The account has no
reservations, and the server answered `resultMap[0].strResult=SUCC` /
`IRZ000005` / "조회할 자료가 없습니다." with `trainListMap: []`,
`payListMap: []`, `rowCnt: 0`, `totPageCnt: 0`. Two things about that response
are load-bearing and both are pinned by tests:

- an empty result here is an empty **array**, not a failure. The train search
  answers an empty window with `strResult=FAIL` / `WRG000000`; this endpoint
  does not, so "you have no reservations" must never surface as an exception;
- the same successful response carries a **second** envelope, `rsMap[0]`, that
  says `FAIL` / `WRT300005` "조회자료가 없습니다.". The parser reads `resultMap`
  and only `resultMap`; `rsMap` stays reachable through `.raw`.

**The populated row shape is unverified here.** The two-parallel-container
layout (`trainListMap[i]` zipped with `payListMap[i]`) and every row field name
come from srtgo's live runs (`srt.py:1069-1082`), not from our v2.0.41 bundle,
where `payListMap`, `tkSpecNum`, `iseLmtTm` and `stlFlg` are 0-hit. Our bundle
attests the route and its `pageNo` parameter only, and as a WebView **GET**
(`SRForegroundDialogActivity.java:31`; the leftover `data-url` on
`sub/ticketList.html:405`) — the JSON-over-POST spelling is srtgo's. Both were
confirmed against the live server on 2026-07-26; only the POST is allowlisted,
because only the JSON is machine readable. Rows are therefore parsed
permissively: only `pnrNo` is required, an unexpected field type is dropped
rather than raised on, asymmetric containers do not truncate the tail, and a
response carrying rows we cannot read a PNR out of fails loudly rather than
reporting an empty account.

### Card payment (live-verified 2026-07-26, on the thinnest static evidence here)

`SrtClient.pay_with_card(reservation, card, consent=...)` builds the 카드결제
form for `POST /ata/selectListAta09036_n.do` from an `SrtReservationSummary` row
and an `SrtPaymentCard`. **It transmits, and it charges a real card.** `payment`
is in `SRT_LIVE_MUTATION_CATEGORIES` as of 2026-07-26; the method still returns a
redacted `MutationPreview` by default, and a `dry_run=False` call additionally
requires an unambiguous card-kind claim (exactly one of `fake_card_only` /
`real_card_acknowledged`) at both the client and the transport layer.

**The live verification, in two stages.** A free probe went first: a fake card
and a non-existent PNR were sent to this route, and it answered a proper business
envelope — `strResult=FAIL`, `msgCd=WRT100170` — rather than a 404 or an HTML
error shell. That established the route exists on our app version without
spending anything. A real charge followed: 수서→동탄, 2026-08-09, train 315, one
adult, 7,500 KRW, answering `strResult=SUCC` / `msgCd=IRT000000`, and the ticket
was refunded in the same run. `IRT000000` is the same confirmation code korail
returns for its own card approval — one more instance of the shared-platform
pattern recorded below for `IRR000018`/`IRG000000`, and still an observation
about the codes rather than a proven claim about the backend.

**Read this before trusting a field the run did not exercise.** The origin is
unchanged, and it is still the least statically corroborated surface in the
repository, in three separate ways. One live success is live-server evidence, not
static corroboration, and it covered one single-journey, one-adult, general-seat
ticket paid with one personal card in one lump sum — group, multi-leg, corporate
cards and instalments were not exercised:

- **the route is not in our app.** `/ata/selectListAta09036_n.do` has zero hits
  across all 21,673 files of our v2.0.41 offline decompile, as does the token
  `Ata09036` and every `Ata09*` route. The only `/ata/` route the bundle
  contains is `/ata/selectListAta01032_n.do`;
- **our app pays a different way.** `ara1001l.js:1550` serialises `#rsvForm` and
  `:1599`/`:1608` point it at `/ard/selectListArd02018_n.do` (group) or
  `/ard/selectListArd02017_n.do` (personal) — server-rendered WebView pages —
  and the charge then goes through the TransKey secure keypad
  (`AndroidManifest.xml:143`, `bridge.js:2,31,66-68`) and RaonSecure FIDO
  (`AndroidManifest.xml:315`). None of that is plain HTTP form fields. It was an
  open question whether this endpoint was a legacy path the server still honours
  or dead for our app version; the 2026-07-26 charge answered it — **the server
  still honours it**, even though our app never takes it;
- **the two reference libraries are one source, not two.** This was verified,
  not assumed. srtgo's 31-field payment dict is character-for-character
  identical to ryanking13/SRT's once the latter's Korean trailing comments are
  stripped — same keys, same values, same non-alphabetical order, same local
  variable names, same method signature. srtgo depended on `SRTrain`
  (ryanking13/SRT on PyPI) until commit `8423f90` "Internalize SRT"
  (2024-12-13) deleted the dependency and added `srtgo/srt.py` in one move, with
  the payment dict already fully formed; srtgo's README credits ryanking13 under
  MIT. Their agreement corroborates nothing. (`srtgo_plus` is a third copy.)

What the bundle *does* corroborate is narrower than "nothing", and the blanket
claim that every field name is 0-hit is **false**. Three of the 32 names appear
in our own bundle (3 + 28 = 31), all in the reservation JS and none on this form:
`mbCrdNo` (`ara0101v.js:319,321`, a client-side 회원카드번호 branched on its
`"11"` prefix), `totPrnb` (`ara1001l.js:104,368,1511,1655`, the 총인원수) and
`jrnyCnt` (`ara0101v.js:92,311`). The other 28 — every card field, every
settlement field, and `ctlDvCd`/`cgPsId`/`strJobId`/`inrecmnsGridcnt`/`chgMcs`/
`dptStnConsOrdr2`/`arvStnConsOrdr2` — are genuinely absent.

**The response envelope is the odd one out.** Every other SRT mutation here
answers in `resultMap`; this one answers in `outDataSets.dsOutput0[0]`, reading
`strResult`/`msgTxt` from there. Supporting that cost no new code path —
`normalize_result_row` already accepted both spellings — and a test pins the
difference side by side with the cancel envelope. `SrtPaymentResult.succeeded`
and `.failed` are deliberately **not** complements: an unrecognised status means
*unknown*, because for a payment a wrong guess in either direction is expensive
and a blind retry can charge twice.

**Amount fidelity was a deliberate choice, not a formality.** korail was found
sending a display total instead of the collectable amount, and the gap only
appeared on a special-class ticket (`h_tot_prc` 59,800 vs `h_tot_rcvd_amt`
83,700). The same trap exists here: the reference ticket model parses `rcvdAmt`
(수납금액, post-discount, collectable) alongside `stdrPrc` (기준운임, list price)
and `dcntPrc` (할인). This builder takes `rcvdAmt` and only `rcvdAmt`, feeding
both `totNewStlAmt` and `mnsStlAmt1`, and there is **no caller override** — an
override is exactly the seam a display total slips through. A missing or zero
amount is refused rather than defaulted. One divergence is unresolved and
recorded: the server sends the amount zero-padded, ryanking13/SRT posts it back
padded, srtgo casts to `int`; we reproduce srtgo's bare digits because only
srtgo's form is attested by the live runs this route rests on.

Its inputs come from `get_reservations`, whose own populated-row shape is
srtgo-attested (only the EMPTY response is live-verified), so `rcvdAmt`,
`tkSpecNum`, `dptTm` and `arvTm` inherit that uncertainty. `totPrnb` comes from
`tkSpecNum`; the reference implementation's `int(seatNum)` fallback is
deliberately **not** copied, because `seatNum` is a seat identifier and
substituting it would mis-state how many people are being settled for — a
`passenger_count` override exists instead. `mbCrdNo` is read from the session's
own `userMap.MB_CRD_NO` rather than asked of the caller.

The PAN, PIN, expiry, birthdate, membership number and PNR are all redacted in
the preview and hidden from every `repr`.

**A PAN may leave this process only as a payment.** The route/category rules
could not close one case on their own: a caller can hand-assemble a payment body
and post it to a *different, permitted* route — `post_form` would send it to any
allowlisted read path, and `post_mutation_form` would send it to the
live-enabled reserve route under a perfectly valid `category="reserve"` consent.
Neither is a category or a route violation. So `safety.CARD_SECRET_FIELDS`
states the rule on the **data** instead: `stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`
and `athnVal1` may travel only as a `payment`, checked in both
`assert_read_only_request` and at the mutation send boundary. **That guard
matters more since payment was live-enabled, not less** — while the category was
shut it was a second lock on a welded door, and it is now the only thing between
a hand-built card form and the wire on every route that is not the payment
route.

### Refund (two steps, live-verified 2026-07-26, on the thinnest evidence here)

A 환불 is two calls, exposed as two methods:

1. `SrtClient.get_refund_ticket_info(pnr)` POSTs `/atc/getListAtc14087.do` with
   **no body**, gated by a `Referer` of
   `<base_url>/common/ATC/ATC0201L/view.do?pnrNo=<PNR>`, and returns
   `outDataSets.dsOutput1[0]` — note `dsOutput1`, not the `dsOutput0` every other
   `outDataSets` read here uses — as an `SrtRefundTicketInfo`;
2. `SrtClient.refund(ticket_info, consent=...)` POSTs
   `/atc/selectListAtc02063_n.do`. **It transmits, and it really returns the
   ticket**: `refund` is in `SRT_LIVE_MUTATION_CATEGORIES` as of 2026-07-26,
   **live-verified** that day against the live server (`SUCC` / `IRT200277`) for
   one single-journey, one-adult ticket. `Atc02063` is srtgo-attested and 0-hit
   across all 21,673 files of our v2.0.41 bundle; those two facts are about
   different evidence and both hold.

**The live verification, in two stages.** A probe with a non-existent PNR hit
step 1 first and got a proper business envelope back —
`{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"WRT300005",
"strResult":"FAIL","msgTxt":"조회자료가 없습니다."}]},"ErrorMsg":""}` — rather
than a 404 or an HTML error shell, which established the route exists on our app
version. The real round trip then read a real ticket's identity from step 1 and
refunded it through step 2: `strResult=SUCC` / `msgCd=IRT200277`, after which
the account was verified empty of both reservations and tickets from a separate
session. `IRT200277` is korail's code for the same operation.

**They are deliberately not fused into one method, and that did not change when
the gate opened** — only the reason did. It used to be that a combined call
would fire step 1 and only *then* discover step 2 was refused, leaving a live
request behind for an operation that could never complete. Now that a refund can
complete, the surviving reason is sequencing: step 2's body is nothing but the
identity step 1 returned, so `refund` takes an already-fetched
`SrtRefundTicketInfo` and never fetches one itself. A refused refund still sends
nothing at all, a permitted one sends exactly one request — to the refund route,
never to step 1 — and a dry run needs no network. Tests pin all three.

Step 1 travels the read path: it is classified as a read and registered in
`READ_ONLY_ROUTES`. That classification is an **inference, not a proof** — the
request carries no body, the response is pure identity data, and the reference
implementation uses it only to gather step-2 fields, but nothing here can prove
the server treats it as side-effect free, and the app's own naming is not
decisive (`/ard/selectListArd02045_n.do` is a *cancel* despite its `selectList`
prefix). Nothing in the refund path calls it for you.

**Static provenance is thinner than the payment's, and the live run did not
change that.** The payment at least has one implementation copied into two
libraries. This route exists in exactly **one**: ryanking13/SRT has no refund at
all — no `reserve_info`, no `getListAtc14087`, no `selectListAtc02063`, no
`tkRetPwd` — and srtgo added both steps from scratch four days after vendoring
its SRT support (2024-12-17). There is no upstream to have agreed with it.
`Atc02063` and `Atc14087` are 0-hit across all 21,673 files of our v2.0.41
decompile; the bundle has **no `Atc02*` family whatsoever**, and the nearest real
routes are `Atc14016`/`Atc14017`. One live success is live-server evidence, not
static corroboration, and it covered one single-journey, one-adult ticket.

**Two of the seven step-2 field names were disputed; the live run settled them
in srtgo's favour.** srtgo sends `tkRetPwd` and `psgNm`; our own app spells them
`retPwd` and `buyPsNm` at
`analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:645,648`. That site is
**not an API schema**: it reads the SharedPreferences key `"ticketListOffline"`,
base64-decodes it and parses it as JSON (`b.java:613,624-632`), then copies keys
into a display model — deserialisation of a *local offline ticket cache*. It
also spells the PNR `pnrNo` where srtgo's form says `pnr_no`, a third
disagreement. That argument is now demonstrated rather than argued: the
2026-07-26 refund sent `tkRetPwd`, `psgNm` and `pnr_no`, and the server refunded
the ticket. Do not "correct" them to the cache spellings. The precedent that
motivated the doubt still stands and is worth keeping straight — this project
really did ship srtgo's misspelling of a korail refund field, `txtPrnNo` for
`txtPnrNo` — and the lesson it actually teaches is that srtgo was wrong *there*
and right *here*, so single-source field names have to be tested one at a time,
not trusted or distrusted as a class.

Step 1's success condition is **stricter** than this library's usual wrapper
check: `ErrorCode == "0"` **and** `ErrorMsg == ""`, where
`parse_mutual_verification_response` accepts `ErrorCode` in `{"", "0"}` and
ignores the message. Implemented as documented rather than relaxed to house
style — on a route with one attesting source, failing loudly on a
half-recognised response is the cheap mistake. Step 2's envelope is the
*ordinary* `resultMap` SUCC/FAIL one, the same as cancel's and unlike the
payment's.

The return password, the purchaser name and the PNR are redacted in the preview
and hidden from every `repr`; the sale identifiers stay legible, because with
the password masked they authorise nothing.

### NetFunnel queue protocol

`/ts.wseq` carries the whole three-opcode conversation now, not just its first
message. The bundle's own vendored `netfunnel.js` defines all three
(`RTYPE_GET_TID_CHK_ENTER=5101`, `RTYPE_CHK_ENTER=5002`,
`RTYPE_SET_COMPLETE=5004`, netfunnel.js:84):

- **5101 getTidChkEnter** — acquire, as before;
- **5002 chkEnter** — poll while the queue holds us. Previously a 201
  (`kContinue`) simply failed the search: the queue working as designed looked
  like an error. The loop is **bounded**, unlike the app's — 20 polls or 60
  seconds of wall clock, whichever comes first — and each wait is the server's
  own `ttl`, clamped to the app's own 1..5s (`TS_MAX_TTL`) so it can never
  become a tight retry loop;
- **5004 setComplete** — release the slot. Without it our place in line was held
  until it timed out, which at peak load is queue pollution we caused.
  `TS_AUTO_COMPLETE = true` in the bundle's config, so the app releases too. A
  failed release is swallowed: it is housekeeping that runs after the caller's
  real request already succeeded or failed, and it must never replace that
  outcome — least of all on a `reserve`, where it would hide a PNR.

`safety.py`'s `/ts.wseq` contract registers **three exact per-opcode query
shapes** rather than being loosened to "any NetFunnel request". Two of the
bundle's own details are worth stating because they contradict the obvious
assumption that one query shape covers all three: `setComplete` carries **no
`sid` and no `aid`** (it is the only one of the four builders in `netfunnel.js`
that omits them), and `ttl` sits **between `prefix` and `sid`** on `chkEnter`
and is the server's returned value rather than a constant. `js=yes` is pinned
throughout — srtgo and ryanking13/SRT both send `js=true`, and the bundle we
ship says `yes`.

**Live status.** A real acquire → release round trip was verified on
2026-07-26: the acquire answered `5002:200` with a 256-character key (typed
5002 even though we asked 5101, which is the app's own retyping) and
`ttl=0`/`nwait=0`, and the `setComplete` answered `5004:200`. **The 201 polling
path is offline-tested only** — at normal load the queue does not engage, and
load was deliberately not synthesised to force it. The live run also caught a
bug no fixture could: the key-shape guard bounded keys at 128 characters while
a real one is 256, so every `setComplete` failed the guard and was silently
swallowed.

One divergence is deliberate. The acquire reply names a specific queue node
(`ip=rnf14.letskorail.com&port=443`), and the app WOULD send its subsequent
`chkEnter`/`setComplete` there (`TS_CONFIG_USE = false`). We do not: the client
is pinned to two canonical origins, and following a server-named host would let
a response choose where the next request goes. The live run showed we do not
have to — the front door released a slot issued by another node.

## Scope

This repository documents SRT Android app APIs under `app.srail.or.kr` and the
NetFunnel helper required by the app flow. It excludes external web APIs, real
payment authorization, and automatic production reservation creation.

## Local Artifacts

`srt.apk` and `build/` are intentionally ignored. They are local evidence
artifacts, not retained source files.

Expected APK identity if static evidence needs to be regenerated:

| Item | Value |
|---|---|
| SHA-256 | `60e894aef1e0345444bd6fd22e1ac87a15b27ac60211b2a21dc6c7738b9c50b9` |
| Size | `26,427,764` bytes |
| Package | `kr.co.srail.newapp` |
| Version | `2.0.41` / `versionCode=150` |

Regenerate evidence locally only when needed:

```bash
mkdir -p build
zipinfo -1 srt.apk | sort > build/apk-file-list.txt
apktool d -f srt.apk -o build/apktool
jadx -d build/jadx srt.apk
```

## Safety

Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or
card-shaped values in the repository. The smoke script reads credentials from
environment variables and does not issue reservation or payment requests.
`SrtConfig` pins app and NetFunnel traffic to the documented production HTTPS
origins; its host fields cannot be used to redirect requests to alternate servers.

## Python Package MVP

This repository now contains an installable Python client package under `src/srt_mobile_api`.

Default tests are offline:

```bash
pip install -e ".[test]"
pytest -q -m "not live"
```

### Error taxonomy

A caller needs three answers out of a failure — *is retrying pointless? do I
need to log in again? or was the request fine and there was simply nothing
there?* — and until now the only way to get them was to substring-match the
Korean `msgTxt`, which is what the third-party `srtgo` does
(`srtgo/srtgo.py:721-744`). Every server-side failure now arrives as a named
type instead.

```
SrtApiError
├── SrtTransportError            HTTP failed before an app response existed
├── SrtProtocolError             the response did not match the protocol
├── SrtAuthError                 login/session
│   ├── SrtSessionExpiredError   → RE-LOGIN AND TRY AGAIN
│   └── SrtIpBlockedError        → retry is pointless from this network
├── SrtAppError                  any app-declared failure (base; unchanged)
│   ├── SrtNoResultsError        → THE REQUEST WAS FINE, NOTHING MATCHED
│   ├── SrtInvalidRequestError   → retry is pointless; fix the payload
│   └── SrtSeatUnavailableError  → retry is pointless for THIS train
├── SrtMutationNotAllowedError   consent/kill-switch refusal, before any send
└── SrtNetFunnelError            the queue
    ├── SrtNetFunnelKeyError     → a fresh key may work (this one IS retried)
    └── SrtQueueRejectedError    → retry is pointless right now
```

**Every new type subclasses the one it refines**, so no existing `except`
clause changes meaning — `except SrtAppError` still catches every app-level
rejection, `except SrtAuthError` around `login()` still catches an IP block. A
test checks that exhaustively rather than by example.

**Classification reads `msgCd`, not message text, because that is what the app
does.** The single place in all 21,673 files of the v2.0.41 bundle where a
server-supplied string is branched on is a code — `resultMap.msgCd == "S111"`
(`ara1001l.js:1565`), which stashes the pending form and calls
`memberShipLogin()`. Every other branch is `strResult == "FAIL"`
(`ara1001l.js:206`, `:234`, `:1855`) or `ErrorCode == -1` (`:193`, `:1840`),
neither of which carries a reason at all, and the app never substring-matches
`msgTxt` — it only displays it. Each exception keeps the raw `.code` and the
whole `.raw` response, so a caller can handle a code this library has not
mapped, and so the map can be grown from real traffic.

| Code | Type | Where it was seen |
|---|---|---|
| `WRG000000` "조회 결과가 없습니다." | `SrtNoResultsError` | live 2026-07-26, empty search window |
| `WRT300005` "조회자료가 없습니다." | `SrtNoResultsError` | live 2026-07-26, reservation list `rsMap` |
| `WRD000061` "직통열차는 없지만, 환승으로 조회 가능합니다." | `SrtNoDirectTrainError` (refines `SrtNoResultsError`) | live 2026-07-26, 동대구→광주송정 direct search |
| `WRP011002` "승객수 오류" | `SrtInvalidRequestError` | live, reserve runtime probe |
| `WRR000100` | `SrtInvalidRequestError` | live 2026-07-15, bounded zero-passenger one-shot |
| `S111` | `SrtSessionExpiredError` | **bundle**, `ara1001l.js:1565` (reserve only) |
| `NET000001` | `SrtNetFunnelKeyError` | live/spec; **0-hit in the bundle** |
| `error001` (a `messages.js` key, not a `msgCd`) | `SrtSeatUnavailableError` | live 2026-07-26, sold-out seat page |
| `301` / `302` (`kTsBlock`/`kTsIpBlock`) | `SrtQueueRejectedError` | **bundle**, netfunnel.js `_showResultChkEnter` |

Anything unmapped stays a plain `SrtAppError` with its code attached — the
pre-existing behaviour, deliberately unchanged.

Two details worth stating plainly:

- **`messages.js` is not a `msgCd` catalogue.** It is a client-side UI string
  table keyed `error001`/`rsv001`/`login018` — 172 strings, zero server codes.
  It earns its keep in exactly one place: the sold-out seat page returns a
  shell whose only content is
  `srtAlertBoxDivShow("알림", Sr.msgs.error001, null, "historyBack();")`, so
  `SrtSeatUnavailableError.code` is that alert *key*. Strictly the shell means
  "no car is selectable"; sold-out is the observed cause, not a claim the
  server makes.
- **The queue distinguishes "refused" from "broken" itself.**
  `_showResultChkEnter` fires `"onBlock"` and `"onIpBlock"` as events separate
  from `"onError"`. `303 kTsExpressNumber` also has its own event and is
  deliberately *not* mapped — it is an admission, not a refusal.

**Nothing about what the library does on its own initiative changed.** The
single bounded `NET000001` search retry remains the only self-directed retry,
and `reserve` is still never retried, because a retried reserve is a duplicate
booking. `srtgo`'s CLI polls forever (`srtgo/srtgo.py:803-807`); that is macro
behaviour for a CLI, not library behaviour. Three tests pin it: a
`SrtNoResultsError` and a `SrtInvalidRequestError` search each issue exactly
one POST, and a `SrtNetFunnelKeyError` search issues exactly two.

**What `srtgo` claimed, and what survived the bundle.** Two of its six
message-matched rules are independently confirmed, but by code rather than by
message: `"로그인 후 사용하십시오"` → re-login *is* our `S111`, and
`"정상적인 경로로 접근 부탁드립니다"` → discard the key *is* our `NET000001`.
Neither exact substring appears in our bundle (the closest are the app's own
client-side prompts `"로그인 후 사용하십시요"`, `messages.js:224`, note 시요 not
시오, and `messages.js:231`). The other four — `"잔여석없음"`,
`"사용자가 많아 접속이 원활하지 않습니다"`, `"예약대기 접수가 마감되었습니다"`,
`"예약대기자한도수초과"` — are **0-hit across the bundle, have no known
`msgCd`, and the last two describe 예약대기 (standby), a surface this library
does not implement**. They are recorded here as srtgo-attested leads and are
*not* encoded; a test pins that a FAIL carrying any of them under an unknown
code stays a plain `SrtAppError`, so the refusal to guess stays a decision.

Finally, the two live empty-result shapes are pinned against regression,
because this is the change most likely to have broken them: an empty search
really is a declared FAIL and now raises `SrtNoResultsError`, while an empty
reservation list is `SUCC`/`IRZ000005` with empty arrays and still returns an
empty list — the second `rsMap` envelope that says `FAIL`/`WRT300005` on that
same response is still never read.

### Typed raw-backed read results

Personal search accepts the exact mixed-case `ErrorCode`/`ErrorMsg` wrapper;
group search accepts the exact uppercase `ERROR_CODE`/`ERROR_MSG` wrapper.
Partial, duplicate, conflicting, and non-string wrapper pairs fail closed, and
an app-level wrapper error is raised before result datasets are considered.

`TrainSearchResult.metadata` provides repr-safe `TrainSearchMetadata` with the
message code/status, integer query count, and optional following-page flag. The
legacy raw `result` field and its positional slot remain available. Search rows
also expose optional consist/run order, delay, seat/wait/standing availability,
received-amount, and discount fields. When the server row omits station names,
the client can enrich them from the already-hydrated request form; blank or
code-only context does not invent a name.

`get_notice_list()` preserves its legacy raw `dict` result.
`get_typed_notice_list()` exposes the same one-request read as a
`NoticeListResult` containing typed `Notice` rows for the observed uppercase
seven-field contract. Notice bodies and raw mappings are excluded from
`repr()`. Timetable parsing skips leading empty cells before choosing the
station name. `FarePage.items` preserves its legacy numeric-only rows, while
`FarePage.semantic_items` also retains unavailable rows as
`FareItem(amount=None, available=False, status=...)`. These parser changes add
no route, seat-inventory, or mutation behavior.

### Bounded train-search pagination

`SrtClient.iter_train_search_pages(query, *, group=False, max_pages=10)`
lazily yields `TrainSearchResult` pages for personal or group search. Existing
`search_trains(query)` and `search_group_trains(query)` remain compatible
single-page calls. `search_transfer_trains(query)` is deliberately **not**
paginated — a 환승 response carries a second, unexplained cursor (`fllwPgExt2`)
that nothing in the bundle reads; see the transfer section.

The iterator obtains one `act_10` key, hydrates the search form, and preserves
the resulting key, passenger fields, `dptTm1`, and unknown hidden inputs across
continuation POSTs. Each continuation changes only `dptTm` to
`last_row.dptTm[:5] + "1"` and clears `trnNo`; the response-only `fllwPgExt`
field is never sent. Pages stay in server order and are neither accumulated nor
deduplicated.

Iteration stops at exact `fllwPgExt=N`, an empty page, a caller-supplied
`max_pages` bound, or caller closure. Missing or malformed metadata and
non-progressing/repeated cursors fail closed. If a continuation is rejected with
`NET000001`, only that cursor obtains one fresh key and hydration and is retried
once; earlier pages are neither replayed nor yielded again.

This contract comes from static SRT Android app 2.0.41 evidence and synthetic
offline request-sequence tests. Live continuation was verified in one bounded
2026-07-15 session: personal and group each returned two pages with 10 rows per
page. The iterator adds no route: the reviewed 20-route read-only boundary and all
reservation, payment, cancellation, refund, native-bridge, and external-seatmap
exclusions from the read-only allowlist remain unchanged.

### Read-only selector popups

`SrtClient` exposes the six runtime-evidenced selector popup reads:

- `get_station_selector(...)`
- `get_station_map_selector()`
- `get_date_selector(...)`
- `get_passenger_selector(...)`
- `get_seat_option_selector(...)`
- `get_train_group_selector(...)`

Each method posts only to its exact allowlisted `/common/ARA/` route and returns
the existing `HtmlPage`, so callers retain compatible `text` and `raw` access.
The live helper calls all six after booking-page hydration and reports only the
bounded integer `selectorLoadedCount`; it never emits popup HTML or extracted
popup text.

These APIs select search-form preferences only. Reservation, payment, refund,
cancellation, `act_19`, ATA/ARD, native bridges, and external seat-map calls
remain outside the read-only allowlist.

### Physical seat-selection page read

`SrtClient.get_seat_page(train)` performs one authenticated read of the
internal SRT seat-selection HTML page for a complete server-returned SRT row.
The request defaults to general class, carries exactly thirteen allowlisted form
fields, and returns `SeatSelectionPage` after requiring the `좌석선택` marker.
Its `choiceSeatCount` is the party size, as the app's is
(`choiceSeatCount: lfn_getRsv("totPrnb")`, `ara1001l.js:1511`): pass
`passengers=` and the count is derived from the total, or `seat_count=` to
override it explicitly. With neither it is one seat.

This method does not select or hold a seat. It does not call NetFunnel
`act_19`, submit a reservation, follow the external Korail seat map, execute
JavaScript/callbacks, retry, or scan fallback trains. The live helper reports
only bounded booleans and never emits the page body.

The internal SRT page was loaded, but the retained sanitized schema-v2 evidence
proves only a bounded car/UI candidate and a static Ajax handoff. It does not
prove a stable iterable physical-seat record or availability vocabulary — that
came later and from elsewhere: the 2026-07-26 live read of the Ajax handoff's
own target. Individual physical seats are typed as of that read; see "Seat grid
(좌석배치도)" below.

### Bounded seat-layout evidence gate

`scripts/capture_seat_layout_evidence.py` is a separately invoked internal
evidence command. It requires `SRT_MOBILE_API_LIVE=1`, the existing live
credential environment variables, and `SRT_TEST_DATE`. Its complete operation
budget is exactly one `SrtClient.login` call, one `SrtClient.search_trains`
operation, and zero or one `SrtClient.get_seat_page` call for the first complete
SRT row. When no complete row exists, it makes no seat-page request.

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
PYTHONPATH="$PWD/src" python3 scripts/capture_seat_layout_evidence.py \
  --output /tmp/srt-seat-layout-evidence.json --force
```

The command writes one deterministic `schema_version: 2` report through a
temporary sibling and atomic replace. It classifies embedded DOM/JSON
candidates, generic scripts, same-origin script/form/iframe references, static
Ajax contracts, cross-origin reference counts, and external seat-map handoffs.
A generic script alone produces `no_inventory_source`; it is not evidence of a
seat inventory source.

The parser analyzes only the already-returned HTML. It does not execute
JavaScript or follow a script, form, iframe, Ajax route, external handoff, or
callback. Same-origin targets and inline route literals are retained only as
query/fragment-free static `.do`/`.js`/`.mjs` paths without dynamic seat/car
segments; cross-origin targets are counts/categories only. Inline scripts retain bounded
lengths, truncation flags, and SHA-256 digests of the captured prefix—not source
text or the truncated tail. JavaScript strings/comments cannot create structural
inventory evidence; backtick and ambiguous slash tails are masked
conservatively. `application/json` blocks retain only bounded key/type,
array-cardinality, depth, and inventory-name summaries after dynamic seat keys
are discarded. Static JavaScript payload metadata accepts only unquoted safe
simple key names; quoted object keys are ignored.

Raw HTML, visible text, attribute/input values, element IDs, query strings,
arbitrary URLs, train/car/seat values, credentials, cookies, tokens, and
exception messages are never written. This evidence command still emits no
typed car or seat of its own, and schema-v2 evidence still does not authorize
another origin, route, or mutation — the seat grid below was authorized by a
separate live read, not by this report.

The exact sanitized offline-replay report is retained as
`tests/fixtures/seat_page_schema_v2_evidence.json`. Its regression test locks
the complete nested schema, canonical digest, zero offline call counts, and the
existing fail-closed safety scan. The fixture stores only bounded structural
metadata: no raw body, visible value, dynamic identifier, credential, cookie,
or session scalar.

That evidence proves one static same-origin `POST` reference to
`/arc/selectListArc02011_n.do` and a separate self-target form summary with
these 11 input names: `trnGpCd`, `runDt`, `trnNo`, `scarNo`, `psrmClCd`,
`dptRsStnCd`, `arvRsStnCd`, `seatAttCd`, `dptStnRunOrdr`, `arvStnRunOrdr`, and
`choiceSeatCount`. The retained fixture does not prove that the script
serializes that form, the controls' input types, the response grammar, or the
DOM sink. It exposes no iterable response schema.

**That last sentence stood for a year and is now out of date, in the good
direction.** On 2026-07-26 the route was read live and Arc02011 is implemented:
it is registered in `READ_ONLY_ROUTES` with its own exact eleven-field contract,
`get_seat_grid(train, car_number)` calls it, and `parse_seat_grid_response`
closes its response. What changed was not the evidence policy but the evidence:
the 2026-07-15 capture summarized the page's *structure* and could not say what
the route answers, and a live read could. See "Seat grid (좌석배치도)" below,
including the one fact the whole endpoint turned on — the train number must be
**zero-padded to five characters**.

The same bounded 2026-07-15 session loaded one seat page from the first
complete personal-search row. The fixed live summary reported the visible
marker, 9 scripts, 3 forms, no iframe, no embedded JSON block, 5 source
categories, and `sufficiency=inventory_source_candidate`; it emitted no raw
HTML or identifiers. A later authorized offline replay produced only the
sanitized fixture described above. Together they prove a candidate source and
the static handoff, not an iterable car/seat response or availability
vocabulary.

### Seat grid (좌석배치도)

`get_seat_grid(train, car_number)` reads one 호차's seat map from
`POST /arc/selectListArc02011_n.do` and returns a `SeatGrid` of `SeatGridSeat`
rows. It is the second half of the seat-selection read: `get_seat_page` says
which cars have seats left, this says which seats and whether they can be
picked.

**Live-confirmed 2026-07-26** (수서 → 동탄, 20260812, train 315): 25,930 bytes,
74 seat cells. Both this route and the `trnScarSeatFrm` form it serializes are
0-hit in the v2.0.41 offline bundle — they exist only in what the server renders
— which is why this was believed for months to need a traffic capture. It did
not. The pages are served to our own authenticated session, so the HTML and its
inline JavaScript can simply be read.

**The train number is zero-padded to five characters, and that is the whole
gate.** The identical request with `trnNo=315` returns a 147-byte alert shell
whose text ("출발 20분 전부터 좌석이 자동배정됩니다…") reads like a timing rule
and is not one; with `trnNo=00315` it returns the seat grid. Referer and route
length change nothing — all three were checked. The app pads the same way and
says so in a comment: `lfn_getTrNoData`, *"열차번호를 5자리로 채워서 가져옴"*.
The padding lives in `payloads.seat_grid_payload` and is re-checked at the
safety boundary, so a hand-assembled unpadded body cannot leave the process.

**A seat has two identifiers and they are not interchangeable.** Each cell is
`choiceSeatNo('3', '1C', 'Y')`: the first argument is the car's *internal* seat
number, the second is the *printed* label on the seat, the third is whether it
can be selected. `SeatGridSeat` models both as `internal_seat_number` and
`printed_seat_label` and never as one field, because conflating them is a
mistake this project already made once on the sibling korail client. The
element id and `aria-label` are built from the printed label; the class is
`seatChoice<seatAttCd><Y|N>`, with `000`, `015`, `021` and `028` all present in
the captured car.

The route answers a refusal as `"0#<message>"` (the page's own handler is
`tmp = args.trim().split("#"); if (tmp[0] == "0") alert(tmp[1])`). That is the
server declining a request it understood, so it raises
`SrtSeatUnavailableError` — a `SrtAppError`, catchable exactly like every other
business refusal — rather than a protocol error. Its `code` is the envelope's
own `"0"`: this route is HTML and carries no `msgCd` at all.

Registering it moved the read allowlist from 22 routes to 23. It creates
nothing, it is refused by `assert_mutation_route`, and
`SRT_LIVE_MUTATION_CATEGORIES` is untouched.

### 좌석지정 — seat-designated reservation (`jobId=1103`)

`reserve(train, *, designated_seats=…, consent=…)` reserves NAMED seats instead
of letting the server assign them. Keyword-only and defaulted to `None`, so an
existing caller's form is byte-for-byte and order-for-order what it was, which a
test asserts. No route and no consent category was added: it is the same
`reserve` operation on `/arc/selectListArc05013_n.do` under the same consent,
and `SRT_LIVE_MUTATION_CATEGORIES` is untouched.

```python
page  = client.get_seat_page(train, passengers=party)
grid  = client.get_seat_grid(train, page.cars[0].car_number, passengers=party)
seats = grid.choose("1B", "2C")          # printed labels, validated selectable
hold  = client.reserve(train, passengers=party, designated_seats=seats,
                       consent=MutationConsent(dry_run=False, allow_reserve=True))
```

The seat count must equal the party size, and `SeatDesignation` will not hold a
seat the grid marked unselectable — so an `N` seat is unrepresentable rather
than merely rejected.

**Read this before sending one live: the body is evidenced, the target is
inferred.** Every field — `jobId=1103`, `seatNo1_1..N` from the PRINTED labels,
`scarGridcnt1`, `scarGridcnt2="0"`, `scarNo1`, `scarNo2=""` — comes from
`ara0101v.js:866-882` and `ara1001l.js:1435-1436`. What does *not* come from
the bundle is the endpoint: the app's seat callback ends in `fn_submit()`, whose
definition lives in the server-rendered booking page, and the endpoint used here
is taken from the commented-out `//Sr.ara1001l.fn_callReserv();` on the very
next line. **The operator's next step is to fetch `/ara/ara0101v.do` and read
its inline `fn_submit`** — the same page-fetching technique that opened the seat
grid. If it targets something other than `Arc05013`, the body is still right and
only the route moves.

It does not compose with `standby` (`jobId` cannot be both `1102` and `1103`) or
with `round_trip` (the app's 왕복 seat callback writes no seat fields at all, so
that body is unevidenced); both raise `ValueError` before anything is built. It
is not offered on `reserve_transfer`, which blanks the slot-2 car and seat.

### 할인 (discount) code tables

`srt_mobile_api.discounts` carries two lookup tables and their accessors,
`discount_kind_name` and `public_discount_name`. Both return `""` for an unknown
code rather than raising, following `stations.station_name_by_code`: these
decode values the SERVER chose, and a client that crashes on an unfamiliar
discount code is worse than one that shows none.

- **`DISCOUNT_KIND_NAMES_BY_CODE`** — 할인종류코드 (`dcntKndCd`), a direct copy of
  that run in the app's own `js/commCode.js`. **173 codes, not 171**: two rows
  (`133` 기본 특별할인(기준), `191` 정차역 할인) carry no `code_group_cd` key at all
  in the source, sit inside the `dcntKndCd` run between `132` and `192`, and are
  included deliberately. 25 rows carry `"rmk": "V"`; nothing in the bundle says
  what `V` marks, so nothing is built on it. `dcntKndCd` is a real transmitted
  field — every SRT booking page this project has fetched carries
  `<input type="hidden" name="dcntKndCd">` — but this library never SETS it.
  Nothing here asks for a discount; the table exists to decode what comes back.
- **`PUBLIC_DISCOUNT_NAMES_BY_CODE`** — 공공할인코드 (`PBL_DISC_CD`) `01`–`06`.
  This is **0-hit in the v2.0.41 bundle**, code and values alike. It comes from
  a page the live server renders to our own authenticated session: the
  승차인원선택 popup writes the whole mapping out as a comment block in its own
  `setPassenger` (fetched 2026-07-26). `07` and `08` have branches on the
  할인 승차권 page and no name on any page fetched here, so they stay unknown
  rather than invented.

`PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE` records the one rule two separate live
pages state identically — 다자녀 (`01`) and 3세대 동행할인 (`06`) refuse a party
under three, message `rsv071` — and `YOUTH_PASSENGER_TYPE_CODE` records
`psgTpCd` **6**, which is in neither copy of `commCode.js` and exists only under
공공할인 `04` (청소년). It is recorded and deliberately **not** wired into
`PassengerCounts`; see "공공할인 is a passenger vocabulary, not just a price"
in `docs/IMPLEMENTATION_PROGRESS.md`.

### 할인쿠폰 (discount coupons) — live-verified empty, 2026-07-26

`SrtClient.get_discount_coupons() -> DiscountCouponList`, one parameterless
`GET /apa/selectListApa03020_n.do`.

**The route is 0-hit in the v2.0.41 bundle**, which contains no `/apa/` route
at all. It was found by reading a page this client already fetches: SRT
server-renders its MY SRT menu into every authenticated page, and that menu is
where `할인쿠폰조회/등록` names the route as
`pageMove('/apa/selectListApa03020_n.do')` — with `pageMove` being
`window.location = url`, so a plain GET. Same technique as the seat grid,
pointed at a menu instead of a form.

**Live-verified for an account holding no coupons**: 77,056 bytes,
`ul.coupList` present and empty, `보유한 쿠폰이 없습니다.` A POPULATED list has not
been read here, and `DiscountCoupon`'s docstring says exactly what its six field
names rest on — the page's own commented-out designer template — and why every
value stays display text rather than a parsed number.

**That template is also why this parser is not a regex.** The live page ships a
two-coupon template, commented out, *inside* `ul.coupList`, with plausible
numbers and rates. `html.parser` hands a comment to `handle_comment` as one
opaque string and never parses markup inside it, so the template cannot become
coupons; a regex over the same bytes would have invented two for an account that
holds none. The fixture keeps the template verbatim so the property is tested.

**"You hold none" and "we did not understand this page" are kept apart.** The
parser refuses a page with no `ul.coupList` (not the coupon page), a list that
neither lists coupons nor carries the marker, and a page that does both.

**Registering a coupon is not implemented and is not reachable.** The same page
carries a `dscp_no`/`dscp_pwd` form, but its submit is a POST to a *different*
route (`/arb/selectListArb02A01_n.do`) which is in neither allowlist and would
need a fifth entry in `SRT_LIVE_MUTATION_CATEGORIES` — pinned to four by its own
canary. Only `GET` is registered for the coupon path, so a coupon number and its
password cannot travel there under a read either.

### 공공할인 (welfare discounts) — live-verified unapproved, 2026-07-26

`SrtClient.get_public_discounts() -> PublicDiscountPage`, one parameterless
`GET /common/ARA/ARA0301V/view.do` — the 할인 승차권 page, named on the same
server-rendered MY SRT menu as the coupon route. `READ_ONLY_ROUTES` 24 → 25.

It answers one question: **which 공공할인 has this account been approved for**.
The page server-renders eight flags, `var data1Check` … `var data8Check`, and
`PublicDiscountPage.entitlements` is those eight resolved to codes `01`–`08` and
names. **Live-verified for an account approved for nothing**: 206,268 bytes,
all eight flags empty, `is_eligible` `False`.

**That is returned, not raised**, and the distinction is worth stating because
the page behaves like a refusal — it alerts `Sr.msgs.notice006` ("할인승차권은
홈페이지를 통해 인증된 고객만 이용이 가능합니다…") and bounces to the main page. The
sold-out seat page raises on its alert because there the refusal means the seat
map a caller asked for does not exist. Here, "you hold none" *is* the answer.

**The code-to-slot mapping is an inference and is labelled one.** Nothing on the
page writes a `PBL_DISC_CD` next to a `dataNCheck`. What ties them is the page's
own comment on the one branch that reads two flags at once —
*"다자녀(01)와 임산부(02)가 신청이 승인된 경우"*, guarding
`if(data1Check == "Y" && data2Check == "Y")`. Slot 1 is `01`, slot 2 is `02`,
there are eight of each, and the `PBL_DISC_CD` branches below run `01`–`08` in
order.

Refused rather than interpreted: a page with no `PBL_DISC_CD` field, and a page
that does not declare exactly eight distinct flags. The flag regex is anchored
on `var` because the same identifiers appear nine more times as `!= "Y"` /
`== "Y"` comparisons — an unanchored match would read the unapproved page as
approved.

**This does not run the 할인 승차권 search and cannot.** The page it reads *is*
that search's form: `#rsvForm`, the booking page's ~140 fields plus
`PBL_DISC_CD` / `PBL_DISC_NM` / `PBL_DISC_MG_NO` / `TGT_DTRM_YN`, submitting to
`/ara/selectListAra10131_n.do` behind a NetFunnel `act_10` gate. That route
exists — a bare live GET answered `200` where a nonexistent sibling answered
`404` — and is registered nowhere here, has no builder and no method. Exercising
it needs an approved 공공할인 that nobody on this project holds.

Also not carried: the approved discount's `PBL_DISC_MG_NO` and its
confirmation/expiry dates. They are server-rendered into the branch bodies of
the page's own `if/else if` chain and every one was empty on the only account
readable here, so their populated shape is unknown and no parser is written
against it. `raw` carries the page.

### What the 할인 survey found that is NOT implemented

Three discount surfaces exist and are deliberately absent, each for a different
reason. The full write-up, with the evidence for each, is in
`docs/IMPLEMENTATION_PROGRESS.md` under "할인 / 쿠폰 / 공공할인 — the survey".

- **`POST /arb/selectListArb02A01_n.do`, 할인쿠폰 등록.** A mutation, and it
  belongs to no member of `SRT_LIVE_MUTATION_CATEGORIES` — which is
  `{reserve, cancel, payment, refund}` and pinned by a canary. Registered in
  neither allowlist.
- **`/ara/selectListAra10131_n.do`, the 할인 승차권 search.** Exists (a bare live
  GET answered `200` where a nonexistent sibling answered `404`), but every
  `PBL_DISC_*` value it needs would be a guess without an approved 공공할인,
  which no account here holds. Unverifiable in principle, not merely unverified.
- **`/ata/selectListAta01032_n.do`, the bundle's only discount route.** Its
  single caller (`arc0102c.js:34`) sends the literal, unsubstituted
  `pnrNo=${commandMap.pnrNo}` — a JSP expression stranded in a static asset — so
  it can never have worked from the offline bundle. The live server says the
  route is **mapped but throws**: it answers `500` where two control routes
  answer `404`, with the identical body, so the status code is the whole signal.
  Reaching it needs a real owned PNR, and this survey created nothing.

**And one gap in what this library can express.** `PassengerCounts` carries five
passenger types; the live app carries seven. 유아 is `passenger6` on the
승차인원선택 popup and travels as `infantCnt` *and* folded into the 어린이 count;
청소년 is `passenger7`, revealed only under 공공할인 `04`, and travels as
`psgTpCd` **6** — a code in neither copy of `commCode.js`. Nothing was changed
in `PassengerCounts` or any payload, because both would change what `reserve()`
transmits and 청소년 needs an approval nobody here holds. Five is now recorded
as this library's deliberate boundary rather than as a fact about SRT; see
"공공할인 is a passenger vocabulary, not just a price".

### Mutual verification

`get_mutual_verification()` manually performs the evidenced empty-form mutual
verification read and returns a repr-safe `MutualVerificationResult`. It is not
called automatically by login or search and does not start seat selection or a
reservation. The opted-in live helper calls it only after personal search and
reports `mutualVerificationLoaded`, never the verification value or raw JSON.

Live smoke is opt-in and limited to login plus read/query calls:

```bash
export SRT_MOBILE_API_LIVE=1
export SRT_LOGIN_ID="<login-id>"
export SRT_LOGIN_PASSWORD="<password>"
export SRT_TEST_DATE="<YYYYMMDD>"
export SRT_DEVICE_KEY="<device-key>"
export SRT_CHILD_COUNT=1
python3 -c "from srt_mobile_api.live import run_live_smoke_from_env; print(run_live_smoke_from_env())"
```

The live helper reports only booleans and bounded counts. It exercises one
non-adult passenger mapping in the example above and contains no `act_19` or
reservation path.

### Offline reservation-attempt response parsing

`parse_reservation_attempt_response()` is a pure offline parser for the
documented reservation-attempt response shape
(`resultMap`/`reservListMap`/`trainListMap`/`commandMap`). It accepts
caller-supplied JSON and returns a typed `ReservationAttemptResult` for a
complete success shape; malformed or rejected shapes raise the existing
protocol/app error types. Server message, temporary job sequence, command map,
and the raw mapping are excluded from `repr()`. This parser itself adds no
route, request builder, NetFunnel `act_19` flow, client method, or live call,
and leaves the reviewed 20-route read-only boundary unchanged; the reservation
surface described next was added separately.

### Consent-gated mutation surface

Two consent-gated methods are implemented and offline-tested (three, counting
`reserve_transfer`, the 환승 half of `reserve` on the same endpoint — see the
reservation variants and transfer sections below):

- `reserve` (`arc/selectListArc05013_n.do`, `jobId=1101` personal) previews by
  default. Given a `dry_run=False` reserve consent it transmits and returns an
  `SrtReservationHold` whose `pnr_no` feeds `cancel`. It obtains its NetFunnel
  key from the **same `act_10` flow as train search** (srtgo `srt.py:987`; *not*
  `act_19`), reusing `_get_act10_key` rather than a second acquisition path; a
  caller-supplied `netfunnel_key` is honoured verbatim and suppresses the
  acquisition. A failed reserve is never retried, so at most one hold can exist
  per call. If strict parsing trips over an unrelated malformed field after the
  server has already created the hold, a degraded but **cancelable** hold is
  returned rather than raising — losing a PNR is the worst outcome this method
  can produce. Its live NetFunnel/referer wiring was accepted by the server in
  the 2026-07-25 round trip below.
- `cancel` (`ard/selectListArd02045_n.do`, unpaid reservation) accepts an
  `SrtReservationHold` or a bare PNR string and previews by default. Given an
  explicit `dry_run=False` cancel consent it transmits, and returns a parsed
  `SrtCancelResult` (a business failure is carried as data, not raised). **Its
  wire shape — the route, the `pnrNo`/`jrnyCnt="1"`/`rsvChgTno="0"` body and the
  `strResult == "SUCC"` success rule — was verified against the live server on
  2026-07-25**, answering `SUCC` / `msgCd=IRG000000` / `정상처리되었습니다` and
  leaving no trace of the reservation in the ticket list. That shape came from
  srtgo and is 0-hit across all 21,673 files of our v2.0.41 offline bundle
  (only the `jrnyCnt="1"` value is partially corroborated by our own app,
  `ara0101v.js:92`), so the single live run is its only corroboration — and it
  exercised one adult on a **single journey**, which is the only case for which
  `jrnyCnt="1"` is confirmed.

The live verification was two runs of
`scripts/verify_reserve_cancel_roundtrip.py` against a real account, each one
adult, general seat, one train: 수서→부산 on 2026-07-25 and 수서→천안아산 on
2026-07-26. Both returned the same codes — `reserve` `strResult=SUCC`,
`msgCd=IRR000018` ("결제하지 않으면 예약이 취소됩니다.") and a PNR; `cancel`
`strResult=SUCC`, `msgCd=IRG000000` ("정상처리되었습니다") — and in both the
ticket list re-read afterwards contained no trace of the hold. Neither hold was
paid, so nothing was charged, and none was left outstanding. The second run also
independently confirms the route on a different origin-destination pair.

Since 2026-07-26 the cancel body is no longer srtgo's word alone: the ticket-list
page the LIVE server renders ships the call inline
(`function cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt)` POSTing exactly
`pnrNo`/`rsvChgTno`/`jrnyCnt` to `/ard/selectListArd02045_n.do` and reading
`data.resultMap[0].strResult`), so the route, all three field names and the
response envelope are attested by the app itself. It is labelled 예약대기 취소,
so it corroborates the wire shape rather than the exact use, and the
0-hit-in-v2.0.41 fact above still stands. Incidentally, those two confirmation
codes are the same ones korail's live-verified reserve and cancel return, which
suggests the two operators share a reservation platform — an observation, not a
proven fact about the backend. Not covered by that run: multi-leg (`jrnyCnt` >
1), group, standby, and anything to do with payment or refund.

### Reservation variants: standby, round trip (bundle-evidenced, NOT live-verified)

These two are the opposite case from payment and refund. Payment and refund had
to be built from srtgo's attestation because their routes are **0-hit** in our
v2.0.41 bundle. Both variants below are evidenced **in our own bundle**, so they
were built from it and srtgo is only a cross-check. **Neither has been
live-verified.** Both preview by default and ride the existing `reserve` consent
category — `SRT_LIVE_MUTATION_CATEGORIES` is unchanged at
`{"reserve", "cancel", "payment", "refund"}`.

There was a third variant here, 단체 (group), and it was removed on 2026-07-26.
What was learned before removing it is kept in full below, under
"단체 (group) booking: removed".

The app documents all three of its job types in a single comment on its own
reservation form seed (`ara0101v.js:90`):
`"jobId" : "1101"  //조정구분코드(1101:개인예약, 1102:예약대기, 1103:시트맵예약)`.

**Standby — `reserve(train, standby=True)`, `jobId=1102` (예약대기).** Three
fields move together, all from the one branch that produces `1102`
(`ara1001l.js:1445-1448`): `jobId` becomes `1102`, `psrmClCd1` is forced to `1`
(일반실 — `:1431` is the only line that can pair a 예약대기 row with a cabin
class, and the 특실 branch beside it tests only the two 예약가능 images), and
`reserveType` is dropped (srtgo sets it for personal only, `srt.py:990-991`).
`stndFlg` stays `"N"`: that is 입석여부, a different concept.

> **Where the bundle and srtgo disagree, and the bundle wins.** srtgo picks
> standby off `rsvWaitPsbCd >= 0`. Our app never reads that column for the
> decision — it reads the selected row's general-cabin **image**
> (`gnrmRsvPsbImg == "IMAGE::grd_WF_Waiting.png"`, or the `_S` spelling the app
> rewrites it to on tap). The two are not interchangeable: the group search
> `Ara10082` omits `rsvWaitPsbCd` entirely, as our own fixtures show, while
> `gnrmRsvPsbImg` is present on both personal and group rows. A row carrying a
> *different* image is refused; a row carrying **no** image column is accepted,
> because absence is not ineligibility.

srtgo also POSTs `/ata/selectListAta01135_n.do` afterwards to set standby
SMS/seat-change options. That route is **0-hit** in our bundle and has no
equivalent in it, so it is deliberately **not** implemented; a standby entry
made here carries the server's defaults.

**Round trip — `reserve(train, round_trip=True)`, `rtnDv=1` (왕복).** The entire
wire delta is that one flag. SRT does not model a round trip as a multi-leg
reservation; it models it as 오는열차. The app reserves the 가는열차, stores the
result, re-searches with the **stations swapped** and the `back_dptDt1` /
`back_dptTm1` date and time, then reserves the 오는열차 as a **second, separate
POST to the same endpoint** whose leg-1 fields are overwritten with the return
train (`ara1001l.js:1454-1470`, `:1580-1596`). So the public API is two ordinary
`reserve` calls, both with `round_trip=True`, with
`TrainSearchQuery.for_return_leg(date, time)` building the swapped return query.
Keeping it two calls preserves the property `reserve` is built around: one call
creates at most one hold, so a failure strands at most one. **The caller owns
both PNRs.**

> **`jrnyCnt` does NOT become `"2"` for a round trip.** `jrnyCnt` has three hits
> in the whole bundle: the seed `"1"` (`ara0101v.js:92`), a null-check read
> (`ara1001l.js:1654`), and exactly one write — the **환승 (transfer)** toggle,
> which sets `jrnyCnt="2"` together with `jrnyTpCd="14"` (`ara0101v.js:288-311`).
> Nothing on the 왕복 path touches it, and 환승 + 왕복 is mutually exclusive
> anyway. By extension the `...2` suffix in this form family indexes the **여정
> (journey) slot** — the app's own gloss is `여정일련번호1(001:선행, 002:후행)`
> (`ara0101v.js:97`, echoed at `ara1001l.js:1607`) — so slot 2 is a transfer's
> *following* leg. A round trip never fills it. It is certainly not a second
> passenger; passengers live in `psgTpCd1..5`, indexed by passenger **type**.

Also unverified for round trip: whether the server *links* the two holds. The
app carries the outbound result forward in `go_baseDsXml` / `go_seatDsXml`
(`ara0101v.js:143-144`), which is not reproducible from a search row. Treat the
two as independent holds until a live run says otherwise.

**`jobId=1103` (시트맵예약) is deliberately not implemented.** The value is
evidenced (`ara0101v.js:90`, `ara1001l.js:1436`) but the request it belongs to is
not. `1103` is set on the ARC0201C branch, which navigates to the seat-map page
(`/arc/selectListArc02012_n.do` — already read-only here as `get_seat_page`) and
hands off to a `fn_submit()` whose only hit in the entire 21,673-file bundle is
the call site itself (`ara0101v.js:882`); its definition is in the
server-rendered page. Neither the submit target nor the body is knowable
offline. What *is* visible is the extra field family it carries
(`seatNo1_1..N` from the picked seat names, `scarGridcnt1`/`scarGridcnt2`,
`scarNo1`/`scarNo2`, `ara0101v.js:871-878`), recorded in
`payloads.RESERVE_SEATMAP_JOBID` so that "not implemented" is not mistaken for
"not known about".

**What an operator must do to verify each of these.** Each is a real state
change on a real account.

- **Standby.** Find a train whose search row's `gnrmRsvPsbImg` is
  `IMAGE::grd_WF_Waiting.png` (a sold-out peak departure), preview
  `reserve(train, standby=True)` first, then send it with a `dry_run=False`
  reserve consent and **keep the PNR**. Confirm `jobId=1102` and the absence of
  `reserveType` on the request, then release it with `cancel` and re-read
  `get_reservations`. `scripts/recover_hold.py` is the safety net.
  `scripts/verify_reserve_cancel_roundtrip.py` cannot be used unmodified: it
  filters *to* reservable trains, which is the opposite of what standby needs.
- **Round trip.** Two reserves and two cancels: `reserve(outbound,
  round_trip=True)`, then `search_trains(query.for_return_leg(date))`, then
  `reserve(inbound, round_trip=True)`. Record **both** PNRs before doing
  anything else, then cancel both and confirm the list is empty. Worth checking
  explicitly: whether the second reserve succeeds at all without the app's
  `go_baseDsXml` hand-off, and whether cancelling one leg affects the other.

### 단체 (group) booking: removed

`reserve_group(...)` and `payloads.group_reservation_payload(...)` existed here
until **2026-07-26**, when they were **deliberately removed** along with the
route registration for `arc/selectListArc06014_n.do`. The request they built was
correct. It is what the endpoint *answers with* that put group booking out of
scope for this library.

**`search_group_trains(...)` is untouched and stays.** It is a read, it works,
it predates the booking code, and group availability and fares are worth looking
up even when this client cannot complete the booking. The ≥10 party floor
(`payloads.GROUP_MIN_PARTY_SIZE`) stays with it, because the app enforces the
same number on the search (`ara0101v.js:551-554`, "단체예약은 10매 이상입니다.";
the converse at `:562-566` pushes any party over 9 *into* group booking, so 10
is a two-sided boundary and not a hint).

**1. `psgGridcnt`, not an account entitlement, was the wrapper error.** The
booking page's group branch sets **both** `grpDv="1"` **and** `psgGridcnt="2"`.
This library derives `psgGridcnt` from the count of distinct passenger *types*,
which is `1` for ten adults. That single mismatch is what produced the
wrapper-level

```json
{"ERROR_CODE": "-1", "ERROR_MSG": "조회 중 에러가 발생 하였습니다..."}
```

The first reading of that error — that the account lacked a 단체 entitlement —
was **wrong**. The alternative it was weighed against, an undisclosed
group-only field, was right.

**2. With `psgGridcnt="2"` the route answers with a payment page, and creates
nothing.** `Arc06014` returns a **66 KB server-rendered HTML page** headed
`단체승차권 직통 / 예약내역 페이지` — not JSON. It carries
`<form id="ata0201cForm">`, the functions `goToPay` and `kakaoPayReturn`,
`tmpJobSqno` six times, and a post target of **`/ata/selectListAta01033_n.do`**.
That is a *payment* route, and it is **not** the `Ata09036` this library
implements for personal payment.

So 단체 is structurally a different product: reserve and pay are **one flow
keyed by `tmpJobSqno`**, not a cancelable PNR hold followed by a separate
payment. There is no reservation object at that step for `cancel` to act on,
because there is no reservation.

**3. The recorded "uncancellable ten-seat hold" risk did not exist — this
corrects it.** Earlier revisions of this document warned that a live group
attempt could strand an unreleasable ten-seat hold, on the reasoning that the
app forces `pnrNo = -1` for a group and identifies it by `resultMap.tmpJobSqno1`
(`ara1001l.js:1597-1610`). The bundle reading was right; the conclusion drawn
from it was not. **Nothing is held.** The route creates no reservation at all,
so there was never anything to strand. The warning is corrected here rather than
deleted, so a future reader does not re-inherit a fear that was disproved.

**What bringing group booking back would take.** Not a revert — the deleted code
would send a correct request to a route that cannot answer it usefully. It
needs, in order:

1. `psgGridcnt="2"` on the group branch (this library derives it from the
   passenger-type count, so it is a group-specific override, not a fix);
2. **a second payment surface**: `/ata/selectListAta01033_n.do`, whose form is
   `ata0201cForm` on the returned page, with `tmpJobSqno` as the identifier
   instead of a PNR. `Ata09036` cannot be reused;
3. **an HTML page parser** for a 66 KB server-rendered response, where every
   other mutation here parses JSON;
4. **a story for KakaoPay**, whose `kakaoPayReturn` hook suggests at least one
   path that leaves an HTTP client entirely;
5. re-registering `arc/selectListArc06014_n.do` in `SRT_MUTATION_ROUTES` and
   `SRT_MUTATION_ROUTE_CATEGORIES` — and deciding, deliberately, whether a flow
   that pays in the same step still belongs to the `reserve` category or needs
   `payment` consent as well.

The payment step was **never attempted**: `Ata01033` is unimplemented, a group
fare is ten seats' worth of real money, and the KakaoPay hooks point off-client.
None of that is a blocker in principle. It is simply a second payment
implementation plus an external redirect flow, for a booking type with a
ten-person minimum — which is why it is out of scope.

### Transfer (환승): the one shape SRT reserves as two journeys in one request

`search_transfer_trains(query)` and `reserve_transfer(itinerary, ...)`.
**Bundle-evidenced request, NOT live-verified — no transfer search or
reservation has ever been sent from this library.** `reserve_transfer` POSTs the
**same** endpoint as `reserve` (`arc/selectListArc05013_n.do`) under the **same**
`reserve` consent category; no route and no category was added, and
`SRT_LIVE_MUTATION_CATEGORIES` is untouched at
`{"reserve", "cancel", "payment", "refund"}`.

A transfer is the opposite of a round trip, and the pair is worth holding side
by side:

| | 왕복 (round trip) | 환승 (transfer) |
| --- | --- | --- |
| `jrnyTpCd` | `11` (편도) | `14` (환승편도) |
| `jrnyCnt` | `1` | **`2`** |
| requests | **two** reserves, one journey each | **one** reserve, two journeys |
| journey slot 2 | never filled | the 후행 leg |
| flag | `rtnDv=1` | `rtnDv` stays `0` |

`jrnyCnt="2"` has **exactly one write in the entire v2.0.41 bundle**: the 환승
toggle, which sets it together with `jrnyTpCd="14"` in a single `lfn_setRsv`
call (`ara0101v.js:302-303`, emitted at `:310-311`). The other two hits are the
seed `"1"` (`:92`) and a null-check read (`ara1001l.js:1654`). The app's own code
table names both values — `11` 편도 / rmk 직통, `14` 환승편도 / rmk 환승
(`commCode.js:296-309`) — and the slot vocabulary is glossed inline:
`"jrnySqno1" : "001"  //여정일련번호1(001:선행, 002:후행)` (`ara0101v.js:97`,
repeated at `ara1001l.js:1607`). So **slot 1 is 선행, slot 2 is 후행**.

**Search — same endpoint, one field.** `chtnDvCd` goes from `"1"` (직통) to
`"2"` (환승). The app derives it itself:

```js
var sChtnDvCd = lfn_getRsv("jrnyTpCd") == "11" ? "1" : "2"; //직통:1, 환승:2
```

(`ara1001l.js:98`, sent at `:159`.) The URL does **not** change with it —
`:174-181` picks the endpoint from `grpDv` alone, so 직통 and 환승 share
`/ara/selectListAra10007_n.do`. `chtnDvCd` is also a **column on every returned
row** (`ara1001l.js:1206` reads `item.chtnDvCd`), kept on `TrainSummary.raw`.

**The response is ONE ROW PER LEG — live-confirmed 2026-07-26.** The bundle
could not have told us: `fn_postSearch` (`ara1001l.js:384-460`) renders one
single-leg `<tr>` per row with no transfer branch, `fn_moveRsv` (`:1453-1468`)
writes only slot 1, `fn_validChk` (`:1649-1700`) validates only slot 1 under a
`//직통` heading, and the 환승 list itself is server-rendered (the stylesheet
keeps its taller two-row card with a layover band, `.time_Difference`,
`.timeDiff`, `custom.css:4412`, `:4431`). A read-only probe of 동대구(`0015`) →
광주송정(`0036`) settled it: 10 ordinary `dsOutput1` rows, every one with
`chtnDvCd="2"`, with the legs of one itinerary **sharing a `trnOrdrNo`**:

| `trnOrdrNo` | train | leg | times |
| --- | --- | --- | --- |
| 1 | 382 | 동대구 → 오송 | 085200 → 095100 |
| 1 | 411 | 오송 → 광주송정 | 100600 → 110500 |
| 2 | 14 | 동대구 → 천안아산 | 085800 → 100900 |
| 2 | 475 | 천안아산 → 광주송정 | 102500 → 125000 |
| 3 | 316 | 동대구 → 오송 | 091600 → 101500 |
| 3 | 655 | 오송 → 광주송정 | 103100 → 113100 |

So `trnOrdrNo` is the **itinerary index** here. The `...2` columns *do* exist on
every row and are **empty strings** (`trnNo2: ""`, `dptRsStnCd2: ""`,
`jrnySqno: ""`) — because the second leg is a separate ROW, not a set of
columns. `fllwPgExt2` was `null`.

`search_transfer_trains` therefore returns a `TransferSearchResult`:

```python
result = client.search_transfer_trains(query)
result.itineraries      # tuple[TransferItinerary, ...] — ready for reserve_transfer
result.unpaired         # groups that did NOT fit, each with a .reason
result.search           # the untouched TrainSearchResult
result.rows, result.raw # the ungrouped rows and the raw JSON
```

> **The grouping is our inference layer, and it is built to fail loudly.**
> `pair_transfer_itineraries` groups by `trnOrdrNo` and requires exactly two
> rows per itinerary.
> - **Leg order comes from the STATIONS, never the row position.** The probe
>   happened to deliver the legs in order, but that is one observation and not a
>   guarantee, and pairing them backwards builds a *clean* reservation that books
>   the journey in reverse. Both orientations are offered to `TransferItinerary`
>   and the one that validates wins, so "is this an itinerary?" has exactly one
>   implementation.
> - **A group that does not fit is set aside, not dropped and not forced.** Wrong
>   row count, legs that do not connect or run backwards, or an ambiguous order
>   all land in `result.unpaired` with a reason. Losing an itinerary silently
>   hides a journey; handing back a mispaired one produces a reservation whose
>   two slots are not one journey and which the server would accept. The second
>   is worse, so nothing is invented and nothing is discarded.
> - **Unless NOTHING pairs.** Rows present and zero itineraries means this
>   grouping rule is wrong for the response in hand, not that the server sent ten
>   broken itineraries — that raises `SrtProtocolError` carrying `raw`, because
>   an empty list would be the one genuinely silent failure available here. An
>   empty response is not that case.
>
> `iter_train_search_pages` is still **not** extended to transfer: the probe
> returned `fllwPgExt2` as `null` just as every direct search does, so what the
> second cursor is *for* remains unobserved and nothing in the bundle reads it.

**`TransferItinerary` is what stops you booking half a journey.** A transfer
search row is an ordinary `TrainSummary` — `reserve(row)` would accept it and
produce a real, successful-looking PNR to the 환승역 and no further. So
`reserve_transfer` takes **only** a `TransferItinerary(first_leg=…,
second_leg=…)`, which validates the join at construction (and which the pairing
above already ran, so anything in `result.itineraries` is ready as it stands): both legs exactly
`TrainSummary`, the first must **arrive where the second departs**, the second
must not depart before the first arrives (the comparison the app applies to the
왕복 second leg, `ara1001l.js:1258-1272`), and the two must not be the same
train. The app states the rule itself, in a message string it ships and never
references because the screen that would raise it is server-rendered
(`messages.js:217`, `rsv023`):

> 선택하신 열차는 선행 및 후행 열차를 모두 선택하셔야 예약이 가능합니다.

```python
itinerary = TransferItinerary(first_leg=rows[0], second_leg=rows[1])
preview = client.reserve_transfer(itinerary, consent=MutationConsent(allow_reserve=True))
```

**The reservation form** is the personal form with two values changed
(`jrnyTpCd` → `14`, `jrnyCnt` → `2`) and one slot appended. Slot 1 keeps its
exact keys, values **and order**; the 23 slot-2 keys are appended after it:

`jrnySqno2` `stlbTrnClsfCd2` `dptRsStnCd2` `dptRsStnCdNm2` `arvRsStnCd2`
`arvRsStnCdNm2` `dptDt2` `dptTm2` `arvDt2` `arvTm2` `trnNo2` `runDt2`
`dptStnConsOrdr2` `arvStnConsOrdr2` `dptStnRunOrdr2` `arvStnRunOrdr2` `trnGpCd2`
`psrmClCd2` `locSeatAttCd2` `rqSeatAttCd2` `dirSeatAttCd2` `smkSeatAttCd2`
`etcSeatAttCd2`

> **How each slot-2 key is known — evidenced vs inferred.** The server-rendered
> `#rsvForm` is not in the bundle (the app POSTs `$("#rsvForm").serialize()`,
> `ara1001l.js:1550`), so this is graded per key in
> `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` and pinned by a test.
>
> - **web bundle** — the literal `...2` string is in the offline JS.
>   `dptRsStnCd2`, `arvRsStnCd2`, `runDt2`, `trnNo2` are the 운임요금 params the
>   app sends blank for a direct journey (`ara1001l.js:1209-1216`), and the LIVE
>   fare page renders a whole second leg from them with its own
>   `selectTransferTrain()` toggle (captured 2026-07-26, reproduced at
>   `tests/fixtures/fare_transfer_placeholder.html`). `smkSeatAttCd2`,
>   `dirSeatAttCd2`, `locSeatAttCd2`, `rqSeatAttCd2`, `etcSeatAttCd2` are seeded
>   at `ara0101v.js:136-140` and written at `:775-777`.
> - **native** — the literal `...2` string is in the app's own two-leg model:
>   the offline-ticket parser at
>   `analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:746-834`, switched
>   on by `isTransfer == "true"` (`:815`). It reads `psrmClCd2` (`:785`),
>   `dptDt2` (`:791`), `dptTm2` (`:794`), `arvDt2` (`:800`), `arvTm2` (`:803`),
>   plus `seatNo2`/`scarNo2`/`trnNo2`/`stlbTrnClsfNm2`/`dptRsStnNm2`/
>   `arvRsStnNm2`. The matching layout ships a 수서 → **천안아산** → 부산
>   placeholder (`analysis/apktool/res/layout/listview_offline_detail_item.xml`).
> - **hydrated** — zero hits in the bundle; already sent on the Ara10007
>   hydration GET by `search_page_payload` (which the live server has accepted on
>   every run) and listed as a booking-page hidden input by the 2026-07-09
>   survey: `jrnySqno2`, `trnGpCd2`, `dptRsStnCdNm2`, `arvRsStnCdNm2`.
> - **INFERRED** — zero hits in any form; slot 1's name with the suffix changed:
>   **`stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`, `dptStnRunOrdr2`,
>   `arvStnRunOrdr2`**. These five are the ones a live run has to settle.
>
> **The 2026-07-26 live search did NOT move any tier, and that is the point.** It
> settled the *response*, and it showed that a search ROW carries `...2` columns
> as empty strings. They are blank because the second leg arrives as its own row,
> so there is nothing for them to hold — which says nothing whatsoever about
> whether the *reservation form* wants them filled. A response column and a
> request field that share a name are still two different things, and only a
> **reserve** capture can settle the request side.

**What composes with transfer, and what does not.**

| feature | with 환승? | evidence |
| --- | --- | --- |
| passenger mix | **yes**, one party for both legs | `psgTpCd1..5` is indexed by passenger TYPE, not by journey slot (`ara0101v.js:117-127`, compacted `:824-836`) |
| seat option (`seat_type`, `window_seat`) | **yes**, one preference for both legs | the 좌석옵션 callback writes slot 1 and then the identical `...2` quartet from the same values (`ara0101v.js:769-778`) |
| 왕복 round trip | **no** | refused in both directions with "환승은 왕복예약이 불가능 합니다." (`ara0101v.js:296-299` and `:331-334`) |
| 예약대기 standby | **not implemented** | `jobId=1102` is chosen from ONE row's image (`ara1001l.js:1445-1448`); a transfer has two rows and the app has no rule for one-leg-only standby |
| 단체 group | **not implemented** | the app *does* model 단체환승 (`eventTrainInfo.js:12`, `:19`; ticket kind 환승단체권 `tkKndCd` 27, `commCode.js:1591-1596`) and forbids it nowhere — but this library does not book 단체 at all since 2026-07-26, so there is no group half to compose with (see "단체 (group) booking: removed") |
| 좌석지정 seat selection | **not implemented** | 좌석지정 explicitly BLANKS slot 2: `scarGridcnt2 = 0`, `scarNo2 = ""` (`ara0101v.js:875-879`), and nothing ever fills them |
| non-SRT (KTX) leg | **refused** | both legs must be `stlbTrnClsfCd == "17"`, the same guard `reserve` has always applied. SRT→SRT transfers only |

> One honest counter-note on the 왕복 exclusion: the app's ticket-kind table
> *does* contain 환승단체왕편권 / 환승단체복편권 (`tkKndCd` 28/29,
> `commCode.js:1597-1612`), so such a ticket exists as an SRT product. The
> refusal above is a **client-side booking rule in this app**; it is not proof
> the server would refuse. We send what the app sends.

**Two things left unchanged on purpose.** `fare_payload` still hard-codes
`chtnDvCd="1"` and blank `dptRsStnCd2`/`arvRsStnCd2`/`runDt2`/`trnNo2` — a
transfer fare lookup would fill them, and `parse_fare_page` would then need to
stop discarding the second table, which is a separate change with its own live
capture. And `cancel` still defaults to `jrnyCnt="1"`.

> **Cancelling a transfer hold needs `journey_count="2"`.** `cancel(hold,
> journey_count="2", consent=…)` — the parameter already exists and was not
> touched, but its **default is wrong for this shape**, and getting it wrong is
> how a hold survives a cancel that looked like it worked. Verify with
> `get_reservations` afterwards, every time.

#### What an operator must do to live-verify transfer

**The precondition is a station pair SRT does not serve directly** — without one
there is no transfer itinerary to find, and this is the single thing that makes
the whole feature testable. SRT runs two lines that meet only at **오송**
(`0297`): 경부선 through 대전 (`0010`) / 동대구 (`0015`) / 부산 (`0020`), and
호남선 through 익산 (`0030`) / 광주송정 (`0036`) / 목포 (`0041`). Any pair with
one station on each line has **no direct SRT train** and must connect. Good
candidates:

- **동대구 (`0015`) → 광주송정 (`0036`)**
- **부산 (`0020`) → 목포 (`0041`)**
- **대전 (`0010`) → 광주송정 (`0036`)** — 대전 is 경부선-only for SRT

A 수서-origin route is the wrong test: 수서→광주송정 and 수서→부산 are both
direct, so `chtnDvCd=2` would return nothing and prove nothing.

1. **The search is already done — 2026-07-26, read-only.** `search_trains` on
   동대구→광주송정 answered `WRD000061` ("직통열차는 없지만, 환승으로 조회
   가능합니다."), now raised as `SrtNoDirectTrainError`, and
   `search_transfer_trains` on the same query returned three well-formed
   itineraries. Re-running it costs nothing and is the cheapest way to confirm
   the account and the date are usable. Check `result.unpaired` is empty; if it
   is not, capture it — the grouping rule met something it has not seen.
2. **Everything left to settle is on the REQUEST side.** The search shape is
   confirmed; the reservation form is not. Nothing below can be learned from
   another search.
3. **Preview the reservation before anything else.** Build the
   `TransferItinerary` from two rows and call `reserve_transfer(...)` with the
   default `dry_run=True`. Check the preview: `jrnyTpCd=14`, `jrnyCnt=2`,
   `jrnySqno1=001`, `jrnySqno2=002`, `rtnDv=0`, and that slot 2 really carries
   the **second** train and not a copy of the first.
4. **Send it, and keep the PNR before doing anything else.** `dry_run=False` with
   a reserve consent creates a **real unpaid hold on a real account**. If the
   server rejects the body, the first field to suspect is **`reserveType`**: we
   send `"11"` (srtgo-only, 0 hits in our bundle, `srt.py:990-991`) and it is not
   known whether it tracks `jrnyTpCd` — if it does, a transfer wants `"14"`. The
   five INFERRED slot-2 key names above are the second thing to suspect.
5. **Cancel with `journey_count="2"`**, then re-read `get_reservations` and
   confirm the account is empty. If the `"2"` cancel fails, retry with the
   default `"1"` and record which one the server accepted — that is itself a
   finding. `scripts/recover_hold.py` releases a hold from the PNR string alone
   and is the safety net.
6. **Do not pay.** Nothing here needs a payment to be verified, and a paid
   transfer ticket is a refund away from a mess.

### Live payment->refund verification (operator-run, 2026-07-26)

Payment and refund were verified separately, on the same day and in the same
spirit: a charge and its reversal, as one round trip, so nothing could be
stranded paid. **A free probe went first** — a fake card and a non-existent PNR
were sent to both routes, and neither answered a 404 or an HTML error shell.
`/atc/getListAtc14087.do` returned
`{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"WRT300005",
"strResult":"FAIL","msgTxt":"조회자료가 없습니다."}]},"ErrorMsg":""}` and the
payment route returned `strResult=FAIL` / `msgCd=WRT100170`. Proper business
envelopes on both, which established the routes exist on our app version without
spending anything.

**Then one real round trip:** 수서→동탄 (`0551`→`0552`, the shortest SRT hop),
2026-08-09, train 315, one adult, 7,500 KRW. The payment answered `strResult=SUCC`
/ `msgCd=IRT000000`; the two-step refund answered `strResult=SUCC` /
`msgCd=IRT200277`; the account was then verified empty of both reservations and
tickets from a separate session. `IRT000000` and `IRT200277` are korail's codes
for the same two operations — the same shared-platform observation as above, and
still an observation about the codes rather than a proven claim about the
backend. It also settled srtgo's disputed refund spellings `tkRetPwd`/`psgNm`:
they are the ones the server takes, unlike srtgo's korail `txtPrnNo`, which this
project found to be a genuine typo.

**What that run did not settle.** Both wire formats are still 0-hit across all
21,673 files of the v2.0.41 offline evidence bundle, our own app still charges
through the `Ard02017`/`Ard02018` WebView plus TransKey and FIDO, and the run
covered exactly one single-journey, one-adult, general-seat ticket paid with one
personal card in one lump sum. Multi-leg, group, standby, corporate cards and
instalments were not exercised. Native-bridge and external seat-map flows remain
excluded entirely.

Each of the four categories may reach the network only through
`post_mutation_form`, only under its own explicit consent with `dry_run=False`,
and only onto its own route: `post_mutation_form` and `_send_mutation_request`
both refuse any category outside `safety.SRT_LIVE_MUTATION_CATEGORIES` and both
apply the route/category binding, the read-only guard refuses all four routes by
allowlist, and card secret fields may travel only as a `payment`.
