"""The 할인쿠폰 read: its route registration, its parser, and its client method."""

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtProtocolError, SrtSessionExpiredError
from srt_mobile_api.models import DiscountCoupon, DiscountCouponList, SrtSession
from srt_mobile_api.parsers import parse_discount_coupon_page
from srt_mobile_api.safety import (
    COUPON_LIST_PATH,
    READ_ONLY_ROUTES,
    ReadOnlyRoute,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
    assert_mutation_route,
)


COUPON_REGISTRATION_ROUTE = "/arb/selectListArb02A01_n.do"


def _authenticated(client: SrtClient) -> SrtClient:
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    return client


# --------------------------------------------------------------------------
# route registration
# --------------------------------------------------------------------------


def test_coupon_list_is_registered_as_a_read_and_only_as_GET():
    assert COUPON_LIST_PATH == "/apa/selectListApa03020_n.do"
    assert ReadOnlyRoute("GET", "app", COUPON_LIST_PATH) in READ_ONLY_ROUTES
    # POST is what the coupon REGISTRATION would look like if someone aimed it
    # at this path. It must not be reachable.
    assert ReadOnlyRoute("POST", "app", COUPON_LIST_PATH) not in READ_ONLY_ROUTES


def test_coupon_list_is_not_a_mutation_route():
    assert all(route.path != COUPON_LIST_PATH for route in SRT_MUTATION_ROUTES)
    assert COUPON_LIST_PATH not in SRT_MUTATION_ROUTE_CATEGORIES
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("POST", COUPON_LIST_PATH)


def test_coupon_registration_route_is_in_neither_allowlist():
    """Registering a coupon changes account state and is not implemented.

    It would need a fifth consent category, and SRT_LIVE_MUTATION_CATEGORIES is
    pinned to four by its own canary. So the route it posts to is absent from
    the read allowlist, absent from the mutation allowlist, and uncategorised.
    """
    for method in ("GET", "POST"):
        assert (
            ReadOnlyRoute(method, "app", COUPON_REGISTRATION_ROUTE)
            not in READ_ONLY_ROUTES
        )
    assert all(
        route.path != COUPON_REGISTRATION_ROUTE for route in SRT_MUTATION_ROUTES
    )
    assert COUPON_REGISTRATION_ROUTE not in SRT_MUTATION_ROUTE_CATEGORIES
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("POST", COUPON_REGISTRATION_ROUTE)


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def test_empty_live_page_parses_as_an_empty_list(load_text_fixture):
    result = parse_discount_coupon_page(load_text_fixture("discount_coupons_empty.html"))
    assert isinstance(result, DiscountCouponList)
    assert result.coupons == ()
    assert result.is_empty is True
    assert "보유한 쿠폰이 없습니다" in result.text


def test_the_live_pages_commented_out_template_is_not_read_as_coupons(load_text_fixture):
    """The single most important property of this parser.

    The real page ships a two-coupon designer template, commented out, INSIDE
    ul.coupList, with plausible numbers (5503900624) and rates (23%, 15%). A
    regex would have produced two coupons for an account that holds none.
    """
    html = load_text_fixture("discount_coupons_empty.html")
    assert "5503900624" in html and "23%" in html
    result = parse_discount_coupon_page(html)
    assert result.coupons == ()
    assert all("5503900624" != coupon.coupon_number for coupon in result.coupons)


def test_populated_page_parses_every_span_as_display_text(load_text_fixture):
    result = parse_discount_coupon_page(load_text_fixture("discount_coupons_held.html"))
    assert result.is_empty is False
    assert result.coupons == (
        DiscountCoupon(
            coupon_number="1000000001",
            # the page prints a leading space inside <span class="type">;
            # whitespace is collapsed, not preserved and not interpreted.
            discount_kind="운임할인",
            discount_rate="30%",
            validity="2026.01.01 ~ 2026.12.31",
            basis="탑승일기준",
            remaining_uses="이용가능 횟수 : 2",
        ),
        DiscountCoupon(
            coupon_number="1000000002",
            discount_kind="특실할인",
            discount_rate="10%",
            validity="2026.03.01 ~ 2026.06.30",
            basis="발권일기준",
            remaining_uses="이용가능 횟수 : 1",
        ),
    )


def test_parser_does_not_read_the_registration_form(load_text_fixture):
    html = load_text_fixture("discount_coupons_empty.html")
    assert "dscp_no" in html and "dscp_pwd" in html
    result = parse_discount_coupon_page(html)
    assert all(
        "dscp" not in value
        for coupon in result.coupons
        for value in vars(coupon).values()
    )


def test_page_without_the_coupon_list_is_refused():
    with pytest.raises(SrtProtocolError):
        parse_discount_coupon_page("<html><body><p>somewhere else</p></body></html>")


def test_list_that_neither_lists_nor_denies_is_refused():
    with pytest.raises(SrtProtocolError):
        parse_discount_coupon_page(
            '<html><body><ul class="coupList"></ul></body></html>'
        )


def test_page_that_both_lists_and_denies_is_refused():
    with pytest.raises(SrtProtocolError):
        parse_discount_coupon_page(
            "<html><body>"
            '<div class="boxType03">보유한 쿠폰이 없습니다.</div>'
            '<ul class="coupList"><li><div class="coup-box">'
            '<span class="num">1000000003</span>'
            "</div></li></ul>"
            "</body></html>"
        )


def test_empty_body_and_login_form_are_classified_before_parsing():
    with pytest.raises(SrtProtocolError):
        parse_discount_coupon_page("   ")
    with pytest.raises(SrtSessionExpiredError):
        parse_discount_coupon_page(
            '<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>'
        )


# --------------------------------------------------------------------------
# client
# --------------------------------------------------------------------------


def test_get_discount_coupons_issues_one_parameterless_GET(load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=load_text_fixture("discount_coupons_empty.html"))

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    result = client.get_discount_coupons()
    assert result.is_empty is True
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == COUPON_LIST_PATH
    assert calls[0].url.query == b""
    assert calls[0].headers["Referer"].endswith("/ara/ara0101v.do")
    assert not calls[0].content


def test_get_discount_coupons_returns_rows(load_text_fixture):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=load_text_fixture("discount_coupons_held.html"))

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    result = client.get_discount_coupons()
    assert [coupon.coupon_number for coupon in result.coupons] == [
        "1000000001",
        "1000000002",
    ]
    assert [coupon.discount_kind for coupon in result.coupons] == ["운임할인", "특실할인"]


def test_expired_session_on_the_coupon_read_clears_session_and_cookies():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>',
        )

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    client.http.cookies.set("JSESSIONID", "session-cookie")
    with pytest.raises(SrtSessionExpiredError):
        client.get_discount_coupons()
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies
