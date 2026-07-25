from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import replace
from html.parser import HTMLParser
from typing import Any

from .client import SrtClient
from .config import SrtConfig
from .errors import SrtAppError
from .models import PassengerCounts, SeatSelectionPage, TrainSearchQuery, TrainSummary
from .payloads import (
    TRAIN_GROUP_OPTIONS,
    _general_seat_available,
    _special_seat_available,
    personal_reservation_payload,
)


def live_enabled() -> bool:
    return os.environ.get("SRT_MOBILE_API_LIVE") == "1"


def read_credentials_from_env() -> tuple[str, str]:
    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        raise RuntimeError("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required for live smoke")
    return login_id, password


def _first_complete_srt_seat_train(
    trains: Sequence[TrainSummary],
) -> TrainSummary | None:
    for train in trains:
        # seat_attr_code is deliberately NOT required here. The app and srtgo
        # both source seatAttCd from the request side (rqSeatAttCd1="015"), and
        # seat_page_payload defaults it rather than reading train.seat_attr_code.
        #
        # CORRECTION, live capture 2026-07-26: this comment used to justify that
        # by claiming "a genuine captured row omits it". It does not -- all 40
        # live rows carried seatAttCd="015", echoing the request. Requiring it
        # would in fact NOT skip every real train. The exclusion stands on the
        # request-side sourcing alone, which is the reason that survives.
        required = (
            train.train_no,
            train.run_date,
            train.departure_date,
            train.departure_time,
            train.departure_station_code,
            train.arrival_station_code,
            train.departure_run_order,
            train.arrival_run_order,
        )
        if train.train_group_code == "300" and all(
            isinstance(value, str) and bool(value) for value in required
        ):
            return train
    return None


def _first_reservable_srt_seat_train(
    trains: Sequence[TrainSummary],
) -> TrainSummary | None:
    """The first completely-described SRT row the server also calls bookable."""
    for train in trains:
        if train_is_reservable(train) and _first_complete_srt_seat_train([train]):
            return train
    return None


def _external_seat_map_handoff_present(page: SeatSelectionPage | None) -> bool:
    if page is None:
        return False
    raw_lower = page.raw.casefold()
    return "korail.com" in raw_lower and "srtjob=seatmap" in raw_lower


SEAT_IDENTIFIER_RE = re.compile(
    r"(?:^|[\s_-])(?:seat|scar)(?:[\s_-]|$)",
    re.IGNORECASE,
)


class _EmbeddedSeatInventoryProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.candidate_count = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() in {"a", "form", "input", "script", "style"}:
            return
        values = {name.casefold(): value or "" for name, value in attrs}
        identifiers = f"{values.get('id', '')} {values.get('class', '')}"
        has_seat_data_attribute = any(
            name.casefold().startswith("data-") and "seat" in name.casefold()
            for name, _value in attrs
        )
        if has_seat_data_attribute or SEAT_IDENTIFIER_RE.search(identifiers):
            self.candidate_count += 1


def _embedded_seat_inventory_candidate_present(
    page: SeatSelectionPage | None,
) -> bool:
    if page is None:
        return False
    parser = _EmbeddedSeatInventoryProbe()
    parser.feed(page.raw)
    return parser.candidate_count >= 2


def run_live_smoke(
    client: SrtClient,
    *,
    login_id: str,
    password: str,
    query: TrainSearchQuery,
) -> dict[str, Any]:
    session = client.login(login_id, password)
    main = client.get_main()
    booking = client.get_booking_page()
    group_name = TRAIN_GROUP_OPTIONS[query.train_group_code][0]
    selectors = (
        client.get_station_selector(
            query.departure_station_name or query.departure_station_code,
            query.arrival_station_name or query.arrival_station_code,
            query.departure_station_code,
            query.arrival_station_code,
        ),
        client.get_station_map_selector(),
        client.get_date_selector(query.departure_date),
        client.get_passenger_selector(query.passengers),
        client.get_seat_option_selector(request_seat_attr_code=query.seat_attr_code),
        client.get_train_group_selector(query.train_group_code, group_name),
    )
    notices = client.get_typed_notice_list()
    tickets = client.get_ticket_list()
    personal = client.search_trains(query)
    # Prefer a train the server currently reports as bookable, falling back to
    # the first completely-described SRT row. A SOLD-OUT train is not answered
    # with a seat map at all: the server returns an error shell, which
    # parse_seat_selection_page now refuses (SrtAppError "error001"). Live
    # capture 2026-07-26 found every train on 수서→부산 매진, so without this
    # preference the smoke reads the error shape on any busy route.
    seat_train = _first_reservable_srt_seat_train(
        personal.trains
    ) or _first_complete_srt_seat_train(personal.trains)
    # The seat page's choiceSeatCount is the party size (ara1001l.js:1511 sends
    # lfn_getRsv("totPrnb")). The smoke searches with query.passengers, so it
    # must read the seat page for the same party rather than silently asking for
    # one seat.
    seat_page = None
    seat_page_error: str | None = None
    if seat_train is not None:
        try:
            seat_page = client.get_seat_page(seat_train, passengers=query.passengers)
        except SrtAppError as exc:
            # Reported, not raised. "Every train on this route is sold out" is
            # the server telling the truth, and it must not read as a broken
            # smoke run -- but it must not read as a successful seat read
            # either, which is what the old marker-only parse produced.
            seat_page_error = exc.code or "UNKNOWN"
    mutual = client.get_mutual_verification()
    # Group search requires >= 10 passengers (the app blocks smaller groups
    # client-side, ara0101v.js:551-554); the individual query above may carry a
    # single passenger, so exercise the group leg with a valid group-sized query.
    group_query = replace(query, passengers=PassengerCounts(adult=10))
    group = client.search_group_trains(group_query)
    timetable = client.get_timetable(personal.trains[0]) if personal.trains else None
    fare = client.get_fare(personal.trains[0], query.passengers) if personal.trains else None
    return {
        "loggedIn": bool(session.user_map),
        "mainLoaded": bool(main.text),
        "bookingLoaded": bool(booking.text),
        "noticeCount": len(notices.notices),
        "ticketPageLoaded": bool(tickets.text),
        "personalTrainCount": len(personal.trains),
        "seatPageLoaded": bool(seat_page and seat_page.text),
        "seatSelectionMarkerPresent": bool(
            seat_page and "좌석선택" in seat_page.text
        ),
        # The car list the seat page actually carries; 0 on a page that brought
        # no inventory. seatPageErrorCode names the server's refusal instead
        # (e.g. "error001" for a sold-out train) so the two are distinguishable.
        "seatCarOptionCount": len(seat_page.cars) if seat_page else 0,
        "seatPageErrorCode": seat_page_error,
        "externalSeatMapHandoffPresent": _external_seat_map_handoff_present(
            seat_page
        ),
        "embeddedSeatInventoryCandidatePresent": (
            _embedded_seat_inventory_candidate_present(seat_page)
        ),
        "mutualVerificationLoaded": bool(mutual.verification_code),
        "groupTrainCount": len(group.trains),
        "timetableRowCount": len(timetable.rows) if timetable else 0,
        "fareItemCount": len(fare.items) if fare else 0,
        "selectorLoadedCount": sum(bool(page.text) for page in selectors),
    }


def read_passenger_counts_from_env() -> PassengerCounts:
    """Build the passenger mix from the documented SRT_*_COUNT variables."""
    return PassengerCounts(
        adult=int(os.environ.get("SRT_ADULT_COUNT", "1")),
        child=int(os.environ.get("SRT_CHILD_COUNT", "0")),
        senior=int(os.environ.get("SRT_SENIOR_COUNT", "0")),
        disability_1_to_3=int(os.environ.get("SRT_DISABILITY_1_TO_3_COUNT", "0")),
        disability_4_to_6=int(os.environ.get("SRT_DISABILITY_4_TO_6_COUNT", "0")),
    )


def read_query_from_env() -> TrainSearchQuery:
    """Build the journey query from the documented live-smoke variables.

    Extracted from :func:`run_live_smoke_from_env` so any other live tool reads
    the SAME variables with the SAME defaults, rather than growing a second,
    silently divergent set. ``SRT_TEST_DATE`` is the only one with no default.
    """
    test_date = os.environ.get("SRT_TEST_DATE")
    if not test_date:
        raise RuntimeError("SRT_TEST_DATE is required for live smoke")
    return TrainSearchQuery(
        departure_station_code=os.environ.get("SRT_DEPARTURE_STATION_CODE", "0551"),
        arrival_station_code=os.environ.get("SRT_ARRIVAL_STATION_CODE", "0020"),
        departure_date=test_date,
        departure_time=os.environ.get("SRT_DEPARTURE_TIME", "060000"),
        passengers=read_passenger_counts_from_env(),
        departure_station_name=os.environ.get("SRT_DEPARTURE_STATION_NAME", "수서"),
        arrival_station_name=os.environ.get("SRT_ARRIVAL_STATION_NAME", "부산"),
    )


def read_device_key_from_env() -> str:
    return os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF")


def train_is_reservable(train: TrainSummary) -> bool:
    """Whether the server currently reports a bookable seat on ``train``.

    Uses the same availability strings srtgo reads (``general_seat_available`` /
    ``special_seat_available``, srt.py:486-490). Either class counts, because
    ``SeatType.GENERAL_FIRST`` falls back from general to special.
    """
    return _general_seat_available(train) or _special_seat_available(train)


def first_reservable_srt_train(
    trains: Sequence[TrainSummary],
    passengers: PassengerCounts | None = None,
) -> TrainSummary | None:
    """The first train that is both bookable AND completely described.

    A row can advertise a free seat yet still be missing a field the reserve
    form requires, so availability alone is not enough. Rather than re-listing
    those fields (and drifting from the builder), this asks the builder itself:
    a row whose form cannot be built is skipped. That way a caller can only be
    handed a train the reserve payload will actually accept.
    """
    for train in trains:
        if not train_is_reservable(train):
            continue
        try:
            personal_reservation_payload(
                train,
                passengers or PassengerCounts(adult=1),
                netfunnel_key="",
            )
        except ValueError:
            continue
        return train
    return None


def run_live_smoke_from_env() -> dict[str, Any]:
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    query = read_query_from_env()
    client = SrtClient(SrtConfig(device_key=read_device_key_from_env()))
    try:
        return run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
