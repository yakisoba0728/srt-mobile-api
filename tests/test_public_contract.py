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
        "cancel",
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
        "get_refund_ticket_info",
        "get_reservations",
        "get_seat_page",
        # The seat page's follow-up read: one 호차's 좌석배치도, live-confirmed
        # 2026-07-26. A read like the rest -- registered in READ_ONLY_ROUTES
        # with its own exact form contract, and it creates nothing.
        "get_seat_grid",
        "get_seat_option_selector",
        "get_station_map_selector",
        "get_station_selector",
        "get_ticket_list",
        "get_timetable",
        "get_train_group_selector",
        "login",
        "logout",
        "iter_train_search_pages",
        # Present, gated, and live-enabled since 2026-07-26 (SUCC / IRT000000):
        # payment is in safety.SRT_LIVE_MUTATION_CATEGORIES, so with
        # dry_run=False and an unambiguous card-kind claim this really charges a
        # card. The default is still a redacted MutationPreview.
        "pay_with_card",
        # Same posture as pay_with_card, live-verified the same day
        # (SUCC / IRT200277): gated, previewable by default, and transmittable.
        "refund",
        "reserve",
        # The 단체 half of reserve, kept as its own method because it POSTs a
        # different endpoint (arc06014) and may not return a cancelable PNR.
        # Same "reserve" consent category and the same kill switch; the
        # request is bundle-evidenced, the response is not live-verified.
        "reserve_group",
        # The 환승 half of reserve. Same endpoint (arc05013) and the same
        # "reserve" consent category as reserve() -- a transfer is a personal
        # reservation with a second 여정 slot, not a new mutation -- but its own
        # method because it takes a TransferItinerary and never a bare train, so
        # half an itinerary cannot be booked by accident. Not live-verified.
        "reserve_transfer",
        "search_group_trains",
        # 환승 search: same endpoint as search_trains with chtnDvCd="2", kept
        # separate because its ROWS are half-itineraries that reserve() would
        # happily book on their own.
        "search_transfer_trains",
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
    assert list(signature.parameters) == [
        "self",
        "train",
        "cabin_class",
        "seat_count",
        "passengers",
        "seat_attr_code",
    ]
    assert signature.parameters["cabin_class"].default == "1"
    # choiceSeatCount is the party size (app: lfn_getRsv("totPrnb"),
    # ara1001l.js:1511), so the count is DERIVED from `passengers` rather than
    # pinned to a constant. `seat_count` stays as the explicit override and
    # therefore defaults to None (= "not overridden"), not to "1".
    assert signature.parameters["seat_count"].default is None
    assert signature.parameters["passengers"].default is None
    assert signature.parameters["passengers"].kind is inspect.Parameter.KEYWORD_ONLY
    # seatAttCd is a request-side constant (app default "015"), not a response-row value.
    assert signature.parameters["seat_attr_code"].default == "015"
    assert signature.parameters["seat_attr_code"].kind is inspect.Parameter.KEYWORD_ONLY
    assert get_type_hints(SrtClient.get_seat_page)["return"] is SeatSelectionPage
    assert srt_mobile_api.SeatSelectionPage is SeatSelectionPage


def test_seat_grid_method_type_and_exports_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import SeatDesignation, SeatGrid, SeatGridSeat

    signature = inspect.signature(SrtClient.get_seat_grid)
    # car_number is POSITIONAL and required: a seat grid is always a grid OF a
    # car, and the page's own form leaves scarNo empty until one is picked.
    assert list(signature.parameters) == [
        "self",
        "train",
        "car_number",
        "cabin_class",
        "seat_count",
        "passengers",
        "seat_attr_code",
    ]
    assert signature.parameters["car_number"].default is inspect.Parameter.empty
    assert signature.parameters["cabin_class"].default == "1"
    assert signature.parameters["seat_count"].default is None
    assert signature.parameters["passengers"].default is None
    assert signature.parameters["passengers"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["seat_attr_code"].default == "015"
    assert signature.parameters["seat_attr_code"].kind is inspect.Parameter.KEYWORD_ONLY
    assert get_type_hints(SrtClient.get_seat_grid)["return"] is SeatGrid
    for exported in (SeatGrid, SeatGridSeat, SeatDesignation):
        assert getattr(srt_mobile_api, exported.__name__) is exported


def test_cancel_method_signature_type_and_export_are_stable():
    from typing import get_type_hints

    from srt_mobile_api import (
        MutationPreview,
        SrtCancelResult,
        SrtReservationHold,
    )

    signature = inspect.signature(SrtClient.cancel)
    assert list(signature.parameters) == [
        "self",
        "reservation",
        "consent",
        "journey_count",
    ]
    assert signature.parameters["consent"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["consent"].default is inspect.Parameter.empty
    # jrnyCnt must be expressible through the public method. Without it, a
    # multi-leg PNR needing jrnyCnt="2" could only be cancelled by hand-rolling
    # the payload and calling post_mutation_form directly, which is the path
    # that orphans holds. Keyword-only and optional, so the default is unchanged.
    assert (
        signature.parameters["journey_count"].kind is inspect.Parameter.KEYWORD_ONLY
    )
    assert signature.parameters["journey_count"].default is None
    # A bare PNR must stay callable: a caller recovering from a partial failure
    # may have nothing else, and refusing that path orphans the reservation.
    hints = get_type_hints(SrtClient.cancel)
    assert hints["reservation"] == SrtReservationHold | str
    assert hints["journey_count"] == str | None
    assert hints["return"] == MutationPreview | SrtCancelResult
    assert srt_mobile_api.SrtCancelResult is SrtCancelResult
