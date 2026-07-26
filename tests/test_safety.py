from urllib.parse import urlencode

import httpx
import pytest

from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtProtocolError
from srt_mobile_api.safety import READ_ONLY_ROUTES, assert_read_only_request


def _request(method: str, url: str | httpx.URL) -> httpx.Request:
    return httpx.Request(method, url)


def _seat_form() -> dict[str, str]:
    return {
        "reqCode": "9",
        "runDt": "20260710",
        "dptDt": "20260710",
        "trnNo": "00303",
        "dptTm": "060000",
        "trnGpCd": "300",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "psrmClCd": "1",
        "seatAttCd": "015",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000010",
        "choiceSeatCount": "1",
    }


def _seat_request(
    *,
    query: str = "",
    body: str | None = None,
    content_type: str = "application/x-www-form-urlencoded",
) -> httpx.Request:
    config = SrtConfig()
    url = config.base_url + "/arc/selectListArc02012_n.do" + query
    encoded = body if body is not None else urlencode(_seat_form())
    return httpx.Request(
        "POST",
        url,
        content=encoded.encode("ascii"),
        headers={"Content-Type": content_type},
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/login/login.do"),
        ("POST", "/apb/selectListApb01080_n.do"),
        ("GET", "/main/main.do"),
        ("GET", "/ara/ara0101v.do"),
        ("POST", "/main/noticeList.do"),
        ("GET", "/atc/selectListAtc14017_n.do"),
        ("POST", "/atc/selectListAtc14016_n.do"),
        ("GET", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10130_n.do"),
        ("POST", "/ara/selectListAra10082_n.do"),
        ("POST", "/ara/selectListAra12009_n.do"),
        ("POST", "/ara/selectListAra13010_n.do"),
        ("POST", "/common/ARA/ARA0501P/view.do"),
        ("POST", "/common/ARA/ARA0502P/view.do"),
        ("POST", "/common/ARA/ARA0401P/view.do"),
        ("POST", "/common/ARA/ARA0901P/view.do"),
        ("POST", "/common/ARA/ARA0701P/view.do"),
        ("POST", "/common/ARA/ARA0201V/view.do"),
    ],
)
def test_current_app_routes_are_allowed(method, path):
    config = SrtConfig()
    assert_read_only_request(_request(method, config.base_url + path), config)


def test_only_exact_act10_netfunnel_url_is_allowed():
    config = SrtConfig()
    allowed = httpx.URL(
        config.netfunnel_url
        + "/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        + "&sid=service_1&aid=act_10&js=yes&1712345678901"
    )
    assert_read_only_request(_request("GET", allowed), config)
    rejected_queries = (
        "opcode=5101&sid=service_1&aid=act_19&js=yes",
        "opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=yes",
        "opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=yes&1712345678901&extra=1",
        "opcode=5101&opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=yes&1712345678901",
    )
    for query in rejected_queries:
        with pytest.raises(SrtProtocolError):
            assert_read_only_request(
                _request("GET", config.netfunnel_url + "/ts.wseq?" + query),
                config,
            )


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "https://evil.example/main/main.do"),
        ("POST", "https://app.srail.or.kr/arc/selectListArc05013_n.do"),
        ("POST", "https://app.srail.or.kr/ard/selectListArd02017_n.do"),
        ("POST", "https://app.srail.or.kr/%61rc/selectListArc05013_n.do"),
        ("GET", "https://app.srail.or.kr/main/noticeList.do"),
        ("POST", "https://app.srail.or.kr/main/main.do"),
    ],
)
def test_off_host_mutation_and_wrong_method_routes_are_rejected(method, url):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_request(method, url), SrtConfig())


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", "https://app.srail.or.kr/arc/selectListArc06014_n.do"),
        ("POST", "https://app.srail.or.kr/arc/selectListArc10013_n.do"),
        ("POST", "https://app.srail.or.kr/ata/selectListAta01032_n.do"),
        (
            "GET",
            "https://www.korail.com/ticket/search/list?srtJob=seatmap",
        ),
    ],
)
def test_named_adjacent_and_external_seat_routes_are_rejected(method, url):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_request(method, url), SrtConfig())


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/common/ARA/ARA0501P/view.do"),
        ("POST", "/common/ARA/ARA0403P/view.do"),
        ("POST", "/common/ARA/ARA0501P/view.do/extra"),
    ],
)
def test_selector_policy_rejects_wrong_method_legacy_neighbor_and_seat_page(method, path):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_request(method, f"{config.base_url}{path}"), config)


def test_route_registry_has_exact_expanded_size():
    # 22 since the refund's step-1 read (/atc/getListAtc14087.do) was
    # registered. That route is classified as a read by inference, not by
    # proof -- see the comment on it in safety.py.
    assert len(READ_ONLY_ROUTES) == 22


@pytest.mark.parametrize(
    "path",
    [
        "/common/ARA/%41RA0501P/view.do",
        "/common/ARA/ARA0501P%2Fview.do",
    ],
)
def test_selector_policy_rejects_percent_encoded_allowed_paths(path):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_request("POST", f"{config.base_url}{path}"), config)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/ara/selectListAra10130_n.do"),
        ("POST", "/ara/selectListAra10h01.do"),
        ("POST", "/ara/%73electListAra10130_n.do"),
        ("POST", "/ara/selectListAra10130_n.do/extra"),
    ],
)
def test_mutual_policy_rejects_wrong_method_legacy_encoded_and_seat_neighbors(
    method,
    path,
):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            _request(method, f"{config.base_url}{path}"),
            config,
        )


def test_exact_seat_page_form_is_allowed():
    assert_read_only_request(_seat_request(), SrtConfig())


def test_seat_page_first_class_cabin_is_allowed():
    # psrmClCd is now dynamic-but-validated ({'1','2'}); 특실 (2) must pass.
    assert_read_only_request(
        _seat_request(body=urlencode({**_seat_form(), "psrmClCd": "2"})),
        SrtConfig(),
    )


def test_seat_page_multi_passenger_count_is_allowed():
    # choiceSeatCount is now dynamic-but-validated (positive integer); a 2+ passenger
    # seat request (totPrnb) must pass.
    assert_read_only_request(
        _seat_request(body=urlencode({**_seat_form(), "choiceSeatCount": "2"})),
        SrtConfig(),
    )


def test_seat_page_rejects_bare_query_delimiter():
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_seat_request(query="?"), SrtConfig())


@pytest.mark.parametrize(
    "seat_request",
    [
        _request(
            "GET",
            SrtConfig().base_url + "/arc/selectListArc02012_n.do",
        ),
        _seat_request(query="?extra=1"),
        _seat_request(body=urlencode(_seat_form()) + "&reqCode=9"),
        _seat_request(
            body=urlencode(
                {
                    name: value
                    for name, value in _seat_form().items()
                    if name != "seatAttCd"
                }
            )
        ),
        _seat_request(body=urlencode({**_seat_form(), "seatNo1_1": ""})),
        _seat_request(body=urlencode({**_seat_form(), "choiceSeatCount": "0"})),
        _seat_request(body=urlencode({**_seat_form(), "choiceSeatCount": ""})),
        _seat_request(body=urlencode({**_seat_form(), "psrmClCd": "3"})),
        _seat_request(body=urlencode({**_seat_form(), "psrmClCd": "0"})),
        _seat_request(body=urlencode({**_seat_form(), "psrmClCd": ""})),
        _seat_request(body=urlencode({**_seat_form(), "trnGpCd": "900"})),
        _seat_request(body=urlencode({**_seat_form(), "trnNo": "303"})),
        _seat_request(content_type="application/json"),
    ],
)
def test_seat_page_rejects_query_duplicates_unknown_fields_and_wrong_values(seat_request):
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(seat_request, SrtConfig())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("trnNo", "٠٠٣٠٣"),
        ("dptRsStnCd", "٠٥٥١"),
    ],
)
def test_seat_page_rejects_non_ascii_digits_in_prepared_form(field, value):
    body = urlencode({**_seat_form(), field: value})

    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_seat_request(body=body), SrtConfig())


def test_seat_page_rejects_percent_encoded_route_spelling():
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            _request(
                "POST",
                config.base_url + "/arc/%73electListArc02012_n.do",
            ),
            config,
        )
