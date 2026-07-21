import inspect

import srt_mobile_api
from srt_mobile_api import SrtClient
from srt_mobile_api.models import HtmlPage as ModelHtmlPage


def test_client_public_method_set_is_stable():
    methods = {
        name
        for name, value in inspect.getmembers(SrtClient, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {
        "clear_session",
        "close",
        "get_booking_page",
        "get_date_selector",
        "get_fare",
        "get_main",
        "get_mutual_verification",
        "get_notice_list",
        "get_typed_notice_list",
        "get_passenger_selector",
        "get_seat_page",
        "get_seat_option_selector",
        "get_station_map_selector",
        "get_station_selector",
        "get_ticket_list",
        "get_timetable",
        "get_train_group_selector",
        "login",
        "logout",
        "iter_train_search_pages",
        "search_group_trains",
        "search_trains",
    }


def test_completed_types_are_exported():
    for name in (
        "FareItem",
        "FarePage",
        "SrtAppError",
        "SrtNetFunnelError",
        "SrtSessionExpiredError",
        "SrtTransportError",
        "TimetablePage",
        "TimetableRow",
    ):
        assert getattr(srt_mobile_api, name)


def test_html_page_is_available_from_the_package_root():
    from srt_mobile_api import HtmlPage

    assert HtmlPage is ModelHtmlPage


def test_existing_method_signatures_remain_compatible():
    assert list(inspect.signature(SrtClient.login).parameters) == [
        "self",
        "login_id",
        "password",
        "login_type",
    ]
    assert list(inspect.signature(SrtClient.get_ticket_list).parameters) == ["self", "page_no"]
    assert list(inspect.signature(SrtClient.get_fare).parameters) == ["self", "train", "passengers"]

    pagination_parameters = inspect.signature(
        SrtClient.iter_train_search_pages
    ).parameters
    assert list(pagination_parameters) == ["self", "query", "group", "max_pages"]
    assert pagination_parameters["group"].kind is inspect.Parameter.KEYWORD_ONLY
    assert pagination_parameters["group"].default is False
    assert pagination_parameters["max_pages"].kind is inspect.Parameter.KEYWORD_ONLY
    assert pagination_parameters["max_pages"].default == 10


def test_selector_method_signatures_are_stable():
    assert list(inspect.signature(SrtClient.get_station_selector).parameters) == [
        "self",
        "departure_name",
        "arrival_name",
        "departure_code",
        "arrival_code",
    ]
    assert list(inspect.signature(SrtClient.get_station_map_selector).parameters) == ["self"]
    date_parameters = inspect.signature(SrtClient.get_date_selector).parameters
    assert list(date_parameters) == ["self", "date"]
    assert list(inspect.signature(SrtClient.get_passenger_selector).parameters) == ["self", "passengers"]
    seat_parameters = inspect.signature(SrtClient.get_seat_option_selector).parameters
    assert list(seat_parameters) == [
        "self",
        "request_seat_attr_code",
        "location_seat_attr_code",
        "seat_name",
    ]
    assert all(
        seat_parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("request_seat_attr_code", "location_seat_attr_code", "seat_name")
    )
    assert [
        seat_parameters[name].default
        for name in ("request_seat_attr_code", "location_seat_attr_code", "seat_name")
    ] == ["015", "000", "일반/기본"]
    train_group_parameters = inspect.signature(SrtClient.get_train_group_selector).parameters
    assert list(train_group_parameters) == ["self", "train_group_code", "train_group_name"]
    assert train_group_parameters["train_group_code"].default == "109"
    assert train_group_parameters["train_group_name"].default == "전체"


def test_mutual_method_signature_type_and_export_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import MutualVerificationResult

    signature = inspect.signature(SrtClient.get_mutual_verification)
    assert list(signature.parameters) == ["self"]
    assert (
        get_type_hints(SrtClient.get_mutual_verification)["return"]
        is MutualVerificationResult
    )
    assert srt_mobile_api.MutualVerificationResult is MutualVerificationResult


def test_seat_page_method_type_and_export_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import SeatSelectionPage

    signature = inspect.signature(SrtClient.get_seat_page)
    assert list(signature.parameters) == ["self", "train", "cabin_class", "seat_count"]
    assert signature.parameters["cabin_class"].default == "1"
    assert signature.parameters["seat_count"].default == "1"
    assert get_type_hints(SrtClient.get_seat_page)["return"] is SeatSelectionPage
    assert srt_mobile_api.SeatSelectionPage is SeatSelectionPage
