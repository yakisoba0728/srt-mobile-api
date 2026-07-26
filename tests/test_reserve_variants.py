"""Offline contract tests for the two reservation variants.

Standby (예약대기) and the round trip / 오는열차 second leg. Unlike payment and
refund, both are evidenced in OUR OWN v2.0.41 bundle, so every expectation below
is built from the bundle and srtgo is only ever a cross-check. Where they
disagree the bundle wins, and the disagreement is pinned as such:

* **standby trigger.** srtgo selects standby from ``rsvWaitPsbCd >= 0``
  (srt.py:840-884). Our app never reads that column for the decision — it reads
  the selected row's general-cabin IMAGE (``ara1001l.js:1445-1448``). The two
  are not interchangeable: the group search (Ara10082) does not return
  ``rsvWaitPsbCd`` at all, and our own group fixture confirms the omission.
* **jrnyCnt.** Neither source says a round trip raises it. The bundle says
  outright that ``jrnyCnt="2"`` is 환승 (``ara0101v.js:288-311``).

There was a THIRD variant here, 단체 (group), and it was removed on 2026-07-26
with the booking code it covered: ``/arc/selectListArc06014_n.do`` answers with
a server-rendered payment page, not a reservation hold, so there is no hold for
this library to create or cancel (docs/IMPLEMENTATION_PROGRESS.md, "단체 (group)
booking: removed"). What survives that removal is pinned at the bottom of this
file — the route is unregistered, the kill switch is unchanged, and every
reservation form this library still builds sends ``grpDv="0"``.

No network: every send here goes through ``httpx.MockTransport``. Nothing in
this file may weaken the existing single-passenger reserve pins in
``test_mutation_live_paths`` — the first test asserts the default form is
byte-for-byte and order-for-order what it was before these parameters existed.
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
    SrtReservationHold,
    SrtSession,
    TrainSearchQuery,
    TrainSummary,
    payloads,
)
from srt_mobile_api.errors import SrtProtocolError
from srt_mobile_api.payloads import (
    RESERVE_PERSONAL_JOBID,
    RESERVE_SEATMAP_JOBID,
    RESERVE_STANDBY_JOBID,
    personal_reservation_payload,
)
from srt_mobile_api.safety import (
    SRT_LIVE_MUTATION_CATEGORIES,
    SRT_MUTATION_ROUTE_CATEGORIES,
    SRT_MUTATION_ROUTES,
    MutationRoute,
    assert_mutation_route,
)

RESERVE_ROUTE = "/arc/selectListArc05013_n.do"
# The removed 단체 endpoint, kept only so the last test in this file can assert
# it is gone. Nothing here may send to it, and _Recorder no longer answers it.
REMOVED_GROUP_RESERVE_ROUTE = "/arc/selectListArc06014_n.do"
NETFUNNEL_PATH = "/ts.wseq"

SYNTHETIC_NF = "SYNTHETIC_NETFUNNEL_KEY"
ACQUIRED_NF = "ACQUIRED_NETFUNNEL_KEY"
NETFUNNEL_BODY = (
    "NetFunnel.gRtype=5101;"
    f"NetFunnel.gControl.result='5101:200:key={ACQUIRED_NF}&nwait=0&nnext=0';"
)

# ara1001l.js:32-33. The server sends the bare spelling; the app rewrites it to
# _S when the row is tapped (:1045), and fn_moveRsv tests the _S form (:1447).
WAITING_IMAGE = "IMAGE::grd_WF_Waiting.png"
WAITING_IMAGE_SELECTED = "IMAGE::grd_WF_Waiting_S.png"
AVAILABLE_IMAGE = "IMAGE::grd_WF_Ok01.png"


def _eligible_train() -> TrainSummary:
    """The same reservable train the existing reserve pins use."""
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


def _standby_train(image: str | None = WAITING_IMAGE) -> TrainSummary:
    """A full train whose row offers 예약대기.

    Deliberately NOT "예약가능" in either cabin: that is what a waitlist row
    looks like, and it is also what makes the ``SeatType.GENERAL_FIRST``
    fallback resolve to 특실 unless standby overrides it.
    """
    raw = {} if image is None else {"gnrmRsvPsbImg": image}
    return dataclasses.replace(
        _eligible_train(),
        general_seat_availability="예약대기",
        special_seat_availability="매진",
        raw=raw,
    )


def _return_train() -> TrainSummary:
    """The 오는열차: the same route reversed, on a later date."""
    return dataclasses.replace(
        _eligible_train(),
        train_no="316",
        departure_station_code="0020",
        arrival_station_code="0551",
        departure_station_name="부산",
        arrival_station_name="수서",
        departure_date="20990103",
        departure_time="180000",
        arrival_time="203000",
    )


def _default_form(**kwargs) -> dict[str, str]:
    return personal_reservation_payload(
        _eligible_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        **kwargs,
    )


def _delta(before: dict[str, str], after: dict[str, str]) -> dict[str, object]:
    """The exact wire delta: which keys were added, changed and omitted.

    Returned rather than asserted piecemeal so a test can pin the WHOLE effect
    of a variant in one comparison. A variant that quietly changed a fourth
    field would fail even though the three it was supposed to change are right.
    """
    return {
        "added": {key: after[key] for key in after.keys() - before.keys()},
        "removed": {key: before[key] for key in before.keys() - after.keys()},
        "changed": {
            key: (before[key], after[key])
            for key in before.keys() & after.keys()
            if before[key] != after[key]
        },
    }


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


# --- the default call is untouched -------------------------------------------


def test_defaulted_variants_leave_the_reserve_form_byte_for_byte_unchanged():
    # The load-bearing compatibility claim. Every new parameter is keyword-only
    # and defaulted, so a caller who names none of them must get the form that
    # was live-verified on 2026-07-25 -- identical values AND identical key
    # order, since order is what the existing arvDt1 position pins depend on.
    implicit = _default_form()
    explicit = _default_form(standby=False, round_trip=False, designated_seats=None)

    assert implicit == explicit
    assert list(implicit) == list(explicit)
    assert _delta(implicit, explicit) == {"added": {}, "removed": {}, "changed": {}}
    # And it is still the personal wire, not something reshaped to accommodate
    # the variants.
    assert implicit["jobId"] == RESERVE_PERSONAL_JOBID == "1101"
    assert implicit["grpDv"] == "0"
    assert implicit["rtnDv"] == "0"
    assert implicit["jrnyCnt"] == "1"
    assert implicit["reserveType"] == "11"


def test_reserve_signature_keeps_every_new_parameter_keyword_only_and_defaulted():
    parameters = inspect.signature(SrtClient.reserve).parameters
    for name in ("standby", "round_trip"):
        parameter = parameters[name]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is False
    # 좌석지정 joined them on the same terms: keyword-only, and defaulted to
    # "not designated" rather than to False, since its absence is an absent
    # object and not a false flag.
    designated = parameters["designated_seats"]
    assert designated.kind is inspect.Parameter.KEYWORD_ONLY
    assert designated.default is None


# --- standby (예약대기, jobId 1102) --------------------------------------------


def test_standby_changes_exactly_the_job_id_the_cabin_and_the_reserve_type():
    # The whole wire delta of standby, in one comparison, against the SAME
    # train so nothing else can move. Built from ara1001l.js:1445-1448 (jobId),
    # :1431 (일반실) and srtgo srt.py:990-991 (reserveType is personal-only).
    before = personal_reservation_payload(
        _standby_train(), PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )
    after = personal_reservation_payload(
        _standby_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        standby=True,
    )

    assert _delta(before, after) == {
        "added": {},
        # reserveType is OMITTED, not blanked: srtgo sets it only for 1101.
        "removed": {"reserveType": "11"},
        "changed": {
            "jobId": ("1101", "1102"),
            # GENERAL_FIRST resolves to 특실 on a train whose general cabin is
            # not 예약가능 -- which is every standby train. Standby overrides it
            # back to 일반실, or asking for a waitlist place would silently
            # order first class.
            "psrmClCd1": ("2", "1"),
        },
    }
    assert after["jobId"] == RESERVE_STANDBY_JOBID
    assert "reserveType" not in after


def test_standby_leaves_the_standing_room_flag_alone():
    # stndFlg is 입석여부 (standing room), a different concept from 예약대기 that
    # is easy to conflate. It has two hits in the whole bundle -- the seed
    # ara0101v.js:96 and a null-check read at ara1001l.js:1656 -- and nothing
    # ever writes it, so it stays "N" on both paths.
    assert _default_form()["stndFlg"] == "N"
    assert (
        personal_reservation_payload(
            _standby_train(),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            standby=True,
        )["stndFlg"]
        == "N"
    )


@pytest.mark.parametrize("image", [WAITING_IMAGE, WAITING_IMAGE_SELECTED])
def test_standby_accepts_both_spellings_of_the_waiting_image(image):
    # The server sends grd_WF_Waiting.png; the app rewrites it to the _S form on
    # row selection (ara1001l.js:1045, :1058) and then tests for _S (:1447). A
    # library performs no such rewrite, so a row may legitimately carry either.
    form = personal_reservation_payload(
        _standby_train(image),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        standby=True,
    )
    assert form["jobId"] == "1102"


def test_standby_refuses_a_row_the_app_would_not_offer_standby_for():
    # fn_moveRsv can only ever produce 1102 for a 예약대기 row. Sending it for a
    # 예약가능 row is sending a body the app cannot produce.
    with pytest.raises(ValueError, match="예약대기"):
        personal_reservation_payload(
            _standby_train(AVAILABLE_IMAGE),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            standby=True,
        )


def test_standby_accepts_a_row_that_carries_no_image_column_at_all():
    # Absence is not ineligibility -- the same "blank, not an error" rule arvDt1
    # gets. A hand-built TrainSummary, or a response shape that drops the
    # column, must not make standby unreachable for reasons unrelated to the
    # train. Only a row that HAS the field and disagrees is refused.
    form = personal_reservation_payload(
        _standby_train(None),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        standby=True,
    )
    assert form["jobId"] == "1102"


def test_standby_is_opt_in_and_never_inferred_from_the_row():
    # A 예약대기 row reserved WITHOUT standby=True still sends 1101. Inferring
    # would change what an existing caller transmits the first time they pass a
    # full train, and a waitlist entry is not a reservation.
    form = personal_reservation_payload(
        _standby_train(), PassengerCounts(adult=1), netfunnel_key=SYNTHETIC_NF
    )
    assert form["jobId"] == "1101"
    assert "reserveType" in form


def test_standby_still_refuses_a_non_srt_train():
    # The SRT-only guard is not bypassed by the new path.
    with pytest.raises(ValueError, match="SRT train"):
        personal_reservation_payload(
            dataclasses.replace(_standby_train(), service_class_code="05"),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            standby=True,
        )


def test_reserve_standby_previews_the_1102_form_on_the_unchanged_route(
    load_json_fixture,
):
    client, recorder = _client(load_json_fixture("reservation_attempt_success.json"))

    preview = client.reserve(
        _standby_train(),
        consent=MutationConsent(allow_reserve=True),
        standby=True,
    )

    assert isinstance(preview, MutationPreview)
    assert preview.category == "reserve"
    assert preview.route == RESERVE_ROUTE
    assert preview.payload["jobId"] == "1102"
    # A preview performs no I/O whatsoever, standby or not.
    assert recorder.requests == []


def test_reserve_standby_live_send_uses_the_same_route_key_flow_and_category(
    load_json_fixture,
):
    # Standby is not a new endpoint and not a new consent category: it is the
    # same arc05013 POST with a different jobId, so it rides the existing
    # "reserve" gate and the same act_10 acquisition.
    client, recorder = _client(load_json_fixture("reservation_attempt_success.json"))

    hold = client.reserve(
        _standby_train(), consent=_live(allow_reserve=True), standby=True
    )

    assert isinstance(hold, SrtReservationHold)
    assert recorder.paths == [NETFUNNEL_PATH, RESERVE_ROUTE, NETFUNNEL_PATH]
    form = recorder.forms(RESERVE_ROUTE)[0]
    assert form["jobId"] == "1102"
    assert form["netfunnelKey"] == ACQUIRED_NF
    assert "reserveType" not in form


def test_no_undesignated_reservation_emits_the_seat_map_job_or_its_fields():
    # 1103 (시트맵예약) IS implemented now -- see tests/test_seat_designation.py
    # -- and this test is the other half of that: it is reachable ONLY through
    # designated_seats. Neither a plain personal reservation nor a standby one
    # may emit the job type or a single field of its family
    # (ara0101v.js:866-882), because both would be a body the app never builds.
    assert RESERVE_SEATMAP_JOBID == "1103"
    for standby in (False, True):
        train = _standby_train() if standby else _eligible_train()
        form = personal_reservation_payload(
            train,
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            standby=standby,
        )
        assert form["jobId"] != RESERVE_SEATMAP_JOBID
        # Nor does anything emit the seat-map field family (ara0101v.js:871-878).
        assert not [key for key in form if key.startswith(("seatNo", "scarNo", "scarGridcnt"))]


# --- round trip / 오는열차 second leg (rtnDv=1) ---------------------------------


def test_round_trip_changes_exactly_the_return_flag():
    # The ENTIRE wire delta. ara0101v.js:381 sets rtnDv="1" on the 왕복 tick and
    # :390 sets it back to "0"; nothing else in the reservation form moves.
    before = _default_form()
    after = _default_form(round_trip=True)

    assert _delta(before, after) == {
        "added": {},
        "removed": {},
        "changed": {"rtnDv": ("0", "1")},
    }


def test_round_trip_does_not_raise_the_journey_count():
    # THE premise most likely to be assumed and most clearly refuted. jrnyCnt has
    # three hits in the whole bundle: the seed "1" (ara0101v.js:92), a null-check
    # read (ara1001l.js:1654), and ONE write -- the 환승 toggle, which sets
    # jrnyCnt="2" with jrnyTpCd="14" (ara0101v.js:288-311). Nothing on the 왕복
    # path touches it, and 환승 + 왕복 is refused anyway (:296-298, :333). So
    # jrnyCnt="2" means TRANSFER, not round trip.
    form = _default_form(round_trip=True)
    assert form["jrnyCnt"] == "1"
    assert form["jrnyTpCd"] == "11"
    assert form["jrnySqno1"] == "001"


def test_round_trip_emits_no_second_journey_slot():
    # The ...2 suffix indexes the 여정 (journey) slot -- the app's own gloss is
    # 여정일련번호1(001:선행, 002:후행) at ara0101v.js:97, echoed at
    # ara1001l.js:1607. Slot 2 belongs to a 환승 second leg, and a round trip
    # never fills it: the one-way seat callback explicitly blanks it
    # (scarGridcnt2=0, scarNo2="", ara0101v.js:875-878) and the return train
    # arrives in slot 1 on the second POST. It is emphatically not a second
    # passenger -- passengers live in psgTpCd1..5, indexed by TYPE.
    form = _default_form(round_trip=True)
    for family in (
        "stlbTrnClsfCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "dptDt",
        "dptTm",
        "arvDt",
        "arvTm",
        "trnNo",
        "runDt",
        "jrnySqno",
        "trnGpCd",
        "psrmClCd",
        "smkSeatAttCd",
        "dirSeatAttCd",
        "locSeatAttCd",
        "rqSeatAttCd",
        "etcSeatAttCd",
    ):
        assert f"{family}2" not in form
    # One adult, so only one passenger-type slot is filled and the padded ones
    # are absent from the reservation form too (that padding is a SEARCH thing).
    assert "psgTpCd2" not in form


def test_round_trip_is_two_separate_reserve_calls_each_creating_one_hold(
    load_json_fixture,
):
    # SRT models a round trip as 오는열차, not as a multi-leg body: the app
    # reserves the outbound, re-searches with the stations swapped, then POSTs
    # the return leg to the SAME endpoint (ara1001l.js:1580-1596). Keeping it two
    # calls preserves the property reserve() is built around -- one call can
    # create at most one hold, so a failure strands at most one.
    client, recorder = _client(load_json_fixture("reservation_attempt_success.json"))
    consent = _live(allow_reserve=True)

    outbound = client.reserve(
        _eligible_train(), consent=consent, round_trip=True, netfunnel_key=SYNTHETIC_NF
    )
    inbound = client.reserve(
        _return_train(), consent=consent, round_trip=True, netfunnel_key=SYNTHETIC_NF
    )

    assert isinstance(outbound, SrtReservationHold)
    assert isinstance(inbound, SrtReservationHold)
    forms = recorder.forms(RESERVE_ROUTE)
    assert len(forms) == 2
    assert [form["rtnDv"] for form in forms] == ["1", "1"]
    assert [form["jrnyCnt"] for form in forms] == ["1", "1"]
    # The return leg's train lands in the leg-1 fields, stations reversed --
    # ara1001l.js:1454-1470 overwrites them from the selected return row.
    assert forms[0]["dptRsStnCd1"] == "0551" and forms[0]["arvRsStnCd1"] == "0020"
    assert forms[1]["dptRsStnCd1"] == "0020" and forms[1]["arvRsStnCd1"] == "0551"
    assert forms[1]["trnNo1"] == "00316"


def test_for_return_leg_swaps_the_stations_and_takes_the_return_date():
    # ara1001l.js:110-115, the fv_sRtnCd == "2" branch: the return search uses
    # back_dptDt1/back_dptTm1 and reverses dptRsStnCd1/arvRsStnCd1.
    outbound = TrainSearchQuery(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="060000",
        departure_station_name="수서",
        arrival_station_name="부산",
        passengers=PassengerCounts(adult=2, child=1),
        train_group_code="300",
        seat_attr_code="021",
    )

    inbound = outbound.for_return_leg("20990103", "180000")

    assert inbound.departure_station_code == "0020"
    assert inbound.arrival_station_code == "0551"
    assert inbound.departure_station_name == "부산"
    assert inbound.arrival_station_name == "수서"
    assert inbound.departure_date == "20990103"
    assert inbound.departure_time == "180000"
    # Carried over, because the app re-searches the same booking form.
    assert inbound.passengers == outbound.passengers
    assert inbound.train_group_code == "300"
    assert inbound.seat_attr_code == "021"
    # And the outbound query is untouched (frozen dataclass, replace()).
    assert outbound.departure_station_code == "0551"


def test_for_return_leg_defaults_the_departure_time_to_the_apps_back_seed():
    # ara0101v.js:111 seeds back_dptTm1 = "000000". Starting the return search at
    # midnight of the return date shows every candidate; inheriting the outbound
    # time would hide the early ones for no reason.
    outbound = TrainSearchQuery(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="140000",
    )
    assert outbound.for_return_leg("20990103").departure_time == "000000"


def test_for_return_leg_still_validates_the_date():
    outbound = TrainSearchQuery(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
    )
    with pytest.raises(ValueError, match="departure_date"):
        outbound.for_return_leg("2099-01-03")


# --- the two do not leak into each other -------------------------------------


def test_each_variant_is_independent_of_the_others():
    # Standby and round trip compose -- both are personal-form flags. Pinned so
    # a later refactor cannot make one variant quietly imply another. grpDv is
    # asserted on both bodies because it is now a constant "0" and nothing in
    # this library may ever flip it on a reservation form again.
    both = personal_reservation_payload(
        _standby_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        standby=True,
        round_trip=True,
    )
    assert both["jobId"] == "1102"
    assert both["rtnDv"] == "1"
    assert both["grpDv"] == "0"
    assert both["psrmClCd1"] == "1"
    assert "reserveType" not in both

    only_round_trip = _default_form(round_trip=True)
    assert only_round_trip["jobId"] == "1101"
    assert only_round_trip["grpDv"] == "0"


@pytest.mark.parametrize("seat_type", list(SeatType))
def test_standby_forces_the_general_cabin_for_every_seat_type(seat_type):
    # Every SeatType, including SPECIAL_ONLY. There is no 특실 standby in the
    # app: ara1001l.js:1431 assigns 일반실 for the 예약대기 image and the 특실
    # branch on the next line tests only the two 예약가능 images. Overriding is
    # chosen over refusing because the default GENERAL_FIRST would otherwise
    # refuse every standby attempt, which is the opposite of the app's behaviour.
    form = personal_reservation_payload(
        _standby_train(),
        PassengerCounts(adult=1),
        netfunnel_key=SYNTHETIC_NF,
        seat_type=seat_type,
        standby=True,
    )
    assert form["psrmClCd1"] == "1"


def test_seat_type_is_still_validated_on_the_standby_path():
    with pytest.raises(ValueError, match="seat_type"):
        personal_reservation_payload(
            _standby_train(),
            PassengerCounts(adult=1),
            netfunnel_key=SYNTHETIC_NF,
            seat_type="SPECIAL_ONLY",  # type: ignore[arg-type]
            standby=True,
        )


# --- 단체 (group) booking: removed, and pinned as removed ----------------------


def test_group_booking_is_gone_from_the_client_and_the_payload_builders():
    # The removal itself, asserted rather than merely done. reserve_group and
    # group_reservation_payload existed until 2026-07-26; Arc06014 turned out to
    # answer with a 단체승차권 payment page (form ata0201cForm, goToPay /
    # kakaoPayReturn, posting to /ata/selectListAta01033_n.do) instead of a
    # cancelable hold, so there was nothing for this library to create.
    #
    # The group SEARCH is deliberately NOT covered by this test -- it stays, and
    # tests/test_client_read_apis.py and test_netfunnel_payloads_parsers.py
    # still exercise it.
    assert not hasattr(SrtClient, "reserve_group")
    assert not hasattr(payloads, "group_reservation_payload")
    # The search half is untouched, floor and all.
    assert payloads.GROUP_MIN_PARTY_SIZE == 10
    assert hasattr(payloads, "group_search_ajax_payload")
    assert hasattr(SrtClient, "search_group_trains")


def test_the_group_route_is_unregistered_and_the_kill_switch_is_unchanged():
    # A route no method can reach must not stay transmittable: Arc06014 was
    # dropped from SRT_MUTATION_ROUTES and from the route->category map when the
    # booking went. What must NOT move is the kill switch -- group rode the
    # "reserve" category, and removing group may not shrink it, because reserve
    # and cancel are the two halves of one reversible operation.
    assert MutationRoute("POST", "app", REMOVED_GROUP_RESERVE_ROUTE) not in SRT_MUTATION_ROUTES
    assert REMOVED_GROUP_RESERVE_ROUTE not in SRT_MUTATION_ROUTE_CATEGORIES
    assert MutationRoute("POST", "app", RESERVE_ROUTE) in SRT_MUTATION_ROUTES
    assert SRT_MUTATION_ROUTE_CATEGORIES[RESERVE_ROUTE] == "reserve"
    assert len(SRT_MUTATION_ROUTES) == 4
    assert SRT_LIVE_MUTATION_CATEGORIES == frozenset(
        {"reserve", "cancel", "payment", "refund"}
    )


def test_the_mutation_send_path_now_refuses_the_group_route_outright():
    # The consequence of unregistering it: assert_mutation_route is the gate the
    # send path runs first, and an unregistered path cannot get past it even
    # with a live reserve consent in hand.
    assert_mutation_route("POST", RESERVE_ROUTE)
    with pytest.raises(SrtProtocolError, match="not allowed"):
        assert_mutation_route("POST", REMOVED_GROUP_RESERVE_ROUTE)
