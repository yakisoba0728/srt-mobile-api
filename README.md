# srt-mobile-api

This repository provides an installable read-only-by-default Python package for
the evidenced SRT Android app WebView API surface. Nothing is transmitted
without an explicit, per-category `MutationConsent` with `dry_run=False`: by
default the client transmits only login/read requests, and a mutation method
returns a redacted `MutationPreview` of the exact form that would be POSTed.

Five consent-gated mutation methods exist: `reserve`, `reserve_group`, `cancel`,
`pay_with_card` and `refund`, across **four** consent categories —
`reserve_group` is the 단체 half of `reserve`, on its own endpoint. All preview
by default and all transmit when given an explicit `dry_run=False` consent for
their category. Each CATEGORY is live-enabled because a live run answered its own
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
settle. In particular the three reservation VARIANTS — group, standby
(`jobId=1102`) and the round trip (`rtnDv=1`) — are **bundle-evidenced and not
live-verified**; see "Reservation variants" below, which also says why a live
group reservation may not be cancellable from this library.

Which mutations may reach the network at all is enforced at the transport
layer, by two different mechanisms which are worth keeping distinct:

- the read-only send path refuses all five mutation routes **by allowlist** —
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

The reviewed safety boundary contains 22 routes on the read side, plus 5
mutation routes (the 단체 reservation endpoint `arc/selectListArc06014_n.do` is
a second URL for the *existing* `reserve` category, not a fifth category). The
integrated 0.2.0 gate
recorded `587 passed, 1 deselected` (historical); after the additive
reservation-attempt response parser, the consent-gated reserve mutation
surface, the transport-layer live-mutation gate, the consent-gated cancel
surface, the two-category live enablement, the operator scripts, the
reservation-list read, the NetFunnel queue protocol, the error taxonomy, the
real-card acknowledgement gate, the consent-gated card-payment and refund
surfaces, the four-category live enablement and the three bundle-evidenced
reservation variants (group, standby, round trip)
landed, the current offline suite at HEAD is
`1348 passed, 1 deselected`. The deselected case is the
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
which rejects all five mutation routes by construction.

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
single-page calls.

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
prove a stable iterable physical-seat record or availability vocabulary, so
individual physical seats remain untyped.

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
exception messages are never written. Typed cars and physical seats remain
unimplemented until separately authorized response evidence identifies a stable
iterable source and availability vocabulary. Schema-v2 evidence does not
authorize another origin, route, or mutation.

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
DOM sink. It exposes no iterable response schema. Arc02011 is not allowlisted,
there is no closed response parser, and the client neither calls nor implements
it.

The same bounded 2026-07-15 session loaded one seat page from the first
complete personal-search row. The fixed live summary reported the visible
marker, 9 scripts, 3 forms, no iframe, no embedded JSON block, 5 source
categories, and `sufficiency=inventory_source_candidate`; it emitted no raw
HTML or identifiers. A later authorized offline replay produced only the
sanitized fixture described above. Together they prove a candidate source and
the static handoff, not an iterable car/seat response or availability
vocabulary, so typed physical seats remain excluded.

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
`reserve_group`, which is the 단체 half of `reserve` — see the reservation
variants section below):

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

### Reservation variants: group, standby, round trip (bundle-evidenced, NOT live-verified)

These three are the opposite case from payment and refund. Payment and refund
had to be built from srtgo's attestation because their routes are **0-hit** in
our v2.0.41 bundle. All three variants below are evidenced **in our own bundle**,
so they were built from it and srtgo is only a cross-check. **None of the three
has been live-verified.** Every one previews by default and rides the existing
`reserve` consent category — `SRT_LIVE_MUTATION_CATEGORIES` is unchanged at
`{"reserve", "cancel", "payment", "refund"}`.

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

**Group — `reserve_group(...)`, `arc/selectListArc06014_n.do`.** A separate
method, not a flag, because the endpoint changes (`ara1001l.js:1542-1547`), the
precondition changes (the train must come from `search_group_trains`), and the
return value may not mean the same thing (below). The body is the personal form
with `grpDv` flipped to `"1"` and **nothing else** — in particular `jobId` stays
`1101`, because the app picks the job type without ever consulting `grpDv`.
Three of the app's own rules are enforced: **party size ≥ 10**
(`ara0101v.js:551-554`, "단체예약은 10매 이상입니다."; the converse at `:562-566`
pushes any party over 9 *into* group booking, so 10 is a two-sided boundary and
not a hint), **no window/aisle preference** (ticking 단체 resets the seat option
and disables the picker, `:446-457` — so there is no `window_seat` argument to
pass), and **no round trip** (refused at `:348-351`, `:440-443` and `:557-560` —
so there is no `round_trip` argument either).

> **Read before sending one live.** The request is bundle-evidenced; the
> response is **not**, and the bundle suggests it differs. The app hands a group
> reservation to the payment page with `pnrNo` forced to `-1` and identifies it
> by `resultMap.tmpJobSqno1` (임시작업일련번호), where a personal reservation
> passes `reservListMap.pnrNo` (`ara1001l.js:1597-1610`). If a real group
> response carries no PNR, `parse_reservation_hold_response` raises rather than
> inventing a hold, and `cancel` — which takes a PNR — has nothing to act on. A
> live group attempt must therefore be treated as **potentially uncancellable
> from this library**. The parsers were deliberately left untouched: a group
> hold object invented with no live evidence of its shape would be worse than an
> exception.

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
- **Group.** Do this **last and most carefully**, because it is the one that may
  not be cancellable from here. Preview first. Before sending, confirm you can
  reach the account through the SRT app or the call centre. Send it, capture the
  **whole raw response** (including from a raised `SrtProtocolError`), and look
  for `pnrNo` versus `tmpJobSqno1` — that single fact is the most valuable thing
  the run can produce, and it decides whether `cancel` can ever work for a group.
  Then release the hold by whatever means exists.

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
apply the route/category binding, the read-only guard refuses all five routes by
allowlist, and card secret fields may travel only as a `payment`.
