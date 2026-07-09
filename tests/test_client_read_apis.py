import httpx

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.models import TrainSearchQuery, TrainSummary


def test_read_pages_and_notice(load_json_fixture, load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/main/main.do":
            return httpx.Response(200, text="<html>main</html>")
        if request.url.path == "/ara/ara0101v.do":
            return httpx.Response(200, text="<html>booking</html>")
        if request.url.path == "/main/noticeList.do":
            return httpx.Response(200, json=load_json_fixture("notice_list.json"))
        if request.url.path == "/atc/selectListAtc14017_n.do":
            return httpx.Response(200, text=load_text_fixture("ticket_list.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    assert "main" in client.get_main().raw
    assert "booking" in client.get_booking_page().raw
    assert client.get_notice_list()["noticeList"][0]["title"] == "공지"
    assert "승차권" in client.get_ticket_list().text


def test_search_uses_act10_and_search_endpoint(load_json_fixture, load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text=load_text_fixture("netfunnel_act10.js"))
        if request.url.path == "/ara/selectListAra10007_n.do" and request.method == "POST":
            return httpx.Response(200, json=load_json_fixture("search_success.json"))
        if request.url.path == "/ara/selectListAra10082_n.do":
            return httpx.Response(200, json=load_json_fixture("group_search_success.json"))
        if request.url.path == "/ara/selectListAra10007_n.do":
            return httpx.Response(200, text="<html>searchForm</html>")
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    query = TrainSearchQuery("0551", "0020", "20260710")
    result = client.search_trains(query)
    group = client.search_group_trains(query)
    assert result.trains[0].train_no == "303"
    assert group.trains[0].train_no == "301"


def test_timetable_and_fare(load_text_fixture):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ara/selectListAra12009_n.do":
            return httpx.Response(200, text=load_text_fixture("timetable.html"))
        if request.url.path == "/ara/selectListAra13010_n.do":
            return httpx.Response(200, text=load_text_fixture("fare.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    train = TrainSummary(train_no="303", train_group_code="300", service_class_code="17", run_date="20260710", departure_date="20260710", departure_time="060000", departure_station_code="0551", arrival_station_code="0020")
    assert "06:00" in client.get_timetable(train).text
    assert "51,900원" in client.get_fare(train).text
