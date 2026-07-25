from unittest.mock import Mock

import pytest

from srt_mobile_api import SrtClient
from srt_mobile_api.live import (
    _embedded_seat_inventory_candidate_present,
    _first_complete_srt_seat_train,
    live_enabled,
    first_reservable_srt_train,
    read_credentials_from_env,
    read_query_from_env,
    run_live_smoke,
    run_live_smoke_from_env,
    train_is_reservable,
)
from srt_mobile_api.models import (
    FareItem,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    Notice,
    NoticeListResult,
    SeatSelectionPage,
    SrtSession,
    TimetablePage,
    TimetableRow,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SRT_MOBILE_API_LIVE", raising=False)
    assert live_enabled() is False


def test_live_enabled_only_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    assert live_enabled() is True


def test_credentials_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("SRT_LOGIN_ID", "member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", "pw")
    assert read_credentials_from_env() == ("member", "pw")


def test_live_result_contains_counts_not_ticket_text():
    train = TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    client = Mock(spec=SrtClient)
    client.login.return_value = SrtSession(login_id="login-id", user_map={"RTNCD": "Y"})
    client.get_main.return_value = HtmlPage(text="main", raw="<html>main</html>")
    client.get_booking_page.return_value = HtmlPage(text="booking", raw="<html>booking</html>")
    selector_page = HtmlPage(text="selector", raw="<html>selector</html>")
    client.get_station_selector.return_value = selector_page
    client.get_station_map_selector.return_value = HtmlPage(
        text="",
        raw='<html><body><input name="startStnCd"></body></html>',
    )
    client.get_date_selector.return_value = selector_page
    client.get_passenger_selector.return_value = selector_page
    client.get_seat_option_selector.return_value = selector_page
    client.get_train_group_selector.return_value = selector_page
    client.get_typed_notice_list.return_value = NoticeListResult(
        notices=(
            Notice(
                is_main="N",
                page_id="SYNTHETIC_PAGE",
                body="synthetic body",
                post_no=42,
                create_date="20990102",
                is_notice="Y",
                subject="Synthetic subject",
            ),
        )
    )
    client.get_ticket_list.return_value = HtmlPage(text="ticket", raw="<html>ticket</html>")
    client.search_trains.return_value = TrainSearchResult(trains=[train], result={}, raw={})
    client.get_seat_page.return_value = SeatSelectionPage(
        text="좌석선택",
        raw=(
            "<html><body><h1>좌석선택</h1>"
            "<script>const map='https://www.korail.com/ticket/search/list?srtJob=seatmap';"
            "</script></body></html>"
        ),
    )
    client.get_mutual_verification.return_value = MutualVerificationResult(
        message_code="IRZ000008",
        status="SUCC",
        verification_code="mutual-secret",
        raw={"mutMrkVrfCd": "mutual-secret"},
    )
    client.search_group_trains.return_value = TrainSearchResult(trains=[train], result={}, raw={})
    client.get_timetable.return_value = TimetablePage(
        text="06:00",
        raw="<html>06:00</html>",
        rows=(TimetableRow(station_name="수서", times=("06:00",), raw_text="수서 06:00"),),
    )
    client.get_fare.return_value = FarePage(
        text="51,900원",
        raw="<html>51,900원</html>",
        items=(FareItem(label="어른 일반실", amount=51900, raw_amount="51,900원"),),
    )
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    result = run_live_smoke(
        client,
        login_id="login-id",
        password="password",
        query=query,
    )
    assert set(result) == {
        "loggedIn",
        "mainLoaded",
        "bookingLoaded",
        "noticeCount",
        "ticketPageLoaded",
        "personalTrainCount",
        "seatPageLoaded",
        "seatSelectionMarkerPresent",
        "externalSeatMapHandoffPresent",
        "embeddedSeatInventoryCandidatePresent",
        "mutualVerificationLoaded",
        "groupTrainCount",
        "timetableRowCount",
        "fareItemCount",
        "selectorLoadedCount",
    }
    assert result["selectorLoadedCount"] == 5
    assert result["noticeCount"] == 1
    assert result["mutualVerificationLoaded"] is True
    assert result["seatPageLoaded"] is True
    assert result["seatSelectionMarkerPresent"] is True
    assert result["externalSeatMapHandoffPresent"] is True
    assert result["embeddedSeatInventoryCandidatePresent"] is False
    assert "text" not in repr(result).lower()
    assert "raw" not in result
    for method_name in (
        "login",
        "get_main",
        "get_booking_page",
        "get_station_selector",
        "get_station_map_selector",
        "get_date_selector",
        "get_passenger_selector",
        "get_seat_option_selector",
        "get_train_group_selector",
        "get_typed_notice_list",
        "get_ticket_list",
        "search_trains",
        "get_seat_page",
        "get_mutual_verification",
        "search_group_trains",
        "get_timetable",
        "get_fare",
    ):
        assert getattr(client, method_name).called
    client.get_station_selector.assert_called_once_with("수서", "부산", "0551", "0020")
    client.get_date_selector.assert_called_once_with("20260710")
    client.get_passenger_selector.assert_called_once_with(query.passengers)
    client.get_seat_option_selector.assert_called_once_with(request_seat_attr_code="015")
    # The query above takes TrainSearchQuery's default train_group_code, which is
    # the app's booking-screen default "109"/전체 (ara0101v.js:85-86, :98-99).
    client.get_train_group_selector.assert_called_once_with("109", "전체")
    method_order = [call[0] for call in client.method_calls]
    assert method_order.index("get_booking_page") < method_order.index("get_station_selector")
    assert method_order.index("get_train_group_selector") < method_order.index("search_trains")
    assert method_order.index("search_trains") < method_order.index(
        "get_seat_page"
    )
    assert method_order.index("get_seat_page") < method_order.index(
        "get_mutual_verification"
    )
    assert method_order.index("get_mutual_verification") < method_order.index(
        "search_group_trains"
    )
    assert "mutual-secret" not in repr(result)
    assert "mutMrkVrfCd" not in repr(result)
    # The seat page must be read for the SAME party the smoke searched with: the
    # app sends choiceSeatCount = lfn_getRsv("totPrnb") (ara1001l.js:1511). The
    # smoke previously passed query.passengers to search_trains and then took
    # get_seat_page's hardcoded one-seat default.
    client.get_seat_page.assert_called_once_with(train, passengers=query.passengers)
    assert "korail.com" not in repr(result)


def test_first_complete_srt_seat_train_does_not_fallback_or_read_raw():
    complete = TrainSummary(
        train_no="303",
        train_group_code="300",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
        raw={"must_not_be_read": object()},
    )
    trains = [
        TrainSummary("101", train_group_code="900"),
        TrainSummary("301", train_group_code="300"),
        complete,
        TrainSummary("305", train_group_code="300"),
    ]

    assert _first_complete_srt_seat_train(trains) is complete


def test_embedded_inventory_probe_uses_structure_without_returning_it():
    page = SeatSelectionPage(
        text="좌석선택",
        raw=(
            '<div class="seat available"></div>'
            '<button data-seat-no="SYNTHETIC"></button>'
        ),
    )

    assert _embedded_seat_inventory_candidate_present(page) is True


def test_live_from_env_requires_explicit_test_date(monkeypatch):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.setenv("SRT_LOGIN_ID", "member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", "pw")
    monkeypatch.delenv("SRT_TEST_DATE", raising=False)
    with pytest.raises(RuntimeError, match="SRT_TEST_DATE"):
        run_live_smoke_from_env()


# --- env helpers shared with the round-trip script --------------------------


def _reservable_train(**overrides) -> TrainSummary:
    base = dict(
        train_no="303",
        service_class_code="17",
        train_group_code="300",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="060000",
        arrival_time="083000",
        departure_station_name="수서",
        arrival_station_name="부산",
        departure_run_order="1",
        arrival_run_order="10",
        departure_consist_order="1",
        arrival_consist_order="2",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )
    base.update(overrides)
    return TrainSummary(**base)


def test_query_from_env_reads_the_documented_variables(monkeypatch):
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")
    monkeypatch.setenv("SRT_DEPARTURE_STATION_CODE", "0015")
    monkeypatch.setenv("SRT_ARRIVAL_STATION_CODE", "0030")
    monkeypatch.setenv("SRT_DEPARTURE_TIME", "093000")
    monkeypatch.setenv("SRT_DEPARTURE_STATION_NAME", "동탄")
    monkeypatch.setenv("SRT_ARRIVAL_STATION_NAME", "동대구")
    monkeypatch.setenv("SRT_ADULT_COUNT", "2")
    monkeypatch.setenv("SRT_SENIOR_COUNT", "1")

    query = read_query_from_env()

    assert query.departure_station_code == "0015"
    assert query.arrival_station_code == "0030"
    assert query.departure_date == "20990101"
    assert query.departure_time == "093000"
    assert query.departure_station_name == "동탄"
    assert query.arrival_station_name == "동대구"
    assert query.passengers.adult == 2
    assert query.passengers.senior == 1


def test_query_from_env_requires_the_test_date(monkeypatch):
    monkeypatch.delenv("SRT_TEST_DATE", raising=False)
    with pytest.raises(RuntimeError, match="SRT_TEST_DATE"):
        read_query_from_env()


def test_train_is_reservable_reads_either_class(monkeypatch):
    assert train_is_reservable(_reservable_train()) is True
    assert (
        train_is_reservable(
            _reservable_train(
                general_seat_availability="매진",
                special_seat_availability="예약가능",
            )
        )
        is True
    )
    assert (
        train_is_reservable(
            _reservable_train(
                general_seat_availability="매진",
                special_seat_availability="매진",
            )
        )
        is False
    )


def test_first_reservable_train_skips_sold_out_rows():
    sold_out = _reservable_train(
        train_no="301",
        general_seat_availability="매진",
        special_seat_availability="매진",
    )
    available = _reservable_train(train_no="305")

    assert first_reservable_srt_train([sold_out, available]) is available


def test_first_reservable_train_skips_a_row_the_reserve_form_rejects():
    # Availability alone is not enough: a row missing a field the reserve form
    # requires would raise at build time, so it must never be selected.
    incomplete = _reservable_train(train_no="301", arrival_time="")
    good = _reservable_train(train_no="305")

    assert first_reservable_srt_train([incomplete, good]) is good


def test_first_reservable_train_returns_none_when_nothing_is_bookable():
    assert first_reservable_srt_train([]) is None
    assert (
        first_reservable_srt_train(
            [
                _reservable_train(
                    general_seat_availability="매진",
                    special_seat_availability="매진",
                )
            ]
        )
        is None
    )
