"""Offline contract tests for the 좌석배치도 read (``/arc/selectListArc02011_n.do``).

Everything here is built from the 2026-07-26 live capture of that route and
from the app's own bundle, and nothing here touches the network: the client
tests all run on ``httpx.MockTransport``.

The one fact that unblocked this endpoint is pinned first and hardest: the
train number goes on the wire zero-padded to FIVE characters. The same request
with ``trnNo=315`` came back as a 147-byte alert shell and with ``trnNo=00315``
came back as a 25,930-byte seat grid, so the padding is tested with a
three-character train number at both the builder and the safety boundary.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode

import httpx
import pytest

from srt_mobile_api import (
    PassengerCounts,
    SeatDesignation,
    SeatGrid,
    SeatGridSeat,
    SrtAppError,
    SrtClient,
    SrtConfig,
    SrtProtocolError,
    SrtSeatUnavailableError,
    SrtSessionExpiredError,
    TrainSummary,
)
from srt_mobile_api.parsers import parse_seat_grid_response
from srt_mobile_api.payloads import SEAT_TRAIN_NUMBER_LENGTH, seat_grid_payload
from srt_mobile_api.safety import (
    SEAT_GRID_PATH,
    SRT_MUTATION_ROUTES,
    MutationRoute,
    READ_ONLY_ROUTES,
    ReadOnlyRoute,
    assert_mutation_route,
    assert_read_only_request,
)

SEAT_GRID_ROUTE = "/arc/selectListArc02011_n.do"


def _seat_train(train_no: str = "315") -> TrainSummary:
    """The 수서 -> 동탄 row the 2026-07-26 seat-grid capture was made from.

    Train 315 is kept verbatim precisely because it is THREE characters: it is
    the case the padding exists for.
    """
    return TrainSummary(
        train_no=train_no,
        train_group_code="300",
        service_class_code="17",
        run_date="20260812",
        departure_date="20260812",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0552",
        departure_run_order="000001",
        arrival_run_order="000002",
    )


# --- the padding, which is the gate ------------------------------------------


def test_three_character_train_number_is_zero_padded_to_five():
    # THE fact. Unpadded, this exact request returns a 147-byte alert shell
    # ("출발 20분 전부터 좌석이 자동배정됩니다..."), which reads like a timing
    # rule and is not one -- padded, it returns the seat grid. The app pads the
    # same way: lfn_getTrNoData, "열차번호를 5자리로 채워서 가져옴"
    # (main.html:642-661), used at ara1001l.js:1461.
    form = seat_grid_payload(_seat_train("315"), "3")

    assert form["trnNo"] == "00315"
    assert len(form["trnNo"]) == SEAT_TRAIN_NUMBER_LENGTH == 5


@pytest.mark.parametrize(
    ("train_no", "expected"),
    [("1", "00001"), ("15", "00015"), ("315", "00315"), ("4315", "04315"), ("54315", "54315")],
)
def test_every_train_number_length_reaches_five_characters(train_no, expected):
    assert seat_grid_payload(_seat_train(train_no), "3")["trnNo"] == expected


def test_seat_grid_form_is_the_eleven_page_fields_in_page_order():
    # trnScarSeatFrm, as the live seat page declares it (and as the retained
    # 2026-07-15 structural evidence names it). Note what is NOT here: the seat
    # PAGE's reqCode/dptDt/dptTm, none of which this form carries.
    assert list(seat_grid_payload(_seat_train(), "3")) == [
        "trnGpCd",
        "runDt",
        "trnNo",
        "scarNo",
        "psrmClCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "seatAttCd",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "choiceSeatCount",
    ]


def test_seat_grid_form_values_come_from_the_row_not_from_constants():
    form = seat_grid_payload(_seat_train(), "7", "2", "3", seat_attr_code="021")

    assert form["trnGpCd"] == "300"
    assert form["runDt"] == "20260812"
    assert form["scarNo"] == "7"
    assert form["psrmClCd"] == "2"
    assert form["dptRsStnCd"] == "0551"
    assert form["arvRsStnCd"] == "0552"
    assert form["seatAttCd"] == "021"
    # The run orders are the ROW's own, which is what an earlier hand-built
    # probe got wrong by hardcoding them.
    assert form["dptStnRunOrdr"] == "000001"
    assert form["arvStnRunOrdr"] == "000002"
    assert form["choiceSeatCount"] == "3"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"car_number": ""}, "car_number"),
        ({"car_number": "3호차"}, "car_number"),
        ({"car_number": "3", "cabin_class": "3"}, "cabin_class"),
        ({"car_number": "3", "seat_count": "0"}, "seat_count"),
        ({"car_number": "3", "seat_attr_code": "15"}, "seat_attr_code"),
    ],
)
def test_seat_grid_form_refuses_malformed_arguments(kwargs, match):
    with pytest.raises(ValueError, match=match):
        seat_grid_payload(_seat_train(), **kwargs)


def test_seat_grid_form_refuses_a_non_srt_train_group():
    with pytest.raises(ValueError, match="train_group_code"):
        seat_grid_payload(
            TrainSummary(train_no="315", train_group_code="100"), "3"
        )


# --- parsing the grid ---------------------------------------------------------


def test_grid_parses_both_identifiers_attribute_codes_and_selectability(
    load_text_fixture,
):
    grid = parse_seat_grid_response(
        load_text_fixture("seat_grid_car_seats.html"), car_number="3"
    )

    assert isinstance(grid, SeatGrid)
    assert grid.car_number == "3"
    assert len(grid.seats) == 12
    # Document order, and BOTH names of each seat. Internal 3 is printed 1C:
    # confusing the two is the mistake this model exists to prevent.
    assert [seat.printed_seat_label for seat in grid.seats][:4] == ["1A", "1B", "1C", "1D"]
    assert [seat.internal_seat_number for seat in grid.seats][:4] == ["1", "2", "3", "4"]
    third = grid.seats[2]
    assert (third.internal_seat_number, third.printed_seat_label) == ("3", "1C")
    # Several 좌석속성코드 in one car, all four the live capture showed.
    assert {seat.seat_attribute_code for seat in grid.seats} == {"000", "015", "021", "028"}
    # Mixed Y/N, and the N cells are kept rather than dropped: the caller needs
    # to be able to see a seat exists and cannot be had.
    assert [seat.selectable for seat in grid.seats][:4] == [False, True, True, False]
    assert len(grid.selectable_seats) == 8
    assert all(seat.selectable for seat in grid.selectable_seats)


def test_grid_attribute_code_is_read_from_the_class_and_may_be_absent():
    grid = parse_seat_grid_response(
        "<div id=\"scarSeat_9A\" onclick=\"choiceSeatNo('40', '9A', 'Y');\">9A</div>",
        car_number="9",
    )

    assert grid.seats[0].seat_attribute_code == ""
    assert grid.seats[0].selectable is True


def test_grid_refusal_envelope_is_a_business_error_not_a_parse_failure():
    # The page's own handler: tmp = args.trim().split("#"); if (tmp[0] == "0")
    # alert(tmp[1]). So "0#..." is the server declining, and the taxonomy
    # already has a class for a declined seat read.
    with pytest.raises(SrtSeatUnavailableError) as raised:
        parse_seat_grid_response(
            "  0#출발 20분 전부터 좌석이 자동배정됩니다. 좌석지정을 원하시면 미리 예약해주세요.  ",
            car_number="3",
        )

    # A SrtAppError subclass, so `except SrtAppError` around the read keeps its
    # meaning -- the same rule every refinement in this taxonomy follows.
    assert isinstance(raised.value, SrtAppError)
    assert not isinstance(raised.value, SrtProtocolError)
    # This route is HTML and carries no msgCd; the envelope's own marker is all
    # there is, and the message is the server's verbatim text.
    assert raised.value.code == "0"
    assert "자동배정" in raised.value.message


def test_grid_refusal_with_no_message_still_classifies():
    with pytest.raises(SrtSeatUnavailableError) as raised:
        parse_seat_grid_response("0#", car_number="3")

    assert raised.value.code == "0"


@pytest.mark.parametrize(
    "html",
    [
        # A '#' in the markup is not an envelope: only a body whose FIRST
        # segment is exactly "0" is a refusal.
        "<div style=\"color:#ff0000\" onclick=\"choiceSeatNo('1', '1A', 'Y');\">1A</div>",
        "<div onclick=\"choiceSeatNo('1', '1A', 'Y');\">1A</div><!-- #grid -->",
    ],
)
def test_grid_hash_inside_markup_is_not_a_refusal(html):
    grid = parse_seat_grid_response(html, car_number="3")

    assert [seat.printed_seat_label for seat in grid.seats] == ["1A"]


def test_grid_refuses_empty_and_seatless_bodies():
    with pytest.raises(SrtProtocolError, match="empty"):
        parse_seat_grid_response("   ", car_number="3")
    # A body with no choiceSeatNo cell is not "an empty car" -- an empty car
    # still renders N cells -- so it is a shape we do not understand.
    with pytest.raises(SrtProtocolError, match="choiceSeatNo"):
        parse_seat_grid_response("<div class='seatArea'></div>", car_number="3")


def test_grid_refuses_the_sign_in_page():
    with pytest.raises(SrtSessionExpiredError):
        parse_seat_grid_response(
            '<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>',
            car_number="3",
        )


# --- choosing seats out of a grid --------------------------------------------


def test_choose_designates_by_printed_label_and_keeps_the_car(load_text_fixture):
    grid = parse_seat_grid_response(
        load_text_fixture("seat_grid_car_seats.html"), car_number="3"
    )

    designation = grid.choose("1B", "2C")

    assert isinstance(designation, SeatDesignation)
    assert designation.car_number == "3"
    assert designation.printed_seat_labels == ("1B", "2C")
    # The internal numbers travel with the seats even though the form sends the
    # labels, so a caller can still see both.
    assert [seat.internal_seat_number for seat in designation.seats] == ["2", "7"]


def test_choose_refuses_an_unselectable_seat(load_text_fixture):
    grid = parse_seat_grid_response(
        load_text_fixture("seat_grid_car_seats.html"), car_number="3"
    )

    with pytest.raises(ValueError, match="not selectable"):
        grid.choose("1A")


def test_choose_refuses_a_label_the_grid_does_not_have(load_text_fixture):
    grid = parse_seat_grid_response(
        load_text_fixture("seat_grid_car_seats.html"), car_number="3"
    )

    with pytest.raises(ValueError, match="not in car 3's grid"):
        grid.choose("9Z")


def test_choose_refuses_the_same_seat_twice(load_text_fixture):
    grid = parse_seat_grid_response(
        load_text_fixture("seat_grid_car_seats.html"), car_number="3"
    )

    with pytest.raises(ValueError, match="only once"):
        grid.choose("1B", "1B")


def test_designation_refuses_an_empty_seat_list_and_a_non_numeric_car():
    seat = SeatGridSeat(
        internal_seat_number="2",
        printed_seat_label="1B",
        seat_attribute_code="015",
        selectable=True,
    )
    with pytest.raises(ValueError, match="at least one seat"):
        SeatDesignation(car_number="3", seats=())
    with pytest.raises(ValueError, match="car number"):
        SeatDesignation(car_number="3호차", seats=(seat,))


# --- the client read ----------------------------------------------------------


def _grid_client(requests: list[httpx.Request], html: str) -> SrtClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, text=html, headers={"Content-Type": "text/html; charset=UTF-8"}
        )

    return SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))


def test_get_seat_grid_posts_once_with_the_padded_train_number(load_text_fixture):
    requests: list[httpx.Request] = []
    client = _grid_client(requests, load_text_fixture("seat_grid_car_seats.html"))
    try:
        grid = client.get_seat_grid(
            _seat_train(), "3", passengers=PassengerCounts(adult=2)
        )
    finally:
        client.close()

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == SEAT_GRID_ROUTE
    assert not requests[0].url.query
    posted = dict(parse_qsl(requests[0].content.decode(), keep_blank_values=True))
    assert posted["trnNo"] == "00315"
    assert posted["scarNo"] == "3"
    assert posted["choiceSeatCount"] == "2"
    assert grid.car_number == "3"
    assert len(grid.seats) == 12


def test_get_seat_grid_seat_count_overrides_the_party(load_text_fixture):
    requests: list[httpx.Request] = []
    client = _grid_client(requests, load_text_fixture("seat_grid_car_seats.html"))
    try:
        client.get_seat_grid(
            _seat_train(), "3", "1", "4", passengers=PassengerCounts(adult=2)
        )
    finally:
        client.close()

    posted = dict(parse_qsl(requests[0].content.decode(), keep_blank_values=True))
    assert posted["choiceSeatCount"] == "4"


def test_get_seat_grid_rejects_an_incomplete_row_before_transport():
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("transport must not be entered for incomplete seat data")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="run_date"):
            client.get_seat_grid(
                TrainSummary(train_no="315", train_group_code="300"), "3"
            )
    finally:
        client.close()


def test_get_seat_grid_surfaces_the_refusal_envelope():
    requests: list[httpx.Request] = []
    client = _grid_client(requests, "0#좌석을 선택할 수 없습니다.")
    try:
        with pytest.raises(SrtSeatUnavailableError):
            client.get_seat_grid(_seat_train(), "3")
    finally:
        client.close()

    assert len(requests) == 1


# --- the safety boundary ------------------------------------------------------


def _grid_form() -> dict[str, str]:
    return dict(seat_grid_payload(_seat_train(), "3"))


def _grid_request(
    *,
    query: str = "",
    body: str | None = None,
    method: str = "POST",
) -> httpx.Request:
    config = SrtConfig()
    encoded = body if body is not None else urlencode(_grid_form())
    return httpx.Request(
        method,
        config.base_url + SEAT_GRID_PATH + query,
        content=encoded.encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_seat_grid_route_is_a_registered_read_and_never_a_mutation():
    assert ReadOnlyRoute("POST", "app", SEAT_GRID_PATH) in READ_ONLY_ROUTES
    assert ReadOnlyRoute("GET", "app", SEAT_GRID_PATH) not in READ_ONLY_ROUTES
    assert MutationRoute("POST", "app", SEAT_GRID_PATH) not in SRT_MUTATION_ROUTES
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("POST", SEAT_GRID_PATH)


def test_exact_seat_grid_form_is_allowed():
    assert_read_only_request(_grid_request(), SrtConfig())


def test_seat_grid_boundary_refuses_an_unpadded_train_number():
    # The builder pads, and the boundary re-checks it: a hand-assembled body
    # that skips the padding is the exact request that answers with an alert
    # shell, and it does not leave this process.
    with pytest.raises(SrtProtocolError, match="seat grid"):
        assert_read_only_request(
            _grid_request(body=urlencode({**_grid_form(), "trnNo": "315"})),
            SrtConfig(),
        )


@pytest.mark.parametrize(
    "body",
    [
        urlencode({**_grid_form(), "reqCode": "9"}),  # a seat-PAGE field
        urlencode({name: value for name, value in _grid_form().items() if name != "scarNo"}),
        urlencode({**_grid_form(), "scarNo": ""}),
        urlencode({**_grid_form(), "psrmClCd": "3"}),
        urlencode({**_grid_form(), "choiceSeatCount": "0"}),
        urlencode(_grid_form()) + "&scarNo=4",
    ],
)
def test_seat_grid_boundary_refuses_bodies_outside_the_contract(body):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_grid_request(body=body), SrtConfig())


@pytest.mark.parametrize("query", ["?", "?scarNo=4"])
def test_seat_grid_boundary_refuses_query_parameters(query):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_grid_request(query=query), SrtConfig())


def test_seat_grid_boundary_refuses_a_get():
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_grid_request(method="GET"), SrtConfig())
