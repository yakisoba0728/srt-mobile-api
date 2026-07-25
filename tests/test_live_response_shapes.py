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
from srt_mobile_api.errors import SrtSessionExpiredError
from srt_mobile_api.parsers import (
    is_login_form,
    is_login_redirect_page,
    is_unauthenticated_page,
    parse_fare_page,
    parse_html_page,
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
