"""Offline contract tests for the SRT refund (환불) surface, both steps.

WHAT IS AND IS NOT BEING PINNED. These pin that the two-step flow is BUILT and
PARSED the way the single reference implementation's live runs did it, and --
since the 2026-07-26 live verification opened the gate -- that a refund is GATED,
ROUTED and SEQUENCED correctly on its way to the wire.

The old central claim of this file was "a refund cannot be transmitted". That
claim is dead: one real refund against the real server returned a real ticket
and answered ``SUCC`` / ``IRT200277``, after which the account was confirmed
empty of both reservations and tickets from a separate session. The pins were
not deleted with it, they were moved onto the invariants that survive:

* consent gating -- no consent, a default consent, another category's consent
  and ``dry_run=True`` all still refuse, and still issue zero requests;
* the route/category binding, in both directions;
* the TWO-STEP SEPARATION: step 1 still POSTs no body at all, and step 2 is
  still built only from an identity step 1 returned. ``refund`` never fetches
  its own ``SrtRefundTicketInfo``, so a refused refund makes zero requests and a
  permitted one makes exactly one -- to the refund route, never to step 1.

One doubt this file used to record is now settled rather than pinned open:
srtgo's ``tkRetPwd`` / ``psgNm`` / ``pnr_no`` spellings are the ones the live
server accepted, so they are pinned as CORRECT instead of as DISPUTED.

What is still not pinned is anything the run did not exercise. ``Atc02063`` and
``Atc14087`` are 0-hit across all 21,673 files of our v2.0.41 offline decompile
(the bundle has no ``Atc02*`` family whatsoever), and unlike the payment this is
not even a claim two libraries make -- ryanking13/SRT has no refund at all, so
there is exactly one source and no upstream. The run covered one single-journey,
one-adult ticket.

No network, no credentials, no real ticket: every value is obviously synthetic
and every send is against an ``httpx.MockTransport``.
"""

from __future__ import annotations

from urllib.parse import parse_qsl

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    SrtAppError,
    SrtAuthError,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtNoResultsError,
    SrtProtocolError,
    SrtRefundResult,
    SrtRefundTicketInfo,
    SrtSession,
    parse_refund_response,
    parse_refund_ticket_info_response,
)
from srt_mobile_api.payloads import REFUND_CANCEL_REASON, refund_payload
from srt_mobile_api.safety import SRT_LIVE_MUTATION_CATEGORIES


REFUND_ROUTE = "/atc/selectListAtc02063_n.do"
TICKET_INFO_ROUTE = "/atc/getListAtc14087.do"

FAKE_PNR = "SYNTHETICPNR"
FAKE_RETURN_PASSWORD = "SYNTHETIC-RETURN-PASSWORD"
FAKE_BUYER = "SYNTHETIC-BUYER"


def _info(**overrides) -> SrtRefundTicketInfo:
    fields = {
        "pnr_no": FAKE_PNR,
        "sale_date": "20990101",
        "sale_window_number": "0000",
        "sale_sequence_number": "0001",
        "return_password": FAKE_RETURN_PASSWORD,
        "buyer_name": FAKE_BUYER,
    }
    fields.update(overrides)
    return SrtRefundTicketInfo(**fields)


def _ticket_info_response(**overrides) -> dict:
    row = {
        "pnrNo": FAKE_PNR,
        "ogtkSaleDt": "20990101",
        "ogtkSaleWctNo": "0000",
        "ogtkSaleSqno": "0001",
        "ogtkRetPwd": FAKE_RETURN_PASSWORD,
        "buyPsNm": FAKE_BUYER,
    }
    row.update(overrides)
    return {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {"dsOutput1": [row]},
    }


class _Recorder:
    def __init__(self, reply: dict | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.reply = reply or {"ok": True}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(200, json=self.reply)


def _client(reply: dict | None = None) -> tuple[SrtClient, _Recorder]:
    recorder = _Recorder(reply)
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(recorder))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, recorder


# --- Step 1: the reserve-info read --------------------------------------------


def test_step_one_posts_no_body_with_the_pnr_referer():
    # The Referer is what identifies the ticket; the body is empty. Both halves
    # are the contract, so both are asserted.
    client, recorder = _client(_ticket_info_response())
    client.get_refund_ticket_info(FAKE_PNR)

    request = recorder.requests[-1]
    assert request.method == "POST"
    assert request.url.path == TICKET_INFO_ROUTE
    assert request.content == b""
    # ... and no query string either, or "no body" would just mean the body
    # moved into the URL.
    assert request.url.query == b""
    assert request.headers["Referer"] == (
        f"{SrtConfig().base_url}/common/ATC/ATC0201L/view.do?pnrNo={FAKE_PNR}"
    )


def test_step_one_route_refuses_a_body_at_the_read_guard():
    # THE GUARD IS ON THE ROUTE, NOT ON THE CALLER. assert_read_only_request
    # otherwise validates method/host/path and lets any body through, and this
    # route is the one an operator experimenting with refunds is most likely to
    # point a payment or refund form at -- it is allowlisted, so no mutation
    # gate applies to it. Without this, `post_form` would transmit a PAN or a
    # ticket return password to an allowlisted path.
    from srt_mobile_api.safety import assert_read_only_request

    config = SrtConfig()
    url = f"{config.base_url}{TICKET_INFO_ROUTE}"
    # The empty body the contract calls for: accepted.
    assert_read_only_request(httpx.Request("POST", url), config)

    for forbidden in (
        {"stlCrCrdNo1": "0000000000000000"},  # a PAN
        {"tkRetPwd": FAKE_RETURN_PASSWORD},  # the refund credential
        {"pnrNo": FAKE_PNR},
    ):
        with pytest.raises(SrtProtocolError):
            assert_read_only_request(httpx.Request("POST", url, data=forbidden), config)
    # ... and the same body smuggled into the query string.
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            httpx.Request("POST", f"{url}?stlCrCrdNo1=0000000000000000"), config
        )


def test_step_one_body_guard_does_not_leak_through_post_form():
    # End to end through the public read path, which is how a caller would
    # actually reach it.
    client, recorder = _client(_ticket_info_response())
    with pytest.raises(SrtProtocolError):
        client.http.post_form(TICKET_INFO_ROUTE, {"stlCrCrdNo1": "0000000000000000"})
    assert recorder.requests == []


def test_step_one_referer_is_per_request_not_a_persistent_session_header():
    # The reference implementation sets this Referer on the session and never
    # removes it, so every later request keeps carrying a PNR. Ours is passed
    # per-request; a following read must not inherit it.
    client, recorder = _client(_ticket_info_response())
    client.get_refund_ticket_info(FAKE_PNR)
    client.http.get_text("/main/main.do", params={"deviceId": "0123456789ABCDEF"})

    assert FAKE_PNR not in recorder.requests[-1].headers.get("Referer", "")


def test_step_one_parses_the_ds_output1_payload():
    # dsOutput1, not the dsOutput0 every other outDataSets read here uses.
    info = parse_refund_ticket_info_response(_ticket_info_response())
    assert isinstance(info, SrtRefundTicketInfo)
    assert info.pnr_no == FAKE_PNR
    assert info.sale_date == "20990101"
    assert info.sale_window_number == "0000"
    assert info.sale_sequence_number == "0001"
    assert info.return_password == FAKE_RETURN_PASSWORD
    assert info.buyer_name == FAKE_BUYER


def test_step_one_does_not_read_an_identity_out_of_ds_output0():
    """The payload container really is dsOutput1.

    An identity row placed under dsOutput0 must never be read as the ticket
    identity -- refunding from a misread identity is how the wrong ticket gets
    refunded. It now raises an app error rather than a protocol error, because
    live traffic showed dsOutput0 is where the server puts its business
    failure; either way, no identity is returned.
    """
    payload = _ticket_info_response()
    payload["outDataSets"] = {"dsOutput0": payload["outDataSets"]["dsOutput1"]}
    with pytest.raises((SrtProtocolError, SrtAppError)):
        parse_refund_ticket_info_response(payload)


def test_step_one_reports_a_missing_ticket_as_a_business_failure():
    """LIVE 2026-07-26: the wrapper succeeds while the lookup fails.

    Probing an unissued PNR returned ErrorCode "0" / ErrorMsg "" with the real
    answer in dsOutput0: msgCd WRT300005, "조회자료가 없습니다.". Before this,
    the parser only looked at dsOutput1 and raised a protocol error, so a
    caller asking "is this PNR refundable?" could not tell a missing ticket
    from a broken server.
    """
    payload = {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": "WRT300005",
                    "strResult": "FAIL",
                    "msgTxt": "조회자료가 없습니다.",
                }
            ]
        },
    }
    with pytest.raises(SrtAppError) as excinfo:
        parse_refund_ticket_info_response(payload)
    assert excinfo.value.code == "WRT300005"
    # WRT300005 is the "nothing there" code the reservation list also returns,
    # so the taxonomy must class it as no-results rather than a hard failure.
    assert isinstance(excinfo.value, SrtNoResultsError)


@pytest.mark.parametrize(
    "overrides",
    [
        {"ErrorCode": "-1", "ErrorMsg": "조회 실패"},
        {"ErrorCode": "1", "ErrorMsg": ""},
        # STRICTER than this library's usual {"", "0"} wrapper check, and
        # deliberately so: the attested success condition is ErrorCode == "0"
        # AND ErrorMsg == "". On a route nobody has exercised, failing loudly on
        # a half-recognised response is the cheap mistake.
        {"ErrorCode": "", "ErrorMsg": ""},
        {"ErrorCode": "0", "ErrorMsg": "무언가"},
    ],
)
def test_step_one_requires_the_exact_documented_success_condition(overrides):
    payload = _ticket_info_response()
    payload.update(overrides)
    with pytest.raises(SrtAppError):
        parse_refund_ticket_info_response(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"ErrorCode": "0", "ErrorMsg": ""},  # no outDataSets
        {"ErrorCode": "0", "ErrorMsg": "", "outDataSets": {"dsOutput1": []}},
        {"ErrorCode": 0, "ErrorMsg": ""},  # non-string wrapper
    ],
)
def test_step_one_refuses_a_malformed_response(payload):
    with pytest.raises(SrtProtocolError):
        parse_refund_ticket_info_response(payload)


def test_step_one_refuses_a_response_with_no_pnr():
    with pytest.raises(SrtProtocolError):
        parse_refund_ticket_info_response(_ticket_info_response(pnrNo=""))


@pytest.mark.parametrize("pnr", ["", "   ", None, 12345])
def test_step_one_refuses_a_missing_pnr(pnr):
    # The emptiness guard, kept separate from the character guard below so a
    # failure names which one broke.
    client, recorder = _client(_ticket_info_response())
    with pytest.raises(ValueError):
        client.get_refund_ticket_info(pnr)
    assert recorder.requests == []


@pytest.mark.parametrize(
    "pnr",
    [
        "PNR&extra=1",
        "PNR?x",
        "PNR#f",
        "PNR 1",
        "PNR\r\nX-Injected: 1",  # header injection
        "..",
        # Unicode alphanumerics. str.isalnum() -- the obvious way to write this
        # check -- accepts every one of these, and they then died deep inside
        # httpx as a bare UnicodeEncodeError: an exception outside this
        # library's taxonomy, raised while BUILDING the request. The guard is an
        # explicit ASCII class for exactly this reason.
        "한글PNR",
        "١٢٣",  # Arabic-Indic digits
        "Ⅳ",  # Roman numeral U+2163
        "ＰＮＲ",  # fullwidth
        # Unbounded length: this used to become a 5,058-byte Referer.
        "A" * 5000,
        "A" * 33,
    ],
)
def test_step_one_refuses_a_pnr_that_is_not_bounded_ascii(pnr):
    # The PNR is interpolated into the Referer URL this endpoint gates on, so
    # the refusal must be a ValueError from THIS library -- not a stray
    # UnicodeEncodeError from the transport, and not a 5KB header.
    client, recorder = _client(_ticket_info_response())
    with pytest.raises(ValueError):
        client.get_refund_ticket_info(pnr)
    assert recorder.requests == []


@pytest.mark.parametrize("pnr", ["ABC123", "ABC-123", "A", "A" * 32, "0123456789"])
def test_step_one_accepts_a_bounded_ascii_pnr(pnr):
    client, recorder = _client(_ticket_info_response())
    client.get_refund_ticket_info(pnr)
    assert recorder.requests[-1].headers["Referer"].endswith(f"pnrNo={pnr}")


def test_step_one_route_is_registered_as_a_read():
    from srt_mobile_api.safety import READ_ONLY_ROUTES, ReadOnlyRoute

    assert ReadOnlyRoute("POST", "app", TICKET_INFO_ROUTE) in READ_ONLY_ROUTES
    # ... and only as a POST. The GET spelling is not a route we have evidence
    # for.
    assert ReadOnlyRoute("GET", "app", TICKET_INFO_ROUTE) not in READ_ONLY_ROUTES


def test_refund_ticket_info_hides_its_secrets_from_repr():
    rendered = repr(_info())
    assert FAKE_RETURN_PASSWORD not in rendered
    assert FAKE_BUYER not in rendered
    assert FAKE_PNR not in rendered


# --- Step 2: the refund form --------------------------------------------------


def test_refund_form_carries_exactly_the_documented_seven_fields():
    assert set(refund_payload(_info())) == {
        "pnr_no",
        "cnc_dmn_cont",
        "saleDt",
        "saleWctNo",
        "saleSqno",
        "tkRetPwd",
        "psgNm",
    }


def test_refund_form_maps_step_one_fields_onto_their_renamed_step_two_names():
    # The renaming is the reference implementation's, not a server contract we
    # can see: step 1 returns ogtkRetPwd / buyPsNm, step 2 sends them as
    # tkRetPwd / psgNm. The body also mixes snake_case (pnr_no, cnc_dmn_cont)
    # with camelCase (saleDt, saleWctNo, saleSqno) in one dict.
    form = refund_payload(_info())
    assert form["pnr_no"] == FAKE_PNR
    assert form["cnc_dmn_cont"] == REFUND_CANCEL_REASON == "승차권 환불로 취소"
    assert form["saleDt"] == "20990101"
    assert form["saleWctNo"] == "0000"
    assert form["saleSqno"] == "0001"
    assert form["tkRetPwd"] == FAKE_RETURN_PASSWORD
    assert form["psgNm"] == FAKE_BUYER


def test_refund_form_uses_the_srtgo_spellings_the_live_server_accepted():
    # SETTLED 2026-07-26, and the pin stays because the answer is now a fact
    # worth protecting rather than a choice worth flagging. srtgo says
    # tkRetPwd / psgNm / pnr_no; our OWN app's offline ticket cache says
    # retPwd / buyPsNm / pnrNo
    # (analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:645,648,651).
    # That site deserialises a base64 SharedPreferences blob ("ticketListOffline")
    # into a display model -- a LOCAL CACHE, not an outbound request -- so it was
    # never evidence about this endpoint, and the live refund proved it: this
    # exact form returned a real ticket (SUCC / IRT200277).
    #
    # This test used to say the three names were DISPUTED and to nominate the
    # cache spellings as the first thing to try if the route were ever rejected.
    # It was not: the route was exercised and accepted. Do not "correct" these
    # to the app's cache spellings.
    #
    # The precedent that motivated the doubt still stands and is worth keeping
    # straight: srtgo really did ship txtPrnNo for korail's txtPnrNo. srtgo was
    # wrong there and right here, so single-source field names have to be tested
    # one at a time, not trusted or distrusted as a class.
    form = refund_payload(_info())
    assert "tkRetPwd" in form and "retPwd" not in form
    assert "psgNm" in form and "buyPsNm" not in form
    assert "pnr_no" in form and "pnrNo" not in form


@pytest.mark.parametrize(
    "overrides",
    [
        {"pnr_no": "   "},
        {"sale_date": ""},
        {"sale_window_number": ""},
        {"sale_sequence_number": ""},
        {"return_password": ""},
        {"buyer_name": ""},
    ],
)
def test_refund_refuses_a_partial_ticket_identity(overrides):
    # Each field is part of the identity the server matches on. A refund built
    # from a partial identity has a failure mode nobody here can predict, and
    # refusing to build one strands nothing.
    with pytest.raises(ValueError):
        refund_payload(_info(**overrides))


def test_refund_refuses_a_foreign_input_type():
    with pytest.raises(ValueError):
        refund_payload(FAKE_PNR)  # type: ignore[arg-type]


# --- The step-2 envelope ------------------------------------------------------


def test_refund_uses_the_ordinary_result_map_envelope():
    # Unlike the card payment on the very same flow, which answers in
    # outDataSets.dsOutput0. This one is the ordinary resultMap, same as cancel.
    result = parse_refund_response(
        {"resultMap": [{"strResult": "SUCC", "msgCd": "IRG000000", "msgTxt": "정상처리"}]}
    )
    assert isinstance(result, SrtRefundResult)
    assert result.succeeded is True
    assert result.message_code == "IRG000000"


def test_refund_business_failure_is_returned_not_raised():
    result = parse_refund_response(
        {"resultMap": [{"strResult": "FAIL", "msgTxt": "환불 불가"}]}
    )
    assert result.succeeded is False
    assert result.message == "환불 불가"


def test_refund_envelope_tolerates_the_payments_container_spelling():
    # Both parsers route through normalize_result_row, which accepts either
    # container, so neither hard-asserts a layout nobody has verified.
    result = parse_refund_response(
        {"outDataSets": {"dsOutput0": [{"strResult": "SUCC"}]}}
    )
    assert result.succeeded is True


@pytest.mark.parametrize(
    "payload",
    [{}, {"resultMap": []}, {"resultMap": [{"msgTxt": "no status"}]}],
)
def test_refund_refuses_a_malformed_envelope(payload):
    with pytest.raises(SrtProtocolError):
        parse_refund_response(payload)


# --- Consent gating and the preview -------------------------------------------


@pytest.mark.parametrize(
    "consent",
    [None, MutationConsent(), MutationConsent(allow_reserve=True, allow_cancel=True)],
)
def test_refund_denies_a_consent_that_does_not_allow_refund(consent):
    client, recorder = _client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.refund(_info(), consent=consent)
    assert recorder.requests == []


def test_refund_requires_an_authenticated_session():
    client, _recorder = _client()
    client.session.current = None
    with pytest.raises(SrtAuthError):
        client.refund(_info(), consent=MutationConsent(allow_refund=True))


def test_refund_dry_run_previews_without_sending():
    client, recorder = _client()
    preview = client.refund(_info(), consent=MutationConsent(allow_refund=True))
    assert isinstance(preview, MutationPreview)
    assert preview.category == "refund"
    assert preview.method == "POST"
    assert preview.route == REFUND_ROUTE
    assert preview.note == "dry-run: not sent"
    assert recorder.requests == []


def test_refund_preview_redacts_the_password_the_name_and_the_pnr():
    client, _recorder = _client()
    preview = client.refund(_info(), consent=MutationConsent(allow_refund=True))
    assert preview.payload["tkRetPwd"] == "[REDACTED]"
    assert preview.payload["psgNm"] == "[REDACTED]"
    assert preview.payload["pnr_no"] == "[REDACTED]"
    rendered = repr(preview)
    for secret in (FAKE_RETURN_PASSWORD, FAKE_BUYER, FAKE_PNR):
        assert secret not in rendered
    # The sale identifiers and the reason literal stay legible: with the
    # password masked they authorise nothing, and a fully-redacted preview says
    # nothing at all. Same line the cancel form draws between pnrNo and jrnyCnt.
    assert preview.payload["saleDt"] == "20990101"
    assert preview.payload["saleWctNo"] == "0000"
    assert preview.payload["saleSqno"] == "0001"
    assert preview.payload["cnc_dmn_cont"] == REFUND_CANCEL_REASON


# --- THE KILL SWITCH ----------------------------------------------------------


def test_refund_is_live_enabled_alongside_the_other_three_canary():
    # CANARY, inverted rather than deleted on 2026-07-26. It used to pin
    # "refund is not in the set". The set now means "a live run answered this
    # category's wire format", and refund qualifies: SUCC / IRT200277 for a real
    # ticket, with the account confirmed empty afterwards from a separate
    # session.
    #
    # The exact contents are still pinned, so a FIFTH category cannot appear
    # quietly. If this fails because one did, do NOT fix the test -- membership
    # is granted for having been answered by the real server, not for being
    # implemented.
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset(
        {"reserve", "cancel", "payment", "refund"}
    )
    assert "refund" in SRT_LIVE_MUTATION_CATEGORIES


def test_a_fully_valid_refund_consent_puts_the_documented_form_on_the_wire():
    # WAS "a fully permissive refund consent still cannot transmit", which was
    # this file's central invariant until the live verification refuted it. The
    # pin moved to the question that replaced it: when every gate IS satisfied,
    # what exactly goes out?
    #
    # Answer, asserted on the recorded request rather than on the builder: one
    # POST, to the refund route and nothing else, carrying the seven documented
    # fields with srtgo's spellings -- the same body the live server accepted.
    # The stubbed reply carries the code it returned (SUCC / IRT200277).
    client, recorder = _client(
        {"resultMap": [{"strResult": "SUCC", "msgCd": "IRT200277", "msgTxt": "정상처리"}]}
    )
    result = client.refund(
        _info(),
        consent=MutationConsent(
            allow_reserve=True,
            allow_payment=True,
            allow_cancel=True,
            allow_refund=True,
            dry_run=False,
            fake_card_only=False,
            real_card_acknowledged=True,
        ),
    )
    assert isinstance(result, SrtRefundResult)
    assert result.succeeded is True
    assert result.message_code == "IRT200277"
    assert len(recorder.requests) == 1
    request = recorder.requests[0]
    assert request.method == "POST"
    assert request.url.path == REFUND_ROUTE
    sent = dict(parse_qsl(request.content.decode("utf-8"), keep_blank_values=True))
    assert sent == refund_payload(_info())
    assert sent["tkRetPwd"] == FAKE_RETURN_PASSWORD
    assert sent["psgNm"] == FAKE_BUYER
    assert sent["pnr_no"] == FAKE_PNR


def test_a_refund_never_performs_the_step_one_read_itself():
    # THE REASON THE TWO STEPS ARE SEPARATE METHODS, and it did not change when
    # the gate opened -- only the reason for caring did. It used to be "a
    # refused refund must not leave a live step-1 request behind for an
    # operation that can never complete". Now that a refund CAN complete, the
    # surviving invariant is the sequencing one: step 2's body is nothing but
    # the identity step 1 returned, so refund() takes an already-fetched
    # SrtRefundTicketInfo and never fetches one itself. A refused refund still
    # makes zero requests; a permitted one makes exactly one, to the refund
    # route, never to step 1.
    #
    # Do not "simplify" this by having refund() fetch its own info.
    client, recorder = _client()
    with pytest.raises(SrtMutationNotAllowedError):
        client.refund(_info(), consent=MutationConsent(dry_run=False))
    assert recorder.requests == []

    permitted, recorder = _client(
        {"resultMap": [{"strResult": "SUCC", "msgCd": "IRT200277"}]}
    )
    permitted.refund(
        _info(), consent=MutationConsent(allow_refund=True, dry_run=False)
    )
    assert [request.url.path for request in recorder.requests] == [REFUND_ROUTE]
    assert TICKET_INFO_ROUTE not in [
        request.url.path for request in recorder.requests
    ]
    # `refund` must not even hold a reference to step 1: assert on the source
    # rather than re-filtering the list above, which would keep passing if the
    # coupling were reintroduced behind a conditional.
    import inspect

    source = inspect.getsource(SrtClient.refund)
    assert "getListAtc14087" not in source
    assert "get_refund_ticket_info" not in source.split('"""')[2]


def test_refund_route_is_not_reachable_through_a_read():
    from srt_mobile_api.safety import assert_read_only_request

    request = httpx.Request(
        "POST", f"{SrtConfig().base_url}{REFUND_ROUTE}", data=refund_payload(_info())
    )
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(request, SrtConfig())


@pytest.mark.parametrize(
    "foreign_route",
    [
        "/arc/selectListArc05013_n.do",  # reserve
        "/ard/selectListArd02045_n.do",  # cancel
        "/ata/selectListAta09036_n.do",  # payment
    ],
)
def test_a_refund_consent_cannot_be_aimed_at_another_categorys_route(foreign_route):
    # The route/category cross-check, and since 2026-07-26 it is the only thing
    # stopping a genuine refund consent from POSTing this body to a different
    # category's endpoint -- the live-enablement block used to refuse a refund
    # ahead of it. Asserted through the public send path (real gate ordering)
    # and directly on the rule.
    from srt_mobile_api.safety import assert_mutation_route_category

    client, recorder = _client()
    with pytest.raises(SrtProtocolError) as excinfo:
        client.http.post_mutation_form(
            foreign_route,
            refund_payload(_info()),
            consent=MutationConsent(allow_refund=True, dry_run=False),
            category="refund",
        )
    assert "does not match route" in str(excinfo.value)
    assert recorder.requests == []

    with pytest.raises(SrtProtocolError):
        assert_mutation_route_category(foreign_route, "refund")
    assert_mutation_route_category(REFUND_ROUTE, "refund")


def test_the_refund_route_refuses_every_other_categorys_consent():
    # The same cross-check from the other side.
    from srt_mobile_api.safety import assert_mutation_route_category

    for category in ("reserve", "cancel", "payment"):
        with pytest.raises(SrtProtocolError):
            assert_mutation_route_category(REFUND_ROUTE, category)
