"""The app's seven passenger types: the 유아 fold, and 청소년 as psgTpCd 6.

Every rule pinned here was read off a live server-rendered page on 2026-07-26,
not off the v2.0.41 bundle, which knows neither type. The two sources are:

* the booking page ``/ara/ara0101v.do`` (``goRevFn``), for the fold;
* the 할인 승차권 page ``/common/ARA/ARA0301V/view.do``
  (``setPassenger_callback``), for psgTpCd 6 and for the same fold again;
* the 승차인원선택 popup ``/common/ARA/ARA0901P/view.do``, for the seven
  counters and their labels.
"""

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.models import (
    PassengerCounts,
    SeatType,
    TrainSearchQuery,
    TrainSummary,
)
from srt_mobile_api.payloads import (
    INFANT_COUNT_FIELD,
    PADDED_PASSENGER_SLOTS,
    PADDED_PASSENGER_SLOTS_WITH_YOUTH,
    PASSENGER_TYPE_CODES,
    fare_payload,
    passenger_selector_payload,
    personal_reservation_payload,
    search_ajax_payload,
    search_page_payload,
)


def _train() -> TrainSummary:
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


def _reserve(passengers: PassengerCounts) -> dict[str, str]:
    return personal_reservation_payload(
        _train(),
        passengers,
        seat_type=SeatType.GENERAL_FIRST,
        netfunnel_key="NF",
    )


def _search(passengers: PassengerCounts) -> dict[str, str]:
    return search_page_payload(
        TrainSearchQuery("0551", "0020", "20990101", passengers=passengers), "NF"
    )


def _ajax(passengers: PassengerCounts) -> dict[str, str]:
    return search_ajax_payload(
        TrainSearchQuery("0551", "0020", "20990101", passengers=passengers),
        "NF",
        hydrated_fields={},
    )


def _all_builders(passengers: PassengerCounts) -> dict[str, dict[str, str]]:
    return {
        "reserve": _reserve(passengers),
        "search": _search(passengers),
        "ajax": _ajax(passengers),
        "fare": fare_payload(_train(), passengers),
        "selector": passenger_selector_payload(passengers),
    }


# --------------------------------------------------------------------------
# the 유아 fold
# --------------------------------------------------------------------------


def test_one_infant_count_produces_both_effects_at_once():
    """The whole rule, from a single number, exactly as `goRevFn` writes it.

        if(i==5){
            passenger = passenger + passenger6;   // (1) folded into the 어린이 COUNT
            $('#infantCnt').val(passenger6);      // (2) declared again, separately
        }
        ...
        totPrnb += passenger;                     // (3) and it is a HEAD
    """
    payload = _reserve(PassengerCounts(adult=1, child=2, infant=3))
    # (1) the 어린이 slot carries 2 + 3, not 2.
    assert payload["psgTpCd2"] == "5"
    assert payload["psgInfoPerPrnb2"] == "5"
    # (2) and the same three infants are declared again on their own.
    assert payload[INFANT_COUNT_FIELD] == "3"
    # (3) totPrnb counts them, because `totPrnb += passenger` runs after the fold.
    assert payload["totPrnb"] == "6"
    # ...and they did NOT create a passenger type: an infant has no psgTpCd.
    assert payload["psgGridcnt"] == "2"


def test_the_fold_is_identical_on_every_builder():
    passengers = PassengerCounts(adult=1, child=2, infant=3)
    for name, payload in _all_builders(passengers).items():
        if name == "selector":
            # The popup is the one place the count is NOT folded -- see below.
            continue
        assert payload["psgInfoPerPrnb2"] == "5", name
        assert payload["psgTpCd2"] == "5", name


def test_infants_without_children_still_fill_the_child_slot():
    # The app tests the SUM (`if(passenger != '' && passenger != '0')`) after
    # folding, so an infant alone opens the 어린이 slot. Following the page
    # rather than the tidier "no children means no child slot".
    payload = _reserve(PassengerCounts(adult=1, infant=2))
    assert payload["psgTpCd2"] == "5"
    assert payload["psgInfoPerPrnb2"] == "2"
    assert payload[INFANT_COUNT_FIELD] == "2"
    assert payload["totPrnb"] == "3"
    assert payload["psgGridcnt"] == "2"


def test_infant_count_field_is_absent_when_there_is_no_infant():
    for name, payload in _all_builders(PassengerCounts(adult=1, child=1)).items():
        assert INFANT_COUNT_FIELD not in payload, name


def test_fare_request_never_carries_the_infant_count():
    # The live fare params are the psgTpCd/psgInfoPerPrnb family and nothing else
    # from it; infantCnt is not among them even though the booking form has it.
    payload = fare_payload(_train(), PassengerCounts(adult=1, infant=2))
    assert INFANT_COUNT_FIELD not in payload
    assert payload["psgInfoPerPrnb2"] == "2"


# --------------------------------------------------------------------------
# 청소년 == psgTpCd 6
# --------------------------------------------------------------------------


def test_youth_is_psgTpCd_six_and_is_its_own_type():
    payload = _reserve(PassengerCounts(adult=1, youth=2))
    assert payload["psgTpCd2"] == "6"
    assert payload["psgInfoPerPrnb2"] == "2"
    assert payload["totPrnb"] == "3"
    # Unlike an infant, a 청소년 DOES add a passenger type.
    assert payload["psgGridcnt"] == "2"
    assert INFANT_COUNT_FIELD not in payload


def test_youth_is_always_compacted_last():
    payload = _reserve(
        PassengerCounts(
            adult=1,
            disability_1_to_3=1,
            disability_4_to_6=1,
            senior=1,
            child=1,
            infant=1,
            youth=1,
        )
    )
    assert [payload[f"psgTpCd{index}"] for index in range(1, 7)] == [
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
    ]
    # slot 5 is 어린이 + 유아
    assert payload["psgInfoPerPrnb5"] == "2"
    assert payload["psgInfoPerPrnb6"] == "1"
    assert payload[INFANT_COUNT_FIELD] == "1"
    assert payload["totPrnb"] == "7"
    assert payload["psgGridcnt"] == "6"


def test_youth_widens_the_padded_forms_to_six_slots():
    # Five is the booking page's loop; six is what the page that can express a
    # 청소년 writes. The padded (search) forms follow whichever the party needs.
    without = _search(PassengerCounts(adult=1, child=1))
    assert f"psgTpCd{PADDED_PASSENGER_SLOTS}" in without
    assert f"psgTpCd{PADDED_PASSENGER_SLOTS_WITH_YOUTH}" not in without

    with_youth = _search(PassengerCounts(adult=1, youth=1))
    assert f"psgTpCd{PADDED_PASSENGER_SLOTS_WITH_YOUTH}" in with_youth
    # The youth compacted to slot 2, so slot 6 is a padded empty one.
    assert with_youth["psgTpCd2"] == "6"
    assert with_youth["psgTpCd6"] == ""
    assert with_youth["psgInfoPerPrnb6"] == "0"


def test_fare_keeps_slot_six_when_a_youth_occupies_it_and_blanks_it_otherwise():
    # The fare form's trailing slot 6 is "" / "" when unfilled -- note "" and not
    # the search form's "0". But when a 청소년 fills it, blanking it would drop
    # that passenger from the quote.
    ordinary = fare_payload(_train(), PassengerCounts(adult=1))
    assert ordinary["psgTpCd6"] == "" and ordinary["psgInfoPerPrnb6"] == ""

    partial = fare_payload(_train(), PassengerCounts(adult=1, youth=2))
    assert partial["psgTpCd2"] == "6" and partial["psgInfoPerPrnb2"] == "2"
    assert partial["psgTpCd6"] == "" and partial["psgInfoPerPrnb6"] == ""

    full = fare_payload(
        _train(),
        PassengerCounts(
            adult=1,
            disability_1_to_3=1,
            disability_4_to_6=1,
            senior=1,
            child=1,
            youth=1,
        ),
    )
    assert full["psgTpCd6"] == "6"
    assert full["psgInfoPerPrnb6"] == "1"


def test_youth_is_accepted_without_checking_the_entitlement():
    """An entitled account is a legitimate caller and this cannot know which.

    The 승차인원선택 popup only REVEALS `passenger7` when 공공할인 "04" is
    approved, but that is a UI gate on the account, not a rule this library can
    evaluate: nothing in a payload builder knows what the caller's account
    holds. Refusing here would lock out the only people the type is for.
    """
    payload = _reserve(PassengerCounts(adult=1, youth=1))
    assert payload["psgTpCd2"] == "6"


def test_youth_never_appears_when_the_count_is_zero():
    for name, payload in _all_builders(PassengerCounts(adult=2, senior=1)).items():
        assert "6" not in [
            payload.get(f"psgTpCd{index}") for index in range(1, 7)
        ], name
        assert "passenger7" not in payload, name


# --------------------------------------------------------------------------
# the invariance that keeps the live-verified bodies valid
# --------------------------------------------------------------------------


ZERO_INFANT_YOUTH_PARTIES = [
    PassengerCounts(adult=1),
    PassengerCounts(adult=2, child=1),
    PassengerCounts(adult=1, senior=2),
    PassengerCounts(adult=0, child=1, senior=2),
    PassengerCounts(
        adult=1, child=1, senior=1, disability_1_to_3=1, disability_4_to_6=1
    ),
]


@pytest.mark.parametrize("passengers", ZERO_INFANT_YOUTH_PARTIES)
def test_zero_infant_and_youth_leaves_every_payload_exactly_as_it_was(passengers):
    """The point of every "only when non-zero" branch in payloads.py.

    The 2026-07-25 live reserve->cancel round trip verified the reservation body
    byte-for-byte. Adding two passenger types must not retire that evidence, so
    a party without either type produces a body with no new field, no widened
    slot range, and no changed count.
    """
    assert passengers.infant == 0 and passengers.youth == 0
    builders = _all_builders(passengers)
    for name, payload in builders.items():
        assert INFANT_COUNT_FIELD not in payload, name
        assert "passenger6" not in payload, name
        assert "passenger7" not in payload, name
    # No builder grows a sixth psgTpCd slot -- except the fare form, which has
    # always carried its own always-empty trailing one.
    for name in ("reserve", "search", "ajax"):
        assert (
            f"psgTpCd{PADDED_PASSENGER_SLOTS_WITH_YOUTH}" not in builders[name]
        ), name
    fare = builders["fare"]
    assert fare["psgTpCd6"] == "" and fare["psgInfoPerPrnb6"] == ""
    # totPrnb is still the plain sum of the five.
    assert _reserve(passengers)["totPrnb"] == str(
        passengers.adult
        + passengers.child
        + passengers.senior
        + passengers.disability_1_to_3
        + passengers.disability_4_to_6
    )


def test_type_code_table_is_the_six_slot_types_in_compaction_order():
    assert PASSENGER_TYPE_CODES == (
        ("adult", "1"),
        ("disability_1_to_3", "2"),
        ("disability_4_to_6", "3"),
        ("senior", "4"),
        # NOT "child": slot 5 carries the folded 어린이 + 유아 count.
        ("child_slot_count", "5"),
        ("youth", "6"),
    )
    # 유아 has no slot of its own, and must not acquire one by accident.
    assert "infant" not in dict(PASSENGER_TYPE_CODES)


# --------------------------------------------------------------------------
# the 승차인원선택 popup, whose numbering is NOT psgTpCd
# --------------------------------------------------------------------------


def test_selector_sends_the_unfolded_child_count():
    # passenger5 on the popup is 어린이 alone; the fold happens on the page that
    # receives the popup's answer. Sending the folded number here would seed the
    # picker with the infants counted twice.
    payload = passenger_selector_payload(PassengerCounts(adult=1, child=2, infant=3))
    assert payload["passenger5"] == "2"
    assert payload["passenger6"] == "3"
    assert payload["totalPessnger"] == "6"


def test_selector_numbering_is_the_popups_own():
    payload = passenger_selector_payload(
        PassengerCounts(
            adult=1,
            disability_1_to_3=2,
            disability_4_to_6=3,
            senior=4,
            child=5,
            infant=6,
            youth=7,
        )
    )
    assert payload["passenger1"] == "1"  # 어른
    assert payload["passenger2"] == "2"  # 중증 장애인
    assert payload["passenger3"] == "3"  # 경증 장애인
    assert payload["passenger4"] == "4"  # 경로
    assert payload["passenger5"] == "5"  # 어린이 (unfolded)
    assert payload["passenger6"] == "6"  # 유아
    assert payload["passenger7"] == "7"  # 청소년
    assert payload["totalPessnger"] == "28"


def test_selector_read_transmits_the_new_counters(load_text_fixture):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text=load_text_fixture("selector_passenger.html"))

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.get_passenger_selector(PassengerCounts(adult=1, infant=1, youth=1))
    body = calls[0].content.decode()
    assert "passenger6=1" in body
    assert "passenger7=1" in body
    assert "totalPessnger=3" in body
