"""Regressions built from REDACTED real responses captured off the live server.

Every fixture referenced here was recorded by
``scripts/capture_live_read_surface.py`` on 2026-07-26 against the real SRT
server and then redacted. These are the shapes the offline v2.0.41 bundle
cannot demonstrate: what the server actually renders, as opposed to what the
bundled JavaScript suggests it would.

Each test names the live observation it pins.
"""

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtAppError, SrtSessionExpiredError
from srt_mobile_api.parsers import (
    parse_train_search_response,
    is_login_form,
    is_login_redirect_page,
    is_unauthenticated_page,
    parse_fare_page,
    parse_html_page,
    parse_seat_selection_page,
    parse_timetable_page,
)


# --------------------------------------------------------------------------
# Expired session: the server answers an authenticated read with the ordinary
# page shell plus a "sign in again" alert -- HTTP 200, and no login form on it.
# --------------------------------------------------------------------------


def test_expired_session_page_carries_no_login_form(load_text_fixture):
    """The captured expiry response has none of the login-FORM markers.

    This is the whole reason the old guard missed it, so it is pinned first: if
    a future fixture edit smuggles a login form in, the tests below would start
    passing for the wrong reason.
    """
    html = load_text_fixture("ticket_list_expired_session.html")
    assert "hmpgPwdCphd" not in html
    assert "selectListApb01080_n.do" not in html
    assert is_login_form(html) is False


def test_expired_session_page_is_detected_as_unauthenticated(load_text_fixture):
    html = load_text_fixture("ticket_list_expired_session.html")
    assert is_login_redirect_page(html) is True
    assert is_unauthenticated_page(html) is True


def test_expired_session_page_raises_for_an_authenticated_read(load_text_fixture):
    html = load_text_fixture("ticket_list_expired_session.html")
    with pytest.raises(SrtSessionExpiredError):
        parse_html_page(html, context="ticket list", require_authenticated=True)


def test_ticket_list_classifies_the_live_expiry_shape_as_expired(load_text_fixture):
    """End to end: the client must raise, not return an empty ticket list."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=load_text_fixture("ticket_list_expired_session.html"),
            headers={"content-type": "text/html; charset=UTF-8"},
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtSessionExpiredError):
        client.get_ticket_list()
    assert client.session.current is None


def test_authenticated_ticket_list_is_not_mistaken_for_an_expiry(load_text_fixture):
    """The authenticated page defines mvLoginPage() too; only the ALERT differs.

    The real authenticated ticket list contains ``mvLoginPage`` twice (the
    function definition) and eight ``/login/login.do`` form actions, so keying
    detection on either would reject every signed-in read.
    """
    html = (
        "<html><body>"
        '<form action="/login/login.do"><input name="login_referer4"></form>'
        "<script>function mvLoginPage() "
        '{ location.href = "/login/login.do?page=menu"; }</script>'
        "<ul id='ticketList'><li>승차권</li></ul>"
        "</body></html>"
    )
    assert is_unauthenticated_page(html) is False
    page = parse_html_page(html, context="ticket list", require_authenticated=True)
    assert "승차권" in page.text


def test_login_redirect_marker_must_sit_inside_a_script(load_text_fixture):
    """Visible copy that merely mentions the key is not an expiry signal."""
    visible = "<html><body><p>Sr.msgs.login020 srtAlertBoxDivShow</p></body></html>"
    assert is_login_redirect_page(visible) is False
    page = parse_html_page(visible, context="ticket list", require_authenticated=True)
    assert "login020" in page.text


# --------------------------------------------------------------------------
# Fare page: the real page always renders a SECOND, placeholder leg whose rows
# repeat the first leg's labels at 0원.
# --------------------------------------------------------------------------


def test_fare_page_ignores_the_unrequested_transfer_leg(load_text_fixture):
    page = parse_fare_page(load_text_fixture("fare_transfer_placeholder.html"))

    assert len(page.semantic_items) == 6
    assert page.items == page.semantic_items
    assert [(item.label, item.amount) for item in page.items] == [
        ("Synthetic Adult Synthetic First", 75700),
        ("Synthetic Adult Synthetic Standard", 51900),
        ("Synthetic Child Synthetic First", 49700),
        ("Synthetic Child Synthetic Standard", 25900),
        ("Synthetic Senior Synthetic First", 60100),
        ("Synthetic Senior Synthetic Standard", 36300),
    ]


def test_fare_page_emits_no_zero_priced_duplicate_labels(load_text_fixture):
    """The defect stated as its consequence, not as a row count.

    Before the fix this page produced nine "available" items, three of them
    ``0원`` under labels identical to real ones, so
    ``{item.label: item.amount}`` answered 0 for a real fare.
    """
    page = parse_fare_page(load_text_fixture("fare_transfer_placeholder.html"))

    labels = [item.label for item in page.semantic_items]
    assert len(labels) == len(set(labels))
    assert all(item.amount for item in page.items)
    by_label = {item.label: item.amount for item in page.items}
    assert by_label["Synthetic Adult Synthetic Standard"] == 51900


def test_fare_page_hide_calls_are_not_used_as_the_signal(load_text_fixture):
    """The page hides BOTH blocks somewhere in its script; only one is real.

    ``$("#trainPayInfo22").hide();`` is a top-level statement, but
    ``$("#trainPayInfo1").hide();`` also appears, inside
    ``selectTransferTrain()``. A parser that collected hide() targets textually
    would drop the real fares and keep nothing.
    """
    html = load_text_fixture("fare_transfer_placeholder.html")
    assert '$("#trainPayInfo22").hide();' in html
    assert '$("#trainPayInfo1").hide();' in html
    assert parse_fare_page(html).items


# --------------------------------------------------------------------------
# Timetable: the station name is never in the markup. The WebView resolves it
# from a code carried in a <script> inside the row.
# --------------------------------------------------------------------------


def test_timetable_markup_carries_no_station_names(load_text_fixture):
    """Pinned first: the names genuinely are not there to be scraped."""
    html = load_text_fixture("timetable_live_shape.html")
    for name in ("수서", "오송", "부산"):
        assert name not in html
    assert 'getStationNameByCode(\'0551\')' in html
    assert '<td id="stationNm_1">' in html


def test_timetable_resolves_each_stop_from_its_own_script(load_text_fixture):
    page = parse_timetable_page(load_text_fixture("timetable_live_shape.html"))

    assert [(row.station_code, row.station_name) for row in page.rows] == [
        ("0551", "수서"),
        ("0297", "오송"),
        ("0020", "부산"),
    ]
    assert [row.times for row in page.rows] == [
        ("10:00",),
        ("10:40", "10:41"),
        ("12:29",),
    ]


def test_timetable_never_reports_the_placeholder_dash_as_a_station(
    load_text_fixture,
):
    """The old heuristic returned '-' for the origin and the terminus.

    Those rows carry a literal "-" where the missing arrival (origin) or
    departure (terminus) time would go, and "first non-time cell" picked it up.
    """
    page = parse_timetable_page(load_text_fixture("timetable_live_shape.html"))
    assert all(row.station_name not in {"", "-"} for row in page.rows)


def test_timetable_falls_back_when_a_row_has_no_station_script():
    """A row without the script keeps the old cell reading, minus the dash."""
    html = (
        "<table><tr><td>Synthetic Stop</td><td>-</td><td>07:15</td></tr>"
        "<tr><td>-</td><td>08:20</td><td>08:22</td></tr></table>"
    )
    page = parse_timetable_page(html)
    assert [(row.station_code, row.station_name) for row in page.rows] == [
        ("", "Synthetic Stop"),
        ("", ""),
    ]


def test_timetable_row_codes_stay_aligned_when_one_row_lacks_a_script():
    """Row affinity, not positional zipping.

    A document-order list of codes matched positionally against rows would
    shift every stop after a row the server rendered without a script.
    """
    html = (
        "<table>"
        "<tr><td id='stationNm_1'><td></td>"
        "<script>$(\"#stationNm_1\").html( getStationNameByCode('0551') );</script>"
        "<td>-</td><td>10:00</td></tr>"
        "<tr><td>Synthetic Unnamed</td><td>10:20</td><td>10:22</td></tr>"
        "<tr><td id='stationNm_3'><td></td>"
        "<script>$(\"#stationNm_3\").html( getStationNameByCode('0020') );</script>"
        "<td>12:29</td><td>-</td></tr>"
        "</table>"
    )
    page = parse_timetable_page(html)
    assert [(row.station_code, row.station_name) for row in page.rows] == [
        ("0551", "수서"),
        ("", "Synthetic Unnamed"),
        ("0020", "부산"),
    ]


# --------------------------------------------------------------------------
# Seat page: a sold-out train is answered with an error shell that carries the
# same heading as a working seat page.
# --------------------------------------------------------------------------


def test_seat_page_exposes_the_car_list_it_carries(load_text_fixture):
    page = parse_seat_selection_page(load_text_fixture("seat_page_car_options.html"))

    assert [(car.car_number, car.available_seat_count) for car in page.cars] == [
        ("3", 11),
        ("7", 2),
    ]
    assert page.cars[1].label == "7호차 (2석)"


def test_seat_page_does_not_invent_a_seat_grid(load_text_fixture):
    """The grid is not in this response; only the car list is.

    The real page leaves ``<div id="trnScarSeatInfo">`` empty and loads the grid
    separately. Pinning that keeps a future change from claiming otherwise.
    """
    html = load_text_fixture("seat_page_car_options.html")
    assert '<div id="trnScarSeatInfo"' in html
    assert "seatNo" not in html


def test_sold_out_seat_page_is_refused_rather_than_returned(load_text_fixture):
    with pytest.raises(SrtAppError) as excinfo:
        parse_seat_selection_page(
            load_text_fixture("seat_page_sold_out_error.html")
        )
    assert excinfo.value.code == "error001"


def test_sold_out_seat_page_carries_the_same_heading_as_a_working_one(
    load_text_fixture,
):
    """Why the old marker check passed it: 좌석선택 is the page TITLE."""
    error_html = load_text_fixture("seat_page_sold_out_error.html")
    working_html = load_text_fixture("seat_page_car_options.html")
    assert "좌석선택" in error_html
    assert "좌석선택" in working_html
    assert "selectScarNo" not in error_html


def test_seat_page_alerts_inside_function_bodies_are_not_a_refusal(
    load_text_fixture,
):
    """A working page mentions srtAlertBoxDivShow too, inside its handlers."""
    html = load_text_fixture("seat_page_car_options.html")
    assert "srtAlertBoxDivShow" in html
    assert "Sr.msgs.rsv046" in html
    assert parse_seat_selection_page(html).cars


def test_seat_page_end_to_end_refuses_the_sold_out_shape(load_text_fixture):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=load_text_fixture("seat_page_sold_out_error.html"),
            headers={"content-type": "text/html; charset=utf-8"},
        )

    from srt_mobile_api.models import TrainSummary

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    train = TrainSummary(
        train_no="999",
        train_group_code="300",
        service_class_code="17",
        run_date="20990102",
        departure_date="20990102",
        departure_time="100000",
        departure_station_code="0551",
        arrival_station_code="0502",
        departure_run_order="000001",
        arrival_run_order="000002",
    )
    with pytest.raises(SrtAppError):
        client.get_seat_page(train)


# --------------------------------------------------------------------------
# Search rows: the server sends JSON null as an ordinary "no value".
# --------------------------------------------------------------------------


def _live_shape_search_response(row_overrides: dict | None = None) -> dict:
    """The envelope the live personal search actually returns, trimmed.

    Reproduces the 2026-07-26 shape: the ErrorCode/ErrorMsg wrapper, dsOutput0
    carrying ``fllwPgExt2: null`` alongside the real metadata, and a dsOutput1
    row carrying ``fresRsvPsbCdNm: null``. Identifiers and figures are synthetic.
    """
    row = {
        "trnNo": "999",
        "trnGpCd": "300",
        "stlbTrnClsfCd": "17",
        "runDt": "20990102",
        "dptDt": "20990102",
        "dptTm": "100000",
        "arvDt": "20990102",
        "arvTm": "122900",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000007",
        "dptStnConsOrdr": "000001",
        "arvStnConsOrdr": "000024",
        "seatAttCd": "015",
        "runTm": "0229",
        "trnOrdrNo": 0,
        "ocurDlayTnum": 0,
        "expnDptDlayTnum": "00000",
        "gnrmRsvPsbStr": "예약가능",
        "sprmRsvPsbStr": "매진",
        "gnrmRsvPsbCdNm": "좌석있음",
        "sprmRsvPsbCdNm": "좌석매진",
        "rsvWaitPsbCd": " 0",
        "rsvWaitPsbCdNm": "신청하기",
        "stmpRsvPsbFlgCd": "YY",
        "stndRsvPsbCdNm": "예약하기",
        "rcvdAmt": "00000000052900",
        "rcvdFare": "00000000023800",
        "trainDiscGenRt": "0000.00",
        "trnCpsCd1": "X",
        # Present in EVERY live row, always null.
        "fresRsvPsbCdNm": None,
    }
    row.update(row_overrides or {})
    return {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": "IRG000000",
                    "seandYo": "N",
                    "qryCnqeCnt": 1,
                    "strResult": "SUCC",
                    "msgTxt": "정상처리되었습니다",
                    "fllwPgExt2": None,
                    "fllwPgExt": "Y",
                }
            ],
            "dsOutput1": [row],
        },
    }


def test_search_parses_the_live_row_shape_including_its_nulls():
    result = parse_train_search_response(_live_shape_search_response())

    assert len(result.trains) == 1
    assert result.metadata.has_following_page is True
    assert result.metadata.query_count == 1


@pytest.mark.parametrize(
    "field",
    [
        "runTm",
        "expnDptDlayTnum",
        "rsvWaitPsbCd",
        "stmpRsvPsbFlgCd",
        "gnrmRsvPsbStr",
        "trnCpsCd1",
    ],
)
def test_a_null_optional_row_field_costs_one_attribute_not_the_search(field):
    """The consequence, not the type check: a null must not empty the page.

    The optional readers used to raise SrtProtocolError for any present
    non-string, and that exception is not scoped to the field -- it aborts the
    whole search. The live server sends nulls in these very rows, so this is the
    difference between one train losing one attribute and a route returning no
    trains at all.
    """
    result = parse_train_search_response(
        _live_shape_search_response({field: None})
    )

    assert len(result.trains) == 1
    assert result.trains[0].train_no == "999"


def test_a_null_message_is_read_as_the_empty_default():
    payload = _live_shape_search_response()
    payload["outDataSets"]["dsOutput0"][0]["msgTxt"] = None

    assert parse_train_search_response(payload).metadata.message == ""


@pytest.mark.parametrize("wrong_value", [42, 4.0, [], {}])
def test_a_non_null_wrong_type_still_rejects(wrong_value):
    """Relaxing null must not relax everything else."""
    with pytest.raises(Exception) as excinfo:
        parse_train_search_response(
            _live_shape_search_response({"gnrmRsvPsbStr": wrong_value})
        )
    assert "gnrmRsvPsbStr" in str(excinfo.value)


def test_search_row_exposes_the_availability_names_not_only_the_codes():
    """The four *CdNm columns every live row carries, previously dropped.

    ``reservation_wait_availability`` and ``standing_availability`` hold CODES
    (" 0" and "YY" as sent), which is not what their names suggest and not what
    a caller can act on. The readable state lived in the sibling columns.
    """
    train = parse_train_search_response(_live_shape_search_response()).trains[0]

    assert train.general_seat_availability == "예약가능"
    assert train.general_seat_availability_name == "좌석있음"
    assert train.special_seat_availability_name == "좌석매진"
    assert train.reservation_wait_availability == " 0"
    assert train.reservation_wait_availability_name == "신청하기"
    assert train.standing_availability == "YY"
    assert train.standing_availability_name == "예약하기"


def test_group_search_rows_omit_the_wait_and_standing_names():
    """Ara10082 sends a narrower row; the new fields must stay optional.

    Live capture 2026-07-26: the ten group rows carried neither rsvWaitPsbCdNm
    nor stndRsvPsbCdNm (nor rsvWaitPsbCd, stmpRsvPsbFlgCd, expnDptDlayTnum,
    dlaySaleFlg, etcRsvPsbCdNm, fresOprCno, fresRsvPsbCdNm or trnNstpLeadInfo),
    while adding chtnTrnOrdrNo and stlbCarTpCd that the personal row lacks.
    """
    payload = _live_shape_search_response()
    row = payload["outDataSets"]["dsOutput1"][0]
    for absent in (
        "rsvWaitPsbCd",
        "rsvWaitPsbCdNm",
        "stmpRsvPsbFlgCd",
        "stndRsvPsbCdNm",
        "expnDptDlayTnum",
        "fresRsvPsbCdNm",
    ):
        row.pop(absent)
    row["chtnTrnOrdrNo"] = "1"
    row["stlbCarTpCd"] = "1"

    train = parse_train_search_response(payload).trains[0]

    assert train.reservation_wait_availability is None
    assert train.reservation_wait_availability_name is None
    assert train.standing_availability is None
    assert train.standing_availability_name is None
    assert train.general_seat_availability_name == "좌석있음"


# --------------------------------------------------------------------------
# Timetable/fare forms: the LIVE search page's own JavaScript refutes the
# bundle-derived field names we were sending.
# --------------------------------------------------------------------------


def test_trn_sort_is_the_display_name_of_the_service_class():
    """getStlbTrnClsfCdNm(stlbTrnClsfCd), per the live page's two call sites."""
    from srt_mobile_api.payloads import fare_payload, stlb_train_class_name, timetable_payload
    from srt_mobile_api.models import PassengerCounts, TrainSummary

    assert stlb_train_class_name("17") == "SRT"
    assert stlb_train_class_name("00") == "KTX"
    assert stlb_train_class_name("99") == ""

    train = TrainSummary(
        train_no="999",
        service_class_code="17",
        run_date="20990102",
        departure_date="20990102",
        departure_station_code="0551",
        arrival_station_code="0020",
    )
    assert timetable_payload(train)["trnSort"] == "SRT"
    assert fare_payload(train, PassengerCounts(adult=1))["trnSort"] == "SRT"


def test_trn_sort_does_not_depend_on_a_field_no_live_row_sends():
    """trnClsfCd is 0-hit across all 40 live dsOutput1 rows.

    Deriving trnSort from it meant every timetable and fare request we ever made
    carried trnSort= empty.
    """
    from srt_mobile_api.payloads import timetable_payload
    from srt_mobile_api.models import TrainSummary

    train = TrainSummary(
        train_no="999",
        service_class_code="17",
        train_class_code=None,
        departure_date="20990102",
        departure_station_code="0551",
        arrival_station_code="0020",
    )
    assert timetable_payload(train)["trnSort"] == "SRT"


def test_fare_form_uses_the_live_passenger_field_names():
    """passenger1..5 was ours; the live page sends psgTpCd*/psgInfoPerPrnb*.

    Live-verified 2026-07-26: with the old names the server computed the page's
    estimated total as 0원 under a "기준" line naming no party at all. With
    these names the identical journey returned "어른 1명 기준" and real totals.
    """
    from srt_mobile_api.payloads import fare_payload
    from srt_mobile_api.models import PassengerCounts, TrainSummary

    train = TrainSummary(
        train_no="999",
        service_class_code="17",
        departure_date="20990102",
        departure_station_code="0551",
        arrival_station_code="0502",
    )
    form = fare_payload(train, PassengerCounts(adult=1))

    assert not any(key.startswith("passenger") for key in form)
    assert form["psgTpCd1"] == "1"
    assert form["psgInfoPerPrnb1"] == "1"
    assert form["psgTpCd6"] == ""
    assert form["psgInfoPerPrnb6"] == ""


def test_timetable_and_fare_date_is_the_departure_date():
    """The live form sends dptDt / qryDtFrom, not the operating date runDt.

    They coincide for a same-day service, which is why this went unnoticed; they
    do not for a past-midnight departure. The RESERVE form is unaffected and
    still sends the operating date, which is what its own call site does.
    """
    from srt_mobile_api.payloads import fare_payload, timetable_payload
    from srt_mobile_api.models import PassengerCounts, TrainSummary

    overnight = TrainSummary(
        train_no="999",
        service_class_code="17",
        run_date="20990101",
        departure_date="20990102",
        departure_station_code="0551",
        arrival_station_code="0020",
    )
    assert timetable_payload(overnight)["runDt"] == "20990102"
    form = fare_payload(overnight, PassengerCounts(adult=1))
    assert form["runDt"] == "20990102"
    assert form["runDt1"] == "20990102"
