# srt-mobile-api

A Python client for the SRT (수서고속철도) mobile app's API. It searches trains,
places and cancels reservations, pays for them and refunds them, and reads the
discount and coupon surface — the same requests the Android app makes, from
Python instead.

**It is reverse-engineered.** SR publishes no API. Every route, field name and
response shape here was recovered by decompiling the SRT Android app v2.0.41
(21,673 files), by reading pages the live server renders to an authenticated
session, and — where neither could answer — from a third-party client's live
traffic. **It talks to the real service.** There is no sandbox: requests go to
`app.srail.or.kr` with your real account, and a reservation, a charge or a
refund made through this library is real. **It is not affiliated with SR
(에스알)**, is not endorsed by them, and carries no warranty that any of it will
keep working.

One structural fact explains a lot about the shape of this client: the SRT app
is a **WebView shell**. Most of its screens are HTML the server renders on
demand, and its own payment step runs through a TransKey secure keypad and a
RaonSecure FIDO SDK that no HTTP client can reproduce. So the surface here is
smaller and more uneven than its KORAIL sibling's — several things are missing
not because nobody tried but because there is nothing static to read.

This repository is an installable read-only-by-default package. Login and reads
transmit; **nothing that changes state transmits unless you say so explicitly**,
per operation, in writing. See [Nothing sends by accident](#nothing-sends-by-accident)
before you call anything in the second half of the API.

---

## Install

Python **3.11 or newer**. One runtime dependency, `httpx`.

There is no PyPI release. Install straight from GitHub:

```bash
python3 -m pip install "srt-mobile-api @ git+https://github.com/yakisoba0728/srt-mobile-api"
```

Or from a clone, if you want the tests and docs alongside it:

```bash
git clone https://github.com/yakisoba0728/srt-mobile-api
cd srt-mobile-api
python3 -m pip install -e ".[test]"
```

Check the install with the offline suite, which touches no network:

```bash
python3 -m pytest -q -m "not live"
```

At `HEAD` that reports `1754 passed, 1 deselected`. The single deselected case
is the live-service test, which additionally requires an explicit
`SRT_MOBILE_API_LIVE=1`. `-m "not live"` is the same gate CI and
[docs/RELEASE.md](docs/RELEASE.md) use.

## Quickstart

Log in, search, and read your reservations back. Every call below is a read;
nothing here creates, cancels, charges or refunds anything.

```python
from srt_mobile_api import PassengerCounts, SrtClient, TrainSearchQuery

client = SrtClient()
client.login("you@example.com", "password")   # email, phone, or membership no.

query = TrainSearchQuery(
    departure_station_code="0551",            # 수서
    arrival_station_code="0015",              # 동대구
    departure_date="20260809",                # YYYYMMDD
    departure_time="060000",                  # HHMMSS — search from
    passengers=PassengerCounts(adult=1),
)

for train in client.search_trains(query).trains:
    print(
        train.train_no,
        train.departure_time,
        train.arrival_time,
        train.general_seat_availability_name,  # e.g. "예약가능"
    )

# Read the account back: an empty account is an empty list, not an error.
for reservation in client.get_reservations().reservations:
    print(reservation.pnr_no)

client.close()
```

Station codes come from `srt_mobile_api.stations`
(`STATION_NAMES_BY_CODE`, `station_name_by_code`) — the app's own table.
`SrtClient()` needs no configuration; `SrtConfig` exists only to adjust the
timeout, user agent and device key, and refuses to point at anything other than
the two canonical SRT origins.

**If you also use `korail-mobile-api` in the same project, three names collide.**
This package and its KORAIL sibling each export a `TrainSearchQuery`, a
`DiscountCoupon` and a `MutationCategory`, and the three are not interchangeable — they are different
types with different shapes, and importing the wrong one type-checks but
builds the wrong request. Here, `TrainSearchQuery.passengers` is a
`PassengerCounts` and `departure_time` defaults to `"060000"`; KORAIL's
`TrainSearchQuery.passengers` is a plain `int` (default `1`) and its default
departure time is `"000000"`. They keep these names because each reads
naturally inside its own package; import both in one module and use the
package-qualified form (`srt_mobile_api.TrainSearchQuery` vs.
`korail_mobile_api.TrainSearchQuery`) rather than a bare `from ... import
TrainSearchQuery` on both. `MutationCategory` is the same story in the type
system: this package's has five members and KORAIL's seven, and the four they
share make the wrong import type-check.

Three parameter types are `Literal` aliases rather than `str`, so an editor
completes their values and a typo is an error rather than a request:
`SrtSeatAttrCode` (`reserve`, `reserve_transfer`), `SrtTrainGroupCode`
(`TrainSearchQuery.train_group_code`, `get_train_group_selector`) and
`MutationCategory` (`require_mutation_consent`). All three are exported, so a
caller can annotate their own wrappers with them. Nothing else is narrowed —
codes read off a response stay `str`, because the server is free to invent one.

## What it can do

Every method below is on `SrtClient`. Method names are given in full so they can
be grepped; each one's docstring carries its evidence.

**Searching**

- `search_trains(query)` — 직통 personal search, one page of `TrainSummary` rows.
- `search_group_trains(query)` — 단체 availability and fares; party of 10 or more.
- `search_transfer_trains(query)` — 환승, returning paired `TransferItinerary`
  objects plus whatever did not pair, with a reason.
- `iter_train_search_pages(query, group=False, max_pages=10)` — bounded lazy
  pagination over personal or group search; stops on the server's own cursor.
- `search_public_discount_trains(query, discount)` — the 할인 승차권 search, for
  an account with an approved 공공할인.

**Reading one train**

- `get_timetable(train)` — the train's stop list.
- `get_fare(train, passengers)` — the 운임 table.
- `get_seat_page(train)` — which cars still have seats (`SeatSelectionPage.cars`).
- `get_seat_grid(train, car_number)` — the 좌석배치도 for one 호차: every seat,
  its printed label and whether it can be picked.

**Reading the account**

- `get_reservations(page_no=0)` — typed reservation rows; the only read that
  enumerates them.
- `get_ticket_list(page_no=0)` — the neighbouring HTML ticket page.
- `get_discount_coupons()` — 할인쿠폰 held.
- `get_public_discounts()` — which 공공할인 this account is approved for.
- `get_typed_notice_list()`, `get_mutual_verification()`, `get_main()`,
  `get_booking_page()`, and six `get_*_selector(...)` popup reads.

**Changing state** — all of these require a `MutationConsent`; see the next
section.

- `reserve(train, consent=...)` — 개인예약, one unpaid hold, returns an
  `SrtReservationHold` carrying the PNR.
- `reserve(train, standby=True, consent=...)` — 예약대기 (`jobId=1102`).
- `reserve(train, round_trip=True, consent=...)` — 왕복 (`rtnDv=1`); two ordinary
  calls, one per leg, and the caller owns both PNRs. Refused for a Korail-only
  station or a 국회의원 후급 membership, because the app refuses both before it
  sends (`ara0101v.js:317-326`, `:337-341`).
- `reserve(train, seat_attr_code="021", consent=...)` — 휠체어석; `"028"` is
  전동휠체어 and `"015"` an ordinary seat. Omit it and the reservation takes
  the code the row was FOUND with, so searching for wheelchair inventory and
  reserving a row out of those results agree by default. The search itself
  validates nothing — `TrainSearchQuery.seat_attr_code` is a plain `str` and is
  forwarded as given — but the reservation accepts only these three, which are
  the ones SRT dispatches on, and its parameter is typed `SrtSeatAttrCode` so a
  type checker completes them and rejects a fourth. That asymmetry is
  deliberate: the query field is narrowed nowhere because nothing narrows it at
  runtime either.
- `reserve(train, designated_seats=..., consent=...)` — 좌석지정 (`jobId=1103`),
  taking a `SeatDesignation` built by `SeatGrid.choose("1B", "2C")`.
- `reserve_transfer(itinerary, consent=...)` — 환승; one request, two journeys.
- `cancel(hold_or_pnr, consent=...)` — release an unpaid hold. A hold records
  the `jrnyCnt` it was created with, so a 환승 hold cancels correctly without
  being told; pass `journey_count` yourself only when cancelling by bare PNR.
- `pay_with_card(reservation, card, consent=...)` — 카드결제. **Charges a real
  card.**
- `get_refund_ticket_info(pnr)` then `refund(ticket_info, consent=...)` — 환불,
  deliberately two calls so nothing is fetched implicitly.
- `register_discount_coupon(number, password, consent=...)` — 할인쿠폰 등록.

Reserve, the reservation list and cancel were re-run against the real server on
2026-07-27 after this round of fixes: a hold was created, read back with its
amount and its six-digit departure and arrival times intact, and released with
`SUCC` / `IRG000000`. Payment and refund were live-verified on 2026-07-26 and
are unchanged since.

Failures arrive as named exceptions, not as message-text matching: `SrtApiError`
at the root, with `SrtSessionExpiredError` (log in again), `SrtNoResultsError`
(the request was fine, nothing matched), `SrtNoDirectTrainError` (try 환승),
`SrtSeatUnavailableError`, `SrtInvalidRequestError`, `SrtIpBlockedError`,
`SrtQueueRejectedError` and `SrtMutationNotAllowedError` among them. Every one
keeps the server's raw `.code` and `.raw`.

## Nothing sends by accident

This is the part to read before calling anything above that changes state.
There are four independent gates, and a request has to pass all four.

**1. An explicit consent object, or nothing happens.** Every state-changing
method takes a keyword-only `consent: MutationConsent`. A fresh
`MutationConsent()` grants nothing — every `allow_*` flag defaults to `False` —
and a missing, wrong-typed or unrelated consent raises
`SrtMutationNotAllowedError` *before the request is even built*.

**2. `dry_run=True` is the default, and it returns a preview.** With the default
consent, a mutation method builds and validates the exact form it would POST,
then hands it back as a `MutationPreview` **without sending**. The preview's
payload is redacted on construction: card numbers, PINs, birthdates, PNRs,
coupon numbers and NetFunnel keys are `[REDACTED]`, and the same values are
excluded from every `repr`.

```python
from srt_mobile_api import MutationConsent

preview = client.reserve(train, consent=MutationConsent(allow_reserve=True))
print(preview.route, preview.payload)   # "dry-run: not sent"
```

**3. Categories are opted into one at a time.** There are five:
`reserve`, `cancel`, `payment`, `refund` and `coupon`. `allow_reserve=True`
authorizes reserving and nothing else — not cancelling, not paying, not
redeeming a coupon. A consent is bound to its route as well as its category, so
a `reserve` consent can never be aimed at the refund endpoint.

**4. A transport-layer kill switch decides which categories may transmit at
all.** `safety.SRT_LIVE_MUTATION_CATEGORIES` is checked at the only two places
that can send a state-changing request, independently of any consent:

| category | in the kill switch | why |
| --- | --- | --- |
| `reserve` | yes | live round trip, 2026-07-25 (`SUCC` / `IRR000018`) |
| `cancel` | yes | live round trip, 2026-07-25 (`SUCC` / `IRG000000`) |
| `payment` | yes | live round trip, 2026-07-26 (`SUCC` / `IRT000000`) |
| `refund` | yes | live round trip, 2026-07-26 (`SUCC` / `IRT200277`) |
| `coupon` | **no** | implemented and previewable; no live run has answered it |

Membership in that set has only ever meant one thing: a live run answered that
category's own wire format. `coupon` (할인쿠폰 등록) is fully implemented, and a
`dry_run=False` coupon call is refused at the transmit gate and again at the
send boundary — opening it needs a real unredeemed coupon, which nobody here
holds. The set is pinned by its own test canary, so widening it is a deliberate,
visible act.

Sending, then, looks like this — and this call really books a seat:

```python
hold = client.reserve(
    train,
    passengers=PassengerCounts(adult=1),
    consent=MutationConsent(allow_reserve=True, dry_run=False),
)
print(hold.pnr_no)      # a real unpaid hold on a real account, now yours
```

A payment needs one more thing on top: an unambiguous card-kind claim, exactly
one of `fake_card_only=True` (a non-chargeable test card, the default) or
`real_card_acknowledged=True` (a real PAN, money moves). Setting neither is
refused; setting both is refused too, because an ambiguous consent is precisely
the state a charge must never be sent on.

Two more boundaries sit underneath all of that:

- **Routes are allowlisted, not filtered.** The reviewed read-only boundary
  contains 26 routes; the five mutation routes are deliberately outside it, so
  `assert_read_only_request` rejects them by construction. Each mutation route
  is bound to exactly one category.
- **Card secrets are policed on the body, not the route.** `stlCrCrdNo1`,
  `vanPwd1`, `crdVlidTrm1` and `athnVal1` may travel **only** as a `payment`, so
  a hand-assembled card form cannot be smuggled out over a read route or under a
  `reserve` consent.

Finally, the library never retries on its own initiative except for one bounded
NetFunnel key refresh. A `reserve` is never retried, because a retried reserve is
a duplicate booking.

## What is not implemented, and why

- **단체 (group) booking — removed on purpose, 2026-07-26.** The request was
  correct; the endpoint answers with a 66 KB server-rendered *payment* page keyed
  by `tmpJobSqno`, not a cancelable PNR hold. It is a different product needing a
  second payment surface, an HTML parser and a KakaoPay story.
  `search_group_trains` is untouched and stays.
- **예약대기 standby and 왕복 round trip — implemented, never live-verified.**
  Both are evidenced in the app's own bundle and both preview correctly, but SRT
  has not offered an eligible 예약대기 train across ten searches, and no operator
  has run the round trip. Treat them as untested code paths.
- **환승 reservation — the search is live-confirmed, the reservation form is
  not.** Five slot-2 field names are inferred from slot 1's spelling and a live
  reserve is what would settle them.
- **할인쿠폰 등록 — implemented and gated shut** (see the table above).
- **할인 승차권 search — the request shape is evidenced, its effect is not.** It
  needs an account with an approved 공공할인; this project's account holds none,
  so all eight entitlement flags read empty and the search has never been
  usefully exercised. The same entitlement gap blocks confirming that a 청소년
  (`psgTpCd` 6) can actually be booked.
- **The app's own WebView payment path** (`Ard02017`/`Ard02018` plus TransKey and
  FIDO), the native bridges and the external Korail seat map are excluded
  entirely and are not reproducible from an HTTP client.

Each of these is written up with its evidence in
[docs/VERIFICATION.md](docs/VERIFICATION.md), including exactly what an operator
would have to do to settle it.

## Where the deep material lives

The verification record was moved out of this README so it could stay readable;
none of it was dropped.

| document | what is in it |
| --- | --- |
| [docs/VERIFICATION.md](docs/VERIFICATION.md) | **The audit log.** Every live run, its date, the server's own confirmation codes, what each run did *not* settle, the static provenance of every route, and corrections kept in place rather than deleted. |
| [docs/IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md) | The implementer's running log: what exists, what is deferred, and the reasoning behind each surface as it was built. |
| [docs/analysis/](docs/analysis/) | Dated static-analysis output, including the merged library specification `srt-app-api-library-spec-2026-07-09.md` and the cross-validation against reference clients. |
| [docs/RELEASE.md](docs/RELEASE.md) | The build-and-verify gate this repository runs before every release, and the record of what it took to clear the public-release blockers. |
| [docs/internal/](docs/internal/) | Development history — audits, superseded plans and design specs. Not user documentation; see its own `README.md`. |
| [SECURITY.md](SECURITY.md) | Credential handling, what must never be committed, and how to report a problem. |
| [CHANGELOG.md](CHANGELOG.md) | Historical record, superseded in place rather than rewritten. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | The three offline gates (tests, `ruff check`, pyright), the evidence tiers a change needs, and what changing the mutation-consent safety model specifically requires. |
| [NOTICE](NOTICE) | What this project studied in reference clients, and why nothing was copied from them. |

Operator tooling lives in `scripts/`: `srt_app_api_smoke.py` (read-only smoke
run), `capture_live_read_surface.py` (raw-response capture, refuses to write
inside this repository), `verify_reserve_cancel_roundtrip.py`, and
`recover_hold.py`, which cancels a stranded hold given nothing but its PNR — or
lists the account's reservations when the PNR itself is what was lost.

## Using it responsibly

SRT is a real, load-bearing public service and this client is indistinguishable
from the app at the wire. Search sits behind a NetFunnel queue; polling it in a
loop risks an IP ban for you and queue pollution for everyone else. Do not
store credentials, cookies, NetFunnel keys, raw response bodies, PNRs or
card-shaped values in this repository. Reservations, charges and refunds you
make are yours, and so is anything you strand.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE). This project is not affiliated
with, endorsed by, or sponsored by SR (수서고속철도), and "SRT" is used here
only to describe interoperability.
