"""The 할인 reads: route registration, parsers, and client methods."""

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtProtocolError, SrtSessionExpiredError
from srt_mobile_api.models import (
    DiscountCoupon,
    DiscountCouponList,
    PublicDiscountPage,
    SrtSession,
)
from srt_mobile_api.parsers import (
    parse_discount_coupon_page,
    parse_public_discount_page,
)
from srt_mobile_api.consent import MUTATION_CATEGORIES
from srt_mobile_api.safety import (
    COUPON_LIST_PATH,
    PUBLIC_DISCOUNT_PAGE_PATH,
    PUBLIC_DISCOUNT_SEARCH_PATH,
    READ_ONLY_ROUTES,
    MutationRoute,
    ReadOnlyRoute,
    SRT_LIVE_MUTATION_CATEGORIES,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
    assert_mutation_route,
    assert_mutation_route_category,
)


COUPON_REGISTRATION_ROUTE = "/arb/selectListArb02A01_n.do"
DISCOUNT_SEARCH_ROUTE = "/ara/selectListAra10131_n.do"


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


def test_coupon_registration_route_is_a_mutation_and_never_a_read():
    """Registering a coupon changes account state: it is a MUTATION route only.

    It got the fifth consent category ("coupon") on 2026-07-26 and is registered
    and categorised accordingly. What must never happen is the other thing: the
    read-only path must not reach it under any method, because a coupon number
    and its password travelling under a read is precisely the leak the GET-only
    registration of COUPON_LIST_PATH exists to prevent.
    """
    for method in ("GET", "POST"):
        assert (
            ReadOnlyRoute(method, "app", COUPON_REGISTRATION_ROUTE)
            not in READ_ONLY_ROUTES
        )
    assert (
        MutationRoute("POST", "app", COUPON_REGISTRATION_ROUTE)
        in SRT_MUTATION_ROUTES
    )
    assert SRT_MUTATION_ROUTE_CATEGORIES[COUPON_REGISTRATION_ROUTE] == "coupon"
    # Registered means the route gate passes; it does NOT mean transmittable.
    assert_mutation_route("POST", COUPON_REGISTRATION_ROUTE)
    # GET is not registered: the app posts, and a mutation performed with the
    # wrong verb is not a mutation this library will make.
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("GET", COUPON_REGISTRATION_ROUTE)


def test_coupon_category_is_bound_to_its_own_route_only():
    # The route/category cross-check is what stops a "coupon" consent being
    # pointed at the reserve route, and a "reserve" consent at this one.
    assert_mutation_route_category(COUPON_REGISTRATION_ROUTE, "coupon")
    with pytest.raises(SrtProtocolError):
        assert_mutation_route_category(COUPON_REGISTRATION_ROUTE, "reserve")
    with pytest.raises(SrtProtocolError):
        assert_mutation_route_category("/arc/selectListArc05013_n.do", "coupon")


def test_the_coupon_category_is_not_live_enabled():
    """The fifth category exists and the kill switch did not widen for it.

    This is the whole safety claim of the coupon half: a caller can name the
    category, build the form and read a preview, and nothing can put it on the
    wire. No coupon registration has ever been sent from this library, and
    membership of SRT_LIVE_MUTATION_CATEGORIES is granted on a live response and
    on nothing else.
    """
    assert "coupon" in MUTATION_CATEGORIES
    assert "coupon" not in SRT_LIVE_MUTATION_CATEGORIES
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset(
        {"reserve", "cancel", "payment", "refund"}
    )


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


# --------------------------------------------------------------------------
# 공공할인 (할인 승차권) page
# --------------------------------------------------------------------------


def test_public_discount_page_is_registered_as_a_read_and_only_as_GET():
    assert PUBLIC_DISCOUNT_PAGE_PATH == "/common/ARA/ARA0301V/view.do"
    assert ReadOnlyRoute("GET", "app", PUBLIC_DISCOUNT_PAGE_PATH) in READ_ONLY_ROUTES
    # POST is how every OTHER /common/ARA/ route in this allowlist is reached
    # (the selector popups), which is exactly why it is worth pinning that this
    # one is not: this page is a search FORM, not a popup.
    assert (
        ReadOnlyRoute("POST", "app", PUBLIC_DISCOUNT_PAGE_PATH) not in READ_ONLY_ROUTES
    )
    assert all(
        route.path != PUBLIC_DISCOUNT_PAGE_PATH for route in SRT_MUTATION_ROUTES
    )


def test_the_discount_search_is_a_read_and_only_as_POST():
    """`/ara/selectListAra10131_n.do` is a SEARCH: a read, and never a mutation.

    POST only. The GET half of this route is the app's page NAVIGATION
    (`goSubmit()` retargets a `method="get"` form at it), and four live probes on
    2026-07-26 showed it returns a byte-identical shell whatever the query
    carries — so registering it would allow an arbitrary ~146-field query string
    on a read route in exchange for a response nothing here would use.
    """
    assert DISCOUNT_SEARCH_ROUTE == PUBLIC_DISCOUNT_SEARCH_PATH
    assert ReadOnlyRoute("POST", "app", DISCOUNT_SEARCH_ROUTE) in READ_ONLY_ROUTES
    assert ReadOnlyRoute("GET", "app", DISCOUNT_SEARCH_ROUTE) not in READ_ONLY_ROUTES
    # A search creates nothing, so it must never be reachable as a mutation --
    # which is also what keeps it out of any consent category.
    assert all(route.path != DISCOUNT_SEARCH_ROUTE for route in SRT_MUTATION_ROUTES)
    assert DISCOUNT_SEARCH_ROUTE not in SRT_MUTATION_ROUTE_CATEGORIES
    with pytest.raises(SrtProtocolError):
        assert_mutation_route("POST", DISCOUNT_SEARCH_ROUTE)


def test_unapproved_live_page_is_an_answer_and_not_an_error(load_text_fixture):
    result = parse_public_discount_page(load_text_fixture("public_discount_none.html"))
    assert isinstance(result, PublicDiscountPage)
    assert result.is_eligible is False
    assert result.approved == ()
    assert len(result.entitlements) == 8
    assert [entry.code for entry in result.entitlements] == [
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "07",
        "08",
    ]
    assert [entry.name for entry in result.entitlements] == [
        "다자녀",
        "임산부",
        "기초생활",
        "청소년",
        "모범 납세자",
        "3세대 동행할인",
        "",
        "",
    ]
    assert all(entry.approved is False for entry in result.entitlements)


def test_the_pages_own_comparisons_are_not_mistaken_for_declarations(load_text_fixture):
    """`data1Check != "Y"` appears nine more times than `var data1Check`.

    The flag regex is anchored on `var` for exactly this reason. If it were not,
    the unapproved page would read as approved, because its very next line
    compares every flag to the literal "Y".
    """
    html = load_text_fixture("public_discount_none.html")
    assert html.count('data1Check != "Y"') >= 1
    assert html.count('data1Check == "Y"') >= 1
    assert parse_public_discount_page(html).is_eligible is False


def test_approved_flags_are_read_by_slot(load_text_fixture):
    result = parse_public_discount_page(
        load_text_fixture("public_discount_approved.html")
    )
    assert result.is_eligible is True
    assert [entry.code for entry in result.approved] == ["01", "06"]
    assert [entry.name for entry in result.approved] == ["다자녀", "3세대 동행할인"]
    assert {entry.code for entry in result.entitlements if not entry.approved} == {
        "02",
        "03",
        "04",
        "05",
        "07",
        "08",
    }


def test_page_without_the_PBL_DISC_CD_field_is_refused():
    with pytest.raises(SrtProtocolError):
        parse_public_discount_page(
            '<html><body><script>var data1Check="";</script></body></html>'
        )


def test_page_without_exactly_eight_flags_is_refused():
    seven = "".join(f'var data{slot}Check="";' for slot in range(1, 8))
    with pytest.raises(SrtProtocolError):
        parse_public_discount_page(
            f'<html><body><input name="PBL_DISC_CD" value="">'
            f"<script>{seven}</script></body></html>"
        )


def test_duplicate_flag_declaration_is_refused():
    eight = "".join(f'var data{slot}Check="";' for slot in range(1, 9))
    with pytest.raises(SrtProtocolError):
        parse_public_discount_page(
            f'<html><body><input name="PBL_DISC_CD" value="">'
            f'<script>{eight}var data1Check="Y";</script></body></html>'
        )


def test_flag_value_that_is_neither_blank_nor_Y_is_not_approved():
    eight = "".join(
        f'var data{slot}Check="{"N" if slot == 3 else ""}";' for slot in range(1, 9)
    )
    result = parse_public_discount_page(
        f'<html><body><input name="PBL_DISC_CD" value="">'
        f"<script>{eight}</script></body></html>"
    )
    assert result.is_eligible is False


def test_get_public_discounts_issues_one_parameterless_GET(load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=load_text_fixture("public_discount_none.html"))

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    result = client.get_public_discounts()
    assert result.is_eligible is False
    assert len(calls) == 1
    assert calls[0].method == "GET"
    assert calls[0].url.path == PUBLIC_DISCOUNT_PAGE_PATH
    assert calls[0].url.query == b""
    assert not calls[0].content


def test_get_public_discounts_never_touches_the_search_or_netfunnel(load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, text=load_text_fixture("public_discount_approved.html")
        )

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    result = client.get_public_discounts()
    assert [entry.code for entry in result.approved] == ["01", "06"]
    # The page it just read contains the search target and an act_10 call. Both
    # stay inert: reading a form is not submitting it.
    assert DISCOUNT_SEARCH_ROUTE in result.raw
    assert "act_10" in result.raw
    assert [request.url.path for request in calls] == [PUBLIC_DISCOUNT_PAGE_PATH]


def test_expired_session_on_the_public_discount_read_clears_session():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<form action="/apb/selectListApb01080_n.do">'
            '<input name="hmpgPwdCphd"></form>',
        )

    client = _authenticated(SrtClient(SrtConfig(), transport=httpx.MockTransport(handler)))
    client.http.cookies.set("JSESSIONID", "session-cookie")
    with pytest.raises(SrtSessionExpiredError):
        client.get_public_discounts()
    assert client.session.current is None
    assert "JSESSIONID" not in client.http.cookies
