import httpx
import pytest

from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtProtocolError
from srt_mobile_api.safety import READ_ONLY_ROUTES, assert_read_only_request


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/login/login.do"),
        ("POST", "/apb/selectListApb01080_n.do"),
        ("GET", "/main/main.do"),
        ("GET", "/ara/ara0101v.do"),
        ("POST", "/main/noticeList.do"),
        ("GET", "/atc/selectListAtc14017_n.do"),
        ("GET", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10007_n.do"),
        ("POST", "/ara/selectListAra10082_n.do"),
        ("POST", "/ara/selectListAra12009_n.do"),
        ("POST", "/ara/selectListAra13010_n.do"),
        ("POST", "/common/ARA/ARA0501P/view.do"),
        ("POST", "/common/ARA/ARA0502P/view.do"),
        ("POST", "/common/ARA/ARA0403P/view.do"),
        ("POST", "/common/ARA/ARA0901P/view.do"),
        ("POST", "/common/ARA/ARA0701P/view.do"),
        ("POST", "/common/ARA/ARA0201V/view.do"),
    ],
)
def test_current_app_routes_are_allowed(method, path):
    config = SrtConfig()
    assert_read_only_request(method, httpx.URL(config.base_url + path), config)


def test_only_exact_act10_netfunnel_url_is_allowed():
    config = SrtConfig()
    allowed = httpx.URL(
        config.netfunnel_url
        + "/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        + "&sid=service_1&aid=act_10&js=true&1712345678901"
    )
    assert_read_only_request("GET", allowed, config)
    rejected_queries = (
        "opcode=5101&sid=service_1&aid=act_19&js=true",
        "opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true",
        "opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true&1712345678901&extra=1",
        "opcode=5101&opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=true&1712345678901",
    )
    for query in rejected_queries:
        with pytest.raises(SrtProtocolError):
            assert_read_only_request(
                "GET",
                httpx.URL(config.netfunnel_url + "/ts.wseq?" + query),
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
        assert_read_only_request(method, httpx.URL(url), SrtConfig())


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/common/ARA/ARA0501P/view.do"),
        ("POST", "/common/ARA/ARA0401P/view.do"),
        ("POST", "/common/ARA/ARA0501P/view.do/extra"),
        ("POST", "/arc/selectListArc02012_n.do"),
    ],
)
def test_selector_policy_rejects_wrong_method_legacy_neighbor_and_seat_page(method, path):
    config = SrtConfig()
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(method, httpx.URL(f"{config.base_url}{path}"), config)


def test_route_registry_has_exact_expanded_size():
    assert len(READ_ONLY_ROUTES) == 18


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
        assert_read_only_request("POST", httpx.URL(f"{config.base_url}{path}"), config)
