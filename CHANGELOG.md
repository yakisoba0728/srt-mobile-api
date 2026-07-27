# Changelog

## 1.0.0 - 2026-07-27

- **Added: Apache-2.0, owner metadata, canonical URL, and `1.0.0`.** The
  repository now carries a verbatim `LICENSE`, and `pyproject.toml` states the
  license in PEP 639 SPDX form (`license = "Apache-2.0"` plus
  `license-files = ["LICENSE", "NOTICE"]`, no `License ::` classifier — the two
  spellings are mutually exclusive), the owner, and the four project URLs.
  `NOTICE` is named there and not only at the repository root because
  Apache-2.0 §4(d) obliges anyone redistributing this to carry the attribution
  notices forward, which they cannot do from a wheel that omits the file; both
  artifacts now carry it, and the verifier checks the `License-File` header as
  a set rather than as a singleton. The
  build-system floor moved `setuptools>=69` → `>=77`, the first release that
  understands either key. `Development Status` moved from `3 - Alpha` to
  `5 - Production/Stable`, and the version from `0.2.0` to `1.0.0`.
  `srt_mobile_api.__version__` now exists and is held equal to the pyproject
  version by a test; it is deliberately not in `__all__`.
- **Changed: the distribution contract now VERIFIES the new metadata instead
  of forbidding it.** `scripts/verify_distribution.py` used to reject
  `license`/`authors`/`urls` in `pyproject.toml` outright and to blacklist the
  `License-Expression`, `Author-email` and `Project-URL` headers. Simply
  deleting those rules would have shipped the release-blocking metadata
  unchecked, so each was inverted into an exact-value check of the same kind
  `Name`/`Version`/`Requires-Python` already get, derived from
  `pyproject.toml`. `License`, `Author`, `Maintainer`, `Maintainer-email`,
  `Home-page` and `Download-URL` stay forbidden — a correct build emits none of
  them. `LICENSE` joined the required sdist documents, and both archives must
  now carry the checkout's license text byte-for-byte (wheel:
  `<dist-info>/licenses/LICENSE`), so an SPDX header cannot claim a license the
  artifact does not contain. Every new check has an adversarial case that
  violates it.

- **Fixed: a failed refund could read as a successful one.**
  `normalize_result_row` folded a conflicting pair of status rows the wrong
  way. It now prefers `dsOutput0` only when that row actually holds a usable
  one, and when two rows disagree the FAILING one wins. Fail-closed: a refund
  that did not happen must never come back looking like it did.
- **Fixed: 특실 was booked on missing data, and 휠체어석 could not be booked
  at all.** `"예약가능" in (None or "")` is `False`, so a search row that
  carried no availability field at all read as "일반실 is gone" and
  `GENERAL_FIRST` silently booked 특실 — reachable through plain
  `search_trains()` → `reserve()`, and it costs the caller the fare
  difference. A missing field is now distinguished from a sold-out class and
  refused rather than guessed. Separately, both reservation builders wrote the
  literal `"015"` while the search honoured
  `TrainSearchQuery.seat_attr_code`, so 021/028 inventory was searchable and
  then unbookable; the reservation now validates against the three codes SRT
  dispatches on and, when the caller names none, inherits the code the row was
  found with.
- **Fixed: reservation identifiers lost their leading zeros.** A JSON number
  arrives with them already gone — a 06:30 departure comes back as `63000` —
  and `str()` alone handed a five-character time to a payment builder that
  requires exactly six digits, so every departure before 10:00 failed to build
  a payment. Five fixed-width identifier columns are now repadded; quantities
  like `rcvdAmt` deliberately are not. `trnGpCd` is also sent as the row gave
  it rather than defaulted.
- **Fixed: a transfer hold could not be released, and a search could depart
  from its own arrival station.**
- **Fixed: a seat designation forgot which cabin its grid came from.** Picking
  특실 seats while `seat_type` stayed at its `GENERAL_FIRST` default sent
  일반실 as the class with 특실 car and seat numbers beside it — a body the app
  cannot express, so there is no evidence for how the server treats it. The
  cabin and the seat numbers must now describe the same cabin.
- **Added: the app's two 왕복 refusals.** A 코레일 전용역 and a 국회의원 후급
  membership are both refused before sending, matching `ara0101v.js:317-341`.
- **Added: the ceiling half of the 10-person party rule.** A non-단체 search
  of 10 or more is refused, as `ara0101v.js:562-567` does; the floor on group
  searches was already enforced. It lives in the client rather than in a
  payload builder because the builders cannot tell the two flows apart.
- **Fixed: 예약대기 refused rows the app would have queued.** The cabin was
  resolved before standby overrode it, so once the availability requirement
  landed, a waitlistable row that carried no `gnrmRsvPsbStr` raised past the
  override. Standby forces 일반실 and reads no availability at all, so the
  decision now happens first.
- **Fixed: a NetFunnel queue slot leaked whenever a client-side guard fired.**
  The reservation form was built outside the `try` whose `finally` releases the
  slot, and `_get_act10_key` recorded its key only after the poll loop, so both
  of its own raises abandoned one too. A key is now registered the moment it
  exists.

- **할인 승차권 검색 (`Ara10131`) — the request is evidenced, the effect is not.**
  `SrtClient.search_public_discount_trains(query, discount, *, page_cursor="")`
  → `TrainSearchResult`, a `POST /ara/selectListAra10131_n.do`. A READ:
  `READ_ONLY_ROUTES` 25 → 26, registered POST-only with its own exact 23-field
  form contract, alongside the seat page and the seat grid.
  **The survey's reason for leaving this out did not survive re-reading the
  pages.** It said every `PBL_DISC_*` value would be a guess; the specific
  mistake was reading the form it could see (the 할인 승차권 page's `#rsvForm`)
  and never reading the form the search actually posts. Three of the four are
  established — `pblDiscCd` has a known domain (`01`–`08`), `tgtDtrmYn` is the
  literal `"Y"` on every branch, and `PBL_DISC_NM` **has no field at all** on
  the ajax form — and only `pblDiscMgNo` is caller-supplied and opaque.
  **The route has two legs and only one searches.** `goSubmit()` retargets a
  `method="get"` form at it and NAVIGATES; the 조회결과 page that comes back
  POSTs `#seatSearchForm` to the *same path* and renders rows from the JSON. Only
  the second is implemented, and the first was **measured, not assumed**: four
  live read-only GET probes (a full 146-field journey, that journey with
  `PBL_DISC_CD="04"`, a bare `?type=`, a de-duplicated journey) returned 142,594
  bytes each, byte-identical apart from the session id, with all eight `var s*`
  hydration slots and all three `pblDisc*` inputs empty every time.
  **Differences from the ordinary search, all from the live page**: three
  discount fields in camelCase (the page form uses `PBL_DISC_*`); **no
  `netfunnelKey`** on either form, though the app still waits behind `act_10` and
  the client takes and releases a slot; **no passenger type mix** — `psgNum`
  only, where the ordinary ajax carries `psgTpCd1..N`; paging by a `gdNo` cursor
  rather than by bumping `dptTm`; `fllwPgExt` on the first ROW rather than on the
  metadata row; and `resultMap`/`trainListMap`/`dsCmdMap` rather than
  `outDataSets`.
  **Two new row columns, and they are the point of the search**:
  `gnrmBkclDcntRt` and `sprmBkclDcntRt`, the 공공할인 rate for 일반실 and 특실 as
  whole-number percentages — 0-hit in the v2.0.41 bundle and absent from every
  ordinary-search row captured here. Appended to `TrainSummary` as
  `general_class_discount_rate` / `.special_class_discount_rate` and defaulted to
  `None`, so an ordinary row is unchanged. A rate below 1 is the page's own way
  of saying "this train carries no discount for you".
  **The row parser was EXTRACTED, not copied.** The columns are the ordinary
  search's and the page's own renderer still calls its parameter `dsOutputTemp`;
  `_parse_search_train_rows` is now the single implementation both parsers use,
  with only the container handling kept separate. The discount parser refuses the
  ordinary `outDataSets` container rather than tolerating it.
  **NEVER EXERCISED, and it says so everywhere.** No reply on this route has ever
  been seen — not the envelope, not a populated discount rate, not a `gdNo`
  round trip — so there is deliberately **no pager**: the stopping condition has
  never been observed. What an entitled account would settle is enumerated in
  `docs/IMPLEMENTATION_PROGRESS.md`; one search answers all seven at once, and
  unlike the coupon registration a search spends nothing.
  Offline gate: `1607 passed, 1 deselected` (was `1553`).

- **할인쿠폰 등록 — a FIFTH consent category, and the first one that cannot be
  sent.** `SrtClient.register_discount_coupon(coupon_number, coupon_password, *,
  consent)` builds `POST /arb/selectListArb02A01_n.do` with exactly two fields,
  `dscp_no` and `dscp_pwd`.
  **The shape is the live coupon page's own `couponReg()` and nothing else**: it
  serialises `#couponInfo` — two inputs, no PNR, no member number, no NetFunnel
  key — posts it as JSON and reads `resultMap[0].RTNCD` / `.MSG` back. Route,
  field names and response keys are all **0-hit** across the 21,673 files of the
  v2.0.41 bundle, which knows no `/arb/` route at all. The bundle does
  corroborate the vocabulary either side of the wire: `messages.js:111-113`
  carries this flow's two validation refusals and its success text
  (`mysrt006`/`007`/`008`) and `sub/main.html:475` carries the member flag
  `DSCP_YN`, which the live user map also returns. The handler is committed
  verbatim in `tests/fixtures/discount_coupons_empty.html`.
  **Why a fifth category rather than a reuse:** a coupon registration changes
  account state but books nothing and moves no money, so folding it into
  `reserve` or `payment` would have made a consent for one of those silently
  authorise the spending of a coupon. The sibling KORAIL port drew the same line
  for 할인카드 구매. `MutationConsent.allow_coupon` was **appended**, after
  `real_card_acknowledged`, so every consent written before it existed means
  exactly what it meant.
  **`SRT_LIVE_MUTATION_CATEGORIES` IS UNCHANGED** at
  `{reserve, cancel, payment, refund}`, and its canary still pins it. `coupon`
  is outside it, so `dry_run=False` is refused at the transmit gate and again
  independently at `_send_mutation_request`; nothing has ever been sent to this
  route from this library. Adding the category was a modelling decision; adding
  it to the kill switch would be an evidence decision, and there is no evidence
  — a live run needs a real unredeemed coupon, which cannot be manufactured.
  **A redaction gap is closed, and it was a real one.** A coupon number plus its
  password is a bearer credential, and neither half was masked: `dscp_pwd` is not
  the literal key `password`, and a coupon number is at most ten digits, which
  `CARD_RE` (13-19) never matches — so a dry-run preview would have printed a
  redeemable coupon in full. `dscp_no`, `dscp_pwd`, `coupon_number` and
  `coupon_password` are now in `SENSITIVE_KEYS`, both request fields are
  `repr=False`, and a preview's payload is two `[REDACTED]` values.
  **Never observed: the response.** `SrtCouponRegistrationResult` keeps the
  page's own polarity (`RTNCD == "N"` fails, anything else succeeds) and is
  stricter in exactly one place — an empty or missing `RTNCD` is a
  `SrtProtocolError`, because under that polarity a missing code would read as a
  SUCCESS. It does not reuse the shared `strResult`/`msgCd`/`msgTxt` envelope
  helper: this route answers in uppercase `RTNCD`/`MSG` with no `strResult`, and
  mapping one onto the other would assert a correspondence nobody has seen.
  A success is a REQUEST accepted, not a coupon visible — the page's own
  `mysrt008` says so.
  **Three route canaries were updated, not weakened**: `SRT_MUTATION_ROUTES` is
  five, and the tests that said "this feature adds no route" now pin the exact
  route SET rather than its size, so they name which routes are transmittable
  instead of counting them.
  Offline gate: `1553 passed, 1 deselected` (was `1520`).

- **`PassengerCounts` now carries the app's SEVEN passenger types.** `infant`
  (유아) and `youth` (청소년) were APPENDED, so every existing positional
  construction keeps its meaning, and both default to zero.
  **유아 has no `psgTpCd` of its own — it is folded, and declared twice**, which
  is the live booking page's rule (`goRevFn`) implemented rather than tidied:
  the 어린이 slot count becomes 어린이 + 유아, `infantCnt` carries the infants
  again on their own, `totPrnb` counts them as heads, and `psgGridcnt` does NOT
  count them as a type. `PassengerCounts.child_slot_count` is the folded number
  and is a separate name from `child` so no caller has to remember which a given
  field wants. Two places where the tidier model would have been wrong: infants
  with no children still fill the 어린이 slot (the app tests the SUM after
  folding), and `total` and `psgGridcnt` genuinely disagree about an infant.
  **청소년 does get a slot, `psgTpCd` 6** — a code in neither copy of
  `commCode.js`. It compacts last and widens the padded search form from five
  slots to six, five being the booking page's loop and six being what the one
  page that can express a 청소년 writes. It is accepted **without** checking the
  entitlement: the 승차인원선택 popup gates `passenger7` on the server rendering
  `pblDiscCd == "04"`, but that is an account fact no payload builder can
  evaluate, and refusing here would lock out exactly the accounts the type is
  for. `get_public_discounts()` is how a caller asks.
  **With `infant=0` and `youth=0` every builder emits exactly what it emitted
  before**, so the 2026-07-25 live reserve→cancel round trip stays valid as
  byte-for-byte evidence. That is why `infantCnt` is conditional even though the
  live form always carries `infantCnt=0`. A parametrised test pins the
  invariance across all five builders, and every pre-existing reservation-form
  test passed **unmodified**.
  **LIVE-VERIFIED read-only 2026-07-26** via the search route's own `commandMap`
  echo: `adult=1, child=2, infant=3` came back as `psgTpCd2="5"`,
  `psgInfoPerPrnb2="5"`, `infantCnt="3"`, and `adult=1, youth=1` came back as
  `psgTpCd2="6"` — both with ten train rows, so neither was rejected.
  **NOT verified**: that a 청소년 can be reserved or is priced differently. That
  needs 공공할인 `04` (no account here holds it) and a reservation (state
  changing). The 운임 read cannot stand in — it returns a per-TYPE price list
  that was identical across all five parties probed — and the popup cannot
  either, since it echoes `passenger6`/`passenger7` but never seeds them back
  into its DOM.
  Offline gate: `1520 passed, 1 deselected` (was `1497`).

- **CORRECTED, in five places: SRT does have an infant type and a `psgTpCd` 6.**
  The repository stated flatly that "`infantCnt` appears nowhere in the app" and
  that "there is NO infant / psgTpCd 6". Both were true of the v2.0.41 offline
  bundle and false of the live server, and the error was the same each time:
  reading "absent from the bundle" as "absent from the protocol".
  The live 승차인원선택 popup — fetched through this library's own already
  allowlisted `get_passenger_selector` — renders a sixth counter `passenger6`
  ("유아 (만 6세미만)") and a seventh `passenger7` ("청소년", hidden unless the
  공공할인 code is `04`), sums `i=1..7`, and returns all seven. The live booking
  page folds 유아 into the 어린이 slot count AND sends it again as `infantCnt`;
  the 할인 승차권 page sends 청소년 as `psgTpCd6`. `psgTpCd` 6 is in NEITHER copy
  of `commCode.js`.
  **No behaviour changed and no assertion was weakened.** `PassengerCounts` is
  still five types and the payload builders still emit no `psgTpCd6` and no
  `infantCnt`; the tests that pin that are unchanged. What changed is the
  JUSTIFICATION: five is now recorded as this library's deliberate boundary
  rather than as a fact about SRT. Widening it would change what `reserve()`
  transmits, and 청소년 is unreachable without a 공공할인 approval no account
  here holds. `discounts.YOUTH_PASSENGER_TYPE_CODE` records the code so the
  knowledge cannot be lost again, and
  `docs/IMPLEMENTATION_PROGRESS.md` ("공공할인 is a passenger vocabulary, not
  just a price") records what implementing it would take.
  Also recorded there: the 할인 survey's three NOT-implemented surfaces —
  coupon registration (`/arb/selectListArb02A01_n.do`, a mutation with no
  category), the 할인 승차권 search (`/ara/selectListAra10131_n.do`, exists but
  needs an approval nobody here has), and `/ata/selectListAta01032_n.do`, whose
  only caller in the bundle sends a literal unsubstituted
  `pnrNo=${commandMap.pnrNo}` and whose live route is mapped-but-throwing
  (`500`, where two control routes answer `404` with the identical body).
  Offline gate: `1497 passed, 1 deselected` (unchanged — comments and one test
  name).

- **공공할인 (welfare discount) entitlement READ — `get_public_discounts()`,
  live-verified unapproved 2026-07-26.** One parameterless
  `GET /common/ARA/ARA0301V/view.do` (할인 승차권) returning `PublicDiscountPage`
  of `PublicDiscountEntitlement`, parsed by `parse_public_discount_page`.
  `READ_ONLY_ROUTES` 24 → 25. Found on the same server-rendered MY SRT menu as
  the coupon route; 0-hit in the v2.0.41 bundle in every part — the route,
  `PBL_DISC_CD`, and every one of its values.
  **Live-verified for an account approved for nothing**: 206,268 bytes, all
  eight `var dataNCheck` flags empty, `is_eligible` `False`.
  **That is returned, not raised.** The page reacts to it like a refusal —
  alert `Sr.msgs.notice006`, bounce to main — which resembles the sold-out seat
  page without being the same thing: there the refusal means the requested seat
  map does not exist, here "you hold none" is the answer to the question asked.
  **The code-to-slot mapping is an inference and says so in the model
  docstring.** Nothing writes a `PBL_DISC_CD` next to a `dataNCheck`; what ties
  them is the page's own comment on the one branch reading two flags at once,
  "다자녀(01)와 임산부(02)가 신청이 승인된 경우", guarding
  `if(data1Check == "Y" && data2Check == "Y")`.
  **The flag regex is anchored on `var`** because those same identifiers appear
  nine more times as `!= "Y"` / `== "Y"` comparisons; unanchored, the unapproved
  page would read as approved. A test pins it. Also refused: a page with no
  `PBL_DISC_CD` field, and one not declaring exactly eight distinct flags.
  **The 할인 승차권 SEARCH is not implemented.** The page IS its form (`#rsvForm`
  plus `PBL_DISC_CD`/`PBL_DISC_NM`/`PBL_DISC_MG_NO`/`TGT_DTRM_YN`), submitting
  to `/ara/selectListAra10131_n.do` behind NetFunnel `act_10`. That route
  exists — a bare live GET answered `200` where a nonexistent sibling answered
  `404` — and is registered nowhere, with no builder and no method: exercising
  it needs an approved 공공할인 nobody here holds. A test pins its absence from
  both allowlists.
  Not carried either: `PBL_DISC_MG_NO` and the confirmation/expiry dates, which
  were empty in every branch of the only page readable here.
  Offline gate: `1497 passed, 1 deselected` (was `1485`).

- **할인쿠폰 (discount coupon) READ — `get_discount_coupons()`, live-verified
  empty 2026-07-26.** One parameterless `GET /apa/selectListApa03020_n.do`
  returning `DiscountCouponList` of `DiscountCoupon`, parsed by
  `parse_discount_coupon_page`. `READ_ONLY_ROUTES` 23 → 24.
  **The route is 0-hit in the v2.0.41 bundle**, which contains no `/apa/` route
  at all. It was found by reading a page this client already fetches: the MY SRT
  menu is server-rendered into every authenticated page and names it as
  `pageMove('/apa/selectListApa03020_n.do')`, with `pageMove` being
  `window.location = url`. The seat-grid technique, pointed at a menu.
  **Live-verified for an account holding nothing**: 77,056 bytes, `ul.coupList`
  present and empty, "보유한 쿠폰이 없습니다." The POPULATED row shape is NOT
  verified and `DiscountCoupon`'s docstring says so; its six field names come
  from the page's own commented-out designer template, and every value stays
  display text rather than a parsed number, because turning "23%" into a number
  would be inventing structure on a shape nobody here has seen the server
  produce.
  **That template is why this is a parser and not a regex.** The live page ships
  a two-coupon template, commented out, INSIDE `ul.coupList`, with plausible
  numbers. `html.parser` never parses markup inside a comment, so it cannot
  become coupons; a regex would have produced two for an empty account. The
  fixture keeps it verbatim and a test pins the property.
  **"You hold none" and "we did not understand this page" cannot look the
  same**: no `ul.coupList` → refused; no coupons and no marker → refused;
  coupons AND the marker → refused.
  **Registration is NOT implemented and NOT reachable.** The same page carries a
  `dscp_no`/`dscp_pwd` form; its submit is a POST to a different route
  (`/arb/selectListArb02A01_n.do`) which is in neither allowlist, is
  uncategorised, and would need a fifth `SRT_LIVE_MUTATION_CATEGORIES` entry —
  pinned to four. Only GET is registered for the coupon path, so a coupon number
  and password cannot travel there under a read either. Tests pin all of it.
  Offline gate: `1485 passed, 1 deselected` (was `1471`).

- **할인 (discount) code tables — `srt_mobile_api.discounts`.** Two tables from
  two different kinds of evidence, and the difference is the point.
  **`DISCOUNT_KIND_NAMES_BY_CODE`** is a direct copy of the `dcntKndCd` run in
  the app's own `js/commCode.js`: **173 codes, not 171**, because `133`
  기본 특별할인(기준) and `191` 정차역 할인 carry no `code_group_cd` key at all in
  the source while sitting inside the run between `132` and `192`. 25 rows carry
  `"rmk": "V"`; the bundle never says what `V` marks, so nothing is built on it
  and no accessor exposes it. The codes are stable and four of the NAMES are
  not: a live fetch of `/js/commCode.js` on 2026-07-26 had renamed `205`/`206`
  to the current legal wording (장애의정도가심한/심하지않은장애인), matching the same
  rename on `psgTpCd` 2 and 3. The table keeps the v2.0.41 wording, because the
  bundle is the committed evidence, and says so.
  **`PUBLIC_DISCOUNT_NAMES_BY_CODE`** (공공할인, `PBL_DISC_CD` `01`–`06`) is
  **0-hit in the bundle** — the field name and every value. It came from a page
  the live server renders to our own session: the 승차인원선택 popup
  (`/common/ARA/ARA0901P/view.do`, already allowlisted and already implemented)
  writes the mapping out as a comment block inside its own `setPassenger`.
  `07` and `08` have branches on the 할인 승차권 page and no name anywhere
  fetched here, so they are absent rather than guessed.
  **`YOUTH_PASSENGER_TYPE_CODE = "6"`** records a `psgTpCd` that is in NEITHER
  copy of `commCode.js` — not v2.0.41, not the live copy — and exists only under
  공공할인 `04` (청소년). It is recorded as a constant and deliberately NOT wired
  into `PassengerCounts`: emitting it would change the reservation payload for a
  discount no account here can hold.
  Nothing is transmitted by this change. No route, payload, model or client
  method moved; `dcntKndCd` is decoded, never set.
  Offline gate: `1471 passed, 1 deselected` (was `1455`).

- **단체 (group) booking REMOVED — `Arc06014` is a payment page, not a hold.**
  `SrtClient.reserve_group`, `payloads.group_reservation_payload` and the
  `SRT_MUTATION_ROUTES` / `SRT_MUTATION_ROUTE_CATEGORIES` registration of
  `/arc/selectListArc06014_n.do` are gone, with the offline tests that covered
  the booking path. The request they built was correct; what put group booking
  out of scope is what the route ANSWERS with.
  **`psgGridcnt`, not an account entitlement, was the wrapper error.** The
  booking page's group branch sets BOTH `grpDv="1"` AND `psgGridcnt="2"`; this
  library derives `psgGridcnt` from the distinct passenger-type count, which is
  `1` for ten adults. That mismatch alone produced
  `{"ERROR_CODE": "-1", "ERROR_MSG": "조회 중 에러가 발생 하였습니다…"}`. The
  first reading — probably an entitlement — was wrong.
  **With `psgGridcnt="2"` the route answers with a 66 KB server-rendered page**
  headed `단체승차권 직통 / 예약내역 페이지`, carrying `<form id="ata0201cForm">`,
  `goToPay` / `kakaoPayReturn`, `tmpJobSqno` six times, and posting to
  `/ata/selectListAta01033_n.do` — a payment route this library does not
  implement, distinct from the `Ata09036` it uses for personal payment. It
  creates **no reservation**.
  **The previously recorded uncancellable-hold risk did not exist, and is
  corrected rather than deleted.** Earlier notes warned that a live group
  attempt could strand an unreleasable ten-seat hold, reasoning from
  `ara1001l.js:1597-1610` (`pnrNo` forced to `-1`, identified by
  `resultMap.tmpJobSqno1`). The bundle reading was right and the conclusion was
  not: nothing is held, so there was never anything to strand.
  **`search_group_trains` STAYS**, with `group_search_ajax_payload` and
  `GROUP_MIN_PARTY_SIZE`. It is a read, it works, it predates the booking code,
  and group availability and fares are worth looking up even when this client
  cannot complete the booking. The ten-person floor survives because the app
  enforces the same number on the SEARCH (`ara0101v.js:551-566`, a two-sided
  boundary), not because the removed builder shared it.
  **`SRT_LIVE_MUTATION_CATEGORIES` is UNCHANGED** at
  `{"reserve", "cancel", "payment", "refund"}` — group rode the `reserve`
  category, and removing it may not shrink the set; the canary in
  `test_mutation_live_paths` pins that. `SRT_MUTATION_ROUTES` drops from five
  to four, one route per category, because a route no client method can reach
  must not stay transmittable; `assert_mutation_route` now refuses `Arc06014`
  outright, and a test pins that too.
  **Tests that pinned the public method set were updated deliberately.**
  `test_client_public_method_set_is_stable` no longer lists `reserve_group`,
  and the two `len(SRT_MUTATION_ROUTES) == 5` pins in `test_transfer` and
  `test_seat_designation` are now `== 4`. New tests assert the removal itself:
  the method and the builder are absent, the route is unregistered and
  uncategorised, the search half is intact, and the kill switch has not moved.
  **What bringing it back would take** — not a revert, but `psgGridcnt="2"`, a
  second payment surface (`Ata01033`, keyed by `tmpJobSqno`), an HTML parser
  for a 66 KB page, a story for KakaoPay's off-client hop, and a deliberate
  decision about which consent category a reserve-and-pay flow belongs to — is
  written down in README.md and docs/IMPLEMENTATION_PROGRESS.md under
  "단체 (group) booking: removed".
  Offline gate: `1455 passed, 1 deselected` (was `1463`).

- **좌석지정 (seat-designated reservation, `jobId=1103`) — body evidenced,
  submit target inferred.** `reserve(train, *, designated_seats=…, consent=…)`,
  keyword-only and defaulted to `None`: the undesignated form is byte-for-byte
  AND order-for-order what the 2026-07-25 live round trip sent, and a test
  asserts it. `SRT_MUTATION_ROUTES` (five) and `SRT_LIVE_MUTATION_CATEGORIES`
  (four) are untouched — a designated reservation is the same operation on the
  same route under the same `reserve` consent.
  **The body is bundle-evidenced field by field** (`ara0101v.js:866-882`):
  `jobId=1103` (`ara1001l.js:1435-1436`), `seatNo1_1..N`, `scarGridcnt1`,
  `scarGridcnt2="0"`, `scarNo1`, `scarNo2=""` — slot 2 blanked rather than
  omitted, because 여정 slot 2 belongs to a 환승 second leg and a designated
  one-way journey has none.
  **`seatNo1_*` carries the PRINTED label, not the internal seat number.** The
  app builds it from `scarSeatNm` and never uses `scarSeatNo`
  (`ara0101v.js:870-874`), so the field spelled `seatNo` transmits the NAME.
  This is the identifier pair the sibling korail client was bitten by, and a
  test pins it against a car where 1B/2C are internally 2/7.
  **THE SUBMIT TARGET IS INFERRED, and it is what an operator must settle.**
  `fn_submit()` is called at `ara0101v.js:882` and defined nowhere in the
  bundle — its definition is in the server-rendered booking page. This library
  POSTs `/arc/selectListArc05013_n.do` on the strength of the commented-out
  `//Sr.ara1001l.fn_callReserv();` on the next line, that being the function
  which serialises `#rsvForm` to exactly that URL (`ara1001l.js:1541-1550`).
  **Fetch `/ara/ara0101v.do` and read its inline `fn_submit` before sending one
  live** — the same technique that opened the seat grid. If it targets
  something else, the body is still right and only the route moves.
  **Validation.** The seat count must equal the passenger count
  (`choiceSeatCount` is `totPrnb`, `ara1001l.js:1511`), and `SeatDesignation`
  refuses at construction to hold a seat the grid marked `N`, a repeated seat,
  an empty list, or a non-numeric car — so an unselectable seat is
  unrepresentable rather than merely rejected.
  **Does not compose with `standby`** (`jobId` cannot be both `1102` and
  `1103`; the app reaches them from two different branches,
  `ara1001l.js:1435-1449`) **or with `round_trip`** (좌석지정 왕복 exists in the
  app but its callback writes no seat fields at all, `ara0101v.js:884-892`, so
  that body is unevidenced). Both raise `ValueError` before anything is built.
  Not offered on `reserve_transfer` (좌석지정 blanks slot 2). It was also not
  offered on `reserve_group` (단체 disabled the seat picker), which has since
  been removed entirely — see the 단체 entry above.
  `reserveType` stays `"11"`: it is srtgo-only, 0-hit in our bundle, srtgo has
  no seat-map reservation, and nothing says it tracks `jobId`.
  Offline gate: `1463 passed, 1 deselected` (was `1448`).

- **좌석배치도 (seat grid) read LIVE-CONFIRMED (2026-07-26), and it needed no
  capture.** `SrtClient.get_seat_grid(train, car_number) -> SeatGrid` over
  `POST /arc/selectListArc02011_n.do` — the seat page's own follow-up read,
  0-hit in the v2.0.41 bundle along with the `trnScarSeatFrm` form it
  serialises, because both exist only in what the server renders. Every prior
  note said this needed a traffic capture; the pages are served to our own
  authenticated session and can simply be read. Live: 수서 -> 동탄, 20260812,
  train 315, 25,930 bytes, 74 seat cells.
  **The train number must be zero-padded to five characters, and that is the
  entire gate.** `trnNo=315` returns a 147-byte alert shell reading
  "출발 20분 전부터 좌석이 자동배정됩니다…"; `trnNo=00315` returns the grid.
  Referer and route length change nothing — all three were checked live. The
  alert reads like a timing rule and is not one, and believing it is what kept
  this endpoint closed. The app pads identically and says so in a comment
  (`lfn_getTrNoData`, "열차번호를 5자리로 채워서 가져옴", `main.html:642-661`).
  The padding lives in `payloads.seat_grid_payload` next to
  `SEAT_TRAIN_NUMBER_LENGTH`, is re-checked at the safety boundary as
  `[0-9]{5}`, and is pinned by a test using the three-character number 315.
  **A seat has TWO identifiers and `SeatGridSeat` keeps them apart by name.**
  Each cell is `choiceSeatNo('3', '1C', 'Y')`: internal seat number, printed
  label, selectable flag — so `internal_seat_number` and `printed_seat_label`
  are separate fields. The element id and `aria-label` use the printed label;
  the class is `seatChoice<seatAttCd><Y|N>` (`000`, `015`, `021`, `028` all
  observed in one car). Conflating the two is the mistake the sibling korail
  client already made, where the form sends one and the detail echoes the other.
  **The `#` envelope is a business refusal, not a parse failure.** The page's
  own handler is `tmp = args.trim().split("#"); if (tmp[0] == "0") alert(tmp[1])`,
  so `"0#<message>"` raises `SrtSeatUnavailableError` (an `SrtAppError`) with
  `code="0"` — this route is HTML and carries no `msgCd` at all — rather than a
  protocol error. A body with neither cells nor envelope raises
  `SrtProtocolError` instead of returning an empty grid.
  **Read-only allowlist: 22 routes -> 23**, with an exact eleven-field form
  contract of its own. `SRT_MUTATION_ROUTES` and `SRT_LIVE_MUTATION_CATEGORIES`
  are untouched and their canaries are unchanged; `assert_mutation_route`
  refuses this path.
  New exports: `SeatGrid`, `SeatGridSeat`, `SeatDesignation`,
  `parse_seat_grid_response`.
  Offline gate: `1448 passed, 1 deselected` (was `1404`).

- **환승 search response shape LIVE-CONFIRMED (2026-07-26): one row per leg,
  paired by `trnOrdrNo`.** A read-only probe of 동대구(0015) -> 광주송정(0036),
  20260809 from 080000, settled what the bundle could not. The direct search on
  that pair answered `WRD000061` "직통열차는 없지만, 환승으로 조회 가능합니다.",
  and the transfer search returned 10 ordinary `dsOutput1` rows, every one with
  `chtnDvCd="2"`, with the legs of one itinerary sharing a `trnOrdrNo`: `1` ->
  trains 382 (동대구->오송) + 411 (오송->광주송정), `2` -> 14 (동대구->천안아산) +
  475 (천안아산->광주송정), `3` -> 316 + 655. So `trnOrdrNo` is the ITINERARY
  index, not a position in the list. The `...2` columns DO exist on every row and
  are EMPTY STRINGS (`trnNo2: ""`, `dptRsStnCd2: ""`, `jrnySqno: ""`) — because
  the second leg is a separate ROW, not a set of columns. `fllwPgExt2` was
  `null`.
  **`search_transfer_trains` now returns a `TransferSearchResult`** —
  `itineraries` (paired and validated), `unpaired` (groups that did not fit, each
  with a reason), `search` (the untouched `TrainSearchResult`), plus `rows` and
  `raw`. The grouping is `parsers.pair_transfer_itineraries`, exported, and it is
  NAMED as an inference layer because that is what it is: the server sends a flat
  row list and the pairing is ours, so the raw rows stay reachable behind it.
  **Leg order is derived from the STATIONS, never from row position.** The probe
  delivered legs in order, but that is one observation and not a guarantee, and a
  reversed pair builds a perfectly clean reservation that books the journey
  backwards — a failure the server would accept. Both orientations are handed to
  `TransferItinerary` and the one that validates wins, so "is this an itinerary?"
  has exactly one implementation: connection, time order and distinct trains all
  come from the type that already enforced them.
  **A group that does not fit is set aside, not dropped and not forced.** Wrong
  row count, legs that do not connect or run backwards, an ambiguous order, or a
  missing `trnOrdrNo` all land in `unpaired` with a plain-sentence reason. The
  choice was between two bad outcomes and it is made deliberately: losing an
  itinerary silently hides a journey the traveller could have taken, but handing
  back a mispaired one produces a reservation whose two slots are not one
  journey. The second is worse, so nothing is invented and nothing is discarded.
  **Except when NOTHING pairs** — rows present and zero itineraries means the
  grouping rule is wrong for the response in hand, not that the server sent ten
  broken itineraries, and an empty list would be the one genuinely silent failure
  available. That raises `SrtProtocolError` carrying `raw`. An empty response is
  not that case.
  **`WRD000061` is now classified as `SrtNoDirectTrainError`**, refining
  `SrtNoResultsError`. It previously fell through to a bare `SrtAppError`, so
  nothing narrowed. It sits one level deeper rather than beside its parent
  because "there is no DIRECT train" IS "this query matched nothing", with the
  remedy named — a caller already writing `except SrtNoResultsError` was right
  about this response too — and because the sibling korail client classifies the
  identical code the same way under `KorailNoResultsError`. No transfer search is
  issued automatically: the app offers the 환승 re-query in a dialog and waits,
  and this library does not turn one caller-requested read into two.
  **The live search moved NO evidence tier, and that is the point.**
  `TRANSFER_SLOT2_FIELD_EVIDENCE` is unchanged: the five INFERRED slot-2 key
  names are still inferred. The search row's `...2` columns are blank because the
  second leg arrives as its own ROW, which says nothing whatsoever about whether
  the RESERVATION form wants them filled. A response column and a request field
  that share a name are two different things, and only a reserve capture can
  settle the request side. **Search shape: live-confirmed. Reservation form
  slot-2 handling: still inferred, still not live-verified.**
  `iter_train_search_pages` is still not extended to transfer: the probe returned
  `fllwPgExt2` as `null` exactly as every direct search does, so what the second
  cursor is FOR remains unobserved.
  Offline gate: `1404 passed, 1 deselected` (was `1388`).

- **환승 (transfer) search and reservation — the one shape SRT reserves as TWO
  journeys in ONE request.** `SrtClient.search_transfer_trains(query)` and
  `SrtClient.reserve_transfer(itinerary, ...)`. **Bundle-evidenced request, NOT
  live-verified**: no transfer search or reservation has ever been sent from
  this library. `reserve_transfer` POSTs the SAME endpoint as `reserve`
  (`/arc/selectListArc05013_n.do`) under the SAME `reserve` consent category —
  no route and no category was added, `SRT_LIVE_MUTATION_CATEGORIES` is
  untouched at `{"reserve", "cancel", "payment", "refund"}`, and its canary is
  unchanged.
  **This is the exact inverse of the round trip**, and the previous change's
  reasoning is what made it findable. 왕복 is TWO reservations of one journey
  each with `jrnyCnt` staying `"1"`; 환승 is ONE reservation of two journeys with
  `jrnyTpCd="14"` and `jrnyCnt="2"`, set together in a single `lfn_setRsv` call
  (`ara0101v.js:302-303`, emitted `:310-311`) that is the ONLY write of
  `jrnyCnt="2"` in the whole v2.0.41 bundle. Both premises this work started
  from survived the bundle: `commCode.js:296-309` names the two `jrnyTpCd`
  values (`11` 편도/직통, `14` 환승편도/환승), and `ara0101v.js:97` glosses the
  slot values (`여정일련번호1(001:선행, 002:후행)`, repeated `ara1001l.js:1607`).
  **SEARCH is the same endpoint with one field changed.** `chtnDvCd` `"1"`
  (직통) → `"2"` (환승), derived by the app itself at `ara1001l.js:98`
  (`jrnyTpCd == "11" ? "1" : "2"`) and sent at `:159`; the URL is picked by
  `grpDv` alone (`:174-181`), so 직통 and 환승 share `Ara10007`. The hydration
  GET additionally carries the toggle's `jrnyTpCd=14`/`jrnyCnt=2`.
  **HOW THE RESPONSE PAIRS THE LEGS IS UNKNOWN OFFLINE, and is not guessed at.**
  The bundled list screen cannot say: `fn_postSearch` renders one single-leg
  `<tr>` per row with no transfer branch (`ara1001l.js:384-460`), `fn_moveRsv`
  writes only slot 1 (`:1453-1468`), and `fn_validChk` validates only slot 1
  under a `//직통` heading (`:1649-1700`). The 환승 list is server-rendered — the
  stylesheet still carries its taller two-row card with a layover band
  (`.time_Difference` / `.timeDiff`, `custom.css:4412`, `:4431`) — and that
  markup is not in the bundle. So `search_transfer_trains` returns rows exactly
  as sent and the caller pairs them. For the same reason
  `iter_train_search_pages` is deliberately NOT extended to transfer: a search
  response carries a second cursor `fllwPgExt2` (null in every direct search
  captured, read by nothing in the bundle), and paging a two-cursor list on a
  guess would walk the wrong leg.
  **`TransferItinerary` is what makes half an itinerary unrepresentable.** A
  transfer search row is an ordinary `TrainSummary` — `reserve(row)` would accept
  it and hand back a real, successful-looking PNR to the 환승역 and no further.
  So `reserve_transfer` takes ONLY a `TransferItinerary(first_leg=…,
  second_leg=…)`, which validates at construction that the first leg ARRIVES
  where the second DEPARTS, that the second does not depart before the first
  arrives (the comparison the app applies to the 왕복 second leg,
  `ara1001l.js:1258-1272`), that both are exact `TrainSummary`, and that they are
  not the same train. The app states the rule in its own words, in a message it
  ships and never references because the screen that would raise it is
  server-rendered (`messages.js:217`, `rsv023`): "선택하신 열차는 선행 및 후행
  열차를 모두 선택하셔야 예약이 가능합니다."
  **The FORM is the personal form with two values changed and one slot
  appended.** Slot 1 keeps its exact keys, values and ORDER; 23 slot-2 keys
  follow it. How each of those keys is known is graded per key in
  `payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` and pinned by a test, because the
  answer genuinely differs: nine are literal `...2` strings in the web bundle
  (`dptRsStnCd2`/`arvRsStnCd2`/`runDt2`/`trnNo2` from the 운임요금 params
  `ara1001l.js:1209-1216`, whose LIVE page renders a whole second leg with its
  own `selectTransferTrain()` toggle; the five seat-attribute keys from
  `ara0101v.js:136-140`, written at `:775-777`); five are literal `...2` strings
  in the app's NATIVE two-leg model, the offline-ticket parser gated on
  `isTransfer == "true"` (`analysis/jadx/.../webview/b.java:746-834`, with a
  수서→**천안아산**→부산 layout placeholder); four are 0-hit here but already
  sent on the hydration GET; and **five are INFERRED** from slot 1's names
  because the server-rendered `#rsvForm` is not in the bundle
  (`stlbTrnClsfCd2`, `dptStnConsOrdr2`, `arvStnConsOrdr2`, `dptStnRunOrdr2`,
  `arvStnRunOrdr2`). Those five are what a live run has to settle, along with
  `reserveType`, which we send as `"11"` and which is srtgo-only — if it tracks
  `jrnyTpCd`, a transfer wants `"14"`, and that is a guess we declined to make.
  **What composes.** Passengers and the seat option apply ONCE to both legs, and
  that is the app's own behaviour, not a simplification: `psgTpCd1..5` is indexed
  by passenger TYPE rather than by journey slot, and the 좌석옵션 callback writes
  slot 1 and then the identical `...2` quartet from the same values
  (`ara0101v.js:769-778`). **왕복 is refused**, in both directions, with the same
  string — "환승은 왕복예약이 불가능 합니다." (`ara0101v.js:296-299` and
  `:331-334`) — so there is no `round_trip` argument to pass and `rtnDv` is
  pinned to `"0"`. **예약대기 is not implemented**: `jobId=1102` is chosen from
  ONE selected row's image (`ara1001l.js:1445-1448`) and a transfer has two rows,
  so there is no app rule to reproduce. **단체 is not implemented**, and this one
  is a scope decision rather than an exclusion: 단체환승 is a real SRT product
  (`eventTrainInfo.js:12`, `:19`; ticket kind 환승단체권 `tkKndCd` 27,
  `commCode.js:1591-1596`) and nothing in the app forbids it, but
  `reserve_group`'s RESPONSE is itself unverified and may carry no cancelable
  PNR — compounding the two risks a ten-seat two-leg hold nobody can release.
  **좌석지정 is not implemented**: it explicitly BLANKS slot 2 (`scarGridcnt2=0`,
  `scarNo2=""`, `ara0101v.js:875-879`).
  One honest counter-note kept rather than smoothed over: the ticket-kind table
  contains 환승단체왕편권 / 환승단체복편권 (`tkKndCd` 28/29,
  `commCode.js:1597-1612`), so a 환승 round-trip TICKET exists as a product. The
  refusal above is a client-side booking rule in this app, not proof the server
  would refuse. We send what the app sends.
  **`cancel` was not touched, and its default is wrong for this shape.** A
  transfer hold has two journeys, so release it with
  `cancel(hold, journey_count="2")`; the parameter already existed. README says
  so where an operator would read it, together with the precondition the whole
  feature needs — a station pair SRT does not serve directly (경부선 and 호남선
  meet only at 오송, so 동대구→광주송정, 부산→목포 or 대전→광주송정).
  Offline gate: `1388 passed, 1 deselected` (was `1348`).

- **Three reservation variants, built from OUR bundle rather than from srtgo:
  group (단체), standby (예약대기) and the round trip / 오는열차 second leg.**
  The opposite evidentiary situation from payment and refund. Those two had to
  be built from srtgo's attestation because their routes are 0-hit here; all
  three of these are evidenced in our own v2.0.41 bundle, so srtgo was used only
  as a cross-check — and where the two disagree, the bundle won and the
  disagreement is recorded. **None of the three is live-verified.** All three
  ride the EXISTING `reserve` consent category:
  `SRT_LIVE_MUTATION_CATEGORIES` is untouched at
  `{"reserve", "cancel", "payment", "refund"}` and its canary is unchanged.
  **The app names all three of its job types itself**, in one comment on its own
  reservation form seed (`ara0101v.js:90`):
  `"jobId" : "1101"  //조정구분코드(1101:개인예약, 1102:예약대기, 1103:시트맵예약)`.
  **Standby** (`reserve(train, standby=True)`) sets `jobId=1102`, forces
  `psrmClCd1=1` and DROPS `reserveType`. All three move together because they
  come from the one branch that produces `1102` (`ara1001l.js:1445-1448` for the
  job id, `:1431` for the cabin — the 특실 branch beside it tests only the two
  예약가능 images, so a 특실 standby has no representation in the app; srtgo
  `srt.py:990-991` for `reserveType` being personal-only). Forcing the cabin is
  not cosmetic: the default `GENERAL_FIRST` resolves to 특실 whenever the general
  cabin is not "예약가능", which is exactly what a standby train looks like, so
  without the override asking for a waitlist place would have silently ordered
  first class. `stndFlg` stays `"N"` — that is 입석여부, a different concept, and
  the app never writes it (2 hits, both non-writes).
  **THE DISAGREEMENT, and the bundle wins.** srtgo selects standby from
  `rsvWaitPsbCd >= 0`. Our app never reads that column for the decision; it reads
  the selected row's general-cabin IMAGE (`gnrmRsvPsbImg`, `ara1001l.js:32-33`,
  `:1447`). The two are not interchangeable: the group search `Ara10082` omits
  `rsvWaitPsbCd` entirely — our own group fixture confirms it — while
  `gnrmRsvPsbImg` is on both personal and group rows. So the image is the rule
  here. Both spellings count (`grd_WF_Waiting.png` is what the server sends;
  the app rewrites it to `_S` on tap, `:1045`), a row with a DIFFERENT image is
  refused, and a row with NO image column is ACCEPTED — absence is not
  ineligibility, the same rule `arvDt1` already gets. srtgo's follow-up
  standby-option POST `/ata/selectListAta01135_n.do` is **0-hit** in our bundle
  with no equivalent in it, so it is deliberately NOT implemented.
  **Group** is `SrtClient.reserve_group`, a separate method rather than
  `reserve(group=True)`, on three grounds: the endpoint changes
  (`/arc/selectListArc06014_n.do`, `ara1001l.js:1542-1547`), the precondition
  changes (the train must come from `search_group_trains`/`Ara10082`, which
  returns different columns), and the return value may not mean the same thing.
  The BODY delta is exactly one field — `grpDv="1"` — the same delegate-and-flip
  shape `group_search_ajax_payload` already uses; in particular `jobId` stays
  `1101`, because the app picks the job type without ever consulting `grpDv`.
  The **party-size floor is 10**, and it is the app's own two-sided boundary, not
  a guess: `ara0101v.js:551-554` refuses 단체 under 10 ("단체예약은 10매
  이상입니다.") and `:562-566` refuses a non-단체 party over 9 ("10매 이상은
  단체예약입니다."). Two more app rules are expressed structurally rather than
  checked: there is no `window_seat` argument, because ticking 단체 resets the
  seat option and disables the picker (`:446-457`), and no `round_trip`
  argument, because 단체 + 왕복 is refused at three separate points (`:348-351`,
  `:440-443`, `:557-560`).
  **What group's request evidence does NOT cover is its response.** The app hands
  a group reservation to the payment page with `pnrNo` forced to `-1`, and
  identifies it by `resultMap.tmpJobSqno1` (임시작업일련번호), where a personal
  reservation passes `reservListMap.pnrNo` (`ara1001l.js:1597-1610`). If a real
  group response carries no PNR, `parse_reservation_hold_response` raises rather
  than inventing a hold, and `cancel` — which takes a PNR — has nothing to act
  on. The parsers were deliberately left untouched: a group hold object invented
  with no live evidence of its shape would be worse than an exception. A live
  group attempt must be treated as potentially uncancellable from this library,
  and README says so at the point an operator would read it.
  **Round trip** (`reserve(train, round_trip=True)`) adds exactly `rtnDv="1"`
  and nothing else, because SRT does not model a round trip as a multi-leg
  reservation — it models it as 오는열차. The app reserves the 가는열차,
  re-searches with the stations swapped and `back_dptDt1`/`back_dptTm1`, then
  reserves the 오는열차 as a SECOND POST to the same endpoint whose leg-1 fields
  are overwritten with the return train (`ara1001l.js:1454-1470`, `:1580-1596`).
  So the public API is two ordinary `reserve` calls, with
  `TrainSearchQuery.for_return_leg(date, time)` building the swapped query. That
  preserves the property `reserve` is built around: one call creates at most one
  hold, so a failure strands at most one. The caller owns both PNRs.
  **`jrnyCnt` does NOT become `"2"` for a round trip**, and the premise that it
  might is refuted by the bundle rather than argued about. `jrnyCnt` has three
  hits in the whole bundle: the seed `"1"`, a null-check read, and ONE write —
  the 환승 (transfer) toggle, which sets `jrnyCnt="2"` with `jrnyTpCd="14"`
  (`ara0101v.js:288-311`). Nothing on the 왕복 path touches it, and 환승 + 왕복
  is mutually exclusive anyway. By extension the `...2` suffix indexes the 여정
  (journey) slot — the app's own gloss is `여정일련번호1(001:선행, 002:후행)`
  (`ara0101v.js:97`, `ara1001l.js:1607`) — so slot 2 is a transfer's FOLLOWING
  leg and a round trip never fills it. It is certainly not a second passenger;
  passengers live in `psgTpCd1..5`, indexed by TYPE.
  **`jobId=1103` (시트맵예약) was deliberately left out.** The value is evidenced
  (`ara0101v.js:90`, `ara1001l.js:1436`) but the request is not: `1103` is set on
  the ARC0201C branch, which navigates to the seat-map page (already read-only
  here as `get_seat_page`) and hands off to a `fn_submit()` whose only hit in the
  entire 21,673-file bundle is the call site (`ara0101v.js:882`) — its definition
  is server-rendered, so neither the submit target nor the body is knowable
  offline. `payloads.RESERVE_SEATMAP_JOBID` records the value and the field
  family a seat-map body would carry (`ara0101v.js:871-878`) so that "not
  implemented" is not mistaken for "not known about", and a test asserts nothing
  emits it.
  **Compatibility.** Every new parameter is keyword-only and defaulted off, and
  the first test in the new file asserts the default form is byte-for-byte AND
  order-for-order identical to what it was — the existing single-passenger pins
  in `test_mutation_live_paths` pass unchanged. `arc06014` is registered in
  `SRT_MUTATION_ROUTES` and mapped to the `reserve` category (a route count of
  five against four categories, deliberately), and the read-capture guard now
  forbids it too.
  Offline gate: `1348 passed, 1 deselected` (was `1311`).

- **Payment and refund are live-verified and live-enabled.**
  `safety.SRT_LIVE_MUTATION_CATEGORIES` now holds
  `{"reserve", "cancel", "payment", "refund"}` — the four categories a live run
  has answered, and nothing is in that set for any other reason. This
  **supersedes the entry below** ("Card payment and refund are implemented, and
  still cannot be transmitted"), which was accurate when it landed: implementing
  them did not open the gate, and verifying them did.
  **The verification, 2026-07-26, in two stages.** A free probe went first: a
  fake card and a non-existent PNR were sent to both routes, and neither
  answered a 404 or an HTML error shell. `/atc/getListAtc14087.do` returned
  `{"ErrorCode":"0","outDataSets":{"dsOutput0":[{"msgCd":"WRT300005",
  "strResult":"FAIL","msgTxt":"조회자료가 없습니다."}]},"ErrorMsg":""}` and the
  payment route `/ata/selectListAta09036_n.do` returned `strResult=FAIL` /
  `msgCd=WRT100170` — proper business envelopes on both, which established that
  `Ata09036` and `Atc14087`/`Atc02063` exist on our v2.0.41 app version without
  spending anything, even though all three are 0-hit in its offline bundle and
  srtgo-attested only. **Then one real round trip:** 수서→동탄
  (`0551`→`0552`, the shortest SRT hop), 2026-08-09, train 315, one adult,
  7,500 KRW. Payment answered `strResult=SUCC` / `msgCd=IRT000000`; the two-step
  refund (`Atc02063`) answered `strResult=SUCC` / `msgCd=IRT200277`; the account
  was then verified empty of both reservations and tickets from a separate
  session. So `Ata09036` and `Atc02063` are **live-verified on 2026-07-26**, for
  a single-journey one-adult ticket, and remain 0-hit in the v2.0.41 bundle —
  two statements about different evidence, both true.
  **Two things this settled that were previously recorded as open.** First,
  `IRT000000` and `IRT200277` are identical to korail's confirmation codes for
  the same two operations, reinforcing the shared-platform observation already
  recorded here for `IRR000018`/`IRG000000` — still an observation about the
  codes, not a proven claim about the backend. Second, **srtgo's refund
  spellings `tkRetPwd`/`psgNm`/`pnr_no` are correct**: the live run sent them
  and the server refunded the ticket, so the doubt recorded below (against our
  app's `retPwd`/`buyPsNm`/`pnrNo` cache spellings) is resolved in srtgo's
  favour. Unlike srtgo's korail `txtPrnNo`, which this project found to be a
  genuine typo. srtgo was wrong there and right here — single-source field names
  have to be tested one at a time, not trusted or distrusted as a class.
  **What it did not settle.** The origin is unchanged: `Ata09036`, `Atc02063`
  and `Atc14087` are still 0-hit across all 21,673 files of the v2.0.41 offline
  bundle (which has no `Atc02*` family at all), our own app still charges
  through the `Ard02017`/`Ard02018` WebView plus TransKey and FIDO, the payment
  shape is still one implementation counted twice and the refund shape one with
  no upstream. One live success is live-server evidence, not static
  corroboration, and it covered a single-journey, one-adult, general-seat ticket
  on one personal card in one lump sum. Group, multi-leg, standby, corporate
  cards and instalments were not exercised.
  **Thirteen tests asserted that payment and refund could not transmit.** None
  of that coverage was deleted; each pin moved onto the invariant that survived,
  and the canaries now pin the exact enabled set so a *fifth* category still
  fails loudly rather than pinning "nothing is enabled". Consent gating,
  `dry_run`, the card-kind XOR, step 1's no-body contract, step 2's dependence
  on a step-1 identity, the route/category binding in both directions and
  `assert_no_card_secrets` all still refuse and still issue zero requests. The
  "cannot be sent" tests became "is built, gated and routed correctly": each
  category's exact wire fields are now asserted off a recorded `MockTransport`
  request under a fully valid consent.
  **`assert_no_card_secrets` matters more now, not less.** While `payment` was
  outside the enabled set, "a PAN cannot leave this process by any path" was
  already guaranteed by the membership gate. It is now the only thing between a
  hand-assembled card body and the wire on every route that is not the payment
  route, so its tests are load-bearing individually.
  Offline gate: `1311 passed, 1 deselected` (was `1285`).

- **Card payment and refund are implemented, and still cannot be transmitted.**
  *(Superseded by the entry above: both were live-verified and live-enabled on
  2026-07-26. The provenance recorded here is unchanged and still applies; only
  the "cannot be transmitted" and "`SRT_LIVE_MUTATION_CATEGORIES` is untouched"
  claims are retired, along with the disputed-spelling doubt.)*
  `SrtClient.pay_with_card` builds the 31-field 카드결제 form for
  `/ata/selectListAta09036_n.do`; `SrtClient.get_refund_ticket_info` reads an
  issued ticket's identity from `/atc/getListAtc14087.do` and
  `SrtClient.refund` builds the 환불 form for `/atc/selectListAtc02063_n.do`.
  All three build, gate, preview and parse. **`SRT_LIVE_MUTATION_CATEGORIES` is
  untouched at exactly `{"reserve", "cancel"}`** — implementing these did not
  live-enable them, that is a separate decision nobody has made, and three
  canary tests plus a test proving a fully-permissive consent (including one
  acknowledging a real chargeable card) still transmits nothing pin it.
  **Read the provenance before trusting any field.** The route
  `Ata09036` and the refund routes `Atc14087`/`Atc02063` are 0-hit across all
  21,673 files of the v2.0.41 offline decompile — the bundle has no `Atc02*`
  family at all — and **our own app does not use the payment path**: it
  serialises `#rsvForm` to `Ard02017`/`Ard02018` (`ara1001l.js:1550,1599,1608`),
  server-rendered WebView pages, then charges through the TransKey secure keypad
  (`AndroidManifest.xml:143`) and RaonSecure FIDO (`:315`). So these plaintext
  endpoints may be a legacy path the server still honours, or dead for our app
  version. **Nobody has tested them.**
  **The two reference libraries are one source, not two, and this was verified
  rather than assumed.** srtgo's payment dict is character-for-character
  identical to ryanking13/SRT's once the latter's Korean comments are stripped
  (same keys, values, non-alphabetical order, variable names, signature); srtgo
  depended on `SRTrain` until commit `8423f90` "Internalize SRT" (2024-12-13)
  vendored it wholesale. For the refund it is worse: ryanking13/SRT has no
  refund at all, so srtgo is the sole origin with no upstream to corroborate it.
  **The blanket "every field name is 0-hit" claim is false**, and the accurate
  version is recorded instead: the routes and the distinctive field names really
  are absent, but `mbCrdNo`, `totPrnb`, `jrnyCnt` (reservation JS) and
  `buyPsNm`, `saleWctNo`, `saleSqno`, `retPwd` (the local `"ticketListOffline"`
  cache handler, `webview/b.java:606-649`) do occur — never as request fields on
  these routes.
  **Amount fidelity was chosen deliberately**, against korail's precedent
  (`h_tot_prc` 59,800 vs `h_tot_rcvd_amt` 83,700): the form sends `rcvdAmt`
  (수납금액, post-discount, collectable) for both `totNewStlAmt` and
  `mnsStlAmt1`, with **no caller override**, and refuses a missing or zero
  amount rather than defaulting. One divergence stays unresolved — the server
  sends it zero-padded, ryanking13/SRT echoes the padding, srtgo casts to `int`;
  we send srtgo's bare digits because only srtgo's form has live attestation.
  **Two refund field names are disputed**: srtgo's `tkRetPwd`/`psgNm` against our
  app's `retPwd`/`buyPsNm` (`webview/b.java:645,648`), plus `pnr_no` against
  `pnrNo`. That b.java site deserialises a base64 SharedPreferences blob into a
  display model — a local cache, not an API schema — so srtgo's spelling ships
  and the doubt is recorded. The project has been burned here before, by srtgo's
  `txtPrnNo` for korail's `txtPnrNo`.
  **The payment's response envelope is the odd one out**: `outDataSets.dsOutput0[0]`
  where every other SRT mutation here uses `resultMap` (the refund included).
  Supporting it cost no new code path — `normalize_result_row` already accepted
  both spellings — and cancel, payment and refund now share one
  `_parse_result_envelope`. `SrtPaymentResult.succeeded`/`.failed` are
  deliberately **not** complements: an unrecognised status means *unknown*,
  because a blind payment retry can charge twice.
  **The refund's two steps are separate methods on purpose**, so a refused
  refund makes zero requests instead of firing step 1 and only then hitting the
  step-2 refusal. Step 1's route is registered as a read; that classification is
  an inference, not a proof, and says so — and because it is allowlisted, its
  "no body at all" contract is now **enforced** rather than merely documented,
  so it cannot be used to POST a card or refund form to a permitted path.
  **A PAN cannot leave this process by any path.** Route and category rules
  could not close one case: a hand-assembled payment body posted to a
  *different, permitted* route — an allowlisted read, or the live-enabled
  reserve route under a valid `category="reserve"` consent — is neither a
  category nor a route violation. `safety.CARD_SECRET_FIELDS` states the rule on
  the **data**: `stlCrCrdNo1`, `vanPwd1`, `crdVlidTrm1`, `athnVal1` may travel
  only as a `payment`, checked in `assert_read_only_request` and again at the
  mutation send boundary. *(When this landed `payment` was not live-enabled, so
  the effect was absolute and this guard was a second lock. It is now the only
  lock on every non-payment route — see the top of this section.)*

- **`MutationConsent.real_card_acknowledged`**, defaulting to `False` and purely
  additive, ports the KORAIL real-card acknowledgement pattern. A payment must
  state exactly one of `fake_card_only` (a non-chargeable test card) or
  `real_card_acknowledged` (a real charge); **neither and both are refused**,
  because an ambiguous consent is exactly the state a payment must never be sent
  on. Every consent written before this flag existed means exactly what it meant.
  Setting it is still not what enables a payment — live enablement is
  `SRT_LIVE_MUTATION_CATEGORIES`'s job — but since payment was enabled on
  2026-07-26 this XOR is the last gate before a real PAN goes out.

- **Redaction covers the payment and refund secrets**, and closed a
  pre-existing hole: `pnr_no` was absent from `SENSITIVE_KEYS` while `pnrNo` and
  `pnr_number` were present, so `redact_value` — which masks a dataclass by
  field name — passed a real PNR straight through for `SrtReservationHold` and
  `SrtReservationSummary`. Also added: the refund return password under all
  three spellings (`ogtkRetPwd`, `tkRetPwd`, `retPwd`), `buyPsNm`/`psgNm`, and
  `SrtPaymentCard`'s own attribute names, since `CARD_RE` only matches a 13-19
  digit run and a 2-digit PIN, a `YYMM` expiry and a `YYMMDD` birthdate all slip
  past it. The refund's `saleDt`/`saleWctNo`/`saleSqno` are deliberately **not**
  masked: with the password redacted they authorise nothing, and a
  fully-redacted preview says nothing at all.

- **Server-side failures now have a taxonomy.** Almost every rejection arrived
  as one undifferentiated `SrtAppError` with only `NET000001` special-cased, so
  a caller could not tell "this train is sold out" from "your session died" from
  "the queue refused you" without substring-matching Korean `msgTxt` — which is
  what `srtgo` does (`srtgo/srtgo.py:721-744`) and which breaks the day a
  message is reworded. Six new types, **each subclassing the one it refines**,
  so no existing `except` clause changes meaning: `SrtNoResultsError`,
  `SrtInvalidRequestError` and `SrtSeatUnavailableError` under `SrtAppError`;
  `SrtNetFunnelKeyError` and `SrtQueueRejectedError` under `SrtNetFunnelError`;
  `SrtIpBlockedError` under `SrtAuthError`. Read the tree as three caller
  answers: *retry is pointless* (`NoResults`, `InvalidRequest`,
  `SeatUnavailable`, `QueueRejected`, `IpBlocked`), *re-login and try again*
  (`SessionExpired`), *get a fresh key* (`NetFunnelKey`).
  **Classification is on `msgCd`, not on message text, because that is what the
  app does.** The single place in all 21,673 files of the v2.0.41 bundle where a
  server-supplied string is branched on is a code — `resultMap.msgCd == "S111"`
  → `memberShipLogin()` (`ara1001l.js:1562-1573`). Every other branch is
  `strResult == "FAIL"` (`ara1001l.js:206`, `:234`, `:1855`) or
  `ErrorCode == -1` (`:193`, `:1840`), which carry no reason at all, and the app
  never substring-matches `msgTxt` — it only displays it. Each exception keeps
  the raw `.code` and `.raw`, and an unmapped code still yields a plain
  `SrtAppError`, so the map grows from real traffic rather than from guesses.
  The queue is the one subsystem whose own bundle discriminates:
  `_showResultChkEnter` gives `kTsBlock` (301) and `kTsIpBlock` (302) their own
  `"onBlock"`/`"onIpBlock"` events beside `"onError"`.
  **`messages.js` turned out not to be a `msgCd` catalogue** — it is a
  client-side UI string table keyed `error001`/`rsv001`/`login018`, 172 strings,
  zero server codes. It matters in exactly one place: the sold-out seat page's
  error shell embeds `Sr.msgs.error001`, so `SrtSeatUnavailableError.code` is
  that alert *key*.
  **Two of srtgo's six leads are confirmed, but by code:**
  `"로그인 후 사용하십시오"` is our `S111` and
  `"정상적인 경로로 접근 부탁드립니다"` is our `NET000001`. The remaining four
  (`잔여석없음`, `사용자가 많아 접속이 원활하지 않습니다`,
  `예약대기 접수가 마감되었습니다`, `예약대기자한도수초과`) are 0-hit in the
  bundle, have no known `msgCd`, and the last two describe 예약대기 — a surface
  this library does not implement. They are **not** encoded; a test pins that
  they stay plain `SrtAppError`.
  **No retry behaviour was added.** The single bounded `NET000001` search retry
  is still the only self-directed retry, and `reserve` is still never retried
  because a retry duplicates a booking. Both live empty-result shapes are pinned
  against regression: the empty search FAIL (`WRG000000`) now raises
  `SrtNoResultsError`, while an empty reservation list still returns an empty
  list and the second `rsMap`/`WRT300005` FAIL envelope on that same successful
  response is still never read.

- The NetFunnel queue protocol is now complete. We sent only `getTidChkEnter`
  (5101); the bundle's own vendored `netfunnel.js` defines three request types
  (`RTYPE_CHK_ENTER=5002`, `RTYPE_SET_COMPLETE=5004`,
  `RTYPE_GET_TID_CHK_ENTER=5101`, netfunnel.js:84) and we implemented one third
  of it. Two consequences: if the queue actually engaged (201 `kContinue`) the
  search **failed** — the queue working as designed looked like an error — and
  the slot was never released, so our place in line was held until it timed out.
  Added `chkEnter` polling with HARD caps (20 polls or 60s wall clock, whichever
  first; each wait is the server's own `ttl` clamped to the app's 1..5s
  `TS_MAX_TTL`, so it can never become a tight retry loop) and `setComplete`
  after every guarded request, matching the bundle's `TS_AUTO_COMPLETE = true`.
  A failed release is swallowed by design: it runs after the caller's real
  request already succeeded or failed, and must never replace that outcome —
  least of all on a `reserve`, where it would hide a PNR.
  `safety.py`'s `/ts.wseq` contract now registers **three exact per-opcode query
  shapes** instead of one; it was not loosened. Two bundle details are recorded
  because they contradict the obvious assumption that one shape covers all
  three: `setComplete` carries **no `sid` and no `aid`** (the only one of the
  four builders in `netfunnel.js` that omits them), and `ttl` sits **between
  `prefix` and `sid`** on `chkEnter`, carrying the server's returned value
  rather than a constant. `js=yes` stays pinned throughout — srtgo and
  ryanking13/SRT both send `js=true`, and the bundle says `yes`.
  **Live-verified 2026-07-26**: a real acquire → release round trip
  (`5002:200` with a 256-character key and `ttl=0`/`nwait=0`, then `5004:200`).
  **Not verified**: the 201 polling path, because at normal load the queue does
  not engage and load was deliberately not synthesised to force it. That live
  run caught a bug no fixture could — the key-shape guard bounded keys at 128
  characters while a real key is 256, so every `setComplete` failed the guard
  and was silently swallowed. One divergence is deliberate: the acquire reply
  names a specific queue node (`ip`/`port`) the app would follow, and we stay
  pinned to the two canonical origins instead; the live run showed the front
  door releases the slot anyway.

- New read: `SrtClient.get_reservations(page_no=0)` — `POST
  /atc/selectListAtc14016_n.do` with `pageNo`, returning typed
  `SrtReservationSummary` rows in an `SrtReservationListResult`. This is the
  first read that ENUMERATES reservations; before it, the only way back to a
  hold whose PNR had been lost was to type the PNR into
  `scripts/recover_hold.py`, which required already knowing it. That script
  gains `--list`, a pure read that constructs no consent and prints the
  candidate PNRs.
  **Live-verified 2026-07-26 for the EMPTY case only** (the account has no
  reservations): `resultMap[0].strResult=SUCC` / `IRZ000005` /
  "조회할 자료가 없습니다." with `trainListMap: []`, `payListMap: []`,
  `rowCnt: 0`, `totPageCnt: 0`. Two verified oddities are pinned by tests: an
  empty result here is an empty *array*, not the `strResult=FAIL` /
  `WRG000000` the train search uses; and the same successful response carries a
  second envelope, `rsMap[0]`, saying `FAIL` / `WRT300005`, which is
  deliberately not read as a failure. The POPULATED row shape is **unverified**
  — the container pairing and every row field name come from srtgo
  (`srt.py:1069-1082`), and `payListMap`, `tkSpecNum`, `iseLmtTm` and `stlFlg`
  are 0-hit in the v2.0.41 bundle. Our bundle attests the route and `pageNo`
  only, as a WebView GET (`SRForegroundDialogActivity.java:31`,
  `sub/ticketList.html:405`); the JSON-over-POST spelling is srtgo's. Both were
  confirmed live; only the POST is allowlisted, taking `READ_ONLY_ROUTES` from
  20 routes to 21.

- A NetFunnel bypass (`kTsBypass` = 300) is now accepted without a key.
  `SUCCESS_CODES` already held `{"200", "300"}`, but the key check below it was
  unconditional, so the acceptance of 300 was unreachable for the only response
  shape a bypass actually has. The app's `_showResultChkEnter` sets
  `PS_N_RUNNING`, stores the result cookie and fires `onBypass` without ever
  reading `getValue("key")` — a bypassed queue has no place in line to key. Our
  `SrtNetFunnelError` escaped `SrtClient._get_act10_key` with code `None`, which
  `_search_with_retry` does not match (it retries only `NET000001`), so a
  bypassed queue aborted the search instead of searching. `kSuccess` (200) still
  requires a key. An empty key is inert downstream — every builder that consumes
  one emits `netfunnelKey=""`, verified by test, which is also what our own app
  sends, its NetFunnel integration being commented out
  (`ara0101v.js:651-655`, `ara1001l.js:1734-1739`) and `netfunnelKey` appearing
  nowhere in the v2.0.41 bundle.
- `TrainSearchQuery.train_group_code` now defaults to `"109"` (전체), the app's
  own booking-screen default, instead of `"900"` (KTX+SRT). `ara0101v.js:85-86`
  sets the picker to `"109"`/전체 on load and `:98-99` seeds
  `trnGpCd1="109"`/`trnGpNm1="전체"`. All three codes are legitimate on the wire,
  so this is a default *choice* rather than a wire error — but the old value had
  no evidence comment and disagreed with two other defaults in this same
  codebase (`SrtClient.get_train_group_selector` and
  `train_group_selector_payload` both already used `"109"`/`"전체"`). `"300"` and
  `"900"` remain constructible.
- `SrtClient.get_seat_page` derives `choiceSeatCount` from the passenger total
  instead of hardcoding one seat. The app sends
  `choiceSeatCount: lfn_getRsv("totPrnb")` (`ara1001l.js:1511`) — the party size
  the booking screen collected (`ara0101v.js:794`/`:809`) — and
  `safety.SEAT_PAGE_VALUE_PATTERNS` already validated the field as any positive
  integer for that reason, but nothing was wired to it. New keyword-only
  `passengers=`; `seat_count=` is kept as the explicit override and now defaults
  to `None` ("not overridden") rather than `"1"`. With neither, the count is
  still one seat. `run_live_smoke` had the same bug — it searched with
  `query.passengers` and then read the seat page for one seat — and now passes
  the party through.
- `personal_reservation_payload` now sends `arvDt1` (도착일자), which it omitted
  entirely. The app writes it in the same block as the `dptDt1`/`dptTm1`/
  `arvTm1` we already sent (`ara1001l.js:1464`), and srtgo omits it only because
  `SRTTrain` has no arrival date — a divergence
  `docs/analysis/cross-validation-2026-07-21.md` had already recorded as an open
  one. Reserve is the only mutation route whose shape can be checked statically,
  so it is closed rather than left unverified. The value comes from
  `TrainSummary.arrival_date`, in the app's own field position (between `dptTm1`
  and `arvTm1`), and is blank when the row omits `arvDt` — matching the app's
  `#rsvForm` seed, and because a form that cannot be built is a reservation that
  cannot be made. The srtgo wire-fidelity test was changed deliberately, not
  weakened: it now pins srtgo's field set PLUS this one field, with the reason
  recorded in place.
- `personal_reservation_payload` now sends the OPERATING date in `runDt1`
  (`TrainSummary.run_date`), not the departure date. The app writes the two from
  different search-row fields in the same block — `ara1001l.js:1460`
  `"runDt1": item.runDt` (운행일자) versus `:1462` `"dptDt1": item.dptDt`
  (출발일자). srtgo sends `dep_date` for both only because `SRTTrain` carries no
  run date, and reproducing that was indistinguishable for a same-day service
  but wrong for a past-midnight one. We already parse `runDt`, and
  `seat_page_payload`, `timetable_payload` and `fare_payload` already use it;
  the reserve builder was the last one substituting the departure date. A row
  that omits `runDt` still falls back to the departure date, so the srtgo-
  equivalent case is unchanged; a `runDt` that is present but not an 8-digit
  date is rejected rather than silently replaced.
- Corrected the reservation-response polarity to the app's. The attempt parser
  failed on `strResult != "SUCC"`, but `ara1001l.js:1562` is
  `if (resultMap.strResult == "FAIL")` — it alerts and returns there, and any
  other value falls through to `:1577`/`:1609`, which read
  `reservListMap[0].pnrNo` and proceed with a created reservation. The app is
  consistent about this (`:206`, `:234`, `:1855`), and the search parser was
  already corrected the same way. The inverted test was duplicated in the
  salvage gate, so a third status value raised `SrtAppError` **and**
  simultaneously suppressed the PNR salvage — the exact orphaned hold that
  subsystem exists to prevent. Both now test `== "FAIL"`
  (`_declares_a_non_success` is renamed `_declares_a_declared_failure` to say
  what it means). `WRP011002` stays an independent failure signal; it was
  observed live alongside `strResult=FAIL`, so it never contradicts the
  polarity. A genuine FAIL still raises, still authoritatively over malformed
  `msgCd`/`msgTxt`, and is still refused by the salvage branch.
- **The live reserve->cancel round trip was performed on 2026-07-25 and both
  halves succeeded.** One operator run of
  `scripts/verify_reserve_cancel_roundtrip.py` against the real server (수서 →
  부산, one adult, general seat, a single train) exited 0: `reserve` returned
  `strResult=SUCC`, `msgCd=IRR000018` ("결제하지 않으면 예약이 취소됩니다.") and a
  PNR, `cancel` (`ard/selectListArd02045_n.do`, body `pnrNo` / `jrnyCnt="1"` /
  `rsvChgTno="0"`) returned `strResult=SUCC`, `msgCd=IRG000000`
  ("정상처리되었습니다"), and the ticket list re-read afterwards held no trace of
  the reservation — re-verified independently in a later session. The hold was
  never paid, so nothing was charged.
  This confirms, **against the live server and for our app version**, the cancel
  route and its exact three-field body, plus reserve's live wiring: the
  NetFunnel `act_10` key flow (the same one train search uses, *not* `act_19`)
  and the referer the client sends were both accepted. It does not change where
  the cancel shape came from: it was taken from srtgo and is still 0-hit across
  all 21,673 files of our v2.0.41 offline decompile, so this single run is its
  only corroboration.
  **Scope.** ONE single-journey, one-adult, general-seat reservation. Multi-leg
  (`jrnyCnt` > 1), group and standby reservations were not exercised, so
  `jrnyCnt="1"` is confirmed only for the single-journey case. `payment` and
  `refund` were unimplemented at the time of this run, stayed out of
  `SRT_LIVE_MUTATION_CATEGORIES`, and nothing was learned about their shapes
  here — they were implemented, then verified separately on 2026-07-26 and
  live-enabled; see the top of this section.
  Worth recording: both confirmation codes are identical to the sibling korail
  app's live-verified ones (reserve `IRR000018`, cancel `IRG000000`), which
  suggests the two operators run on a shared reservation platform. That is an
  observation about the codes, not a proven claim about the backend.
- Added `scripts/verify_reserve_cancel_roundtrip.py`, the operator-run live
  reserve->cancel verification. **It has since been run once, successfully — see
  the entry at the top of this section.** It logs in, searches,
  selects ONE train that actually has a bookable seat (refusing to proceed if
  none does), reserves one adult in the cheapest class, prints the PNR
  immediately, cancels it, and re-reads the ticket list to confirm nothing
  remains. It requires a second opt-in beyond the normal live flag —
  `SRT_LIVE_MUTATION=1` on top of `SRT_MOBILE_API_LIVE=1` — so it can never
  fire from an ordinary live smoke run, since "live reads are acceptable" is
  not consent to create a reservation. The raw `strResult`/`msgCd` are printed
  for both operations: they are the evidence the run exists to capture. Reserve
  and cancel are performed under separate single-category consents, so neither
  call carries the other's authority. Everything after a successful reserve is
  wrapped in `try`/`finally`; the `finally` retries the cancel if it has not
  already succeeded, and if that fails too the PNR is printed in an unmissable
  banner with the exact `recover_hold.py` command line. Exits non-zero on any
  failure; the password is never printed and the login id is masked.
- Extracted `read_query_from_env()`, `read_passenger_counts_from_env()`,
  `read_device_key_from_env()`, `train_is_reservable()` and
  `first_reservable_srt_train()` into `srt_mobile_api.live`, and rebuilt
  `run_live_smoke_from_env()` on the first three. The round-trip script reads
  the journey environment through these same helpers instead of growing a
  second, silently divergent set. `first_reservable_srt_train()` screens a row
  by asking the reserve builder whether its form can be built, rather than
  re-listing the required fields and drifting from it.
- Added `scripts/recover_hold.py`, the operator safety net for a stranded
  unpaid hold. It takes a PNR on the command line, logs in from
  `SRT_LOGIN_ID`/`SRT_LOGIN_PASSWORD`, and cancels that hold — deliberately
  standalone, needing no hold object or state from the run that created it,
  because the situation it exists for is the one where that run is gone. Its
  consent is constructed explicitly and grants `cancel` only (never reserve,
  payment or refund) with `dry_run=False`, since a dry run would preview and
  release nothing. It exits 0 only when the server reports the hold released,
  prints the raw `strResult`/`msgCd`, and reprints the PNR in a banner on every
  other outcome, including any exception. The password is never printed.
- **`SrtClient.reserve()` can now transmit.** It returns
  `MutationPreview | SrtReservationHold`: unchanged under the default
  `dry_run=True`, but a `dry_run=False` reserve consent now POSTs
  `arc/selectListArc05013_n.do` and returns the parsed `SrtReservationHold`
  whose `pnr_no` feeds `cancel()`. **A success creates a real unpaid hold on a
  real account**, which the caller owns and must cancel or pay. The NetFunnel
  gate is the same `act_10` key flow as train search (srtgo `srt.py:987`, *not*
  `act_19`), so it reuses the existing `_get_act10_key` rather than adding a
  second acquisition path; a caller-supplied `netfunnel_key` is honoured
  verbatim and suppresses the acquisition. A failed reserve is never retried, so
  at most one hold can exist per call, and session expiry clears the session and
  re-raises as it does for every other authenticated call.
  Losing a PNR is the worst outcome this path can produce, so it is designed
  against: if strict parsing trips over a field unrelated to the PNR *after* the
  server has created the hold, a degraded but **cancelable** hold is returned
  instead of raising, while a server-declared failure still raises rather than
  inventing a hold that does not exist. The live NetFunnel/referer wiring was
  unverified when this landed and **has since been exercised successfully** (see
  the 2026-07-25 entry at the top of this section); `scripts/recover_hold.py`
  cancels a stranded hold from nothing but its PNR string.
- **Live-enabled exactly two mutation categories, `reserve` and `cancel`.**
  `safety.SRT_LIVE_MUTATION_CATEGORIES` was an empty frozenset and is now
  `{"reserve", "cancel"}`, so a consented `dry_run=False` call in either
  category reaches the network. They are enabled together and only together:
  reserve creates an unpaid hold and cancel releases one (from a hold object or
  a bare PNR string), so enabling reserve without a transmittable cancel would
  strand a real reservation on any mid-flow failure. **`payment` and `refund`
  stayed out at this point**, and adding either required implementing it
  (neither had a client method then) and live-verifying its own wire format;
  a payment keeps a separate `fake_card_only` gate behind the live-enablement
  one. *(Both requirements were met later in this same unreleased range: the
  methods landed, then the 2026-07-26 live round trip verified them and the set
  grew to four. See the top of this section.)*
  This was a decision about **recoverability, not evidence**, and asserted
  nothing about verification: when it landed, the cancel route `ard02045` was
  srtgo-sourced and unconfirmed against our v2.0.41 app (0 hits across all
  21,673 files of the offline evidence bundle) and the live reserve->cancel round
  trip had not been performed. Opening the gate is what made performing it
  possible — **and it was performed on 2026-07-25**, confirming both halves
  against the live server (see the entry at the top of this section). The 0-hit
  fact is unchanged; what changed is that a live run now corroborates the shape.
- Ported the consent-gated mutation model from the verified korail surface. The
  package stays read-only **by default**: `MutationConsent` grants nothing on
  construction (every `allow_*` flag defaults to `False`), `dry_run` defaults to
  `True`, and `fake_card_only` defaults to `True`;
  `require_mutation_consent()` denies before any request is built, raising the
  new `SrtMutationNotAllowedError`. A `MutationPreview` forces its payload
  through `redact_payload()`, so a preview can never hold card data, PII, a PNR,
  or a NetFunnel key.
- Tiered the four evidenced state-changing routes (reserve `arc05013`, cancel
  `ard02045`, payment `ata09036`, refund `atc02063`) in
  `safety.SRT_MUTATION_ROUTES`, deliberately **outside** `READ_ONLY_ROUTES`:
  `assert_read_only_request()` still refuses every one of them, so the read-only
  allowlist and its 20-route guarantee are unchanged. `SRT_MUTATION_ROUTE_CATEGORIES`
  binds each route to exactly one consent category, so a consent for one
  category cannot be redirected to another category's route.
- Added `SrtClient.reserve()` (personal reservation, `arc/selectListArc05013_n.do`),
  its request builder `personal_reservation_payload()`, the
  `parse_reservation_hold_response()` parser, and the `SeatType` /
  `SrtReservationHold` types. As first added, `reserve()` was **preview-only**:
  `dry_run=False` was refused and the method returned a redacted
  `MutationPreview` of the exact form that would be POSTed, performing no I/O,
  because no cancel existed to release a hold it would create. **Superseded
  within this same unreleased range** — see the `reserve()` entry at the top of
  this section: once `cancel()` existed and both were live-enabled, that refusal
  was removed and `reserve()` now transmits under an explicit non-dry-run
  consent.
- Closed the transport-layer gap that this port opened. `SrtHttpClient.post_mutation_form`
  was ported wholesale and did transmit, so a caller reaching `SrtClient.http`
  directly could bypass `reserve()`'s preview-only hardening for any of the four
  categories. `safety.SRT_LIVE_MUTATION_CATEGORIES` — an empty frozenset when
  introduced — now names the categories permitted to reach the network, and it
  is enforced in `post_mutation_form` and re-asserted in the underlying
  `_send_mutation_request`, the function that actually calls `send`. Which
  categories are in that set changed twice more in this same unreleased range
  (see the top of this section: it now holds
  `{"reserve", "cancel", "payment", "refund"}`); what this entry established,
  and what still holds, is that membership is decided at the **transport layer**
  rather than only at the client methods, so a category outside the set cannot
  be transmitted even by a caller reaching `SrtClient.http` directly.
- Added `SrtClient.cancel()` for a created-but-unpaid reservation (예약취소,
  `ard/selectListArd02045_n.do`), with its request builder
  `unpaid_reservation_cancel_payload()`, the `parse_unpaid_cancel_response()`
  parser and the typed repr-safe `SrtCancelResult`. It accepts an
  `SrtReservationHold` or a bare PNR string (a caller recovering from a partial
  failure may have only the PNR), requires an authenticated session, is gated by
  `require_mutation_consent(consent, "cancel")`, and with the default
  `dry_run=True` returns a redacted `MutationPreview` and performs no I/O. As
  first added it was implemented and offline-tested only, its wire shape taken
  from srtgo and unconfirmed against our v2.0.41 app: the route is 0-hit across
  all 21,673 files of the offline evidence bundle, and only the `jrnyCnt="1"`
  value is partially corroborated by our own app (`ara0101v.js:92`). It could
  not transmit at all, the gate being empty. **Superseded twice within this same
  unreleased range**: `cancel` was live-enabled (see the top of this section) so
  `dry_run=False` reaches the wire, and the "unconfirmed" half of the provenance
  caveat fell on **2026-07-25**, when a live round trip released a real hold
  through this exact form (`SUCC` / `IRG000000`). What is NOT superseded is the
  shape's origin: it still comes from srtgo, is still 0-hit in the v2.0.41
  bundle, and is now corroborated by exactly one live run of one single-journey,
  one-adult hold.
- `jrnyCnt` is defaulted to `"1"`, not derived from the hold: the reserve
  response carries `totSeatNum` (a SEAT count) and no journey count, so
  `SrtReservationHold` has nothing to derive from, and every hold this library
  can create is single-journey. The optional `journey_count` override is
  compared numerically, tolerates zero-padding and whitespace (`"0001"` ->
  `"1"`), and falls back to `"1"` for anything unusable instead of raising —
  applying the korail regression (korail commit `3d7e8a5`), where a builder that
  demanded exactly `"1"` refused a live `h_jrny_cnt="0001"` and stranded a real
  unpaid hold. A cancel form that cannot be built means a hold that cannot be
  released. "Never raises" is now literally true: the zero padding is stripped
  textually before any numeric conversion, and a value past CPython's int/str
  conversion limit (4300 significant digits, on which `int()` raises
  `ValueError`) falls back instead of propagating. The override is reachable
  from `SrtClient.cancel(..., journey_count=...)` as well as from the builder:
  without it, the day live capture shows a multi-leg PNR needing `jrnyCnt="2"`
  a caller would have to hand-roll `payloads` plus `post_mutation_form`, which
  is precisely the path that orphans holds. The default is unchanged.
- `parse_reservation_hold_response()` no longer discards a reserve response that
  fails strict validation. A live reserve can create a hold before we parse, so
  when strict parsing raises a protocol error and a usable
  `reservListMap[0].pnrNo` is present, a minimal `SrtReservationHold` carrying
  the PNR is returned instead (mirroring korail's
  `_hold_from_reservation_response`); with no PNR the original error is
  re-raised, and business failures and session expiries are never salvaged. This
  is a prerequisite for ever enabling live reserve.
- Made "business failures and session expiries are never salvaged" actually
  true. `parse_reservation_attempt_response` read `msgCd`/`msgTxt` strictly
  BEFORE classifying the declared `strResult`, so a FAIL that was also slightly
  malformed (no `msgCd`, an int `msgCd`, no `msgTxt`) raised `SrtProtocolError`
  — the one exception the salvage branch catches — and
  `parse_reservation_hold_response` returned a minimal hold for a reservation
  the server had just refused. Telling a caller a hold exists when it does not
  is as damaging as losing one that does: they stop trying to recover. The
  declared status is now classified first, so such a response raises
  `SrtAppError` / `SrtSessionExpiredError` as its own docstring always claimed,
  and the salvage branch independently re-reads `strResult` off the raw payload
  and refuses to build a hold for any declared non-success. A declared SUCCESS
  is still validated strictly; only a declared failure short-circuits.
  **Partially superseded within this same unreleased range**: "any declared
  non-success" was the wrong set — it is now "a declared `FAIL`", matching the
  app (see the polarity entry at the top of this section). The ordering fix
  itself, and the guarantee that a declared FAIL is never salvaged however
  malformed its optional fields, are unchanged.
- Corrected the statements the cancel method falsified. `reserve`'s docstring
  and refusal message, `safety.SRT_MUTATION_ROUTES` /
  `SRT_LIVE_MUTATION_CATEGORIES`, and `post_mutation_form`'s refusal message
  said "there is no cancel method". The real blocker is restated: a cancel
  method exists but sends through the same closed gate, so a live reserve would
  still create a hold this library could not release — and having a method is not
  evidence that the form it builds is the one this app version sends.
- Supersedes the 0.2.0 entry's statement that no reservation route, request
  builder, or client method was added, and the 0.1.0 entry's statement that
  mutation operations are excluded. Both were accurate at their release; as of
  this section a reservation route, builder, and client method exist, and so do
  a cancel route, builder and preview-by-default method. **This entry's own "no
  state-changing request is transmitted" is itself superseded within this
  range**: all four categories were live-enabled and now transmit under an
  explicit non-dry-run consent (see the top of this section). External seat-map
  and native-bridge flows remain unimplemented. The cancel, payment and refund
  wire formats are all 0-hit across the 21,673 files of the v2.0.41 offline
  evidence bundle, but none is unverified any more: a live round trip exercised
  cancel on 2026-07-25 and payment and refund on 2026-07-26.

## 0.2.0 - 2026-07-15

- Normalized the two observed personal/group search wrapper casings strictly,
  added typed repr-safe search metadata and optional row availability details,
  and enriched missing station names only from hydrated request context.
- Preserved the legacy raw notice mapping and numeric-only fare item contracts;
  added typed uppercase notice results and all semantic fare rows through
  separate additive APIs/fields, and retained leading-empty timetable names.
- Aligned search details with sanitized 51-field personal and 43-field group
  shapes, including integer delay/order values, received fare, and five train
  composition codes.
- Added bounded, lazy personal and group train-search page iteration while
  preserving the existing single-page search methods.
- Reused the hydrated search form and NetFunnel key across continuation pages,
  with exact cursor validation, progress bounds, and one refresh/retry for only
  a continuation page rejected with `NET000001`.
- Kept the reviewed 20-route read-only boundary unchanged. A bounded live run
  verified two personal and two group pages without retaining response values.
- Added the pure offline `parse_reservation_attempt_response()` parser and the
  typed repr-safe `ReservationAttemptResult` for the documented
  reservation-attempt response shape. No reservation route, request builder,
  NetFunnel `act_19` flow, client method, or live call was added; the read-only
  boundary is unchanged.

## 0.1.0 - 2026-07-14

- Prepared the existing installable, typed, read-only SRT mobile API client for
  reproducible internal builds and offline verification.
- Retained the 20-route safety boundary, including the bounded seat-page read;
  mutation operations and physical-seat schemas remain excluded.
