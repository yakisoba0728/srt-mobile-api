"""The error taxonomy: telling one server-side failure from another.

Before this, essentially every app-level rejection arrived as one
undifferentiated ``SrtAppError`` with only ``NET000001`` singled out, so a
caller could not tell "this train is sold out" from "your session died" from
"the queue refused you" without substring-matching Korean message text —
which is exactly what srtgo does (``srtgo/srtgo.py:721-744``) and is fragile.

What the tests here pin, in order of importance:

  * **compatibility.** Every new type SUBCLASSES the type it refines, so no
    pre-existing ``except`` clause changes meaning. This is checked
    exhaustively, not by example.
  * **codes, not text.** Classification reads ``msgCd``. The app itself only
    ever branches on a code once in the whole v2.0.41 bundle —
    ``resultMap.msgCd == "S111"`` (``ara1001l.js:1565``) — and never
    substring-matches ``msgTxt``, so neither do we. A FAIL carrying one of
    srtgo's Korean markers under an unknown code stays a plain
    ``SrtAppError``; that is pinned, because it is a deliberate refusal to
    guess rather than an oversight.
  * **the raw code survives.** Every classified exception still carries
    ``.code`` and ``.raw``, so a caller can migrate to code-based handling and
    a code map can be grown from real traffic.
  * **no new retries.** Classification tells the caller something; it changes
    nothing about what the library does on its own initiative. The single
    bounded ``NET000001`` search retry is still the only one, and ``reserve``
    is still never retried.
  * **the two empty-result shapes do not regress.** An empty search is a
    declared FAIL (``WRG000000``); an empty reservation list is a SUCC with
    empty arrays plus a second ``rsMap`` envelope that says FAIL
    (``WRT300005``). Both live-captured 2026-07-26, and the taxonomy must not
    turn the second into an exception.
"""

from __future__ import annotations

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig, TrainSearchQuery
from srt_mobile_api.errors import (
    INVALID_REQUEST_CODES,
    NETFUNNEL_KEY_REQUIRED_CODE,
    NO_RESULT_CODES,
    SESSION_EXPIRED_CODE,
    SrtApiError,
    SrtAppError,
    SrtAuthError,
    SrtInvalidRequestError,
    SrtIpBlockedError,
    SrtNetFunnelError,
    SrtNetFunnelKeyError,
    SrtNoResultsError,
    SrtQueueRejectedError,
    SrtSeatUnavailableError,
    SrtSessionExpiredError,
    classify_app_error,
)
from srt_mobile_api.models import SrtSession
from srt_mobile_api.netfunnel import (
    QUEUE_REJECTED_CODES,
    parse_netfunnel_response,
    parse_queue_response,
    parse_set_complete_response,
)
from srt_mobile_api.parsers import (
    parse_reservation_attempt_response,
    parse_reservation_list_response,
    parse_seat_selection_page,
    parse_train_search_response,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _search_response(code: str, message: str = "", status: str = "FAIL") -> dict:
    return {
        "ErrorCode": "0",
        "ErrorMsg": "",
        "outDataSets": {
            "dsOutput0": [
                {
                    "msgCd": code,
                    "strResult": status,
                    "msgTxt": message,
                    "qryCnqeCnt": 0,
                }
            ],
            "dsOutput1": [],
        },
    }


def _reserve_response(code: str, message: str = "synthetic") -> dict:
    return {"resultMap": [{"strResult": "FAIL", "msgCd": code, "msgTxt": message}]}


def _reservation_list_response(code: str, message: str = "synthetic") -> dict:
    return {
        "resultMap": [{"strResult": "FAIL", "msgCd": code, "msgTxt": message}],
        "trainListMap": [],
        "payListMap": [],
    }


def _netfunnel_body(code: str, params: str = "") -> str:
    return f"NetFunnel.gRtype=5101;NetFunnel.gControl.result='5002:{code}:{params}';"


# --------------------------------------------------------------------------
# Compatibility: every refinement subclasses what it refines
# --------------------------------------------------------------------------


def test_every_new_type_subclasses_the_one_it_replaces():
    """The whole compatibility contract, stated once.

    A caller who wrote ``except SrtAppError`` before this change still catches
    every app-level rejection; a caller who wrote ``except SrtNetFunnelError``
    still catches every queue failure; a caller who wrote ``except
    SrtAuthError`` around ``login()`` still catches an IP block. If any line
    below stops holding, an existing ``except`` clause silently narrowed.
    """
    assert issubclass(SrtNoResultsError, SrtAppError)
    assert issubclass(SrtInvalidRequestError, SrtAppError)
    assert issubclass(SrtSeatUnavailableError, SrtAppError)
    assert issubclass(SrtNetFunnelKeyError, SrtNetFunnelError)
    assert issubclass(SrtQueueRejectedError, SrtNetFunnelError)
    assert issubclass(SrtIpBlockedError, SrtAuthError)
    # ...and everything still descends from the one root, so a caller who
    # wraps the whole library in `except SrtApiError` is unaffected too.
    for error_type in (
        SrtNoResultsError,
        SrtInvalidRequestError,
        SrtSeatUnavailableError,
        SrtNetFunnelKeyError,
        SrtQueueRejectedError,
        SrtIpBlockedError,
    ):
        assert issubclass(error_type, SrtApiError)


def test_the_new_app_error_types_are_siblings_not_a_chain():
    """"No results" must not accidentally be caught by ``except`` on another.

    They answer different questions ("nothing matched" vs "your payload is
    wrong" vs "no seat on this train"), so a caller handling one must not
    swallow the others.
    """
    siblings = (SrtNoResultsError, SrtInvalidRequestError, SrtSeatUnavailableError)
    for one in siblings:
        for other in siblings:
            if one is not other:
                assert not issubclass(one, other)
    assert not issubclass(SrtQueueRejectedError, SrtNetFunnelKeyError)
    assert not issubclass(SrtNetFunnelKeyError, SrtQueueRejectedError)


def test_the_app_error_types_are_exported_from_the_package_root():
    import srt_mobile_api

    for name in (
        "SrtNoResultsError",
        "SrtInvalidRequestError",
        "SrtSeatUnavailableError",
        "SrtNetFunnelKeyError",
        "SrtQueueRejectedError",
        "SrtIpBlockedError",
        "classify_app_error",
    ):
        assert name in srt_mobile_api.__all__
        assert getattr(srt_mobile_api, name)


# --------------------------------------------------------------------------
# classify_app_error: the code map itself
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(NO_RESULT_CODES))
def test_no_result_codes_classify_as_no_results(code):
    error = classify_app_error(code, "조회 결과가 없습니다.", raw={"seen": code})
    assert isinstance(error, SrtNoResultsError)
    assert error.code == code
    assert error.raw == {"seen": code}


@pytest.mark.parametrize("code", sorted(INVALID_REQUEST_CODES))
def test_invalid_request_codes_classify_as_invalid_request(code):
    error = classify_app_error(code, "승객수 오류", raw={"seen": code})
    assert isinstance(error, SrtInvalidRequestError)
    assert error.code == code
    assert error.raw == {"seen": code}


@pytest.mark.parametrize("code", ["IRG099999", "WRG000001", "", None])
def test_an_unmapped_code_stays_a_plain_app_error(code):
    """The default is the OLD behaviour, unchanged.

    An unrecognised code must not be forced into a bucket. It comes back as
    the base type with the code attached, which is exactly what a caller needs
    in order to report a new code worth mapping.
    """
    error = classify_app_error(code, "unknown")
    assert type(error) is SrtAppError
    assert error.code == code


def test_classification_never_reads_the_message_text():
    """srtgo's markers under an unknown code do NOT change the class.

    All four of srtgo's non-fatal substrings (``srtgo/srtgo.py:736-744``) are
    0-hit across our v2.0.41 bundle, have no known ``msgCd``, and two of them
    describe 예약대기, a surface this library does not implement. The app
    itself never substring-matches ``msgTxt`` — it only displays it — so
    encoding them would be inventing a rule neither ground-truth source has.
    They stay plain ``SrtAppError`` deliberately, and this test exists so that
    stays a decision rather than drifting into one by accident.
    """
    for srtgo_marker in (
        "잔여석없음",
        "사용자가 많아 접속이 원활하지 않습니다",
        "예약대기 접수가 마감되었습니다",
        "예약대기자한도수초과",
        "정상적인 경로로 접근 부탁드립니다",
        "로그인 후 사용하십시오",
    ):
        error = classify_app_error("UNMAPPED0", srtgo_marker)
        assert type(error) is SrtAppError
        # ...and the message is still there for a caller who wants to match it
        # themselves, which is the migration path until a code is observed.
        assert srtgo_marker in error.message


def test_the_two_specially_handled_codes_are_not_in_the_app_error_map():
    """``S111`` and ``NET000001`` are answered outside the app-error map.

    ``S111`` becomes ``SrtSessionExpiredError`` (an ``SrtAuthError``, not an
    ``SrtAppError``) and only on the reserve response, matching the single
    bundle branch. ``NET000001`` becomes ``SrtNetFunnelKeyError``. Routing
    either through ``classify_app_error`` would have to return an
    ``SrtAppError``, which is the wrong family for both.
    """
    assert type(classify_app_error(SESSION_EXPIRED_CODE, "relogin")) is SrtAppError
    assert (
        type(classify_app_error(NETFUNNEL_KEY_REQUIRED_CODE, "key")) is SrtAppError
    )
    assert SESSION_EXPIRED_CODE not in NO_RESULT_CODES | INVALID_REQUEST_CODES
    assert NETFUNNEL_KEY_REQUIRED_CODE not in NO_RESULT_CODES | INVALID_REQUEST_CODES


# --------------------------------------------------------------------------
# App-level: the parsers now hand back the refined type
# --------------------------------------------------------------------------


def test_an_empty_search_window_is_a_no_results_error():
    """LIVE, 2026-07-26. An empty search is a declared FAIL, not an empty list.

    The deliberate empty-window step of the read-surface capture answered
    ``strResult=FAIL`` / ``WRG000000`` / "조회 결과가 없습니다." and the app
    alerts on it (``ara1001l.js:206-210``). The refinement says "retry is
    pointless, ask a different question"; the base class still catches it.
    """
    with pytest.raises(SrtNoResultsError) as exc_info:
        parse_train_search_response(
            _search_response("WRG000000", "조회 결과가 없습니다.")
        )
    assert isinstance(exc_info.value, SrtAppError)
    assert exc_info.value.code == "WRG000000"
    assert "조회 결과가 없습니다." in exc_info.value.message


def test_a_search_netfunnel_rejection_is_a_netfunnel_key_error():
    """``NET000001`` keeps its code, so the bounded retry gate is untouched."""
    with pytest.raises(SrtNetFunnelKeyError) as exc_info:
        parse_train_search_response(
            _search_response("NET000001", "NetFunnel key required")
        )
    assert isinstance(exc_info.value, SrtNetFunnelError)
    assert exc_info.value.code == "NET000001"


def test_a_reserve_passenger_count_rejection_is_an_invalid_request_error():
    with pytest.raises(SrtInvalidRequestError) as exc_info:
        parse_reservation_attempt_response(
            _reserve_response("WRP011002", "승객수 오류")
        )
    assert isinstance(exc_info.value, SrtAppError)
    assert exc_info.value.code == "WRP011002"


def test_a_reserve_input_validation_rejection_is_an_invalid_request_error():
    with pytest.raises(SrtInvalidRequestError) as exc_info:
        parse_reservation_attempt_response(_reserve_response("WRR000100"))
    assert exc_info.value.code == "WRR000100"


def test_a_reserve_s111_is_still_a_session_expiry_and_not_an_app_error():
    """UNCHANGED, and pinned so the refinement cannot have moved it.

    ``ara1001l.js:1562-1573`` is the one place in the bundle that reads a
    ``msgCd`` value, and what it does with ``S111`` is stash the pending form
    and call ``memberShipLogin()``. That is an auth outcome, not a business
    one, and it stays scoped to the reserve response because that is the only
    handler the branch appears in.
    """
    with pytest.raises(SrtSessionExpiredError) as exc_info:
        parse_reservation_attempt_response(_reserve_response("S111", "relogin"))
    assert not isinstance(exc_info.value, SrtAppError)
    assert isinstance(exc_info.value, SrtAuthError)


def test_a_sold_out_seat_page_is_a_seat_unavailable_error(load_text_fixture):
    """LIVE, 2026-07-26, from a train whose every class was 매진.

    The server answers with a shell: the heading, no ``<select>``, no options,
    no form, and one trailing ``srtAlertBoxDivShow("알림", Sr.msgs.error001,
    null, "historyBack();")``. ``code`` is that ``messages.js`` KEY, not a
    ``msgCd`` — this route returns HTML and has no ``msgCd`` at all.
    """
    with pytest.raises(SrtSeatUnavailableError) as exc_info:
        parse_seat_selection_page(load_text_fixture("seat_page_sold_out_error.html"))
    assert isinstance(exc_info.value, SrtAppError)
    assert exc_info.value.code == "error001"


def test_a_working_seat_page_still_parses(load_text_fixture):
    """The mirror image: the refinement must not start refusing real pages."""
    page = parse_seat_selection_page(load_text_fixture("seat_page_car_options.html"))
    assert page.cars


# --------------------------------------------------------------------------
# The two empty-result shapes: neither regresses
# --------------------------------------------------------------------------


def test_an_empty_reservation_list_is_still_an_empty_list(load_json_fixture):
    """LIVE, 2026-07-26. THE regression this taxonomy could most easily cause.

    The verified empty response says ``resultMap[0]`` SUCC / ``IRZ000005`` with
    empty arrays, while a SECOND envelope on the same response, ``rsMap[0]``,
    says FAIL / ``WRT300005`` "조회자료가 없습니다.". ``WRT300005`` is now a
    mapped no-results code — so if anything ever started reading ``rsMap``, or
    gated on "a FAIL anywhere", an empty account would raise instead of
    answering. It must keep answering: this is the read whose entire job is
    telling an operator whether a hold survived.
    """
    result = parse_reservation_list_response(
        load_json_fixture("reservation_list_empty.json")
    )
    assert result.status == "SUCC"
    assert result.message_code == "IRZ000005"
    assert result.reservations == ()
    # The FAIL envelope is present on the very same response and still ignored.
    assert result.raw["rsMap"][0]["strResult"] == "FAIL"
    assert result.raw["rsMap"][0]["msgCd"] in NO_RESULT_CODES


def test_a_reservation_list_whose_own_envelope_fails_still_raises():
    """The other half: a real ``resultMap`` FAIL is still an error, refined."""
    with pytest.raises(SrtNoResultsError) as exc_info:
        parse_reservation_list_response(
            _reservation_list_response("WRT300005", "조회자료가 없습니다.")
        )
    assert exc_info.value.code == "WRT300005"

    with pytest.raises(SrtAppError) as unmapped:
        parse_reservation_list_response(_reservation_list_response("WRG000001"))
    assert type(unmapped.value) is SrtAppError


# --------------------------------------------------------------------------
# NetFunnel: rejected is not the same fact as broken
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(QUEUE_REJECTED_CODES))
def test_a_blocked_queue_reply_is_a_queue_rejection(code):
    """``kTsBlock``/``kTsIpBlock`` get their own events in the app's own switch.

    ``_showResultChkEnter`` fires ``"onBlock"`` and ``"onIpBlock"`` beside
    ``"onError"`` (netfunnel.js), so the bundle itself says "refused" is not
    the same fact as "malfunctioned".
    """
    with pytest.raises(SrtQueueRejectedError) as exc_info:
        parse_queue_response(_netfunnel_body(code), action="act_10")
    assert isinstance(exc_info.value, SrtNetFunnelError)
    assert exc_info.value.code == code

    with pytest.raises(SrtQueueRejectedError):
        parse_netfunnel_response(_netfunnel_body(code), action="act_10")
    with pytest.raises(SrtQueueRejectedError):
        parse_set_complete_response(
            _netfunnel_body(code).replace("5002:", "5004:"), action="act_10"
        )


@pytest.mark.parametrize("code", ["500", "505", "507", "900", "502"])
def test_other_queue_failures_stay_the_generic_netfunnel_error(code):
    """Everything else in the table falls to the app's ``onError``, and to ours.

    Including ``502`` here matters: it is accepted for ``setComplete`` only,
    so on a ``chkEnter`` it is still an error — and specifically NOT a
    rejection, because the app does not treat it as one either.
    """
    with pytest.raises(SrtNetFunnelError) as exc_info:
        parse_queue_response(_netfunnel_body(code), action="act_10")
    assert type(exc_info.value) is SrtNetFunnelError
    assert exc_info.value.code == code


def test_a_queued_reply_is_still_a_wait_and_not_a_rejection():
    """201 ``kContinue`` must never become an exception: it is the queue working."""
    token = parse_queue_response(
        _netfunnel_body("201", "key=SYNTHETIC&nwait=3&ttl=2"), action="act_10"
    )
    assert token.code == "201"
    assert token.key == "SYNTHETIC"


def test_303_express_number_is_deliberately_not_classified_as_a_rejection():
    """``kTsExpressNumber`` is an ADMISSION in the app (it stores the cookie and
    proceeds), so folding it into "rejected" would be a guess in the wrong
    direction. It has never been observed and stays generic.
    """
    assert "303" not in QUEUE_REJECTED_CODES
    with pytest.raises(SrtNetFunnelError) as exc_info:
        parse_queue_response(_netfunnel_body("303"), action="act_10")
    assert type(exc_info.value) is SrtNetFunnelError


# --------------------------------------------------------------------------
# Auth: the edge's ban vs a wrong password
# --------------------------------------------------------------------------


def test_a_blocked_ip_is_its_own_auth_error():
    """Still an ``SrtAuthError`` — the existing login handling is untouched —
    but now distinguishable without substring-matching an English
    infrastructure message. Not bundle-attested: this is not an app response
    at all (no JSON, no envelope, no ``msgCd``), which is why it is the one
    place in the taxonomy that reads text.
    """
    block_body = "Your IP Address Blocked. Please contact the administrator."

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, text=block_body, headers={"Content-Type": "text/html"})

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtIpBlockedError) as exc_info:
        client.login("login-id", "pw")
    assert isinstance(exc_info.value, SrtAuthError)
    assert "Your IP Address Blocked" in str(exc_info.value)
    assert client.session.current is None


def test_a_wrong_password_is_not_an_ip_block(load_json_fixture):
    """The distinction is only worth anything if it is exclusive."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/login.do":
            return httpx.Response(200, text="<html>login</html>")
        return httpx.Response(200, json=load_json_fixture("login_failure.json"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    with pytest.raises(SrtAuthError) as exc_info:
        client.login("login-id", "bad")
    assert not isinstance(exc_info.value, SrtIpBlockedError)


# --------------------------------------------------------------------------
# Classification changes nothing about what the library DOES
# --------------------------------------------------------------------------


def _search_client(reply: dict, page_html: str) -> tuple[SrtClient, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/ts.wseq":
            if request.url.params["opcode"] == "5004":
                return httpx.Response(
                    200, text="NetFunnel.gControl.result='5004:200:utime=1';"
                )
            return httpx.Response(
                200,
                text="NetFunnel.gControl.result='5101:200:key=SYNTHETIC&nwait=0';",
            )
        if request.method == "GET":
            return httpx.Response(200, text=page_html)
        return httpx.Response(200, json=reply)

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, calls


def _search_posts(calls: list[httpx.Request]) -> int:
    return sum(
        call.method == "POST" and call.url.path == "/ara/selectListAra10007_n.do"
        for call in calls
    )


def test_a_no_results_search_is_not_retried(load_text_fixture):
    """A refined class must not become a retry signal.

    ``NET000001`` is the ONLY code this library retries on, once. "Nothing
    matched" is a stable answer — retrying it is pure load for a guaranteed
    identical reply — and srtgo's forever-poll (``srtgo/srtgo.py:803-807``) is
    macro behaviour for a CLI, not something a library should do on its own.
    """
    client, calls = _search_client(
        _search_response("WRG000000", "조회 결과가 없습니다."),
        load_text_fixture("search_page.html"),
    )
    with pytest.raises(SrtNoResultsError):
        client.search_trains(TrainSearchQuery("0551", "0020", "20990101"))
    assert _search_posts(calls) == 1


def test_a_netfunnel_key_rejection_is_still_retried_exactly_once(load_text_fixture):
    """The one pre-existing retry, unchanged by the refinement."""
    client, calls = _search_client(
        _search_response("NET000001", "key"), load_text_fixture("search_page.html")
    )
    with pytest.raises(SrtNetFunnelKeyError):
        client.search_trains(TrainSearchQuery("0551", "0020", "20990101"))
    assert _search_posts(calls) == 2


def test_an_invalid_request_search_is_not_retried(load_text_fixture):
    client, calls = _search_client(
        _search_response("WRR000100", "invalid"), load_text_fixture("search_page.html")
    )
    with pytest.raises(SrtInvalidRequestError):
        client.search_trains(TrainSearchQuery("0551", "0020", "20990101"))
    assert _search_posts(calls) == 1
