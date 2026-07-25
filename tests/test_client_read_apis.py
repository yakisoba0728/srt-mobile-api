from urllib.parse import parse_qs, parse_qsl

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtAppError, SrtNetFunnelError, SrtProtocolError, SrtSessionExpiredError
from srt_mobile_api.models import (
    FarePage,
    NoticeListResult,
    PassengerCounts,
    SeatSelectionPage,
    SrtSession,
    TimetablePage,
    TrainSearchQuery,
    TrainSummary,
)
from srt_mobile_api.parsers import (
    parse_html_page,
    parse_notice_list_response,
    parse_seat_selection_page,
)


def test_html_page_rejects_empty_and_login_form_for_authenticated_context():
    with pytest.raises(SrtProtocolError):
        parse_html_page("", context="ticket list")
    with pytest.raises(SrtSessionExpiredError):
        parse_html_page(
            '<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>',
            context="ticket list",
            require_authenticated=True,
        )
    lookalike = parse_html_page(
        "<p>hmpgPwdCphd selectListApb01080_n.do</p>",
        context="ticket list",
        require_authenticated=True,
    )
    assert "hmpgPwdCphd" in lookalike.text
    off_host_form = parse_html_page(
        '<form action="https://evil.example/apb/selectListApb01080_n.do">'
        '<input name="hmpgPwdCphd"></form>',
        context="ticket list",
        require_authenticated=True,
    )
    assert off_host_form.raw


def test_notice_requires_notice_list():
    with pytest.raises(SrtProtocolError):
        parse_notice_list_response({})
    with pytest.raises(SrtAppError):
        parse_notice_list_response({"ErrorCode": "NOTICE_ERR", "ErrorMsg": "notice failed"})
    result = parse_notice_list_response({"noticeList": []})
    assert isinstance(result, NoticeListResult)
    assert result.notices == ()
    assert result.raw == {"noticeList": []}


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
    notice_raw = client.get_notice_list()
    assert isinstance(notice_raw, dict)
    assert notice_raw["noticeList"][0]["SUBJ"] == "Synthetic subject"
    notice_result = client.get_typed_notice_list()
    assert notice_result.notices[0].subject == "Synthetic subject"
    assert notice_result.notices[0].post_no == 42
    assert "승차권" in client.get_ticket_list().text


def test_ticket_list_classifies_returned_login_form_as_expired():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>',
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "session-cookie")
    with pytest.raises(SrtSessionExpiredError):
        client.get_ticket_list()
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


def test_json_login_form_expiry_clears_session_and_cookies():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>',
            headers={"Content-Type": "text/html"},
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "session-cookie")
    with pytest.raises(SrtSessionExpiredError):
        client.get_notice_list()
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


def test_valid_notice_json_with_login_markup_preserves_session_and_cookies():
    login_markup = "<form action='/apb/selectListApb01080_n.do'><input name='hmpgPwdCphd'></form>"
    payload = {"noticeList": [], "ordinary": login_markup}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    session = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    client.session.current = session
    client.http.cookies.set("JSESSIONID", "session-cookie")

    result = client.get_notice_list()
    assert result == payload
    assert client.session.current is session
    assert "JSESSIONID" in client.http.cookies


def test_detail_login_form_expiry_clears_session_and_cookies():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>',
            headers={"Content-Type": "text/html"},
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "session-cookie")
    with pytest.raises(SrtSessionExpiredError):
        client.get_fare(TrainSummary(train_no="303"))
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies


def test_selector_methods_send_exact_path_form_accept_and_referer(load_text_fixture):
    expected = [
        (
            "/common/ARA/ARA0501P/view.do",
            "selector_station.html",
            {
                "reqCode": "1",
                "sDptStnNm": "수서",
                "sArvStnNm": "부산",
                "sDptStnCd": "0551",
                "sArvStnCd": "0020",
                "sNowSel": "1",
            },
        ),
        (
            "/common/ARA/ARA0502P/view.do",
            "selector_station_map.html",
            {
                "reqCode": "2",
                "sNowSel": "1",
            },
        ),
        (
            "/common/ARA/ARA0401P/view.do",
            "selector_date.html",
            {"reqCode": "3", "selectDay": "", "selectDt": "20260714"},
        ),
        (
            "/common/ARA/ARA0901P/view.do",
            "selector_passenger.html",
            {
                "reqCode": "6",
                "isOrg": "2",
                "passenger1": "1",
                "passenger2": "0",
                "passenger3": "0",
                "passenger4": "0",
                "passenger5": "1",
                "totalPessnger": "2",
            },
        ),
        (
            "/common/ARA/ARA0701P/view.do",
            "selector_seat_option.html",
            {"reqCode": "5", "rqSeatAttCd": "015", "locSeatAttCd": "000", "seatAttNm": "일반/기본"},
        ),
        (
            "/common/ARA/ARA0201V/view.do",
            "selector_train_group.html",
            {"reqCode": "7", "trnGpCd": "109", "trnGpCdNm": "전체"},
        ),
    ]
    fixtures_by_path = {path: fixture for path, fixture, _payload in expected}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=load_text_fixture(fixtures_by_path[request.url.path]))

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        pages = [
            client.get_station_selector("수서", "부산", "0551", "0020"),
            client.get_station_map_selector(),
            client.get_date_selector("20260714"),
            client.get_passenger_selector(PassengerCounts(adult=1, child=1)),
            client.get_seat_option_selector(),
            client.get_train_group_selector(),
        ]
    finally:
        client.close()

    assert [request.url.path for request in seen] == [path for path, _fixture, _payload in expected]
    assert [dict(parse_qsl(request.content.decode(), keep_blank_values=True)) for request in seen] == [
        payload for _path, _fixture, payload in expected
    ]
    assert all(request.method == "POST" for request in seen)
    assert all(request.headers["accept"] == "text/html, */*; q=0.01" for request in seen)
    assert all(
        request.headers["content-type"] == "application/x-www-form-urlencoded; charset=UTF-8"
        for request in seen
    )
    assert all(request.headers["origin"] == "https://app.srail.or.kr" for request in seen)
    assert all(request.headers["referer"] == "https://app.srail.or.kr/ara/ara0101v.do" for request in seen)
    assert [page.raw for page in pages] == [
        load_text_fixture(fixture) for _path, fixture, _payload in expected
    ]


@pytest.mark.parametrize(
    ("method_name", "args", "kwargs"),
    [
        ("get_station_selector", ("", "부산", "0551", "0020"), {}),
        ("get_date_selector", ("2026-07-14",), {}),
        ("get_seat_option_selector", (), {"seat_name": ""}),
        ("get_train_group_selector", ("999", "전체"), {}),
        ("get_train_group_selector", ("109", ""), {}),
    ],
)
def test_selector_validation_fails_before_transport(method_name, args, kwargs):
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text="<html>unexpected</html>")

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError):
            getattr(client, method_name)(*args, **kwargs)
        assert called is False
    finally:
        client.close()


def test_selector_empty_body_is_protocol_failure():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SrtProtocolError, match="station map selector"):
            client.get_station_map_selector()
    finally:
        client.close()


def test_selector_login_form_clears_session_and_cookies():
    login_html = '<form action="/apb/selectListApb01080_n.do"><input name="hmpgPwdCphd"></form>'

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=login_html)

    client = SrtClient(transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "synthetic-cookie")
    try:
        with pytest.raises(SrtSessionExpiredError):
            client.get_station_map_selector()
        assert client.session.current is None
        assert not list(client.http.cookies.jar)
    finally:
        client.close()


def test_selector_json_app_error_is_typed_raw_preserving_and_redacted():
    payload = {
        "ErrorCode": "SELECTOR_ERR",
        "ErrorMsg": '{"netfunnelKey":"key-secret"}',
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SrtAppError) as exc_info:
            client.get_station_map_selector()
        assert exc_info.value.code == "SELECTOR_ERR"
        assert exc_info.value.raw == payload
        assert "key-secret" not in str(exc_info.value)
        assert "key-secret" not in repr(exc_info.value)
    finally:
        client.close()


@pytest.mark.parametrize(
    "payload",
    [
        {"ErrorCode": "0", "netfunnelKey": "key-secret"},
        {"html": "<html><body>JSON is not popup HTML framing</body></html>"},
        ["not", "an", "object"],
    ],
)
def test_selector_json_success_or_non_object_shape_is_protocol_failure(payload):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    client = SrtClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SrtProtocolError) as exc_info:
            client.get_station_map_selector()
        assert exc_info.value.raw == payload
        assert "key-secret" not in str(exc_info.value)
        assert "key-secret" not in repr(exc_info.value)
    finally:
        client.close()


def test_search_uses_act10_and_search_endpoint(load_json_fixture, load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text=load_text_fixture("netfunnel_act10.js"))
        if request.url.path == "/ara/selectListAra10007_n.do" and request.method == "POST":
            return httpx.Response(200, json=load_json_fixture("search_success.json"))
        if request.url.path == "/ara/selectListAra10082_n.do":
            return httpx.Response(200, json=load_json_fixture("group_search_success.json"))
        if request.url.path == "/ara/selectListAra10007_n.do":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(handler),
        clock=lambda: 1712345678.901,
    )
    # A group search requires totPrnb >= 10 (ara0101v.js:551-554); use a valid group-size
    # query so search_group_trains builds a payload the app would actually send.
    query = TrainSearchQuery(
        "0551", "0020", "20260710", passengers=PassengerCounts(adult=10)
    )
    result = client.search_trains(query)
    group = client.search_group_trains(query)
    assert result.trains[0].train_no == "303"
    assert result.trains[0].departure_station_name == "수서"
    assert result.trains[0].arrival_station_name == "부산"
    assert group.trains[0].train_no == "301"
    assert group.trains[0].departure_station_name == "수서"
    assert group.trains[0].arrival_station_name == "부산"
    assert [request.url.path for request in calls].count("/ts.wseq") == 2
    assert all(str(request.url).endswith("&1712345678901") for request in calls if request.url.path == "/ts.wseq")
    assert sum(
        request.method == "GET" and request.url.path == "/ara/selectListAra10007_n.do" for request in calls
    ) == 2
    search_posts = [request for request in calls if request.method == "POST"]
    for request in search_posts:
        payload = parse_qs(request.content.decode(), keep_blank_values=True)
        assert payload["serverNonce"] == ["nonce-1"]
        assert payload["unknownField"] == ["keep-me"]
        assert payload["dptRsStnCdNm1"] == ["수서"]


def test_search_proceeds_through_a_bypassed_netfunnel_queue(
    load_json_fixture,
    load_text_fixture,
):
    # kTsBypass=300 with no key. The app sets the running state and fires
    # onBypass without reading a key (netfunnel.js, _showResultChkEnter), i.e. it
    # simply proceeds. We used to raise SrtNetFunnelError out of _get_act10_key,
    # and because that error carries code None rather than NET000001 it was not
    # covered by _search_with_retry either -- so a bypassed queue aborted the
    # search outright instead of searching.
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(
                200,
                text="NetFunnel.gRtype=5101;NetFunnel.gControl.result='5101:300:nwait=0&nnext=0';",
            )
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        return httpx.Response(200, json=load_json_fixture("search_success.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    try:
        result = client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    finally:
        client.close()

    assert result.trains[0].train_no == "303"
    # One acquisition, one hydration, one search POST: the bypass costs no retry.
    assert [request.url.path for request in calls].count("/ts.wseq") == 1
    posts = [request for request in calls if request.method == "POST"]
    assert len(posts) == 1
    # The keyless bypass is sent as netfunnelKey="", not dropped and not invented.
    posted = dict(parse_qsl(posts[0].content.decode(), keep_blank_values=True))
    assert posted["netfunnelKey"] == ""


def _paginated_search_response(
    departure_times: list[str | None],
    flag: object = "N",
    *,
    metadata_as_object: bool = False,
    include_flag: bool = True,
) -> dict:
    metadata: dict[str, object] = {
        "msgCd": "IRG000000",
        "strResult": "SUCC",
        "qryCnqeCnt": str(len(departure_times)),
    }
    if include_flag:
        metadata["fllwPgExt"] = flag
    rows = []
    for index, departure_time in enumerate(departure_times, start=1):
        row: dict[str, object] = {
            "trnNo": str(300 + index),
            "trnGpCd": "300",
            "stlbTrnClsfCd": "17",
        }
        if departure_time is not None:
            row["dptTm"] = departure_time
        rows.append(row)
    return {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": metadata if metadata_as_object else [metadata],
            "dsOutput1": rows,
        },
    }


def test_iter_train_search_pages_reuses_personal_hydration_key_and_cursor(load_text_fixture):
    calls: list[httpx.Request] = []
    responses = iter(
        [
            _paginated_search_response(["060000"], "Y"),
            _paginated_search_response(["070000"], "N", metadata_as_object=True),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        return httpx.Response(200, json=next(responses))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_train_search_pages(
            TrainSearchQuery("0551", "0020", "20260710", departure_time="050000")
        )
    )

    assert [[train.departure_time for train in page.trains] for page in pages] == [
        ["060000"],
        ["070000"],
    ]
    assert [request.url.path for request in calls] == [
        "/ts.wseq",
        "/ara/selectListAra10007_n.do",
        "/ara/selectListAra10007_n.do",
        "/ara/selectListAra10007_n.do",
    ]
    posts = [request for request in calls if request.method == "POST"]
    first, second = [
        dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        for request in posts
    ]
    assert first["dptTm"] == "050000"
    assert second["dptTm"] == "060001"
    assert first["dptTm1"] == second["dptTm1"] == "050000"
    assert first["netfunnelKey"] == second["netfunnelKey"] == "NF"
    assert first["unknownField"] == second["unknownField"] == "keep-me"
    assert first["trnNo"] == second["trnNo"] == ""
    assert "fllwPgExt" not in first
    assert "fllwPgExt" not in second


def test_iter_train_search_pages_stops_after_first_n_page(load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        return httpx.Response(200, json=_paginated_search_response(["060000"], "N"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(client.iter_train_search_pages(TrainSearchQuery("0551", "0020", "20260710")))

    assert len(pages) == 1
    assert sum(request.method == "POST" for request in calls) == 1


def test_iter_train_search_pages_yields_empty_continuation_once_then_stops(load_text_fixture):
    calls: list[httpx.Request] = []
    responses = iter(
        [
            _paginated_search_response(["060000"], "Y"),
            _paginated_search_response([], "Y"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        return httpx.Response(200, json=next(responses))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_train_search_pages(
            TrainSearchQuery("0551", "0020", "20260710", departure_time="050000")
        )
    )

    assert [len(page.trains) for page in pages] == [1, 0]
    assert sum(request.method == "POST" for request in calls) == 2


def test_iter_snapshots_empty_state_and_cursor_before_yield(load_text_fixture):
    posted_cursors: list[str] = []
    responses = iter(
        [
            _paginated_search_response(["060000", "063000"], "Y"),
            _paginated_search_response(["070000"], "N"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        posted_cursors.append(
            dict(parse_qsl(request.content.decode(), keep_blank_values=True))["dptTm"]
        )
        return httpx.Response(200, json=next(responses))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    iterator = client.iter_train_search_pages(
        TrainSearchQuery("0551", "0020", "20260710", departure_time="050000")
    )

    first_page = next(iterator)
    first_page.trains.clear()
    second_page = next(iterator)

    assert second_page.trains[0].departure_time == "070000"
    assert posted_cursors == ["050000", "063001"]


def test_iter_group_train_search_pages_keeps_group_route_and_state(load_text_fixture):
    calls: list[httpx.Request] = []
    responses = iter(
        [
            _paginated_search_response(["060000"], "Y"),
            _paginated_search_response(["070000"], "N"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        return httpx.Response(200, json=next(responses))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_train_search_pages(
            TrainSearchQuery(
                "0551",
                "0020",
                "20260710",
                departure_time="050000",
                passengers=PassengerCounts(adult=10),
            ),
            group=True,
        )
    )

    assert len(pages) == 2
    assert [
        (request.method, request.url.path)
        for request in calls
        if request.url.host != "nf.letskorail.com"
    ] == [
        ("GET", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10082_n.do"),
        ("POST", "/ara/selectListAra10082_n.do"),
    ]
    payloads = [
        dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        for request in calls
        if request.method == "POST"
    ]
    assert [payload["grpDv"] for payload in payloads] == ["1", "1"]
    assert [payload["psgNum"] for payload in payloads] == ["10", "10"]
    assert [payload["psgInfoPerPrnb1"] for payload in payloads] == ["10", "10"]
    assert [payload["unknownField"] for payload in payloads] == ["keep-me", "keep-me"]


def test_iter_first_page_net000001_repeats_full_flow_once(
    load_json_fixture,
    load_text_fixture,
):
    calls: list[httpx.Request] = []
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            key = "FIRST" if sum(call.url.path == "/ts.wseq" for call in calls) == 1 else "SECOND"
            return httpx.Response(200, text=f"NetFunnel.gControl.result='5101:200:key={key}';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        if post_count == 1:
            return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))
        return httpx.Response(200, json=_paginated_search_response(["060000"], "N"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(client.iter_train_search_pages(TrainSearchQuery("0551", "0020", "20260710")))

    assert len(pages) == 1
    assert sum(call.url.path == "/ts.wseq" for call in calls) == 2
    assert sum(call.method == "GET" and call.url.path != "/ts.wseq" for call in calls) == 2
    payloads = [
        dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        for request in calls
        if request.method == "POST"
    ]
    assert [payload["netfunnelKey"] for payload in payloads] == ["FIRST", "SECOND"]


def test_iter_continuation_net000001_refreshes_only_failing_cursor_once(
    load_json_fixture,
):
    calls: list[httpx.Request] = []
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        calls.append(request)
        if request.url.host == "nf.letskorail.com":
            key = "FIRST" if sum(call.url.path == "/ts.wseq" for call in calls) == 1 else "SECOND"
            return httpx.Response(200, text=f"NetFunnel.gControl.result='5101:200:key={key}';")
        if request.method == "GET":
            key = "FIRST" if sum(call.method == "GET" and call.url.path != "/ts.wseq" for call in calls) == 1 else "SECOND"
            return httpx.Response(
                200,
                text=(
                    '<form><input name="serverNonce" value="nonce-'
                    + key
                    + '"><input name="unknownField" value="keep-me"></form>'
                ),
            )
        post_count += 1
        if post_count == 1:
            return httpx.Response(200, json=_paginated_search_response(["060000"], "Y"))
        if post_count == 2:
            return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))
        return httpx.Response(200, json=_paginated_search_response(["070000"], "N"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_train_search_pages(
            TrainSearchQuery("0551", "0020", "20260710", departure_time="050000")
        )
    )

    assert [page.trains[0].departure_time for page in pages] == ["060000", "070000"]
    posts = [
        dict(parse_qsl(request.content.decode(), keep_blank_values=True))
        for request in calls
        if request.method == "POST"
    ]
    assert [payload["dptTm"] for payload in posts] == ["050000", "060001", "060001"]
    assert [payload["netfunnelKey"] for payload in posts] == ["FIRST", "FIRST", "SECOND"]
    assert [payload["serverNonce"] for payload in posts] == [
        "nonce-FIRST",
        "nonce-FIRST",
        "nonce-SECOND",
    ]
    assert sum(call.url.path == "/ts.wseq" for call in calls) == 2


def test_iter_continuation_second_net000001_raises_without_replaying_first_page(
    load_json_fixture,
):
    post_count = 0
    post_cursors: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text='<form><input name="unknownField" value="keep-me"></form>')
        post_count += 1
        post_cursors.append(dict(parse_qsl(request.content.decode(), keep_blank_values=True))["dptTm"])
        if post_count == 1:
            return httpx.Response(200, json=_paginated_search_response(["060000"], "Y"))
        return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    iterator = client.iter_train_search_pages(
        TrainSearchQuery("0551", "0020", "20260710", departure_time="050000")
    )

    assert next(iterator).trains[0].departure_time == "060000"
    with pytest.raises(SrtNetFunnelError) as exc_info:
        next(iterator)
    assert exc_info.value.code == "NET000001"
    assert post_cursors == ["050000", "060001", "060001"]


@pytest.mark.parametrize(
    ("departure_time", "row_time", "error_match"),
    [
        ("050000", None, "last_departure_time"),
        ("050000", "06000A", "last_departure_time"),
        ("060001", "060000", "repeated"),
        ("070000", "060000", "progress"),
    ],
)
def test_iter_rejects_bad_or_nonprogress_cursor_without_another_post(
    load_text_fixture,
    departure_time,
    row_time,
    error_match,
):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(200, json=_paginated_search_response([row_time], "Y"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    iterator = client.iter_train_search_pages(
        TrainSearchQuery("0551", "0020", "20260710", departure_time=departure_time)
    )

    assert len(next(iterator).trains) == 1
    with pytest.raises(SrtProtocolError, match=error_match):
        next(iterator)
    assert post_count == 1


@pytest.mark.parametrize(
    ("flag", "include_flag"),
    [(None, False), ("", True), ("y", True), (True, True)],
)
def test_iter_rejects_missing_or_invalid_following_flag_without_another_post(
    load_text_fixture,
    flag,
    include_flag,
):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(
            200,
            json=_paginated_search_response(
                ["060000"],
                flag,
                include_flag=include_flag,
            ),
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtProtocolError, match="fllwPgExt"):
        list(client.iter_train_search_pages(TrainSearchQuery("0551", "0020", "20260710")))
    assert post_count == 1


def test_iter_max_pages_is_exact_and_stops_without_extra_post(load_text_fixture):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        departure_time = "060000" if post_count == 1 else "070000"
        return httpx.Response(200, json=_paginated_search_response([departure_time], "Y"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    pages = list(
        client.iter_train_search_pages(
            TrainSearchQuery("0551", "0020", "20260710", departure_time="050000"),
            max_pages=2,
        )
    )

    assert len(pages) == 2
    assert post_count == 2


@pytest.mark.parametrize("max_pages", [0, -1, True, False, 1.0, "2", None])
def test_iter_rejects_invalid_max_pages_before_transport(max_pages):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("transport must not be called")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError, match="max_pages"):
        client.iter_train_search_pages(
            TrainSearchQuery("0551", "0020", "20260710"),
            max_pages=max_pages,
        )
    assert calls == 0


def test_net000001_repeats_full_flow_once_with_fresh_keys(load_json_fixture, load_text_fixture):
    calls: list[tuple[str, str]] = []
    posted_keys: list[str] = []
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        calls.append((request.method, request.url.path))
        if request.url.host == "nf.letskorail.com":
            key = "FIRST" if sum(path == "/ts.wseq" for _, path in calls) == 1 else "SECOND"
            return httpx.Response(200, text=f"NetFunnel.gControl.result='5101:200:key={key}';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        posted_keys.append(parse_qs(request.content.decode())["netfunnelKey"][0])
        if post_count == 1:
            return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))
        return httpx.Response(200, json=load_json_fixture("search_success.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler), clock=lambda: 1712345678.901)
    result = client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert result.trains[0].train_no == "303"
    assert [path for _, path in calls].count("/ts.wseq") == 2
    assert calls.count(("GET", "/ara/selectListAra10007_n.do")) == 2
    assert calls.count(("POST", "/ara/selectListAra10007_n.do")) == 2
    assert posted_keys == ["FIRST", "SECOND"]


def test_net000001_is_not_retried_more_than_once(load_json_fixture, load_text_fixture):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(200, json=load_json_fixture("search_netfunnel_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtNetFunnelError) as exc_info:
        client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert exc_info.value.code == "NET000001"
    assert post_count == 2


def test_ordinary_app_failure_is_not_retried(load_text_fixture):
    post_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_count
        if request.url.host == "nf.letskorail.com":
            return httpx.Response(200, text="NetFunnel.gControl.result='5101:200:key=NF';")
        if request.method == "GET":
            return httpx.Response(200, text=load_text_fixture("search_page.html"))
        post_count += 1
        return httpx.Response(
            200,
            json={
                "ErrorCode": "0",
                "ErrorMsg": "",
                "outDataSets": {
                    "dsOutput0": [{"msgCd": "SEARCH_ERR", "strResult": "FAIL", "msgTxt": "failed"}],
                    "dsOutput1": [],
                },
            },
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtAppError):
        client.search_trains(TrainSearchQuery("0551", "0020", "20260710"))
    assert post_count == 1


def _complete_seat_train() -> TrainSummary:
    # A real captured train has no seatAttCd (request-side field); get_seat_page must still
    # build the arc02012 request, defaulting seatAttCd to "015".
    return TrainSummary(
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
    )


def test_seat_selection_parser_requires_authenticated_marker(load_text_fixture):
    page = parse_seat_selection_page(load_text_fixture("seat_selection_page.html"))
    assert isinstance(page, SeatSelectionPage)
    assert "좌석선택" in page.text
    assert "합성 테스트 페이지" in page.raw

    with pytest.raises(SrtProtocolError, match="seat selection"):
        parse_seat_selection_page("<html><body>unexpected page</body></html>")
    with pytest.raises(SrtSessionExpiredError):
        parse_seat_selection_page(
            '<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>'
        )


@pytest.mark.parametrize(
    "html",
    [
        '<script>const label = "좌석선택";</script>',
        '<style>.x::after { content: "좌석선택"; }</style>',
        '{"ErrorMsg":"좌석선택"}',
    ],
)
def test_seat_selection_parser_requires_marker_in_visible_element_data(html):
    with pytest.raises(SrtProtocolError, match="seat selection"):
        parse_seat_selection_page(html)


def test_get_seat_page_posts_once_and_returns_inert_page(load_text_fixture):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=load_text_fixture("seat_selection_page.html"),
            headers={"Content-Type": "text/html; charset=UTF-8"},
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    page = client.get_seat_page(_complete_seat_train())

    assert isinstance(page, SeatSelectionPage)
    assert "좌석선택" in page.text
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/arc/selectListArc02012_n.do"
    assert not requests[0].url.query
    posted = dict(parse_qsl(requests[0].content.decode(), keep_blank_values=True))
    assert posted["choiceSeatCount"] == "1"
    # seatAttCd comes from the request-side default "015", not the (absent) row value.
    assert posted["seatAttCd"] == "015"


def _seat_page_client(requests: list[httpx.Request], html: str) -> SrtClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, text=html, headers={"Content-Type": "text/html; charset=UTF-8"}
        )

    return SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))


def _posted_seat_count(request: httpx.Request) -> str:
    return dict(parse_qsl(request.content.decode(), keep_blank_values=True))[
        "choiceSeatCount"
    ]


def test_get_seat_page_derives_choice_seat_count_from_the_passenger_total(
    load_text_fixture,
):
    # choiceSeatCount is the PARTY SIZE, not a constant: the app sends
    # choiceSeatCount = lfn_getRsv("totPrnb") (ara1001l.js:1511), and totPrnb is
    # the booking screen's passenger total (ara0101v.js:794/:809,
    # getPsgTotCnt()). It used to be a hardcoded "1" with nothing wired to it.
    requests: list[httpx.Request] = []
    client = _seat_page_client(requests, load_text_fixture("seat_selection_page.html"))
    try:
        client.get_seat_page(
            _complete_seat_train(),
            passengers=PassengerCounts(adult=2, child=1),
        )
    finally:
        client.close()

    assert _posted_seat_count(requests[0]) == "3"


def test_get_seat_page_seat_count_overrides_the_passenger_total(load_text_fixture):
    # The explicit override is kept and wins, so a caller can still ask for a
    # specific count without constructing a PassengerCounts.
    requests: list[httpx.Request] = []
    client = _seat_page_client(requests, load_text_fixture("seat_selection_page.html"))
    try:
        client.get_seat_page(
            _complete_seat_train(), "1", "4", passengers=PassengerCounts(adult=2)
        )
    finally:
        client.close()

    assert _posted_seat_count(requests[0]) == "4"


def test_get_seat_page_defaults_to_one_seat_with_neither_argument(load_text_fixture):
    # With no party and no override the count is "1" -- the single traveller
    # PassengerCounts() itself defaults to -- so the previous behaviour is the
    # fallback rather than the only option.
    requests: list[httpx.Request] = []
    client = _seat_page_client(requests, load_text_fixture("seat_selection_page.html"))
    try:
        client.get_seat_page(_complete_seat_train())
    finally:
        client.close()

    assert _posted_seat_count(requests[0]) == "1"


def test_get_seat_page_rejects_incomplete_train_before_transport():
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        raise AssertionError("transport must not be entered for incomplete seat data")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="run_date"):
            client.get_seat_page(TrainSummary(train_no="303", train_group_code="300"))
        assert called is False
    finally:
        client.close()


def test_timetable_and_fare(load_text_fixture):
    captured: dict[str, dict[str, list[str]]] = {}
    headers: dict[str, httpx.Headers] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured[request.url.path] = parse_qs(request.content.decode(), keep_blank_values=True)
        headers[request.url.path] = request.headers
        if request.url.path == "/ara/selectListAra12009_n.do":
            return httpx.Response(200, text=load_text_fixture("timetable.html"))
        if request.url.path == "/ara/selectListAra13010_n.do":
            return httpx.Response(200, text=load_text_fixture("fare.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    train = TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    passengers = PassengerCounts(adult=1, child=1)
    timetable = client.get_timetable(train)
    fare = client.get_fare(train, passengers)
    assert isinstance(timetable, TimetablePage)
    assert "05:01" in timetable.text
    assert isinstance(fare, FarePage)
    assert "12,340원" in fare.text
    assert captured["/ara/selectListAra12009_n.do"]["stnCourseNm"] == ["수서-부산"]
    fare_form = captured["/ara/selectListAra13010_n.do"]
    # psgInfoPerPrnb1..5 are COMPACTED (ara0101v.js:824-836): adult and child pack
    # into the first two contiguous slots, so psgInfoPerPrnb1=1, psgInfoPerPrnb2=1,
    # rest "0" — NOT positional. The FIELD NAMES are the live page's
    # (captured 2026-07-26); the passenger1..5 spelling appears nowhere in it.
    assert fare_form["psgInfoPerPrnb1"] == ["1"]
    assert fare_form["psgInfoPerPrnb2"] == ["1"]
    assert fare_form["psgInfoPerPrnb5"] == ["0"]
    assert fare_form["psgTpCd1"] == ["1"]
    assert fare_form["psgTpCd2"] == ["5"]
    assert fare_form["psgTpCd6"] == [""]
    assert fare_form["psgInfoPerPrnb6"] == [""]
    assert "passenger1" not in fare_form
    assert fare_form["dptRsStnCd2"] == [""]
    # B4: both requests originate from the search-results page, so the app sends
    # /ara/selectListAra10007_n.do as Referer (ara1001l.js:1188-1194 & :1228-1234),
    # mirroring get_seat_page / get_mutual_verification.
    assert (
        headers["/ara/selectListAra12009_n.do"]["referer"]
        == "https://app.srail.or.kr/ara/selectListAra10007_n.do"
    )
    assert (
        headers["/ara/selectListAra13010_n.do"]["referer"]
        == "https://app.srail.or.kr/ara/selectListAra10007_n.do"
    )


def test_timetable_and_fare_stn_course_resolved_from_codes_only(load_text_fixture):
    # B3: on a code-only search the TrainSummary carries no station names; the app resolves
    # stnCourseNm from the codes via getStnNameByCd (ara1001l.js:1176-1185 / :1203-1218),
    # always producing "name-name" with the dash. Our builder must do the same rather than
    # emitting an empty / dash-less value.
    captured: dict[str, dict[str, list[str]]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured[request.url.path] = parse_qs(request.content.decode(), keep_blank_values=True)
        if request.url.path == "/ara/selectListAra12009_n.do":
            return httpx.Response(200, text=load_text_fixture("timetable.html"))
        if request.url.path == "/ara/selectListAra13010_n.do":
            return httpx.Response(200, text=load_text_fixture("fare.html"))
        raise AssertionError(f"unexpected path {request.url.path}")

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    train = TrainSummary(
        train_no="303",
        train_group_code="300",
        service_class_code="17",
        run_date="20260710",
        departure_date="20260710",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_station_name=None,
        arrival_station_name=None,
    )
    client.get_timetable(train)
    client.get_fare(train, PassengerCounts(adult=1))
    assert captured["/ara/selectListAra12009_n.do"]["stnCourseNm"] == ["수서-부산"]
    assert captured["/ara/selectListAra13010_n.do"]["stnCourseNm"] == ["수서-부산"]
