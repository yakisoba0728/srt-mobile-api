"""The 예약/발권 목록 read: ``POST /atc/selectListAtc14016_n.do``.

This is the only read that ENUMERATES reservations, so the properties pinned
here are the ones that decide whether a lost PNR is recoverable at all:

  * an empty account comes back as an EMPTY LIST, not an error;
  * a populated response never loses a PNR to a shape surprise;
  * a response that carries rows we cannot read a PNR out of fails LOUDLY,
    because "you have no reservations" is the one wrong answer that stops an
    operator from looking further.

The empty envelope is live-verified (2026-07-26); the populated row shape is
not, and the tests that exercise it say so.
"""

from urllib.parse import parse_qsl

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtAppError, SrtProtocolError, SrtSessionExpiredError
from srt_mobile_api.models import SrtReservationListResult, SrtSession
from srt_mobile_api.parsers import parse_reservation_list_response
from srt_mobile_api.payloads import reservation_list_payload
from srt_mobile_api.safety import READ_ONLY_ROUTES, ReadOnlyRoute, assert_read_only_request


RESERVATION_LIST_PATH = "/atc/selectListAtc14016_n.do"

# Obviously synthetic. A real PNR is an account identifier and must never enter
# the repository.
FAKE_PNR = "SYNTHETIC-PNR-1"
FAKE_PNR_2 = "SYNTHETIC-PNR-2"


def _ok_envelope(**overrides):
    row = {
        "msgCd": "IRZ000005",
        "strResult": "SUCC",
        "msgTxt": "조회할 자료가 없습니다.",
        "totPageCnt": 0,
        "rowCnt": 0,
    }
    row.update(overrides)
    return {"resultMap": [row], "trainListMap": [], "payListMap": []}


def _populated(train_rows, pay_rows):
    body = _ok_envelope(rowCnt=len(train_rows), totPageCnt=1)
    body["trainListMap"] = train_rows
    body["payListMap"] = pay_rows
    return body


# --------------------------------------------------------------------------
# Payload
# --------------------------------------------------------------------------


def test_payload_is_exactly_page_no():
    # The live server echoed the request back as commandMap {"pageNo": "0"},
    # which is the strongest confirmation available that the name is right.
    assert reservation_list_payload() == {"pageNo": "0"}
    assert reservation_list_payload(3) == {"pageNo": "3"}


@pytest.mark.parametrize("bad", [-1, "0", 1.0, True, None])
def test_payload_refuses_a_page_number_that_cannot_be_a_page(bad):
    with pytest.raises(ValueError):
        reservation_list_payload(bad)


# --------------------------------------------------------------------------
# The live-verified EMPTY shape
# --------------------------------------------------------------------------


def test_empty_account_is_an_empty_list_not_an_error(load_json_fixture):
    """LIVE, 2026-07-26. The whole envelope, verbatim except for the ids.

    Unlike the train search -- which answers an empty result with
    strResult=FAIL / WRG000000 -- this endpoint reports SUCC / IRZ000005 and
    sends genuinely empty arrays.
    """
    result = parse_reservation_list_response(
        load_json_fixture("reservation_list_empty.json")
    )

    assert isinstance(result, SrtReservationListResult)
    assert result.reservations == ()
    assert result.pnr_numbers == ()
    assert result.status == "SUCC"
    assert result.message_code == "IRZ000005"
    assert result.message == "조회할 자료가 없습니다."
    assert result.row_count == 0
    assert result.total_page_count == 0


def test_the_rs_map_that_says_fail_on_that_same_response_is_not_a_failure(
    load_json_fixture,
):
    """The verified empty response carries TWO envelopes and they disagree.

    resultMap says SUCC; rsMap says FAIL / WRT300005 "조회자료가 없습니다.".
    A parser that gated on "any FAIL anywhere" would classify the one shape we
    have actually verified as an error, and the recovery path would break
    exactly when someone is checking whether a hold survived.
    """
    body = load_json_fixture("reservation_list_empty.json")
    assert body["rsMap"][0]["strResult"] == "FAIL"

    result = parse_reservation_list_response(body)

    assert result.status == "SUCC"
    # ...and rsMap is still reachable for a caller who wants it.
    assert result.raw["rsMap"][0]["msgCd"] == "WRT300005"


def test_null_and_empty_list_both_mean_empty(load_json_fixture):
    """The verified response spells absence both ways in one body.

    rsListMap arrived as null while trainListMap arrived as []. Refusing null
    would fail on a response the server demonstrably sends.
    """
    body = load_json_fixture("reservation_list_empty.json")
    assert body["rsListMap"] is None
    body["trainListMap"] = None
    body["payListMap"] = None

    assert parse_reservation_list_response(body).reservations == ()


# --------------------------------------------------------------------------
# Envelope failures
# --------------------------------------------------------------------------


def test_a_declared_fail_raises_with_the_servers_own_code():
    with pytest.raises(SrtAppError) as exc_info:
        parse_reservation_list_response(
            {
                "resultMap": [
                    {
                        "msgCd": "WRG000001",
                        "strResult": "FAIL",
                        "msgTxt": "실패",
                    }
                ]
            }
        )
    assert exc_info.value.code == "WRG000001"


def test_an_unrecognised_third_status_is_not_read_as_a_failure():
    # Gated on == "FAIL", not != "SUCC": a status we have never seen means "not
    # declared failed", and treating it as failure would hide a list that exists.
    result = parse_reservation_list_response(
        _ok_envelope(strResult="PARTIAL", msgCd="")
    )
    assert result.status == "PARTIAL"


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        "not an object",
        {"trainListMap": []},
        {"resultMap": []},
        {"resultMap": [{"msgCd": "X", "msgTxt": "y"}]},
        {"resultMap": [{"strResult": "", "msgCd": "X", "msgTxt": "y"}]},
        {"resultMap": [{"strResult": "SUCC", "msgCd": 5, "msgTxt": "y"}]},
        {"resultMap": [{"strResult": "SUCC", "msgCd": "X", "msgTxt": None}]},
    ],
)
def test_a_malformed_envelope_raises(body):
    with pytest.raises(SrtProtocolError):
        parse_reservation_list_response(body)


def test_the_error_code_wrapper_is_honoured():
    with pytest.raises(SrtAppError):
        parse_reservation_list_response(
            {"ERROR_CODE": "E1", "ERROR_MSG": "nope", **_ok_envelope()}
        )


@pytest.mark.parametrize("value", ["nope", {"a": 1}, [1, 2]])
def test_a_container_that_is_not_a_list_of_objects_raises(value):
    with pytest.raises(SrtProtocolError):
        parse_reservation_list_response(_ok_envelope() | {"trainListMap": value})


@pytest.mark.parametrize("value", [1.5, "x", True, [0]])
def test_a_count_that_cannot_be_a_count_raises(value):
    with pytest.raises(SrtProtocolError):
        parse_reservation_list_response(_ok_envelope(rowCnt=value))


def test_counts_accept_both_spellings_and_absence():
    assert parse_reservation_list_response(_ok_envelope(rowCnt="7")).row_count == 7
    body = _ok_envelope()
    del body["resultMap"][0]["rowCnt"]
    del body["resultMap"][0]["totPageCnt"]
    parsed = parse_reservation_list_response(body)
    assert parsed.row_count is None and parsed.total_page_count is None


# --------------------------------------------------------------------------
# The UNVERIFIED populated shape. Every row field name below comes from srtgo
# (srt.py:1069-1082); this repository has never seen a populated response,
# because the account used for live verification has no reservations.
# --------------------------------------------------------------------------


def test_srtgo_shaped_rows_are_zipped_by_index():
    result = parse_reservation_list_response(
        _populated(
            [
                {
                    "pnrNo": FAKE_PNR,
                    "rcvdAmt": "12000",
                    "tkSpecNum": "1",
                    "seatNum": "000001",
                },
                {"pnrNo": FAKE_PNR_2, "rcvdAmt": "8000"},
            ],
            [
                {
                    "stlbTrnClsfCd": "17",
                    "trnNo": "00301",
                    "dptDt": "20260801",
                    "dptTm": "060000",
                    "dptRsStnCd": "0551",
                    "arvTm": "082500",
                    "arvRsStnCd": "0020",
                    "iseLmtDt": "20260730",
                    "iseLmtTm": "153000",
                    "stlFlg": "N",
                },
                {"trnNo": "00305"},
            ],
        )
    )

    assert result.pnr_numbers == (FAKE_PNR, FAKE_PNR_2)
    first = result.reservations[0]
    assert first.received_amount == "12000"
    assert first.ticket_special_number == "1"
    assert first.seat_number == "000001"
    assert first.service_class_code == "17"
    assert first.train_no == "00301"
    assert first.departure_date == "20260801"
    assert first.departure_time == "060000"
    assert first.departure_station_code == "0551"
    assert first.arrival_time == "082500"
    assert first.arrival_station_code == "0020"
    assert first.payment_limit_date == "20260730"
    assert first.payment_limit_time == "153000"
    assert first.settlement_flag == "N"
    # Whatever we did not model stays reachable.
    assert first.raw_train["pnrNo"] == FAKE_PNR
    assert first.raw_pay["trnNo"] == "00301"
    # A pay row with almost nothing on it does not sink the reservation.
    assert result.reservations[1].train_no == "00305"
    assert result.reservations[1].payment_limit_date is None


def test_a_shorter_pay_container_does_not_truncate_the_pnrs():
    """Asymmetric containers must not cost the tail its identity.

    srtgo zips, which silently drops every train row past the end of payListMap.
    Since the populated shape is unverified, an asymmetry is plausible, and the
    consequence of dropping it is a reservation nobody knows exists.
    """
    result = parse_reservation_list_response(
        _populated(
            [{"pnrNo": FAKE_PNR}, {"pnrNo": FAKE_PNR_2}],
            [{"trnNo": "00301"}],
        )
    )

    assert result.pnr_numbers == (FAKE_PNR, FAKE_PNR_2)
    assert result.reservations[1].raw_pay == {}


def test_a_pnr_carried_on_the_pay_row_instead_is_still_found():
    """A swapped layout is a shape surprise, not a reason to lose the PNR."""
    result = parse_reservation_list_response(
        _populated([{"rcvdAmt": "12000"}], [{"pnrNo": FAKE_PNR}])
    )
    assert result.pnr_numbers == (FAKE_PNR,)


def test_a_numeric_amount_is_read_as_text_not_dropped():
    """LIVE 2026-07-26: the real row sends the amount as a JSON number.

    The observed row was {"pnrNo": "3202607...", "rcvdAmt": 7500,
    "jrnyCnt": 1, "tkSpecNum": 1}. An earlier version dropped every non-string
    to None, which was safe while the shape was unobserved and silently cost
    the caller the amount: a card payment refused to build for want of an
    amount the reservation plainly carried.
    """
    result = parse_reservation_list_response(
        _populated([{"pnrNo": FAKE_PNR, "rcvdAmt": 7500}], [{"trnNo": None}])
    )
    assert result.pnr_numbers == (FAKE_PNR,)
    assert result.reservations[0].received_amount == "7500"
    assert result.reservations[0].train_no is None
    assert result.reservations[0].raw_train["rcvdAmt"] == 7500


def test_an_unusable_field_type_is_still_dropped_rather_than_raising():
    """One cosmetic field must still never cost every PNR.

    Numbers are now text, but a container or a bool is not an amount, and
    raising over it would lose the whole list -- the outcome this read exists
    to prevent.
    """
    result = parse_reservation_list_response(
        _populated([{"pnrNo": FAKE_PNR, "rcvdAmt": {"nested": 1}}], [{"trnNo": True}])
    )
    assert result.pnr_numbers == (FAKE_PNR,)
    assert result.reservations[0].received_amount is None
    assert result.reservations[0].train_no is None


# 12345 was here while numbers were dropped; a numeric PNR is now readable,
# which is right -- a recoverable identifier must never be thrown away. The
# invariant being pinned is unchanged: if NO pnr can be read, say so loudly
# rather than reporting an empty account.
@pytest.mark.parametrize("pnr", [None, "", "   ", {"nested": 1}, ["x"]])
def test_rows_with_no_readable_pnr_fail_loudly_instead_of_reporting_an_empty_account(
    pnr,
):
    row = {"rcvdAmt": "12000"} if pnr is None else {"pnrNo": pnr, "rcvdAmt": "12000"}
    with pytest.raises(SrtProtocolError) as exc_info:
        parse_reservation_list_response(_populated([row], [{}]))
    # The whole response rides along, so the PNR is still recoverable by hand.
    assert exc_info.value.raw["trainListMap"] == [row]


# --------------------------------------------------------------------------
# Route + client wiring
# --------------------------------------------------------------------------


def test_the_route_is_on_the_read_only_allowlist_for_post_only():
    config = SrtConfig()
    assert (
        ReadOnlyRoute("POST", "app", RESERVATION_LIST_PATH) in READ_ONLY_ROUTES
    )
    assert_read_only_request(
        httpx.Request("POST", config.base_url + RESERVATION_LIST_PATH), config
    )
    # The app's WebView loads this path as HTML with ?pageNo=0, and the live
    # server does serve that -- but no client method reads it, so the GET stays
    # off the allowlist rather than widening the boundary for nothing.
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            httpx.Request("GET", config.base_url + RESERVATION_LIST_PATH), config
        )


def _client(handler):
    return SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))


def test_client_posts_the_page_number_and_returns_parsed_rows(load_json_fixture):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == RESERVATION_LIST_PATH
        assert request.method == "POST"
        seen["form"] = dict(parse_qsl(request.content.decode()))
        seen["accept"] = request.headers.get("Accept")
        seen["referer"] = request.headers.get("Referer")
        return httpx.Response(
            200, json=load_json_fixture("reservation_list_empty.json")
        )

    result = _client(handler).get_reservations(2)

    assert seen["form"] == {"pageNo": "2"}
    assert "json" in seen["accept"]
    assert seen["referer"] == SrtConfig().base_url + "/main/main.do"
    assert result.reservations == ()
    assert result.status == "SUCC"


def test_client_treats_a_returned_login_form_as_an_expired_session():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=(
                '<form action="/apb/selectListApb01080_n.do">'
                '<input name="hmpgPwdCphd"></form>'
            ),
        )

    client = _client(handler)
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    client.http.cookies.set("JSESSIONID", "session-cookie")

    with pytest.raises(SrtSessionExpiredError):
        client.get_reservations()

    assert client.session.current is None


# --------------------------------------------------------------------------
# The int-typed row. _ZERO_PADDED_RESERVATION_COLUMNS exists because a JSON
# number arrives with its leading zeros already gone, and until now NOTHING
# forced that repair to run: every test above hands these five columns
# pre-padded string literals. The 2026-07-27 sweep proved the gap by emptying
# the table at runtime and watching the whole suite stay green -- i.e. the
# repair could have been deleted wholesale and no test would have noticed.
# That is the shape of the korail bug that made every hold unpayable while
# 2340 tests passed, so it gets pinned here from both sides.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "sent", "expected", "attribute"),
    [
        ("dptTm", 63000, "063000", "departure_time"),
        ("arvTm", 82500, "082500", "arrival_time"),
        ("iseLmtTm", 93000, "093000", "payment_limit_time"),
        ("dptRsStnCd", 551, "0551", "departure_station_code"),
        ("arvRsStnCd", 20, "0020", "arrival_station_code"),
    ],
)
def test_a_numeric_identifier_column_keeps_its_width(key, sent, expected, attribute):
    """A 06:30 departure sent as the number 63000 must read back as "063000".

    Without the repair this is "63000", five characters, and
    ``card_payment_payload``'s ``_required_digits(..., length=6)`` -- an exact
    length check, not a minimum -- refuses every departure before 10:00.
    """
    result = parse_reservation_list_response(
        _populated(
            [{"pnrNo": FAKE_PNR, "rcvdAmt": "12000"}],
            [{"stlbTrnClsfCd": "17", "trnNo": "00301", key: sent}],
        )
    )

    assert getattr(result.reservations[0], attribute) == expected


def test_a_numeric_quantity_column_is_not_padded():
    """The other half of the rule: only IDENTIFIERS get a width.

    ``rcvdAmt`` is a quantity, so 7500 is "7500" and not "007500". This is why
    the table is an explicit list rather than a blanket "pad anything numeric".
    """
    result = parse_reservation_list_response(
        _populated(
            [{"pnrNo": FAKE_PNR, "rcvdAmt": 7500}],
            [{"stlbTrnClsfCd": "17", "trnNo": "00301"}],
        )
    )

    assert result.reservations[0].received_amount == "7500"


def test_every_padded_column_is_covered_by_a_test():
    """Guard the guard: a new entry in the table needs a case above.

    The defect this file is pinning was not a wrong width, it was a repair
    nothing exercised. A column added to _ZERO_PADDED_RESERVATION_COLUMNS
    without a case in the parametrize list would reproduce exactly that, so
    the omission fails here instead of passing silently.
    """
    from srt_mobile_api import parsers

    covered = {
        case[0]
        for case in test_a_numeric_identifier_column_keeps_its_width.pytestmark[
            0
        ].args[1]
    }

    assert covered == set(parsers._ZERO_PADDED_RESERVATION_COLUMNS)
