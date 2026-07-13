from unittest.mock import Mock

import pytest

from srt_mobile_api import SrtClient
from srt_mobile_api.live import (
    live_enabled,
    read_credentials_from_env,
    run_live_smoke,
    run_live_smoke_from_env,
)
from srt_mobile_api.models import (
    FareItem,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
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
        departure_station_code="0551",
        arrival_station_code="0020",
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
    client.get_notice_list.return_value = {"noticeList": [{"title": "notice"}]}
    client.get_ticket_list.return_value = HtmlPage(text="ticket", raw="<html>ticket</html>")
    client.search_trains.return_value = TrainSearchResult(trains=[train], result={}, raw={})
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
        "mutualVerificationLoaded",
        "groupTrainCount",
        "timetableRowCount",
        "fareItemCount",
        "selectorLoadedCount",
    }
    assert result["selectorLoadedCount"] == 5
    assert result["mutualVerificationLoaded"] is True
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
        "get_notice_list",
        "get_ticket_list",
        "search_trains",
        "get_mutual_verification",
        "search_group_trains",
        "get_timetable",
        "get_fare",
    ):
        assert getattr(client, method_name).called
    client.get_station_selector.assert_called_once_with("수서", "부산", "0551", "0020")
    client.get_date_selector.assert_called_once_with("20260710", hour="06")
    client.get_passenger_selector.assert_called_once_with(query.passengers)
    client.get_seat_option_selector.assert_called_once_with(request_seat_attr_code="015")
    client.get_train_group_selector.assert_called_once_with("900", "KTX+SRT")
    method_order = [call[0] for call in client.method_calls]
    assert method_order.index("get_booking_page") < method_order.index("get_station_selector")
    assert method_order.index("get_train_group_selector") < method_order.index("search_trains")
    assert method_order.index("search_trains") < method_order.index(
        "get_mutual_verification"
    )
    assert method_order.index("get_mutual_verification") < method_order.index(
        "search_group_trains"
    )
    assert "mutual-secret" not in repr(result)
    assert "mutMrkVrfCd" not in repr(result)


def test_live_from_env_requires_explicit_test_date(monkeypatch):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.setenv("SRT_LOGIN_ID", "member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", "pw")
    monkeypatch.delenv("SRT_TEST_DATE", raising=False)
    with pytest.raises(RuntimeError, match="SRT_TEST_DATE"):
        run_live_smoke_from_env()
