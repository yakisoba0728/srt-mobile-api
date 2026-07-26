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

import inspect
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    PassengerCounts,
    SeatDesignation,
    SeatGrid,
    SeatGridSeat,
    SrtAppError,
    SrtClient,
    SrtConfig,
    SrtProtocolError,
    SrtReservationHold,
    SrtSeatUnavailableError,
    SrtSession,
    SrtSessionExpiredError,
    TrainSummary,
)
from srt_mobile_api.parsers import parse_seat_grid_response
from srt_mobile_api.payloads import (
    RESERVE_SEATMAP_JOBID,
    SEAT_TRAIN_NUMBER_LENGTH,
    personal_reservation_payload,
    seat_grid_payload,
    transfer_reservation_payload,
)
from srt_mobile_api.safety import (
    SEAT_GRID_PATH,
    SRT_LIVE_MUTATION_CATEGORIES,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
    MutationRoute,
    READ_ONLY_ROUTES,
    ReadOnlyRoute,
    assert_mutation_route,
    assert_read_only_request,
)

FIXTURES = Path(__file__).parent / "fixtures"
SEAT_GRID_ROUTE = "/arc/selectListArc02011_n.do"
RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
SYNTHETIC_NF = "SYNTHETIC_NETFUNNEL_KEY"


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


def _reservable_train(raw: dict | None = None) -> TrainSummary:
    """The same row, completed with everything a reservation form needs.

    Kept separate from :func:`_seat_train` so the grid tests keep exercising the
    minimum a seat read requires, which is less than a reservation requires.
    """
    return TrainSummary(
        train_no="315",
        train_group_code="300",
        service_class_code="17",
        run_date="20260812",
        departure_date="20260812",
        departure_time="060000",
        arrival_time="061900",
        departure_station_code="0551",
        arrival_station_code="0552",
        departure_station_name="수서",
        arrival_station_name="동탄",
        departure_run_order="000001",
        arrival_run_order="000002",
        departure_consist_order="000001",
        arrival_consist_order="000002",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
        raw=raw or {},
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


# --- seat-designated reservation (좌석지정, jobId 1103) -------------------------
#
# The REQUEST body below is bundle-evidenced field by field (ara0101v.js:866-882)
# and the seats in it come from a live-confirmed read. The submit TARGET is
# inferred -- fn_submit is defined in a server-rendered page -- and these tests
# pin the inference as an inference: they assert the route this library uses,
# not that the server accepts it.


def _designation(*labels: str, car_number: str = "3") -> SeatDesignation:
    grid = parse_seat_grid_response(
        (FIXTURES / "seat_grid_car_seats.html").read_text(encoding="utf-8"),
        car_number=car_number,
    )
    return grid.choose(*labels)


def _reserve_form(**kwargs) -> dict[str, str]:
    return personal_reservation_payload(
        _reservable_train(),
        kwargs.pop("passengers", PassengerCounts(adult=1)),
        netfunnel_key=SYNTHETIC_NF,
        **kwargs,
    )


def test_the_undesignated_reserve_form_is_byte_for_byte_and_order_for_order():
    # The compatibility claim, stated against the parameter that was just
    # added: naming designated_seats=None must produce the form that existed
    # before it did -- same values, same key ORDER (the arvDt1 position pins in
    # test_mutation_live_paths depend on order).
    implicit = _reserve_form()
    explicit = _reserve_form(designated_seats=None)

    assert implicit == explicit
    assert list(implicit) == list(explicit)
    assert implicit["jobId"] == "1101"
    assert not [
        key for key in implicit if key.startswith(("seatNo", "scarNo", "scarGridcnt"))
    ]


def test_designated_form_adds_only_the_seat_family_and_switches_the_job_id():
    before = _reserve_form()
    after = _reserve_form(designated_seats=_designation("1B"))

    added = {key: value for key, value in after.items() if key not in before}
    changed = {
        key: (before[key], after[key])
        for key in before.keys() & after.keys()
        if before[key] != after[key]
    }
    # ara0101v.js:872-879, in the app's own write order.
    assert added == {
        "seatNo1_1": "1B",
        "scarGridcnt1": "1",
        "scarGridcnt2": "0",
        "scarNo1": "3",
        "scarNo2": "",
    }
    # jobId and NOTHING else: ara1001l.js:1435-1436 sets 1103 on the seat
    # branch, and the seat callback touches no other reservation field.
    assert changed == {"jobId": ("1101", RESERVE_SEATMAP_JOBID)}
    assert not [key for key in before if key not in after]
    # reserveType is left where the live-verified personal path put it: srtgo
    # has no seat-map reservation, so there is no source saying it should move.
    assert after["reserveType"] == "11"


def test_seat_numbers_on_the_wire_are_the_printed_labels_not_the_internal_ones():
    # THE trap. ara0101v.js:870-874 builds seatNo1_* from scarSeatNm (the
    # printed labels) and never uses scarSeatNo (the internal numbers), so the
    # field spelled "seatNo" carries the NAME. In this car the printed 1B/2C are
    # internal 2/7 -- if the two were ever swapped, this is the test that says so.
    designation = _designation("1B", "2C")
    form = _reserve_form(
        passengers=PassengerCounts(adult=2), designated_seats=designation
    )

    assert [seat.internal_seat_number for seat in designation.seats] == ["2", "7"]
    assert form["seatNo1_1"] == "1B"
    assert form["seatNo1_2"] == "2C"
    assert "2" not in (form["seatNo1_1"], form["seatNo1_2"])


def test_seat_slots_are_numbered_from_one_in_the_chosen_order():
    form = _reserve_form(
        passengers=PassengerCounts(adult=3),
        designated_seats=_designation("2D", "1C", "3A"),
    )

    assert [form[f"seatNo1_{index}"] for index in (1, 2, 3)] == ["2D", "1C", "3A"]
    assert form["scarGridcnt1"] == "3"
    assert "seatNo1_4" not in form


def test_journey_slot_two_is_blanked_rather_than_omitted():
    # ara0101v.js:877-879 writes scarGridcnt2=0 and scarNo2="" explicitly on the
    # 편도 path. 여정 slot 2 belongs to a 환승 second leg; a designated one-way
    # journey has none, and the app clears the slot rather than leaving it.
    form = _reserve_form(designated_seats=_designation("1B"))

    assert form["scarGridcnt2"] == "0"
    assert form["scarNo2"] == ""
    # And the journey count still says one journey: slot 2 being present and
    # empty is not a transfer.
    assert form["jrnyCnt"] == "1"
    assert form["jrnyTpCd"] == "11"


@pytest.mark.parametrize(
    ("party", "labels"),
    [(1, ("1B", "2C")), (2, ("1B",)), (3, ("1B", "2C"))],
)
def test_designated_seat_count_must_equal_the_passenger_count(party, labels):
    with pytest.raises(ValueError, match="match the passenger count"):
        _reserve_form(
            passengers=PassengerCounts(adult=party),
            designated_seats=_designation(*labels),
        )


def test_a_seat_the_grid_marked_unselectable_cannot_reach_the_form():
    # Two layers, on purpose. SeatDesignation refuses to hold an 'N' seat at
    # all, so the form builder cannot be handed one through the normal path;
    # constructing one directly is refused for the same reason.
    grid = parse_seat_grid_response(
        (FIXTURES / "seat_grid_car_seats.html").read_text(encoding="utf-8"),
        car_number="3",
    )
    unselectable = next(seat for seat in grid.seats if not seat.selectable)

    with pytest.raises(ValueError, match="not selectable"):
        SeatDesignation(car_number="3", seats=(unselectable,))
    with pytest.raises(ValueError, match="not selectable"):
        grid.choose(unselectable.printed_seat_label)


def test_designated_seats_must_be_a_seat_designation():
    with pytest.raises(ValueError, match="SeatDesignation"):
        _reserve_form(designated_seats=("1B",))


def test_seat_designation_does_not_compose_with_standby_or_round_trip():
    # jobId cannot be both 1102 and 1103, and the app reaches them from two
    # different branches (ara1001l.js:1435-1449).
    with pytest.raises(ValueError, match="cannot be both"):
        personal_reservation_payload(
            _reservable_train(raw={"gnrmRsvPsbImg": "IMAGE::grd_WF_Waiting.png"}),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            standby=True,
            designated_seats=_designation("1B"),
        )
    # 좌석지정 왕복 exists in the app but its callback writes no seat fields
    # (ara0101v.js:884-892), so the 왕복 designated body is unevidenced.
    with pytest.raises(ValueError, match="편도 only"):
        _reserve_form(round_trip=True, designated_seats=_designation("1B"))


def test_the_transfer_builder_takes_no_designated_seats():
    # 좌석지정 blanks a transfer's slot 2 (ara0101v.js:875-879), so the builder
    # does not offer the parameter -- rather than accepting one and discarding
    # it. The 단체 builder was the other half of this test until 2026-07-26,
    # when group booking was removed; 단체 disabled the seat picker outright
    # (ara0101v.js:446-457), and now there is no 단체 body to designate seats on.
    assert (
        "designated_seats"
        not in inspect.signature(transfer_reservation_payload).parameters
    )


# --- the client path ----------------------------------------------------------


def _reserving_client() -> tuple[SrtClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/ts.wseq":
            if request.url.params["opcode"] == "5004":
                return httpx.Response(
                    200, text="NetFunnel.gControl.result='5004:200:utime=1';"
                )
            return httpx.Response(
                200,
                text=(
                    "NetFunnel.gRtype=5101;NetFunnel.gControl.result="
                    "'5101:200:key=SYNTHETIC_ACQUIRED_KEY&nwait=0&nnext=0';"
                ),
            )
        if request.url.path == RESERVE_ROUTE:
            return httpx.Response(
                200,
                json={
                    "resultMap": [
                        {
                            "strResult": "SUCC",
                            "msgCd": "IRR000018",
                            "msgTxt": "정상처리되었습니다",
                        }
                    ],
                    "reservListMap": [{"pnrNo": "SYNTHETIC-PNR"}],
                    "trainListMap": [],
                    "commandMap": [],
                },
            )
        raise AssertionError(f"unexpected request to {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, requests


def test_reserve_preview_carries_the_seat_fields_and_sends_nothing():
    client, requests = _reserving_client()
    try:
        preview = client.reserve(
            _reservable_train(),
            consent=MutationConsent(allow_reserve=True),
            passengers=PassengerCounts(adult=2),
            designated_seats=_designation("1B", "2C"),
        )
    finally:
        client.close()

    assert isinstance(preview, MutationPreview)
    assert requests == []
    assert preview.category == "reserve"
    assert preview.route == RESERVE_ROUTE
    assert preview.payload["jobId"] == RESERVE_SEATMAP_JOBID
    assert preview.payload["seatNo1_1"] == "1B"
    assert preview.payload["seatNo1_2"] == "2C"
    assert preview.payload["scarNo1"] == "3"


def test_reserve_transmits_the_designated_body_on_the_existing_reserve_route():
    # The route is the INFERENCE this feature rests on: fn_submit's definition
    # is server-rendered, and this library sends the designated body to the same
    # personal reservation endpoint under the same consent category. The test
    # pins what we send, not that the server accepts it.
    client, requests = _reserving_client()
    try:
        hold = client.reserve(
            _reservable_train(),
            consent=MutationConsent(dry_run=False, allow_reserve=True),
            passengers=PassengerCounts(adult=1),
            designated_seats=_designation("3C"),
        )
    finally:
        client.close()

    assert isinstance(hold, SrtReservationHold)
    assert [request.url.path for request in requests] == [
        "/ts.wseq",
        RESERVE_ROUTE,
        "/ts.wseq",
    ]
    form = dict(httpx.QueryParams(requests[1].content.decode()))
    assert form["jobId"] == RESERVE_SEATMAP_JOBID
    assert form["seatNo1_1"] == "3C"
    assert form["scarGridcnt1"] == "1"
    assert form["scarNo1"] == "3"


def test_seat_designation_adds_no_route_and_no_consent_category():
    # It rides the existing reserve category on the existing reserve route. The
    # canary in test_mutation_live_paths pins the category set globally; this
    # pins that THIS feature did not touch it.
    assert SRT_LIVE_MUTATION_CATEGORIES == {"reserve", "cancel", "payment", "refund"}
    assert SRT_MUTATION_ROUTE_CATEGORIES[RESERVE_ROUTE] == "reserve"
    assert MutationRoute("POST", "app", RESERVE_ROUTE) in SRT_MUTATION_ROUTES
    # Four since 2026-07-26: the 단체 endpoint arc06014 was unregistered when
    # group booking was removed.
    assert len(SRT_MUTATION_ROUTES) == 4
