"""Offline contract tests for 환승 (transfer) search and reservation.

Transfer is the one reservation shape SRT models as a single request carrying
TWO 여정 (journey) slots. Everything asserted here about the REQUEST comes from
our own v2.0.41 bundle; srtgo has no transfer support at all, so it is not even
a cross-check this time.

The three claims this file exists to pin, in order of how easy they are to get
wrong:

* ``jrnyCnt="2"`` means TRANSFER. It has exactly one write in the whole bundle,
  the 환승 toggle, which sets it together with ``jrnyTpCd="14"``
  (``ara0101v.js:302-303``). A round trip never raises it.
* The ``...2`` suffix on JOURNEY fields is the 후행 leg
  (``//여정일련번호1(001:선행, 002:후행)``, ``ara0101v.js:97``). The ``...2``
  suffix on PASSENGER fields is a passenger TYPE index (``psgTpCd2``,
  ``psgInfoPerPrnb2``, ``ara0101v.js:118-121``). Both families live in this one
  form and they are not the same thing.
* A transfer search row is HALF an itinerary and looks exactly like a reservable
  train. ``TransferItinerary`` is what makes half of one unrepresentable.

What is NOT pinned, because the bundle does not say it: how the search JSON
pairs the two legs. The 환승 result list is server-rendered (the stylesheet keeps
a ``.timeDiff`` rule for it, ``custom.css:4431``) and ``fn_postSearch`` has no
transfer branch, so no test here asserts a response shape for a transfer search.

No network: every send goes through ``httpx.MockTransport``.
"""

from __future__ import annotations

import dataclasses
import inspect

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    MutationPreview,
    PassengerCounts,
    SeatType,
    SrtClient,
    SrtConfig,
    SrtMutationNotAllowedError,
    SrtReservationHold,
    SrtSession,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
    TransferItinerary,
    TransferSearchResult,
)
from srt_mobile_api.errors import (
    NO_DIRECT_TRAIN_CODE,
    SrtAppError,
    SrtAuthError,
    SrtNoDirectTrainError,
    SrtNoResultsError,
    SrtProtocolError,
    classify_app_error,
)
from srt_mobile_api.parsers import (
    TRANSFER_ITINERARY_COLUMN,
    TRANSFER_LEGS_PER_ITINERARY,
    pair_transfer_itineraries,
    parse_train_search_response,
)
from srt_mobile_api.payloads import (
    JOURNEY_COUNT_ONE_WAY,
    JOURNEY_COUNT_TRANSFER,
    JOURNEY_SEQUENCE_FOLLOWING,
    JOURNEY_SEQUENCE_LEADING,
    JOURNEY_TYPE_ONE_WAY,
    JOURNEY_TYPE_TRANSFER,
    RESERVE_PERSONAL_JOBID,
    SEARCH_CONNECTION_DIRECT,
    SEARCH_CONNECTION_TRANSFER,
    TRANSFER_SLOT2_FIELD_EVIDENCE,
    personal_reservation_payload,
    search_ajax_payload,
    search_page_payload,
    transfer_reservation_payload,
)
from srt_mobile_api.safety import (
    SRT_LIVE_MUTATION_CATEGORIES,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
)

RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
SEARCH_ROUTE = "/ara/selectListAra10007_n.do"
GROUP_SEARCH_ROUTE = "/ara/selectListAra10082_n.do"
NETFUNNEL_PATH = "/ts.wseq"

SYNTHETIC_NF = "SYNTHETIC_NETFUNNEL_KEY"
ACQUIRED_NF = "ACQUIRED_NETFUNNEL_KEY"
NETFUNNEL_BODY = (
    "NetFunnel.gRtype=5101;"
    f"NetFunnel.gControl.result='5101:200:key={ACQUIRED_NF}&nwait=0&nnext=0';"
)

# 동대구 -> 오송 -> 광주송정. SRT runs 경부선 through 동대구 and 호남선 through
# 광주송정, and the two lines only meet at 오송, so this pair has no direct SRT
# service and is exactly the shape that makes a transfer itinerary exist.
DONGDAEGU = "0015"
OSONG = "0297"
GWANGJU_SONGJEONG = "0036"


def _first_leg() -> TrainSummary:
    """동대구 -> 오송, the 선행 leg."""
    return TrainSummary(
        train_no="352",
        service_class_code="17",
        train_group_code="300",
        departure_station_code=DONGDAEGU,
        arrival_station_code=OSONG,
        departure_station_name="동대구",
        arrival_station_name="오송",
        run_date="20990101",
        departure_date="20990101",
        departure_time="090000",
        arrival_date="20990101",
        arrival_time="094500",
        departure_run_order="6",
        arrival_run_order="9",
        departure_consist_order="6",
        arrival_consist_order="9",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )


def _second_leg() -> TrainSummary:
    """오송 -> 광주송정, the 후행 leg, departing after the first one lands."""
    return TrainSummary(
        train_no="661",
        service_class_code="17",
        train_group_code="300",
        departure_station_code=OSONG,
        arrival_station_code=GWANGJU_SONGJEONG,
        departure_station_name="오송",
        arrival_station_name="광주송정",
        run_date="20990101",
        departure_date="20990101",
        departure_time="101500",
        arrival_date="20990101",
        arrival_time="113000",
        departure_run_order="5",
        arrival_run_order="11",
        departure_consist_order="5",
        arrival_consist_order="11",
        general_seat_availability="예약가능",
        special_seat_availability="예약가능",
    )


def _itinerary(**kwargs) -> TransferItinerary:
    return TransferItinerary(
        first_leg=kwargs.pop("first_leg", _first_leg()),
        second_leg=kwargs.pop("second_leg", _second_leg()),
        **kwargs,
    )


def _direct_train() -> TrainSummary:
    """The reservable single-leg train the existing reserve pins use."""
    return TrainSummary(
        train_no="303",
        service_class_code="17",
        train_group_code="300",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="060000",
        arrival_time="083000",
        departure_station_name="수서",
        arrival_station_name="부산",
        departure_run_order="1",
        arrival_run_order="10",
        departure_consist_order="1",
        arrival_consist_order="2",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )


def _one_leg_form(**kwargs) -> dict[str, str]:
    return personal_reservation_payload(
        _direct_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        **kwargs,
    )


def _transfer_form(**kwargs) -> dict[str, str]:
    return transfer_reservation_payload(
        kwargs.pop("itinerary", _itinerary()),
        kwargs.pop("passengers", PassengerCounts(adult=1)),
        netfunnel_key=SYNTHETIC_NF,
        **kwargs,
    )


def _delta(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    """The exact wire delta: which keys were added, changed and omitted."""
    return {
        "added": {key: after[key] for key in after.keys() - before.keys()},
        "removed": {key: before[key] for key in before.keys() - after.keys()},
        "changed": {
            key: (before[key], after[key])
            for key in before.keys() & after.keys()
            if before[key] != after[key]
        },
    }


def _query() -> TrainSearchQuery:
    return TrainSearchQuery(
        departure_station_code=DONGDAEGU,
        arrival_station_code=GWANGJU_SONGJEONG,
        departure_date="20990101",
        departure_time="080000",
        departure_station_name="동대구",
        arrival_station_name="광주송정",
    )


class _Recorder:
    """Answers the act_10 GET and the reservation POST; records everything."""

    def __init__(self, reply: dict) -> None:
        self.reply = reply
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == NETFUNNEL_PATH:
            if request.url.params["opcode"] == "5004":
                return httpx.Response(
                    200, text="NetFunnel.gControl.result='5004:200:utime=1';"
                )
            return httpx.Response(200, text=NETFUNNEL_BODY)
        if request.url.path == RESERVE_ROUTE:
            return httpx.Response(200, json=self.reply)
        # Any other path -- notably the removed 단체 endpoint arc06014 -- is a
        # failure here, not a recorded request.
        raise AssertionError(f"unexpected request to {request.url.path}")

    @property
    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def forms(self, route: str) -> list[dict[str, str]]:
        return [
            dict(httpx.QueryParams(request.content.decode()))
            for request in self.requests
            if request.url.path == route
        ]


def _client(reply: dict) -> tuple[SrtClient, _Recorder]:
    recorder = _Recorder(reply)
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(recorder))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, recorder


def _live(**allow: bool) -> MutationConsent:
    return MutationConsent(dry_run=False, **allow)


# --- the single-journey form is untouched ------------------------------------


def test_a_one_leg_reservation_is_unchanged_including_key_order():
    # The load-bearing compatibility claim of this whole change. Nothing about
    # transfer may reach the form a caller already sends: same keys, same
    # values, same ORDER (the arvDt1 position pins depend on order).
    baseline_keys = [
        "jobId",
        "jrnyCnt",
        "jrnyTpCd",
        "jrnySqno1",
        "stndFlg",
        "trnGpCd1",
        "trnGpCd",
        "grpDv",
        "rtnDv",
        "stlbTrnClsfCd1",
        "dptRsStnCd1",
        "dptRsStnCdNm1",
        "arvRsStnCd1",
        "arvRsStnCdNm1",
        "dptDt1",
        "dptTm1",
        "arvDt1",
        "arvTm1",
        "trnNo1",
        "runDt1",
        "dptStnConsOrdr1",
        "arvStnConsOrdr1",
        "dptStnRunOrdr1",
        "arvStnRunOrdr1",
        "netfunnelKey",
        "reserveType",
        "totPrnb",
        "psgGridcnt",
        "locSeatAttCd1",
        "rqSeatAttCd1",
        "dirSeatAttCd1",
        "smkSeatAttCd1",
        "etcSeatAttCd1",
        "psrmClCd1",
        "psgTpCd1",
        "psgInfoPerPrnb1",
    ]
    form = _one_leg_form()
    assert list(form) == baseline_keys
    assert form["jrnyCnt"] == JOURNEY_COUNT_ONE_WAY == "1"
    assert form["jrnyTpCd"] == JOURNEY_TYPE_ONE_WAY == "11"
    assert form["jrnySqno1"] == JOURNEY_SEQUENCE_LEADING == "001"
    # And no journey slot 2 exists on it at all.
    assert not [key for key in form if key.endswith("2")]


def test_the_one_leg_search_payloads_are_byte_for_byte_unchanged():
    # transfer= is keyword-only and defaults to False on both search builders.
    query = _query()
    hydrated = {"serverNonce": "synthetic"}
    assert search_page_payload(query, SYNTHETIC_NF) == search_page_payload(
        query, SYNTHETIC_NF, transfer=False
    )
    assert list(search_page_payload(query, SYNTHETIC_NF)) == list(
        search_page_payload(query, SYNTHETIC_NF, transfer=False)
    )
    direct = search_ajax_payload(query, SYNTHETIC_NF, hydrated_fields=hydrated)
    explicit = search_ajax_payload(
        query, SYNTHETIC_NF, hydrated_fields=hydrated, transfer=False
    )
    assert direct == explicit and list(direct) == list(explicit)
    assert direct["chtnDvCd"] == SEARCH_CONNECTION_DIRECT == "1"


def test_every_new_parameter_is_keyword_only_and_defaulted():
    for function, name in (
        (search_page_payload, "transfer"),
        (search_ajax_payload, "transfer"),
    ):
        parameter = inspect.signature(function).parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False
    for method in (SrtClient.search_trains, SrtClient.search_group_trains):
        assert list(inspect.signature(method).parameters) == ["self", "query"]


# --- the search delta ---------------------------------------------------------


def test_transfer_search_changes_only_the_connection_code():
    # ara1001l.js:98 derives it -- `jrnyTpCd == "11" ? "1" : "2" //직통:1, 환승:2`
    # -- and :159 sends it. Nothing else in the body moves.
    query = _query()
    hydrated = {"serverNonce": "synthetic"}
    before = search_ajax_payload(query, SYNTHETIC_NF, hydrated_fields=hydrated)
    after = search_ajax_payload(
        query, SYNTHETIC_NF, hydrated_fields=hydrated, transfer=True
    )
    assert _delta(before, after) == {
        "added": {},
        "removed": {},
        "changed": {"chtnDvCd": ("1", "2")},
    }
    assert after["chtnDvCd"] == SEARCH_CONNECTION_TRANSFER == "2"


def test_transfer_hydration_changes_only_the_journey_type_and_count():
    # The 환승 toggle is one lfn_setRsv call with exactly two members
    # (ara0101v.js:310-311). It does NOT touch jrnySqno2, so neither do we.
    query = _query()
    before = search_page_payload(query, SYNTHETIC_NF)
    after = search_page_payload(query, SYNTHETIC_NF, transfer=True)
    assert _delta(before, after) == {
        "added": {},
        "removed": {},
        "changed": {"jrnyTpCd": ("11", "14"), "jrnyCnt": ("1", "2")},
    }
    assert after["jrnySqno2"] == ""


def test_transfer_search_uses_the_same_endpoint_as_the_direct_search():
    # ara1001l.js:174-181 picks the URL from grpDv ALONE. The connection type
    # travels in chtnDvCd, not in the path.
    hydration = httpx.Response(
        200,
        text=(
            '<html><body><form id="seatSearchForm">'
            '<input type="hidden" name="serverNonce" value="synthetic" />'
            "</form>"
            '<a href="/kr/logout.do">logout</a></body></html>'
        ),
    )
    seen: list[tuple[str, str]] = []
    bodies: list[dict[str, str]] = []
    hydration_queries: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == NETFUNNEL_PATH:
            if request.url.params["opcode"] == "5004":
                return httpx.Response(
                    200, text="NetFunnel.gControl.result='5004:200:utime=1';"
                )
            return httpx.Response(200, text=NETFUNNEL_BODY)
        seen.append((request.method, request.url.path))
        if request.method == "GET":
            hydration_queries.append(dict(request.url.params))
            return httpx.Response(200, text=hydration.text)
        bodies.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(
            200,
            json={
                "ErrorCode": "0",
                "ErrorMsg": "",
                "outDataSets": {
                    "dsOutput0": [
                        {
                            "msgCd": "IRG000000",
                            "strResult": "SUCC",
                            "msgTxt": "",
                            "qryCnqeCnt": 0,
                            "fllwPgExt": "N",
                            "fllwPgExt2": None,
                        }
                    ],
                    "dsOutput1": [],
                },
            },
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    result = client.search_transfer_trains(_query())

    # An empty response is not a pairing failure: no rows, no itineraries, no
    # complaint.
    assert isinstance(result, TransferSearchResult)
    assert result.itineraries == () and result.unpaired == ()
    assert seen == [("GET", SEARCH_ROUTE), ("POST", SEARCH_ROUTE)]
    assert GROUP_SEARCH_ROUTE not in [path for _, path in seen]
    # The hydration GET carries the 환승 toggle...
    assert hydration_queries[0]["jrnyTpCd"] == "14"
    assert hydration_queries[0]["jrnyCnt"] == "2"
    # ...and the search POST carries the connection code.
    assert bodies[0]["chtnDvCd"] == "2"


def test_transfer_search_is_not_paginated():
    # dsOutput0 carries a SECOND cursor, fllwPgExt2. The 2026-07-26 live transfer
    # probe returned it null, exactly as every direct search does, so what it is
    # FOR is still unobserved and nothing in the bundle reads it. Paging a
    # two-cursor list on a guess would walk the wrong leg.
    parameters = inspect.signature(SrtClient.iter_train_search_pages).parameters
    assert list(parameters) == ["self", "query", "group", "max_pages"]
    assert "transfer" not in parameters


# --- the itinerary refuses to be half of one ---------------------------------


def test_a_transfer_reservation_cannot_be_given_a_single_train():
    # The whole point of the type. A transfer search row is an ordinary
    # TrainSummary that reserve() would book on its own; reserve_transfer must
    # not accept one.
    with pytest.raises(ValueError, match="TransferItinerary"):
        transfer_reservation_payload(
            _first_leg(),  # type: ignore[arg-type]
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
        )


def test_the_app_s_own_both_legs_message_is_what_the_refusal_says():
    # messages.js:217 (rsv023), shipped and never referenced because the screen
    # that would raise it is server-rendered.
    with pytest.raises(ValueError) as excinfo:
        transfer_reservation_payload(
            _first_leg(),  # type: ignore[arg-type]
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
        )
    assert "선행 및 후행 열차를 모두 선택하셔야" in str(excinfo.value)


def test_legs_that_do_not_connect_are_refused():
    # The first leg must ARRIVE where the second DEPARTS. That station is the
    # 환승역, and getting it wrong is silent otherwise: it builds a perfectly
    # plausible form.
    stranded = dataclasses.replace(
        _second_leg(),
        departure_station_code="0010",  # 대전, not 오송
        departure_station_name="대전",
    )
    with pytest.raises(ValueError, match="do not connect"):
        TransferItinerary(first_leg=_first_leg(), second_leg=stranded)


def test_a_second_leg_that_departs_before_the_first_arrives_is_refused():
    # The app applies exactly this comparison to the 왕복 second leg
    # (ara1001l.js:1258-1272); a transfer needs it at least as much.
    too_early = dataclasses.replace(
        _second_leg(), departure_time="090500", arrival_time="102000"
    )
    with pytest.raises(ValueError, match="departs before"):
        TransferItinerary(first_leg=_first_leg(), second_leg=too_early)


def test_a_same_day_connection_at_the_exact_arrival_minute_is_allowed():
    # Not a realistic connection, but "arrives 09:45, departs 09:45" is not
    # backwards, and the validator must refuse only what actually runs backwards.
    tight = dataclasses.replace(_second_leg(), departure_time="094500")
    itinerary = TransferItinerary(first_leg=_first_leg(), second_leg=tight)
    assert itinerary.transfer_station_code == OSONG


def test_an_overnight_connection_is_allowed():
    late = dataclasses.replace(
        _second_leg(),
        departure_date="20990102",
        departure_time="060000",
        arrival_date="20990102",
        arrival_time="072000",
        run_date="20990102",
    )
    itinerary = TransferItinerary(first_leg=_first_leg(), second_leg=late)
    assert itinerary.destination_station_code == GWANGJU_SONGJEONG


def test_a_leg_with_no_arrival_time_is_not_treated_as_invalid():
    # Absence is "cannot tell", never "invalid" -- the same rule the standby row
    # image guard and arvDt1 follow. A hand-built row may simply omit it.
    partial = dataclasses.replace(_first_leg(), arrival_time=None, arrival_date=None)
    itinerary = TransferItinerary(first_leg=partial, second_leg=_second_leg())
    assert itinerary.legs == (partial, _second_leg())


def test_the_same_train_twice_is_not_an_itinerary():
    leg = _first_leg()
    doubled = dataclasses.replace(
        leg, departure_station_code=OSONG, arrival_station_code=OSONG
    )
    with pytest.raises(ValueError, match="two different trains"):
        TransferItinerary(first_leg=doubled, second_leg=doubled)


def test_a_leg_missing_its_connecting_station_is_refused():
    nowhere = dataclasses.replace(_first_leg(), arrival_station_code=None)
    with pytest.raises(ValueError, match="legs connect"):
        TransferItinerary(first_leg=nowhere, second_leg=_second_leg())


def test_both_legs_must_be_exact_train_summaries():
    class Sneaky(TrainSummary):
        pass

    subclassed = Sneaky(
        train_no="661",
        service_class_code="17",
        departure_station_code=OSONG,
        arrival_station_code=GWANGJU_SONGJEONG,
    )
    with pytest.raises(ValueError, match="exact TrainSummary"):
        TransferItinerary(first_leg=_first_leg(), second_leg=subclassed)


def test_the_itinerary_names_the_whole_journey():
    itinerary = _itinerary()
    assert itinerary.origin_station_code == DONGDAEGU
    assert itinerary.transfer_station_code == OSONG
    assert itinerary.destination_station_code == GWANGJU_SONGJEONG
    assert itinerary.legs == (itinerary.first_leg, itinerary.second_leg)


# --- the reservation wire -----------------------------------------------------


def test_the_journey_count_and_type_follow_the_itinerary_shape():
    # ara0101v.js:302-303: sJrnyTp="14" and nJrnyCnt="2" are set in the same
    # branch and emitted together at :310-311. This is the ONLY write of
    # jrnyCnt="2" in the bundle.
    one_leg = _one_leg_form()
    two_legs = _transfer_form()

    assert (one_leg["jrnyTpCd"], one_leg["jrnyCnt"]) == ("11", "1")
    assert (two_legs["jrnyTpCd"], two_legs["jrnyCnt"]) == ("14", "2")
    assert two_legs["jrnyTpCd"] == JOURNEY_TYPE_TRANSFER
    assert two_legs["jrnyCnt"] == JOURNEY_COUNT_TRANSFER
    # 여정일련번호: 001 선행, 002 후행 (ara0101v.js:97).
    assert two_legs["jrnySqno1"] == JOURNEY_SEQUENCE_LEADING == "001"
    assert two_legs["jrnySqno2"] == JOURNEY_SEQUENCE_FOLLOWING == "002"
    # Still a 개인예약 on the personal route: 환승 is a journey shape, not a job
    # type (ara1001l.js:1434-1449 never consults jrnyTpCd).
    assert two_legs["jobId"] == RESERVE_PERSONAL_JOBID == "1101"
    assert two_legs["grpDv"] == "0"


def test_the_exact_wire_keys_the_second_journey_slot_adds():
    # The WHOLE delta of a transfer, in one comparison. A slot-2 key that
    # appeared or vanished later would fail here even if the ones below are
    # right, and slot 1 must be untouched apart from the two toggle fields.
    # Baselined on the SAME first leg, so the delta is purely "what does adding
    # a second journey slot do" and not "what does changing the train do".
    one_leg = personal_reservation_payload(
        _first_leg(), PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )
    two_legs = _transfer_form()
    delta = _delta(one_leg, two_legs)

    assert delta["removed"] == {}
    assert set(delta["added"]) == {
        "jrnySqno2",
        "stlbTrnClsfCd2",
        "dptRsStnCd2",
        "dptRsStnCdNm2",
        "arvRsStnCd2",
        "arvRsStnCdNm2",
        "dptDt2",
        "dptTm2",
        "arvDt2",
        "arvTm2",
        "trnNo2",
        "runDt2",
        "dptStnConsOrdr2",
        "arvStnConsOrdr2",
        "dptStnRunOrdr2",
        "arvStnRunOrdr2",
        "trnGpCd2",
        "psrmClCd2",
        "locSeatAttCd2",
        "rqSeatAttCd2",
        "dirSeatAttCd2",
        "smkSeatAttCd2",
        "etcSeatAttCd2",
    }
    # Slot 1 moves ONLY where the 환승 toggle moves it -- the two fields
    # ara0101v.js:310-311 emits, and nothing else.
    assert delta["changed"] == {"jrnyTpCd": ("11", "14"), "jrnyCnt": ("1", "2")}
    # Stated the other way round: every key slot 1 had, it still has, verbatim.
    assert all(
        two_legs[key] == value
        for key, value in one_leg.items()
        if key not in {"jrnyTpCd", "jrnyCnt"}
    )
    assert list(two_legs)[: len(one_leg)] == list(one_leg)


def test_the_second_slot_carries_the_second_leg_and_the_first_slot_the_first():
    # The failure this catches is legs swapped or duplicated: a form where both
    # slots describe the same train would still look well-formed.
    form = _transfer_form()

    assert form["dptRsStnCd1"] == DONGDAEGU
    assert form["arvRsStnCd1"] == OSONG
    assert form["trnNo1"] == "00352"
    assert form["dptTm1"] == "090000"
    assert form["arvTm1"] == "094500"

    assert form["dptRsStnCd2"] == OSONG
    assert form["arvRsStnCd2"] == GWANGJU_SONGJEONG
    assert form["trnNo2"] == "00661"
    assert form["dptTm2"] == "101500"
    assert form["arvTm2"] == "113000"
    # 5-digit zero padding on BOTH legs, the same rule slot 1 has always had.
    assert form["trnNo1"] != form["trnNo2"]
    assert form["dptRsStnCdNm2"] == "오송"
    assert form["arvRsStnCdNm2"] == "광주송정"


def test_the_second_slot_keys_come_after_the_first_slot_keys():
    # Order matters here for the same reason it does for arvDt1: slot 1's key
    # order is what the one-leg pins assert, so slot 2 is appended and never
    # interleaved.
    form = _transfer_form()
    slot_two = [key for key in form if key in TRANSFER_SLOT2_FIELD_EVIDENCE]
    first_slot_two = list(form).index(slot_two[0])
    assert set(slot_two) == set(TRANSFER_SLOT2_FIELD_EVIDENCE)
    assert all(
        not key.endswith("2") or key in TRANSFER_SLOT2_FIELD_EVIDENCE
        for key in list(form)[first_slot_two:]
    )
    assert list(form)[:first_slot_two] == list(_one_leg_form())[:first_slot_two]


def test_every_slot_two_key_declares_how_it_is_known():
    # The evidence map is not decoration: five of these key NAMES are inferred
    # from slot 1 because the server-rendered #rsvForm is not in the bundle, and
    # nothing may quietly graduate to a stronger tier without a capture.
    assert set(TRANSFER_SLOT2_FIELD_EVIDENCE.values()) <= {
        "web",
        "native",
        "hydrated",
        "inferred",
    }
    inferred = {
        key
        for key, tier in TRANSFER_SLOT2_FIELD_EVIDENCE.items()
        if tier == "inferred"
    }
    assert inferred == {
        "stlbTrnClsfCd2",
        "dptStnConsOrdr2",
        "arvStnConsOrdr2",
        "dptStnRunOrdr2",
        "arvStnRunOrdr2",
    }
    # And the map describes the form that is actually built -- no key in the map
    # that the builder omits, and no slot-2 key the builder emits that the map
    # does not account for.
    form = _transfer_form()
    assert set(TRANSFER_SLOT2_FIELD_EVIDENCE) == {
        key for key in form if key.endswith("2") and not key.startswith("psg")
    }


def test_passengers_are_not_duplicated_across_the_legs():
    # psgTpCd2 / psgInfoPerPrnb2 are the PASSENGER-TYPE family (ara0101v.js:
    # 118-121), not journey slot 2. Two adults and a child fill three type
    # slots on one party that rides both legs.
    form = _transfer_form(passengers=PassengerCounts(adult=2, child=1))
    assert form["totPrnb"] == "3"
    assert form["psgGridcnt"] == "2"
    assert form["psgTpCd1"] == "1" and form["psgInfoPerPrnb1"] == "2"
    assert form["psgTpCd2"] == "5" and form["psgInfoPerPrnb2"] == "1"
    # ... and there is no second copy of the party for the second leg.
    assert "totPrnb2" not in form
    assert "psgGridcnt2" not in form


def test_one_seat_preference_covers_both_legs():
    # ara0101v.js:769-778: the 좌석옵션 callback writes rqSeatAttCd1/locSeatAttCd1/
    # dirSeatAttCd1 and then the identical ...2 quartet from the same values.
    form = _transfer_form(window_seat=True)
    assert form["locSeatAttCd1"] == form["locSeatAttCd2"] == "012"
    assert form["rqSeatAttCd1"] == form["rqSeatAttCd2"] == "015"
    assert form["dirSeatAttCd1"] == form["dirSeatAttCd2"] == "009"
    assert form["smkSeatAttCd1"] == form["smkSeatAttCd2"] == "000"
    assert form["etcSeatAttCd1"] == form["etcSeatAttCd2"] == "000"
    aisle = _transfer_form(window_seat=False)
    assert aisle["locSeatAttCd1"] == aisle["locSeatAttCd2"] == "013"


@pytest.mark.parametrize("seat_type", list(SeatType))
def test_both_legs_get_the_cabin_the_first_leg_resolved_to(seat_type):
    # Not the raw seat_type: a *_FIRST preference falls back on availability,
    # and once slot 1 has fallen back, slot 2 must agree or the reservation is
    # asking for two different cabins on one ticket.
    form = _transfer_form(seat_type=seat_type)
    assert form["psrmClCd1"] == form["psrmClCd2"]
    assert form["psrmClCd1"] in {"1", "2"}


def test_a_non_srt_second_leg_is_refused():
    # personal_reservation_payload refuses a non-SRT train for slot 1; the same
    # guard has to cover slot 2, or a transfer would be the way around it.
    ktx = dataclasses.replace(_second_leg(), service_class_code="00")
    with pytest.raises(ValueError, match="SRT train"):
        transfer_reservation_payload(
            TransferItinerary(first_leg=_first_leg(), second_leg=ktx),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
        )


def test_a_non_srt_first_leg_is_still_refused():
    ktx = dataclasses.replace(_first_leg(), service_class_code="00")
    with pytest.raises(ValueError, match="SRT train"):
        transfer_reservation_payload(
            TransferItinerary(first_leg=ktx, second_leg=_second_leg()),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
        )


def test_the_second_leg_falls_back_to_its_departure_date_for_the_run_date():
    # Same rule slot 1 has: runDt is a distinct row field (ara1001l.js:1460 vs
    # :1462) and only falls back when the row omits it.
    without = dataclasses.replace(_second_leg(), run_date=None)
    form = transfer_reservation_payload(
        TransferItinerary(first_leg=_first_leg(), second_leg=without),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )
    assert form["runDt2"] == form["dptDt2"] == "20990101"


def test_a_second_leg_without_an_arrival_date_sends_a_blank_not_an_error():
    # arvDt1's rule, applied to arvDt2: blank when the row omits it, because the
    # app's own form seed ships arvDt1="" and refusing would mean a reservation
    # that cannot be made.
    without = dataclasses.replace(_second_leg(), arrival_date=None)
    form = transfer_reservation_payload(
        TransferItinerary(first_leg=_first_leg(), second_leg=without),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )
    assert form["arvDt2"] == ""
    assert form["arvTm2"] == "113000"


# --- what transfer does NOT compose with -------------------------------------


def test_transfer_and_round_trip_are_mutually_exclusive():
    # The app refuses it in BOTH directions with the same string:
    # picking 환승 while 왕복 is ticked (ara0101v.js:296-299) and ticking 왕복
    # while 환승 is selected (:331-334). Expressed structurally -- there is no
    # round_trip argument to pass -- and the flag it would set stays "0".
    assert "round_trip" not in inspect.signature(transfer_reservation_payload).parameters
    assert "round_trip" not in inspect.signature(SrtClient.reserve_transfer).parameters
    assert _transfer_form()["rtnDv"] == "0"
    # And the round-trip flag on the ONE-leg form still does not raise jrnyCnt,
    # which is the other half of the same claim.
    assert _one_leg_form(round_trip=True)["jrnyCnt"] == "1"
    assert _one_leg_form(round_trip=True)["jrnyTpCd"] == "11"


def test_transfer_offers_no_standby_and_no_group_and_no_seat_selection():
    # jobId=1102 is chosen from ONE row's image (ara1001l.js:1445-1448) and a
    # transfer has two rows; 단체환승 exists as an SRT product but this library
    # does not book 단체 at all since 2026-07-26; 좌석지정 explicitly blanks slot
    # 2's car and seat (ara0101v.js:875-879). None of the three is a parameter
    # here.
    parameters = inspect.signature(SrtClient.reserve_transfer).parameters
    assert list(parameters) == [
        "self",
        "itinerary",
        "consent",
        "passengers",
        "seat_type",
        "window_seat",
        "netfunnel_key",
    ]
    for name in ("standby", "group", "round_trip", "seat_numbers", "car_number"):
        assert name not in parameters
    form = _transfer_form()
    assert form["jobId"] == "1101"
    assert form["grpDv"] == "0"
    assert form["stndFlg"] == "N"
    for key in ("scarNo1", "scarNo2", "scarGridcnt1", "scarGridcnt2"):
        assert key not in form
    assert not [key for key in form if key.startswith("seatNo")]


# --- the send path ------------------------------------------------------------


def test_reserve_transfer_previews_the_two_leg_form_on_the_personal_route(
    load_json_fixture,
):
    client, recorder = _client(load_json_fixture("reservation_attempt_success.json"))
    preview = client.reserve_transfer(
        _itinerary(), consent=MutationConsent(allow_reserve=True)
    )

    assert isinstance(preview, MutationPreview)
    assert preview.category == "reserve"
    assert preview.method == "POST"
    assert preview.route == RESERVE_ROUTE
    assert preview.payload["jrnyCnt"] == "2"
    assert preview.payload["jrnyTpCd"] == "14"
    assert preview.payload["trnNo2"] == "00661"
    # A preview performs NO I/O at all.
    assert recorder.requests == []


def test_reserve_transfer_live_send_goes_to_arc05013_under_the_reserve_category(
    load_json_fixture,
):
    client, recorder = _client(load_json_fixture("reservation_attempt_success.json"))
    hold = client.reserve_transfer(
        _itinerary(),
        consent=_live(allow_reserve=True),
        netfunnel_key=SYNTHETIC_NF,
    )

    assert isinstance(hold, SrtReservationHold)
    assert recorder.paths.count(RESERVE_ROUTE) == 1
    form = recorder.forms(RESERVE_ROUTE)[0]
    assert form["jrnyCnt"] == "2"
    assert form["jrnySqno2"] == "002"
    assert form["netfunnelKey"] == SYNTHETIC_NF
    # ONE call, ONE hold -- both legs went in the same body, so a failure could
    # not have stranded half an itinerary.
    assert len(recorder.forms(RESERVE_ROUTE)) == 1


def test_reserve_transfer_is_gated_by_the_same_reserve_consent():
    client, recorder = _client({})
    with pytest.raises(SrtMutationNotAllowedError):
        client.reserve_transfer(_itinerary(), consent=MutationConsent())
    assert recorder.requests == []


def test_reserve_transfer_requires_an_authenticated_session():
    client, recorder = _client({})
    client.clear_session()
    with pytest.raises(SrtAuthError):
        client.reserve_transfer(
            _itinerary(), consent=_live(allow_reserve=True)
        )
    assert recorder.requests == []


def test_transfer_adds_no_route_and_does_not_widen_the_kill_switch():
    # A transfer is a personal reservation with a second journey slot, so it
    # rides the EXISTING route and the EXISTING category. Nothing here may grow.
    assert SRT_LIVE_MUTATION_CATEGORIES == {"reserve", "cancel", "payment", "refund"}
    assert SRT_MUTATION_ROUTE_CATEGORIES[RESERVE_ROUTE] == "reserve"
    # Four since 2026-07-26, when the 단체 endpoint arc06014 was unregistered
    # along with the booking that reached it. One route per category again.
    assert len(SRT_MUTATION_ROUTES) == 4
    assert RESERVE_ROUTE in SRT_MUTATION_ROUTE_CATEGORIES


# --- WRD000061: the server names its own remedy ------------------------------


def test_no_direct_train_is_classified_and_refines_no_results():
    # Live 2026-07-26 on 동대구 -> 광주송정, the direct search answered
    # WRD000061 "직통열차는 없지만, 환승으로 조회 가능합니다." Before this it fell
    # through to a bare SrtAppError.
    error = classify_app_error(
        NO_DIRECT_TRAIN_CODE,
        "직통열차는 없지만, 환승으로 조회 가능합니다.",
        raw={"msgCd": NO_DIRECT_TRAIN_CODE},
    )
    assert isinstance(error, SrtNoDirectTrainError)
    assert error.code == "WRD000061"
    assert error.raw == {"msgCd": NO_DIRECT_TRAIN_CODE}
    # The catchability rule: it still IS an SrtAppError, and it refines the
    # no-results branch because the direct query genuinely matched nothing.
    assert issubclass(SrtNoDirectTrainError, SrtNoResultsError)
    assert issubclass(SrtNoDirectTrainError, SrtAppError)


def test_a_direct_search_of_a_transfer_only_pair_raises_no_direct_train():
    # The whole point of the classification: this is the signal to re-ask the
    # same query as a transfer search.
    with pytest.raises(SrtNoDirectTrainError) as excinfo:
        parse_train_search_response(
            {
                "ErrorCode": "0",
                "ErrorMsg": "",
                "outDataSets": {
                    "dsOutput0": [
                        {
                            "msgCd": NO_DIRECT_TRAIN_CODE,
                            "strResult": "FAIL",
                            "msgTxt": "직통열차는 없지만, 환승으로 조회 가능합니다.",
                        }
                    ],
                    "dsOutput1": [],
                },
            }
        )
    assert excinfo.value.code == NO_DIRECT_TRAIN_CODE
    # The other no-result codes are untouched by the new entry.
    assert type(classify_app_error("WRG000000", "조회 결과가 없습니다.")) is (
        SrtNoResultsError
    )


# --- the live-confirmed response shape ---------------------------------------
#
# The rows below reproduce the 2026-07-26 read-only probe of
# 동대구(0015) -> 광주송정(0036), 20260809 from 080000, verbatim in structure:
# ONE ROW PER LEG, paired by trnOrdrNo, every row chtnDvCd="2", and the ...2
# columns present but EMPTY because the second leg is a separate row.

CHEONAN_ASAN = "0502"


def _probe_row(
    train_no: str,
    departure: str,
    arrival: str,
    departure_time: str,
    arrival_time: str,
    itinerary_no: object,
) -> TrainSummary:
    return TrainSummary(
        train_no=train_no,
        service_class_code="17",
        train_group_code="300",
        departure_station_code=departure,
        arrival_station_code=arrival,
        run_date="20260809",
        departure_date="20260809",
        departure_time=departure_time,
        arrival_date="20260809",
        arrival_time=arrival_time,
        departure_run_order="1",
        arrival_run_order="9",
        departure_consist_order="1",
        arrival_consist_order="9",
        general_seat_availability="예약가능",
        special_seat_availability="예약가능",
        train_run_order=itinerary_no if isinstance(itinerary_no, int) else None,
        raw={
            "trnOrdrNo": itinerary_no,
            "chtnDvCd": "2",
            # Present on every live row and blank, because the second leg is a
            # ROW and not a set of columns.
            "trnNo2": "",
            "dptRsStnCd2": "",
            "jrnySqno": "",
        },
    )


def _probe_rows() -> list[TrainSummary]:
    return [
        _probe_row("382", DONGDAEGU, OSONG, "085200", "095100", 1),
        _probe_row("411", OSONG, GWANGJU_SONGJEONG, "100600", "110500", 1),
        _probe_row("14", DONGDAEGU, CHEONAN_ASAN, "085800", "100900", 2),
        _probe_row("475", CHEONAN_ASAN, GWANGJU_SONGJEONG, "102500", "125000", 2),
        _probe_row("316", DONGDAEGU, OSONG, "091600", "101500", 3),
        _probe_row("655", OSONG, GWANGJU_SONGJEONG, "103100", "113100", 3),
    ]


def _search_result(rows: list[TrainSummary]) -> TrainSearchResult:
    return TrainSearchResult(
        trains=rows,
        result={"msgCd": "IRG000000", "strResult": "SUCC"},
        raw={"outDataSets": {"dsOutput1": [row.raw for row in rows]}},
    )


def test_rows_are_paired_into_itineraries_by_the_itinerary_column():
    # The live shape: one row per leg, grouped by trnOrdrNo, three itineraries
    # out of six rows.
    result = pair_transfer_itineraries(_search_result(_probe_rows()))

    assert isinstance(result, TransferSearchResult)
    assert result.unpaired == ()
    assert len(result.itineraries) == 3
    assert [
        (itinerary.first_leg.train_no, itinerary.second_leg.train_no)
        for itinerary in result.itineraries
    ] == [("382", "411"), ("14", "475"), ("316", "655")]
    # Each one is a whole journey from the query's origin to its destination,
    # via a real 환승역.
    assert [itinerary.transfer_station_code for itinerary in result.itineraries] == [
        OSONG,
        CHEONAN_ASAN,
        OSONG,
    ]
    for itinerary in result.itineraries:
        assert itinerary.origin_station_code == DONGDAEGU
        assert itinerary.destination_station_code == GWANGJU_SONGJEONG


def test_itineraries_keep_the_servers_own_ordering():
    result = pair_transfer_itineraries(_search_result(_probe_rows()))
    assert [itinerary.first_leg.train_no for itinerary in result.itineraries] == [
        "382",
        "14",
        "316",
    ]


def test_leg_order_comes_from_the_stations_and_not_from_the_row_order():
    # THE test this pairing exists for. The live probe happened to deliver the
    # legs in order, but that is an observation about one response, not a
    # guarantee -- and pairing them backwards builds a clean reservation whose
    # two slots describe the journey in reverse. So every group is handed to
    # TransferItinerary in BOTH orders and the stations decide.
    rows = _probe_rows()
    reversed_within_groups = [
        rows[1], rows[0],  # 411 오송->광주송정 BEFORE 382 동대구->오송
        rows[3], rows[2],
        rows[5], rows[4],
    ]
    result = pair_transfer_itineraries(_search_result(reversed_within_groups))

    assert result.unpaired == ()
    assert [
        (itinerary.first_leg.train_no, itinerary.second_leg.train_no)
        for itinerary in result.itineraries
    ] == [("382", "411"), ("14", "475"), ("316", "655")]
    # ... and every one still runs forwards in time.
    for itinerary in result.itineraries:
        assert itinerary.first_leg.arrival_time <= itinerary.second_leg.departure_time


def test_a_group_that_is_not_two_rows_is_set_aside_with_a_reason():
    # Not dropped (that hides a journey) and not paired anyway (that hands back
    # two trains that are not one itinerary). The good itineraries still come
    # back alongside it.
    rows = _probe_rows()
    rows.append(
        _probe_row("999", DONGDAEGU, OSONG, "120000", "130000", 4)
    )  # a lone leg for itinerary 4
    result = pair_transfer_itineraries(_search_result(rows))

    assert len(result.itineraries) == 3
    assert len(result.unpaired) == 1
    orphan = result.unpaired[0]
    assert orphan.itinerary_no == "4"
    assert [row.train_no for row in orphan.rows] == ["999"]
    assert "1 rows" in orphan.reason and TRANSFER_ITINERARY_COLUMN in orphan.reason
    assert str(TRANSFER_LEGS_PER_ITINERARY) in orphan.reason


def test_a_group_of_three_rows_is_set_aside_too():
    rows = _probe_rows()
    rows.insert(2, _probe_row("999", OSONG, GWANGJU_SONGJEONG, "110000", "120000", 1))
    result = pair_transfer_itineraries(_search_result(rows))

    assert len(result.itineraries) == 2
    assert [group.itinerary_no for group in result.unpaired] == ["1"]
    assert "3 rows" in result.unpaired[0].reason


def test_legs_that_do_not_connect_are_set_aside_rather_than_paired():
    # The failure that matters most: two rows sharing a trnOrdrNo whose stations
    # do not meet are NOT one journey, whatever the server grouped them as.
    rows = _probe_rows()
    rows[1] = _probe_row("411", "0010", GWANGJU_SONGJEONG, "100600", "110500", 1)
    result = pair_transfer_itineraries(_search_result(rows))

    assert len(result.itineraries) == 2
    assert [group.itinerary_no for group in result.unpaired] == ["1"]
    assert "do not connect" in result.unpaired[0].reason
    assert {row.train_no for row in result.unpaired[0].rows} == {"382", "411"}


def test_an_ambiguous_leg_order_is_refused_rather_than_broken_by_a_tiebreak():
    # A there-and-back pair with no usable times reads as a valid itinerary in
    # BOTH directions. There is no evidence for choosing one, so neither is
    # chosen.
    loop_out = dataclasses.replace(
        _probe_row("382", DONGDAEGU, OSONG, "085200", "095100", 9),
        arrival_time=None,
        arrival_date=None,
    )
    loop_back = dataclasses.replace(
        _probe_row("411", OSONG, DONGDAEGU, "100600", "110500", 9),
        arrival_time=None,
        arrival_date=None,
    )
    result = pair_transfer_itineraries(
        _search_result(_probe_rows() + [loop_out, loop_back])
    )

    assert len(result.itineraries) == 3
    assert [group.itinerary_no for group in result.unpaired] == ["9"]
    assert "ambiguous" in result.unpaired[0].reason


def test_a_row_without_the_itinerary_column_is_set_aside():
    rows = _probe_rows()
    rows.append(_probe_row("999", DONGDAEGU, OSONG, "120000", "130000", None))
    result = pair_transfer_itineraries(_search_result(rows))

    assert len(result.itineraries) == 3
    assert result.unpaired[0].itinerary_no == ""
    assert TRANSFER_ITINERARY_COLUMN in result.unpaired[0].reason


def test_rows_that_pair_into_nothing_at_all_raise_rather_than_return_empty():
    # If not one itinerary can be made from a response that HAS rows, this
    # grouping rule is wrong for the response in hand -- and an empty list would
    # be the one genuinely silent failure available here.
    lone = [_probe_row("382", DONGDAEGU, OSONG, "085200", "095100", 1)]
    with pytest.raises(SrtProtocolError) as excinfo:
        pair_transfer_itineraries(_search_result(lone))
    assert TRANSFER_ITINERARY_COLUMN in str(excinfo.value)
    # raw is carried, because this is exactly the response a capture wants.
    assert excinfo.value.raw == _search_result(lone).raw


def test_no_rows_is_not_a_pairing_failure():
    result = pair_transfer_itineraries(_search_result([]))
    assert result.itineraries == () and result.unpaired == ()


def test_the_raw_rows_stay_reachable_behind_the_inference():
    # The grouping is ours, so a caller must be able to get behind it.
    search = _search_result(_probe_rows())
    result = pair_transfer_itineraries(search)

    assert result.search is search
    assert result.rows == search.trains
    assert len(result.rows) == 6
    assert result.raw is search.raw
    # Including the columns the pairing does not use: chtnDvCd says what kind of
    # row it is, and the ...2 columns are present-but-empty.
    assert result.rows[0].raw["chtnDvCd"] == "2"
    assert result.rows[0].raw["trnNo2"] == ""
    assert result.rows[0].raw[TRANSFER_ITINERARY_COLUMN] == 1


def test_a_paired_itinerary_is_ready_to_reserve_as_it_stands():
    # The pairing runs TransferItinerary's own validation, so anything handed
    # back can go straight into the reservation builder.
    result = pair_transfer_itineraries(_search_result(_probe_rows()))
    form = transfer_reservation_payload(
        result.itineraries[0],
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
    )
    assert form["jrnyCnt"] == "2" and form["jrnyTpCd"] == "14"
    assert form["trnNo1"] == "00382" and form["trnNo2"] == "00411"
    assert form["dptRsStnCd1"] == DONGDAEGU
    assert form["arvRsStnCd2"] == GWANGJU_SONGJEONG


def test_the_empty_slot_two_columns_on_a_search_row_change_no_evidence_tier():
    # A response COLUMN and a request FIELD that share a name are two different
    # things. The search row's trnNo2/dptRsStnCd2 are blank because the second
    # leg is a separate ROW, which says nothing about whether the RESERVATION
    # form wants them filled -- so the five inferred names stay inferred.
    rows = _probe_rows()
    assert rows[0].raw["trnNo2"] == "" and rows[0].raw["dptRsStnCd2"] == ""
    inferred = {
        key
        for key, tier in TRANSFER_SLOT2_FIELD_EVIDENCE.items()
        if tier == "inferred"
    }
    assert inferred == {
        "stlbTrnClsfCd2",
        "dptStnConsOrdr2",
        "arvStnConsOrdr2",
        "dptStnRunOrdr2",
        "arvStnRunOrdr2",
    }
    # And the reservation form fills them, blank column or not.
    result = pair_transfer_itineraries(_search_result(rows))
    form = transfer_reservation_payload(
        result.itineraries[0], PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )
    assert form["trnNo2"] == "00411"
    assert all(form[key] for key in inferred)


def test_search_transfer_trains_returns_paired_itineraries_end_to_end():
    hydration = (
        '<html><body><form id="seatSearchForm">'
        '<input type="hidden" name="serverNonce" value="synthetic" />'
        "</form>"
        '<a href="/kr/logout.do">logout</a></body></html>'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == NETFUNNEL_PATH:
            if request.url.params["opcode"] == "5004":
                return httpx.Response(
                    200, text="NetFunnel.gControl.result='5004:200:utime=1';"
                )
            return httpx.Response(200, text=NETFUNNEL_BODY)
        if request.method == "GET":
            return httpx.Response(200, text=hydration)
        return httpx.Response(
            200,
            json={
                "ErrorCode": "0",
                "ErrorMsg": "",
                "outDataSets": {
                    "dsOutput0": [
                        {
                            "msgCd": "IRG000000",
                            "strResult": "SUCC",
                            "msgTxt": "",
                            "qryCnqeCnt": 6,
                            "fllwPgExt": "N",
                            "fllwPgExt2": None,
                        }
                    ],
                    "dsOutput1": [
                        {
                            "trnNo": row.train_no,
                            "trnOrdrNo": row.raw["trnOrdrNo"],
                            "chtnDvCd": "2",
                            "stlbTrnClsfCd": "17",
                            "trnGpCd": "300",
                            "runDt": row.run_date,
                            "dptDt": row.departure_date,
                            "dptTm": row.departure_time,
                            "arvDt": row.arrival_date,
                            "arvTm": row.arrival_time,
                            "dptRsStnCd": row.departure_station_code,
                            "arvRsStnCd": row.arrival_station_code,
                            "dptStnRunOrdr": "1",
                            "arvStnRunOrdr": "9",
                            "dptStnConsOrdr": "1",
                            "arvStnConsOrdr": "9",
                            "trnNo2": "",
                            "dptRsStnCd2": "",
                            "jrnySqno": "",
                        }
                        for row in _probe_rows()
                    ],
                },
            },
        )

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    result = client.search_transfer_trains(_query())

    assert isinstance(result, TransferSearchResult)
    assert len(result.itineraries) == 3
    assert result.unpaired == ()
    assert len(result.rows) == 6
    assert [
        (itinerary.first_leg.train_no, itinerary.second_leg.train_no)
        for itinerary in result.itineraries
    ] == [("382", "411"), ("14", "475"), ("316", "655")]
