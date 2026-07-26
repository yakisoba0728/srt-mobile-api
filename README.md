# srt-mobile-api

This repository provides an installable read-only-by-default Python package for
the evidenced SRT Android app WebView API surface. Nothing is transmitted
without an explicit, per-category `MutationConsent` with `dry_run=False`: by
default the client transmits only login/read requests, and a mutation method
returns a redacted `MutationPreview` of the exact form that would be POSTed.

Two consent-gated mutation methods exist, `reserve` and `cancel`. Both preview
by default and both transmit when given an explicit `dry_run=False` consent for
their own category. A live `reserve` creates a **real unpaid hold on a real
account**, which the caller then owns. **One live reserve->cancel round trip was
performed on 2026-07-25** and both halves succeeded — reserve
`strResult=SUCC`/`msgCd=IRR000018`, cancel `strResult=SUCC`/`msgCd=IRG000000`,
with no trace of the reservation left in the ticket list. It covered one adult,
one journey, a general seat, one train; nothing broader is claimed.

A third consent-gated method, `pay_with_card`, exists and **cannot transmit**.
`payment` is not in `SRT_LIVE_MUTATION_CATEGORIES`, so it can only ever return a
redacted preview; implementing it did not open that gate, and a test pins that a
consent opting into everything — including one that acknowledges a real,
chargeable card — still sends nothing. Its wire format is the least corroborated
in this repository: see "Card payment" below before trusting any of it.

`refund` and its step-1 read `get_refund_ticket_info` exist on the same terms,
with evidence thinner still — see "Refund" below. `refund` cannot transmit
either, and a refused refund makes **no request at all**, not even the step-1
read, because the two steps are deliberately separate methods.

Which mutations may reach the network at all is enforced at the transport
layer, by two different mechanisms which are worth keeping distinct:

- the read-only send path refuses the four mutation routes **by allowlist** —
  they are deliberately not in `READ_ONLY_ROUTES`, so `assert_read_only_request`
  rejects them;
- `post_mutation_form`, the only method that can send a state-changing request,
  refuses every category outside `safety.SRT_LIVE_MUTATION_CATEGORIES`, which
  holds **exactly `{"reserve", "cancel"}`**. So `payment` and `refund` are
  rejected however permissive the caller's consent is — including a consent
  that acknowledges a real card — and that refusal, not the presence or absence
  of a client method, is what holds the line. It separately refuses a
  `dry_run=True` consent, so a
  preview can never be transmitted either. `_send_mutation_request`, the
  function that actually calls `send`, re-asserts the same membership.

`reserve` and `cancel` are enabled together because they are the two halves of
one reversible operation: reserve creates an unpaid hold, cancel releases one
(from a hold object or a bare PNR string). Enabling reserve alone would mean a
crash mid-flow strands a real reservation with no programmatic way out. Opening
that gate was a decision about **recoverability, not evidence** — it is what
made the operator-run reserve->cancel round trip possible, and that round trip
has since been run once (2026-07-25, see below). Adding `payment` or `refund` to
that set would require live-verifying each one's own wire format — a thing no
one has done, and which this library cannot do for itself. The
retained APK specification and smoke tooling remain the evidence context for
that package.

The reviewed safety boundary contains 22 routes. The integrated 0.2.0 gate
recorded `587 passed, 1 deselected` (historical); after the additive
reservation-attempt response parser, the consent-gated reserve mutation
surface, the transport-layer live-mutation gate, the consent-gated cancel
surface, the two-category live enablement, the operator scripts, the
reservation-list read, the NetFunnel queue protocol, the error taxonomy, the
real-card acknowledgement gate and the consent-gated card-payment and refund
surfaces
landed, the current offline suite at HEAD is
`1249 passed, 1 deselected`. The deselected case is the
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

### Card payment (preview only, and the weakest evidence here)

`SrtClient.pay_with_card(reservation, card, consent=...)` builds the 카드결제
form for `POST /ata/selectListAta09036_n.do` from an `SrtReservationSummary` row
and an `SrtPaymentCard`. **It cannot transmit.** `payment` is not in
`SRT_LIVE_MUTATION_CATEGORIES`, so the method returns a redacted
`MutationPreview` and a `dry_run=False` call is refused at the transport layer.

**Read this before trusting a single field.** This surface is less corroborated
than anything else in the repository, in three separate ways:

- **the route is not in our app.** `/ata/selectListAta09036_n.do` has zero hits
  across all 21,673 files of our v2.0.41 offline decompile, as does the token
  `Ata09036` and every `Ata09*` route. The only `/ata/` route the bundle
  contains is `/ata/selectListAta01032_n.do`;
- **our app pays a different way.** `ara1001l.js:1550` serialises `#rsvForm` and
  `:1599`/`:1608` point it at `/ard/selectListArd02018_n.do` (group) or
  `/ard/selectListArd02017_n.do` (personal) — server-rendered WebView pages —
  and the charge then goes through the TransKey secure keypad
  (`AndroidManifest.xml:143`, `bridge.js:2,31,66-68`) and RaonSecure FIDO
  (`AndroidManifest.xml:315`). None of that is plain HTTP form fields. So this
  endpoint may be a legacy path the server still honours, or it may be dead for
  our app version. **Nobody has tested it**;
- **the two reference libraries are one source, not two.** This was verified,
  not assumed. srtgo's 32-field payment dict is character-for-character
  identical to ryanking13/SRT's once the latter's Korean trailing comments are
  stripped — same keys, same values, same non-alphabetical order, same local
  variable names, same method signature. srtgo depended on `SRTrain`
  (ryanking13/SRT on PyPI) until commit `8423f90` "Internalize SRT"
  (2024-12-13) deleted the dependency and added `srtgo/srt.py` in one move, with
  the payment dict already fully formed; srtgo's README credits ryanking13 under
  MIT. Their agreement corroborates nothing. (`srtgo_plus` is a third copy.)

What the bundle *does* corroborate is narrower than "nothing", and the blanket
claim that every field name is 0-hit is **false**. Three of the 32 names appear
in our own bundle, all in the reservation JS and none of them on this form:
`mbCrdNo` (`ara0101v.js:319,321`, a client-side 회원카드번호 branched on its
`"11"` prefix), `totPrnb` (`ara1001l.js:104,368,1511,1655`, the 총인원수) and
`jrnyCnt` (`ara0101v.js:92,311`). The other 29 — every card field, every
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

### Refund (two steps, preview only, and the thinnest evidence here)

A 환불 is two calls, exposed as two methods:

1. `SrtClient.get_refund_ticket_info(pnr)` POSTs `/atc/getListAtc14087.do` with
   **no body**, gated by a `Referer` of
   `<base_url>/common/ATC/ATC0201L/view.do?pnrNo=<PNR>`, and returns
   `outDataSets.dsOutput1[0]` — note `dsOutput1`, not the `dsOutput0` every other
   `outDataSets` read here uses — as an `SrtRefundTicketInfo`;
2. `SrtClient.refund(ticket_info, consent=...)` POSTs
   `/atc/selectListAtc02063_n.do`. **It cannot transmit**: `refund` is not in
   `SRT_LIVE_MUTATION_CATEGORIES`.

**They are deliberately not fused into one method.** A combined call would
perform step 1 — a real network request — and only *then* discover step 2 is
refused, leaving a live request behind for an operation that can never complete.
Kept apart, a refused refund sends nothing at all, and a dry run needs no
network because the preview is built from the `ticket_info` the caller already
holds. A test pins the zero-request property.

Step 1 *can* transmit: it is classified as a read and registered in
`READ_ONLY_ROUTES`. That classification is an **inference, not a proof** — the
request carries no body, the response is pure identity data, and the reference
implementation uses it only to gather step-2 fields, but nothing here can prove
the server treats it as side-effect free, and the app's own naming is not
decisive (`/ard/selectListArd02045_n.do` is a *cancel* despite its `selectList`
prefix). Nothing in the refund path calls it for you.

**Provenance is thinner than the payment's.** The payment at least has one
implementation copied into two libraries. This route exists in exactly **one**:
ryanking13/SRT has no refund at all — no `reserve_info`, no `getListAtc14087`,
no `selectListAtc02063`, no `tkRetPwd` — and srtgo added both steps from scratch
four days after vendoring its SRT support (2024-12-17). There is no upstream to
have agreed with it. `Atc02063` and `Atc14087` are 0-hit across all 21,673 files
of our v2.0.41 decompile; the bundle has **no `Atc02*` family whatsoever**, and
the nearest real routes are `Atc14016`/`Atc14017`.

**Two of the seven step-2 field names are disputed, and this project has been
burned here before.** srtgo sends `tkRetPwd` and `psgNm`; our own app spells them
`retPwd` and `buyPsNm` at
`analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:645,648`. That site is
**not an API schema**: it reads the SharedPreferences key `"ticketListOffline"`,
base64-decodes it and parses it as JSON (`b.java:613,624-632`), then copies keys
into a display model — deserialisation of a *local offline ticket cache*. It
also spells the PNR `pnrNo` where srtgo's form says `pnr_no`, a third
disagreement. We send srtgo's spelling, because it is the only one attested by a
live run of *this* endpoint and a cache key is not evidence about it. The doubt
is recorded rather than resolved: if this route is ever exercised and rejected,
`retPwd`/`buyPsNm`/`pnrNo` are the first alternatives to try. The precedent is
concrete — this project already shipped srtgo's misspelling of a korail refund
field, `txtPrnNo` for `txtPnrNo`, from the same class of single-source trust.

Step 1's success condition is **stricter** than this library's usual wrapper
check: `ErrorCode == "0"` **and** `ErrorMsg == ""`, where
`parse_mutual_verification_response` accepts `ErrorCode` in `{"", "0"}` and
ignores the message. Implemented as documented rather than relaxed to house
style — on a route nobody has exercised, failing loudly on a half-recognised
response is the cheap mistake. Step 2's envelope is the *ordinary* `resultMap`
SUCC/FAIL one, the same as cancel's and unlike the payment's.

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

Two consent-gated methods are implemented and offline-tested:

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

Payment and refund now have client methods, and they still cannot transmit —
see "Card payment" and "Refund" above for what that means and how thin the
evidence is. Their wire formats are likewise 0-hit across all 21,673 files of
the v2.0.41 offline evidence bundle, so they need live response capture (see
docs/MUTATION_HANDOFF.md in the korail repo). The 2026-07-25 round trip taught
nothing about either: it never paid the hold, so no payment or refund shape was
observed. Native-bridge and external seat-map flows remain excluded entirely.

Independently of which methods exist, `payment` and `refund` cannot be
transmitted at all: `post_mutation_form` and `_send_mutation_request` both
refuse any category outside `safety.SRT_LIVE_MUTATION_CATEGORIES`, and the
read-only guard refuses all four routes by allowlist.
