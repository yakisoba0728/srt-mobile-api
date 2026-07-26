"""할인 승차권 검색 (Ara10131) — the request is evidenced, the reply is not.

Two kinds of test live here and they must not be confused with each other:

* tests whose expectation comes from the LIVE 조회결과 page, committed verbatim
  as ``tests/fixtures/public_discount_search_page.html``. Everything about the
  REQUEST is of this kind — the 23 field names, the nine constants, the
  camelCase ``pblDisc*`` spelling, the absence of a ``netfunnelKey`` and of any
  passenger type mix;
* tests whose payload is SYNTHETIC, because no reply to this request has ever
  been seen by anyone here. Every JSON object below is hand-built from the
  page's own success handler, and is labelled where it appears.

Nothing here is live. Running this search for real needs an approved 공공할인 and
no account on this project holds one.
"""

from __future__ import annotations

import httpx
import pytest

from srt_mobile_api import (
    PassengerCounts,
    PublicDiscountSelection,
    SrtClient,
    SrtConfig,
    SrtSession,
    TrainSearchQuery,
)
from srt_mobile_api.errors import (
    SrtNetFunnelKeyError,
    SrtNoResultsError,
    SrtProtocolError,
)
from srt_mobile_api.parsers import (
    parse_public_discount_search_response,
    parse_train_search_response,
)
from srt_mobile_api.payloads import (
    PUBLIC_DISCOUNT_SEARCH_CONSTANTS,
    public_discount_search_payload,
)
from srt_mobile_api.safety import (
    PUBLIC_DISCOUNT_SEARCH_FIELDS,
    PUBLIC_DISCOUNT_SEARCH_PATH,
    assert_read_only_request,
)


def _query(**overrides) -> TrainSearchQuery:
    fields = {
        "departure_station_code": "0551",
        "arrival_station_code": "0020",
        "departure_date": "20990101",
        "departure_time": "000000",
        "passengers": PassengerCounts(adult=1),
        "departure_station_name": "수서",
        "arrival_station_name": "부산",
    }
    fields.update(overrides)
    return TrainSearchQuery(**fields)


def _request(payload: dict[str, str]) -> httpx.Request:
    return httpx.Request(
        "POST",
        f"{SrtConfig().base_url}{PUBLIC_DISCOUNT_SEARCH_PATH}",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


# --------------------------------------------------------------------------
# the form: every expectation below is the live page's #seatSearchForm
# --------------------------------------------------------------------------


def test_the_form_is_exactly_the_pages_twenty_three_fields(load_text_fixture):
    payload = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02")
    )
    page = load_text_fixture("public_discount_search_page.html")
    # Derived from the committed page rather than restated, so the two cannot
    # drift: every name the builder emits must be a name the form declares, and
    # vice versa.
    declared = {
        name
        for name in PUBLIC_DISCOUNT_SEARCH_FIELDS
        if f'name="{name}"' in page
    }
    assert declared == PUBLIC_DISCOUNT_SEARCH_FIELDS
    assert set(payload) == PUBLIC_DISCOUNT_SEARCH_FIELDS
    assert len(payload) == 23


def test_the_nine_constants_are_the_pages_own(load_text_fixture):
    page = load_text_fixture("public_discount_search_page.html")
    for name, value in PUBLIC_DISCOUNT_SEARCH_CONSTANTS.items():
        assert f'name="{name}"' in page
        assert f'value="{value}"' in page
    payload = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02")
    )
    for name, value in PUBLIC_DISCOUNT_SEARCH_CONSTANTS.items():
        assert payload[name] == value


def test_the_discount_fields_use_the_ajax_spelling_and_omit_the_name():
    # The PAGE form carries PBL_DISC_CD / PBL_DISC_NM / PBL_DISC_MG_NO /
    # TGT_DTRM_YN; the AJAX form carries three camelCase fields and NO name.
    payload = public_discount_search_payload(
        _query(passengers=PassengerCounts(adult=3)),
        PublicDiscountSelection(code="01", management_no="APPROVAL-1"),
    )
    assert payload["pblDiscCd"] == "01"
    assert payload["pblDiscMgNo"] == "APPROVAL-1"
    assert payload["tgtDtrmYn"] == "Y"
    assert "pblDiscNm" not in payload
    assert "PBL_DISC_CD" not in payload
    assert "PBL_DISC_NM" not in payload


def test_no_netfunnel_key_travels_on_this_form():
    # Neither form on this route has the field, unlike Ara10007 where this
    # library puts the key in the body. The queue gate here is on the page
    # NAVIGATION (goSubmit's NetFunnel_Action), not on the request.
    payload = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02")
    )
    assert "netfunnelKey" not in payload


def test_no_passenger_type_mix_travels_on_this_form():
    # The head count and nothing else. The ordinary ajax carries psgTpCd1..N and
    # psgInfoPerPrnb1..N; this one has no field for either, so a 청소년 or a 유아
    # changes only the total here.
    payload = public_discount_search_payload(
        _query(passengers=PassengerCounts(adult=1, child=1, infant=1, youth=1)),
        PublicDiscountSelection(code="04"),
    )
    assert payload["psgNum"] == "4"
    assert not any(name.startswith("psgTpCd") for name in payload)
    assert not any(name.startswith("psgInfoPerPrnb") for name in payload)
    assert "infantCnt" not in payload


def test_the_management_number_defaults_to_empty():
    # It is a server-issued approval number rendered into a branch body that is
    # EMPTY for every account readable here. A caller without one can still build
    # and inspect the request.
    payload = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="03")
    )
    assert payload["pblDiscMgNo"] == ""


def test_the_first_page_cursor_is_empty_and_paging_is_a_cursor():
    first = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02")
    )
    assert first["gdNo"] == ""
    # gdNo is the ONLY thing that changes between pages: the result page re-posts
    # the otherwise identical body. dptTm, which the ordinary search bumps, does
    # not move.
    second = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02"), page_cursor="CURSOR-2"
    )
    assert second["gdNo"] == "CURSOR-2"
    assert {k: v for k, v in first.items() if k != "gdNo"} == {
        k: v for k, v in second.items() if k != "gdNo"
    }


def test_the_party_size_rule_is_the_pages_own():
    # if((pblDiscCd == "01" || pblDiscCd == "06") && totalPessnger < 3) -> rsv071
    for code in ("01", "06"):
        for total in (1, 2):
            with pytest.raises(ValueError, match=code):
                public_discount_search_payload(
                    _query(passengers=PassengerCounts(adult=total)),
                    PublicDiscountSelection(code=code),
                )
        payload = public_discount_search_payload(
            _query(passengers=PassengerCounts(adult=3)),
            PublicDiscountSelection(code=code),
        )
        assert payload["psgNum"] == "3"
    # and it applies to NO other code
    payload = public_discount_search_payload(
        _query(passengers=PassengerCounts(adult=1)),
        PublicDiscountSelection(code="02"),
    )
    assert payload["psgNum"] == "1"


@pytest.mark.parametrize("code", ["00", "09", "1", "0a", "", "01 "])
def test_an_unknown_discount_code_is_refused(code):
    with pytest.raises(ValueError):
        public_discount_search_payload(
            _query(), PublicDiscountSelection(code=code)
        )


@pytest.mark.parametrize("code", ["01", "02", "03", "04", "05", "06", "07", "08"])
def test_every_code_the_page_branches_on_is_accepted(code):
    # discounts.py NAMES six; the page's if/else chain runs 01..08. Refusing 07
    # and 08 would be deciding a discount does not exist because nobody wrote its
    # name where we can read it.
    payload = public_discount_search_payload(
        _query(passengers=PassengerCounts(adult=3)),
        PublicDiscountSelection(code=code),
    )
    assert payload["pblDiscCd"] == code


def test_the_selection_names_the_six_it_can():
    assert PublicDiscountSelection(code="01").name == "다자녀"
    assert PublicDiscountSelection(code="06").name == "3세대 동행할인"
    # 07 and 08 have branches on the page and a name nowhere.
    assert PublicDiscountSelection(code="07").name == ""


def test_the_builder_refuses_lookalike_types():
    class FakeQuery(TrainSearchQuery):
        pass

    class FakeSelection(PublicDiscountSelection):
        pass

    with pytest.raises(ValueError):
        public_discount_search_payload(
            FakeQuery(
                departure_station_code="0551",
                arrival_station_code="0020",
                departure_date="20990101",
                departure_time="000000",
                passengers=PassengerCounts(adult=1),
            ),
            PublicDiscountSelection(code="02"),
        )
    with pytest.raises(ValueError):
        public_discount_search_payload(_query(), FakeSelection(code="02"))


# --------------------------------------------------------------------------
# the route contract
# --------------------------------------------------------------------------


def test_the_built_form_satisfies_the_read_only_contract():
    payload = public_discount_search_payload(
        _query(passengers=PassengerCounts(adult=3)),
        PublicDiscountSelection(code="01", management_no="A-1"),
        page_cursor="CURSOR",
    )
    assert_read_only_request(_request(payload), SrtConfig())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("pblDiscCd"),
        lambda p: p.__setitem__("stlCrCrdNo1", "4111111111111111"),
        lambda p: p.__setitem__("pblDiscCd", "99"),
        lambda p: p.__setitem__("chtnDvCd", "2"),
        lambda p: p.__setitem__("menuId", "42"),
        lambda p: p.__setitem__("trnNo", "00315"),
        lambda p: p.__setitem__("dptDt", "2099-01-01"),
        lambda p: p.__setitem__("tgtDtrmYn", "N"),
        lambda p: p.__setitem__("pblDiscMgNo", "a" * 33),
    ],
)
def test_the_route_refuses_a_body_that_is_not_the_registered_contract(mutate):
    payload = public_discount_search_payload(
        _query(), PublicDiscountSelection(code="02")
    )
    mutate(payload)
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(_request(payload), SrtConfig())


def test_the_route_refuses_a_GET():
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(
            httpx.Request(
                "GET",
                f"{SrtConfig().base_url}{PUBLIC_DISCOUNT_SEARCH_PATH}?type=",
            ),
            SrtConfig(),
        )


# --------------------------------------------------------------------------
# the reply: every payload below is SYNTHETIC (see the module docstring)
# --------------------------------------------------------------------------


def _synthetic_reply(**overrides) -> dict:
    """A reply shaped the way the page's success handler reads one.

    SYNTHETIC. Nobody here has seen a real one.
    """
    reply = {
        "resultMap": [{"strResult": "SUCC", "msgCd": "IRG000000", "msgTxt": ""}],
        "trainListMap": [
            {
                "trnNo": "00315",
                "trnGpCd": "300",
                "stlbTrnClsfCd": "17",
                "dptDt": "20990101",
                "dptTm": "060000",
                "arvTm": "083000",
                "dptRsStnCd": "0551",
                "arvRsStnCd": "0020",
                "runTm": "0230",
                "gnrmRsvPsbCd": "11",
                "sprmRsvPsbCd": "-1",
                "gnrmBkclDcntRt": "30",
                "sprmBkclDcntRt": "0",
                "fllwPgExt": "N",
            }
        ],
        "dsCmdMap": {"gdNo": "CURSOR-2"},
    }
    reply.update(overrides)
    return reply


def test_the_rows_go_through_the_ordinary_row_parser():
    result = parse_public_discount_search_response(_synthetic_reply())
    train = result.trains[0]
    assert train.train_no == "00315"
    assert train.train_group_code == "300"
    assert train.departure_station_code == "0551"
    assert train.run_time == "0230"


def test_the_two_discount_columns_are_carried():
    # These are the point of this search: 0-hit in the v2.0.41 bundle and absent
    # from every ordinary-search row captured here.
    train = parse_public_discount_search_response(_synthetic_reply()).trains[0]
    assert train.general_class_discount_rate == "30"
    assert train.special_class_discount_rate == "0"


def test_an_ordinary_search_row_leaves_both_rates_unset():
    # The same TrainSummary fields, appended and defaulted, so the ordinary
    # search is unchanged by their existence.
    result = parse_train_search_response(
        {
            "ErrorCode": "",
            "ErrorMsg": "",
            "outDataSets": {
                "dsOutput0": [
                    {
                        "strResult": "SUCC",
                        "msgCd": "IRG000000",
                        "qryCnt": "1",
                        "qryCnqeCnt": "1",
                    }
                ],
                "dsOutput1": [{"trnNo": "00315"}],
            },
        }
    )
    assert result.trains[0].general_class_discount_rate is None
    assert result.trains[0].special_class_discount_rate is None


def test_the_paging_cursor_and_flag_stay_reachable_without_being_normalised():
    # fllwPgExt rides the FIRST ROW here, not the metadata row, and gdNo is the
    # cursor. Neither is mapped into TrainSearchMetadata, because asserting they
    # mean the same as their dsOutput0 namesakes would be a guess.
    result = parse_public_discount_search_response(_synthetic_reply())
    assert result.metadata is None
    assert result.raw["dsCmdMap"]["gdNo"] == "CURSOR-2"
    assert result.raw["trainListMap"][0]["fllwPgExt"] == "N"


def test_a_FAIL_is_classified_like_the_ordinary_search():
    with pytest.raises(SrtNoResultsError):
        parse_public_discount_search_response(
            _synthetic_reply(
                resultMap=[
                    {
                        "strResult": "FAIL",
                        "msgCd": "WRG000000",
                        "msgTxt": "조회 결과가 없습니다.",
                    }
                ]
            )
        )


def test_a_stale_netfunnel_key_is_signalled_for_the_retry():
    with pytest.raises(SrtNetFunnelKeyError):
        parse_public_discount_search_response(
            _synthetic_reply(
                resultMap=[{"strResult": "FAIL", "msgCd": "NET000001", "msgTxt": ""}]
            )
        )


def test_msgCd_is_optional_because_the_page_never_reads_it():
    result = parse_public_discount_search_response(
        _synthetic_reply(resultMap=[{"strResult": "SUCC"}])
    )
    assert result.trains[0].train_no == "00315"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"trainListMap": []},
        {"resultMap": [], "trainListMap": []},
        {"resultMap": [{"strResult": "SUCC"}]},
        {"resultMap": [{"strResult": "SUCC"}], "trainListMap": {}},
        {"resultMap": [{}], "trainListMap": []},
        {"resultMap": [{"strResult": "SUCC"}], "trainListMap": ["not a row"]},
    ],
)
def test_a_reply_that_is_not_this_shape_is_refused(payload):
    with pytest.raises(SrtProtocolError):
        parse_public_discount_search_response(payload)


def test_the_ordinary_search_container_is_not_silently_accepted():
    # The two routes answer in different containers, and this parser must not
    # quietly read the other one -- that would be asserting a correspondence
    # nobody has seen.
    with pytest.raises(SrtProtocolError):
        parse_public_discount_search_response(
            {
                "ErrorCode": "",
                "ErrorMsg": "",
                "outDataSets": {
                    "dsOutput0": [{"strResult": "SUCC", "msgCd": "IRG000000"}],
                    "dsOutput1": [{"trnNo": "00315"}],
                },
            }
        )


# --------------------------------------------------------------------------
# the client method
# --------------------------------------------------------------------------


def _client(handler) -> SrtClient:
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="member", user_map={"RTNCD": "Y"})
    return client


NETFUNNEL_KEY = "0123456789ABCDEF"


def _netfunnel_response(request: httpx.Request) -> httpx.Response:
    opcode = request.url.params.get("opcode")
    if opcode == "5101":
        body = (
            "NetFunnel.gRtype=5101;NetFunnel.gControl.result="
            f"'5101:200:key={NETFUNNEL_KEY}&nwait=0&nnext=0';"
        )
    else:
        body = (
            "NetFunnel.gRtype=5004;NetFunnel.gControl.result="
            "'5004:200:key=" + NETFUNNEL_KEY + "';"
        )
    return httpx.Response(200, text=body)


def test_the_client_posts_once_and_takes_and_releases_a_queue_slot():
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.host != "app.srail.or.kr":
            return _netfunnel_response(request)
        assert request.url.path == PUBLIC_DISCOUNT_SEARCH_PATH
        return httpx.Response(200, json=_synthetic_reply())

    client = _client(handler)
    result = client.search_public_discount_trains(
        _query(), PublicDiscountSelection(code="02", management_no="A-1")
    )
    assert result.trains[0].train_no == "00315"
    # act_10 acquire, the search, act_10 release. The app waits behind
    # NetFunnel_Action for this flow and the result page calls
    # NetFunnel_Complete; no key goes on the form.
    assert calls == [
        ("GET", "/ts.wseq"),
        ("POST", PUBLIC_DISCOUNT_SEARCH_PATH),
        ("GET", "/ts.wseq"),
    ]


def test_the_client_never_issues_the_page_navigation_GET():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host != "app.srail.or.kr":
            return _netfunnel_response(request)
        return httpx.Response(200, json=_synthetic_reply())

    client = _client(handler)
    client.search_public_discount_trains(_query(), PublicDiscountSelection(code="02"))
    app_calls = [r for r in seen if r.url.host == "app.srail.or.kr"]
    assert [r.method for r in app_calls] == ["POST"]
    assert all(request.url.query == b"" for request in app_calls)


def test_a_refused_party_size_costs_no_request_at_all():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError(f"must not send (saw {request.method} {request.url})")

    client = _client(handler)
    with pytest.raises(ValueError):
        client.search_public_discount_trains(
            _query(passengers=PassengerCounts(adult=1)),
            PublicDiscountSelection(code="01"),
        )


def test_the_body_the_client_sends_is_the_registered_contract():
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != "app.srail.or.kr":
            return _netfunnel_response(request)
        bodies.append(request.content)
        return httpx.Response(200, json=_synthetic_reply())

    client = _client(handler)
    client.search_public_discount_trains(
        _query(), PublicDiscountSelection(code="05", management_no="A-1")
    )
    from urllib.parse import parse_qsl

    sent = dict(parse_qsl(bodies[0].decode(), keep_blank_values=True))
    assert set(sent) == PUBLIC_DISCOUNT_SEARCH_FIELDS
    assert sent["pblDiscCd"] == "05"
    assert sent["pblDiscMgNo"] == "A-1"
