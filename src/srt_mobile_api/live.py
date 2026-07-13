from __future__ import annotations

import os
from typing import Any

from .client import SrtClient
from .config import SrtConfig
from .models import PassengerCounts, TrainSearchQuery
from .payloads import TRAIN_GROUP_OPTIONS


def live_enabled() -> bool:
    return os.environ.get("SRT_MOBILE_API_LIVE") == "1"


def read_credentials_from_env() -> tuple[str, str]:
    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        raise RuntimeError("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required for live smoke")
    return login_id, password


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
        client.get_date_selector(query.departure_date, hour=query.departure_time[:2]),
        client.get_passenger_selector(query.passengers),
        client.get_seat_option_selector(request_seat_attr_code=query.seat_attr_code),
        client.get_train_group_selector(query.train_group_code, group_name),
    )
    notices = client.get_notice_list()
    tickets = client.get_ticket_list()
    personal = client.search_trains(query)
    group = client.search_group_trains(query)
    timetable = client.get_timetable(personal.trains[0]) if personal.trains else None
    fare = client.get_fare(personal.trains[0], query.passengers) if personal.trains else None
    return {
        "loggedIn": bool(session.user_map),
        "mainLoaded": bool(main.text),
        "bookingLoaded": bool(booking.text),
        "noticeCount": len(notices["noticeList"]),
        "ticketPageLoaded": bool(tickets.text),
        "personalTrainCount": len(personal.trains),
        "groupTrainCount": len(group.trains),
        "timetableRowCount": len(timetable.rows) if timetable else 0,
        "fareItemCount": len(fare.items) if fare else 0,
        "selectorLoadedCount": sum(bool(page.text) for page in selectors),
    }


def run_live_smoke_from_env() -> dict[str, Any]:
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    test_date = os.environ.get("SRT_TEST_DATE")
    if not test_date:
        raise RuntimeError("SRT_TEST_DATE is required for live smoke")
    passengers = PassengerCounts(
        adult=int(os.environ.get("SRT_ADULT_COUNT", "1")),
        child=int(os.environ.get("SRT_CHILD_COUNT", "0")),
        senior=int(os.environ.get("SRT_SENIOR_COUNT", "0")),
        disability_1_to_3=int(os.environ.get("SRT_DISABILITY_1_TO_3_COUNT", "0")),
        disability_4_to_6=int(os.environ.get("SRT_DISABILITY_4_TO_6_COUNT", "0")),
        infant=int(os.environ.get("SRT_INFANT_COUNT", "0")),
    )
    query = TrainSearchQuery(
        departure_station_code=os.environ.get("SRT_DEPARTURE_STATION_CODE", "0551"),
        arrival_station_code=os.environ.get("SRT_ARRIVAL_STATION_CODE", "0020"),
        departure_date=test_date,
        departure_time=os.environ.get("SRT_DEPARTURE_TIME", "060000"),
        passengers=passengers,
        departure_station_name=os.environ.get("SRT_DEPARTURE_STATION_NAME", "수서"),
        arrival_station_name=os.environ.get("SRT_ARRIVAL_STATION_NAME", "부산"),
    )
    client = SrtClient(SrtConfig(device_key=os.environ.get("SRT_DEVICE_KEY", "0123456789ABCDEF")))
    try:
        return run_live_smoke(client, login_id=login_id, password=password, query=query)
    finally:
        client.close()
