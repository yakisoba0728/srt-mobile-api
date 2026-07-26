"""할인쿠폰 등록 — the fifth consent category, and the one that cannot send.

Every test here is offline. Nothing in this file can reach the network even if
it tried: ``"coupon"`` is deliberately outside
``safety.SRT_LIVE_MUTATION_CATEGORIES``, so the transmit gate refuses it, and the
one test that asks for ``dry_run=False`` asserts exactly that refusal against a
transport that fails the test if it is ever called.

The coupon numbers below are obviously-synthetic placeholders. A real coupon
number and password are a BEARER credential — whoever holds the pair can redeem
it — which is also why two of these tests are about redaction rather than about
the wire.
"""

from __future__ import annotations

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtSession,
)
from srt_mobile_api.consent import MUTATION_CATEGORIES, require_mutation_consent
from srt_mobile_api.errors import SrtAuthError, SrtProtocolError
from srt_mobile_api.models import (
    SrtCouponRegistrationRequest,
    SrtCouponRegistrationResult,
)
from srt_mobile_api.parsers import parse_coupon_registration_response
from srt_mobile_api.payloads import coupon_registration_payload
from srt_mobile_api.redaction import redact_payload, redact_value
from srt_mobile_api.safety import (
    COUPON_LIST_PATH,
    COUPON_REGISTRATION_PATH,
    SRT_LIVE_MUTATION_CATEGORIES,
)


# Obviously fake, and shaped like the page's own inputs (10 digits / 4 chars).
FAKE_COUPON_NUMBER = "0000000000"
FAKE_COUPON_PASSWORD = "0000"


def _no_network_client() -> SrtClient:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(
            "a coupon registration must not send a request "
            f"(saw {request.method} {request.url.path})"
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client


def _allow_coupon(**overrides: bool) -> MutationConsent:
    return MutationConsent(allow_coupon=True, **overrides)


# --------------------------------------------------------------------------
# the category itself
# --------------------------------------------------------------------------


def test_coupon_is_a_category_of_its_own_and_defaults_denied():
    assert "coupon" in MUTATION_CATEGORIES
    assert MutationConsent().allow_coupon is False
    with pytest.raises(SrtMutationNotAllowedError):
        require_mutation_consent(MutationConsent(), "coupon")
    require_mutation_consent(MutationConsent(allow_coupon=True), "coupon")


def test_allow_coupon_is_additive_and_grants_nothing_else():
    # The flag was APPENDED to MutationConsent so every consent written before it
    # existed means exactly what it meant. The other direction matters just as
    # much: opting into a coupon must not open a booking or a charge.
    consent = MutationConsent(allow_coupon=True)
    assert consent.allow_reserve is False
    assert consent.allow_payment is False
    assert consent.allow_cancel is False
    assert consent.allow_refund is False
    assert consent.dry_run is True
    for category in ("reserve", "payment", "cancel", "refund"):
        with pytest.raises(SrtMutationNotAllowedError):
            require_mutation_consent(consent, category)


def test_no_other_category_grants_a_coupon_registration():
    # The converse, and the reason this is a fifth category rather than a reuse
    # of one of the four: nobody who consented to booking a seat consented to
    # spending a coupon.
    for category in ("reserve", "payment", "cancel", "refund"):
        consent = MutationConsent(**{f"allow_{category}": True})
        with pytest.raises(SrtMutationNotAllowedError):
            require_mutation_consent(consent, "coupon")


# --------------------------------------------------------------------------
# the form
# --------------------------------------------------------------------------


def test_the_body_is_exactly_the_pages_two_fields():
    form = coupon_registration_payload(
        SrtCouponRegistrationRequest(
            coupon_number="1234567890",
            coupon_password="9876",
        )
    )
    # #couponInfo holds exactly these two inputs. No PNR, no member number, no
    # NetFunnel key -- the session is the only thing that says whose account the
    # coupon lands on.
    assert form == {"dscp_no": "1234567890", "dscp_pwd": "9876"}


@pytest.mark.parametrize(
    ("number", "password"),
    [
        ("", "1234"),  # mysrt006
        ("1234567890", ""),  # mysrt007
        ("12345678901", "1234"),  # maxlength="10"
        ("123456789a", "1234"),  # type="number" + the keyup digit strip
        ("12-3456789", "1234"),
        ("1234567890", "12345"),  # maxlength="4"
    ],
)
def test_the_builder_restates_the_pages_own_validation(number, password):
    with pytest.raises(ValueError):
        coupon_registration_payload(
            SrtCouponRegistrationRequest(
                coupon_number=number,
                coupon_password=password,
            )
        )


def test_the_password_is_not_restricted_to_digits():
    # The page constrains only the NUMBER field (type="number" plus a keyup
    # handler); the password input is a bare type="password" maxlength="4".
    # Guessing a charset the page does not enforce would refuse coupons the app
    # itself would accept.
    form = coupon_registration_payload(
        SrtCouponRegistrationRequest(
            coupon_number="1", coupon_password="a1-B"
        )
    )
    assert form["dscp_pwd"] == "a1-B"


def test_the_builder_refuses_a_lookalike_request_type():
    class Impostor(SrtCouponRegistrationRequest):
        pass

    with pytest.raises(ValueError):
        coupon_registration_payload(
            Impostor(coupon_number="1", coupon_password="1")
        )


# --------------------------------------------------------------------------
# redaction: a coupon is a bearer credential
# --------------------------------------------------------------------------


def test_both_wire_fields_are_redacted():
    # THE GAP THIS CLOSES. `dscp_pwd` is not the literal key `password`, and
    # `dscp_no` is at most ten digits -- CARD_RE matches a 13-to-19 digit run and
    # never sees it. Before these keys were registered, a preview printed a
    # redeemable coupon in full.
    redacted = redact_payload({"dscp_no": "1234567890", "dscp_pwd": "9876"})
    assert redacted == {"dscp_no": "[REDACTED]", "dscp_pwd": "[REDACTED]"}


def test_the_request_dataclass_is_redacted_by_field_name():
    request = SrtCouponRegistrationRequest(
        coupon_number="1234567890",
        coupon_password="9876",
    )
    assert redact_value(request) == {
        "coupon_number": "[REDACTED]",
        "coupon_password": "[REDACTED]",
    }
    # And repr, which is where a credential leaks into a traceback.
    assert "1234567890" not in repr(request)
    assert "9876" not in repr(request)


def test_the_preview_carries_no_usable_coupon():
    client = _no_network_client()
    preview = client.register_discount_coupon(
        "1234567890",
        "9876",
        consent=_allow_coupon(),
    )
    assert isinstance(preview, MutationPreview)
    assert preview.category == "coupon"
    assert preview.method == "POST"
    assert preview.route == COUPON_REGISTRATION_PATH
    assert preview.payload == {"dscp_no": "[REDACTED]", "dscp_pwd": "[REDACTED]"}
    assert "1234567890" not in repr(preview)
    assert "9876" not in repr(preview)


# --------------------------------------------------------------------------
# the client method
# --------------------------------------------------------------------------


def test_a_default_consent_is_denied_before_anything_is_built():
    client = _no_network_client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.register_discount_coupon(
            FAKE_COUPON_NUMBER, FAKE_COUPON_PASSWORD, consent=MutationConsent()
        )
    with pytest.raises(SrtMutationNotAllowedError):
        client.register_discount_coupon(
            FAKE_COUPON_NUMBER, FAKE_COUPON_PASSWORD, consent=None
        )


def test_an_anonymous_session_is_refused():
    client = SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(  # pragma: no cover
                AssertionError("must not send")
            )
        ),
    )
    with pytest.raises(SrtAuthError):
        client.register_discount_coupon(
            FAKE_COUPON_NUMBER, FAKE_COUPON_PASSWORD, consent=_allow_coupon()
        )


def test_a_malformed_coupon_is_refused_in_the_dry_run_too():
    # The form is built BEFORE the dry-run branch, so a preview validates exactly
    # what a send would transmit.
    client = _no_network_client()
    with pytest.raises(ValueError):
        client.register_discount_coupon("", "1234", consent=_allow_coupon())


def test_dry_run_false_is_refused_at_the_transmit_gate_and_sends_nothing():
    # THE CENTRAL CLAIM OF THIS HALF. The category is registered, categorised and
    # consented, and it still cannot leave the process, because
    # SRT_LIVE_MUTATION_CATEGORIES is the switch and "coupon" is not in it. The
    # transport raises if it is ever reached.
    client = _no_network_client()
    with pytest.raises(SrtMutationNotAllowedError, match="not live-enabled"):
        client.register_discount_coupon(
            FAKE_COUPON_NUMBER,
            FAKE_COUPON_PASSWORD,
            consent=_allow_coupon(dry_run=False),
        )
    assert "coupon" not in SRT_LIVE_MUTATION_CATEGORIES


def test_the_send_boundary_refuses_the_category_independently():
    # Defense in depth: _send_mutation_request re-asserts membership itself, so a
    # future refactor of post_mutation_form cannot widen this by accident.
    client = _no_network_client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.http._send_mutation_request(
            COUPON_REGISTRATION_PATH,
            category="coupon",
            data={"dscp_no": FAKE_COUPON_NUMBER, "dscp_pwd": FAKE_COUPON_PASSWORD},
            headers={},
        )


def test_reading_the_coupon_page_still_issues_no_post(load_text_fixture):
    # The fixture now carries couponReg() verbatim. Reading the page must not
    # execute it, and the read route stays GET-only.
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=load_text_fixture("discount_coupons_empty.html"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    result = client.get_discount_coupons()
    assert result.is_empty
    assert [(call.method, call.url.path) for call in calls] == [
        ("GET", COUPON_LIST_PATH)
    ]
    # And the page really does name the registration route, so the assertion
    # above is about behaviour rather than about an absent fixture.
    assert COUPON_REGISTRATION_PATH in result.raw


# --------------------------------------------------------------------------
# the response envelope (never observed; read off the page's own handler)
# --------------------------------------------------------------------------


def test_a_success_is_any_rtncd_that_is_not_N():
    result = parse_coupon_registration_response(
        {"resultMap": [{"RTNCD": "Y", "MSG": "정상처리되었습니다."}]}
    )
    assert isinstance(result, SrtCouponRegistrationResult)
    assert result.status == "Y"
    assert result.succeeded is True
    assert result.message == "정상처리되었습니다."


def test_a_stated_failure_is_returned_and_not_raised():
    result = parse_coupon_registration_response(
        {"resultMap": [{"RTNCD": "N", "MSG": "쿠폰번호 또는 비밀번호가 일치하지 않습니다."}]}
    )
    assert result.succeeded is False
    assert result.status == "N"
    # The message is the only thing that says WHICH failure it was.
    assert "일치하지" in result.message


def test_the_result_repr_cannot_echo_a_coupon_back():
    result = parse_coupon_registration_response(
        {"resultMap": [{"RTNCD": "N", "MSG": "쿠폰 1234567890 는 이미 사용되었습니다."}]}
    )
    assert "1234567890" not in repr(result)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"resultMap": []},
        {"resultMap": [{}]},
        # RTNCD missing: under the page's own polarity ("N" fails, anything else
        # passes) this would read as a SUCCESS, which is the wrong direction to
        # be wrong in when the question is "did my coupon get spent?".
        {"resultMap": [{"MSG": "..."}]},
        {"resultMap": [{"RTNCD": "", "MSG": "..."}]},
        {"resultMap": [{"RTNCD": 1}]},
    ],
)
def test_a_response_that_does_not_say_is_a_protocol_error(payload):
    with pytest.raises(SrtProtocolError):
        parse_coupon_registration_response(payload)


def test_the_app_level_wrapper_still_rejects():
    from srt_mobile_api.errors import SrtAppError

    with pytest.raises(SrtAppError):
        parse_coupon_registration_response(
            {
                "ERROR_CODE": "E0001",
                "ERROR_MSG": "rejected",
                "resultMap": [{"RTNCD": "Y"}],
            }
        )
