import re

from .discounts import (
    PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE,
    PUBLIC_DISCOUNT_NAMES_BY_CODE,
)
from .errors import SrtProtocolError
from .models import (
    PassengerCounts,
    PublicDiscountSelection,
    SeatDesignation,
    SeatType,
    SrtCouponRegistrationRequest,
    SrtPaymentCard,
    SrtRefundTicketInfo,
    SrtReservationHold,
    SrtReservationSummary,
    SrtTrainGroupCode,
    TrainSearchQuery,
    TrainSummary,
    TransferItinerary,
)
from .stations import SRT_STATION_CODES, station_name_by_code


# 공공할인코드 the 할인 승차권 page has a branch for. discounts.py NAMES six of
# them; the page's own if/else chain runs 01..08, so 07 and 08 are ACCEPTED here
# and merely nameless -- refusing a code the server branches on would be this
# library deciding a discount does not exist because nobody has written its name
# down where we can read it.
PUBLIC_DISCOUNT_CODES = frozenset(
    set(PUBLIC_DISCOUNT_NAMES_BY_CODE) | {"07", "08"}
)


# The three 조정구분코드 (jobId) values, documented by the app itself in a single
# comment on its own reservation-form seed (ara0101v.js:90):
#   "jobId" : "1101"  //조정구분코드(1101:개인예약, 1102:예약대기, 1103:시트맵예약)
# so SRT has the same three job types korail does, and all three are built here.
# 1103 arrived last, on 2026-07-26, once the seat grid turned out to be readable
# without a traffic capture; RESERVE_SEATMAP_JOBID below records what about it
# is still inferred rather than observed.

# 개인예약. srtgo agrees on the value (RESERVE_JOBID["PERSONAL"], srt.py:31).
RESERVE_PERSONAL_JOBID = "1101"

# 예약대기 (standby / waitlist). ara1001l.js:1445-1448: fn_moveRsv defaults
# sJobId="1101" and overwrites it with "1102" when the selected row's
# general-cabin image is the 예약대기 image. srtgo agrees on the VALUE
# (RESERVE_JOBID["STANDBY"], srt.py:31) but not on the TRIGGER -- see
# _STANDBY_ROW_IMAGES.
RESERVE_STANDBY_JOBID = "1102"

# 시트맵예약 (seat-map / seat-designated reservation). Emitted by
# personal_reservation_payload when designated_seats is given, and by nothing
# else. The value is evidenced twice: the app's own gloss on its form seed
# (ara0101v.js:90) and the single write, on the ARC0201C branch that navigates
# to the seat-map page (ara1001l.js:1435-1436).
#
# WHAT IS EVIDENCED AND WHAT IS NOT, because the difference matters more here
# than anywhere else in this module:
#
#   * The field family IS evidenced, in full, at ara0101v.js:866-882 -- see
#     _seat_designation_fields for the line-by-line reading.
#   * The SUBMIT TARGET IS NOT. The seat callback ends in `fn_submit()`, which
#     has exactly one hit in all 21,673 bundle files, the call site itself
#     (ara0101v.js:882); its definition lives in the server-rendered booking
#     page. The line immediately below it is the commented-out
#     `//Sr.ara1001l.fn_callReserv();` -- the function that serialises #rsvForm
#     and POSTs /arc/selectListArc05013_n.do (ara1001l.js:1541-1550) -- which
#     is why this library sends a designated reservation there. That is an
#     INFERENCE from a comment, not a capture, and it is the single thing an
#     operator must settle; see SrtClient.reserve.
RESERVE_SEATMAP_JOBID = "1103"

# 여정유형코드 (jrnyTpCd). Two values exist and the app's own common-code table
# names both: 11 = 편도, rmk 직통, and 14 = 환승편도, rmk 환승
# (commCode.js:296-309). The booking screen repeats the gloss inline --
# "jrnyTpCd" :"11"  //여정유형코드(11:편도, 14:환승편도) (ara0101v.js:91) -- and the
# 환승 toggle is the one place 14 is written (ara0101v.js:302, emitted :310).
JOURNEY_TYPE_ONE_WAY = "11"
JOURNEY_TYPE_TRANSFER = "14"

# 여정건수 (jrnyCnt). One journey for 편도, TWO for 환승, set together with
# jrnyTpCd="14" in the single branch that toggles 환승 (ara0101v.js:302-303,
# emitted :310-311). That branch is the ONLY write of jrnyCnt="2" in the entire
# v2.0.41 bundle -- the other two hits are the seed "1" (:92) and a null-check
# read (ara1001l.js:1654) -- which is why jrnyCnt="2" means transfer and never
# round trip.
JOURNEY_COUNT_ONE_WAY = "1"
JOURNEY_COUNT_TRANSFER = "2"

# 여정일련번호 (jrnySqno) slot values, glossed by the app on its own seed:
# "jrnySqno1" : "001"  //여정일련번호1(001:선행, 002:후행) (ara0101v.js:97), repeated
# at ara1001l.js:1611 as "0001 : 선행, 0002 : 후행". 선행 is the leading leg, 후행
# the following one, so a transfer's second leg is slot 2 / value "002".
JOURNEY_SEQUENCE_LEADING = "001"
JOURNEY_SEQUENCE_FOLLOWING = "002"

# 직통환승구분 (chtnDvCd) on the SEARCH request, derived from jrnyTpCd by the app
# itself: `var sChtnDvCd = lfn_getRsv("jrnyTpCd") == "11" ? "1" : "2";
# //직통:1, 환승:2` (ara1001l.js:98), sent at :159. It is also a COLUMN on every
# search row (ara1001l.js:1206 reads item.chtnDvCd, and the 2026-07-26 live
# capture has it on every dsOutput1 row).
SEARCH_CONNECTION_DIRECT = "1"
SEARCH_CONNECTION_TRANSFER = "2"

# The app's own refusal to reserve half a 환승 itinerary, verbatim
# (messages.js:217, message id rsv023): "you must select BOTH the leading and
# the following train". The string is DEFINED and never referenced anywhere in
# the bundle -- the screen that would raise it is server-rendered -- but it is
# the app stating the rule TransferItinerary enforces, in the app's own words,
# so the builder raises with it rather than inventing wording.
TRANSFER_BOTH_LEGS_MESSAGE = (
    "선택하신 열차는 선행 및 후행 열차를 모두 선택하셔야 예약이 가능합니다."
)

# How each 여정 slot-2 key of a 환승 reservation form is known. Recorded as DATA
# rather than prose because the honest answer differs per key, and pinned by a
# test so that nothing here can quietly graduate to a stronger tier:
#
#   "web"      -- the literal `...2` string is in the offline WEB bundle
#                 (assets/offline/js), i.e. in the booking flow itself.
#   "native"   -- the literal `...2` string is in the app's NATIVE two-leg
#                 model: the offline-ticket parser at
#                 analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:746-834,
#                 which reads a whole second leg out of a saved ticket and is
#                 switched on by `isTransfer` == "true" (:815, consumed at
#                 a.java:82 and :133). That is the app's own naming for a
#                 transfer's second leg, from the ticket side rather than the
#                 booking side.
#   "hydrated" -- ZERO hits in the bundle. Already emitted by
#                 search_page_payload on the Ara10007 hydration GET, which the
#                 live server has accepted on every live run, and listed as a
#                 booking-page hidden input by the 2026-07-09 survey
#                 (docs/analysis/srt-app-api-library-spec-2026-07-09.md:162-170).
#   "inferred" -- ZERO hits anywhere, in any form. Slot 1's name from
#                 fn_moveRsv (ara1001l.js:1453-1468) with the suffix changed to
#                 2, which is the rule every "web" and "native" entry obeys.
#
# The server-rendered #rsvForm is not in the bundle -- the app POSTs
# $("#rsvForm").serialize() (ara1001l.js:1550) -- so the hydrated and inferred
# tiers cannot be settled offline. They are a capture away, not a guess away.
#
# THE 2026-07-26 LIVE TRANSFER SEARCH DID NOT MOVE ANY TIER, AND THAT IS THE
# POINT. It settled the RESPONSE (one row per leg, paired by trnOrdrNo -- see
# parsers.pair_transfer_itineraries) and it showed that a search ROW carries
# ...2 columns as EMPTY STRINGS: trnNo2 "", dptRsStnCd2 "", jrnySqno "". Those
# are blank because the second leg arrives as its own ROW, so there is nothing
# for the columns to hold -- which says nothing whatsoever about whether the
# RESERVATION form wants them filled. A response column and a request field that
# share a name are still two different things, and only a reserve capture can
# settle the request side. The five INFERRED names below remain inferred.
TRANSFER_SLOT2_FIELD_EVIDENCE = {
    # ara1001l.js:1209-1216, the 운임요금 (Ara13010) params: the app sends
    # dptRsStnCd2/arvRsStnCd2/runDt2/trnNo2 verbatim, blank for a direct
    # journey -- and the LIVE fare page (captured 2026-07-26, reproduced at
    # tests/fixtures/fare_transfer_placeholder.html) renders a whole second leg
    # from them, with its own selectTransferTrain() toggle.
    "dptRsStnCd2": "web",
    "arvRsStnCd2": "web",
    "runDt2": "web",
    "trnNo2": "web",  # also native, b.java:827
    # ara0101v.js:136-140 seeds them; :775-777 writes them with slot 1's VALUES,
    # which is why this builder mirrors the seat preference across both legs.
    "smkSeatAttCd2": "web",
    "dirSeatAttCd2": "web",
    "locSeatAttCd2": "web",
    "rqSeatAttCd2": "web",
    "etcSeatAttCd2": "web",
    # b.java:785 (psrmClCd2), :791, :794, :800, :803. The native offline ticket
    # carries the second leg's cabin class and its four date/time fields under
    # exactly these names.
    "psrmClCd2": "native",
    "dptDt2": "native",
    "dptTm2": "native",
    "arvDt2": "native",
    "arvTm2": "native",
    # 0-hit in the bundle. jrnySqno2's VALUE is nonetheless glossed by the app
    # ("002:후행", ara0101v.js:97), so only the key name is unattested here.
    "jrnySqno2": "hydrated",
    "trnGpCd2": "hydrated",
    "dptRsStnCdNm2": "hydrated",
    "arvRsStnCdNm2": "hydrated",
    # 0-hit in any form. Slot 1's name with the suffix changed, and nothing more.
    "stlbTrnClsfCd2": "inferred",
    "dptStnConsOrdr2": "inferred",
    "arvStnConsOrdr2": "inferred",
    "dptStnRunOrdr2": "inferred",
    "arvStnRunOrdr2": "inferred",
}

# The 예약대기 row images (ara1001l.js:32-33). The SERVER sends
# grd_WF_Waiting.png; the app rewrites it to the _S ("selected") spelling when
# the row is tapped (:1045, :1058), and fn_moveRsv then tests for the _S form
# (:1447). A library never performs that rewrite, so both spellings count as the
# same signal.
#
# THIS IS WHERE THE BUNDLE AND srtgo DISAGREE, and the bundle wins. srtgo picks
# standby off `reserve_wait_possible_code >= 0` (rsvWaitPsbCd); our app never
# reads rsvWaitPsbCd for this decision at all -- it reads gnrmRsvPsbImg. The two
# are not interchangeable: rsvWaitPsbCd is present on personal search rows and
# ABSENT from group ones (Ara10082 omits it, as our own fixtures show), while
# gnrmRsvPsbImg is on both.
_STANDBY_ROW_IMAGES = frozenset(
    {
        "IMAGE::grd_WF_Waiting.png",
        "IMAGE::grd_WF_Waiting_S.png",
    }
)

# The minimum party size the app enforces for a 단체 (group) search, and the
# maximum it allows without one. ara0101v.js:549-566, on the 조회하기 button:
# 단체 checked with totPrnb < 10 alerts "단체예약은 10매 이상입니다." and returns
# without sending; 단체 unchecked with totPrnb > 9 alerts "10매 이상은
# 단체예약입니다." and returns. So 10 is a real, client-enforced boundary in both
# directions, not a UI hint.
#
# The one consumer is group_search_ajax_payload. Group BOOKING was removed on
# 2026-07-26 (Arc06014 answers with a payment page, not a hold -- see
# docs/IMPLEMENTATION_PROGRESS.md "단체 (group) booking: removed"), and this
# floor survived that removal because the group SEARCH is still offered and the
# app enforces the same number on it.
#
# The CEILING on personal searches is enforced too, but NOT in this module.
# ara0101v.js:562-567 refuses a non-단체 search of 10 or more, and no builder
# here can reproduce that: search_page_payload hydrates the group flow as well,
# so a cap applied at this layer would refuse the very searches this floor
# exists to allow. The check therefore lives one layer up, in
# SrtClient._prepare_search, which receives the `group: bool` that tells the two
# flows apart. This comment used to read as though the ceiling could not be
# enforced at all, which is what kept it on the deferred list.
GROUP_MIN_PARTY_SIZE = 10

# WINDOW_SEAT mapping (srtgo srt.py:86): None -> "000" (no preference),
# True -> "012" (window), False -> "013" (aisle). Fed into locSeatAttCd1.
_WINDOW_SEAT_CODES = {None: "000", True: "012", False: "013"}

# The SRT train class code (stlbTrnClsfCd) whose TRAIN_NAME is "SRT" (srtgo
# TRAIN_NAME "17" -> "SRT", srt.py:82). srtgo's _reserve refuses any train whose
# train_name != "SRT" (srt.py:950-951); this is the equivalent evidence-based
# SRT-only guard for the reservation route.
_SRT_TRAIN_CLASS_CODE = "17"


TRAIN_GROUP_OPTIONS = {
    "300": ("SRT", "17"),
    "900": ("KTX+SRT", "00"),
    "109": ("전체", "05"),
}
# The SIX psgTpCd slots, in the positional order the app compacts them in, paired
# with the PassengerCounts attribute each one's count comes from.
#
# THIS TUPLE USED TO BE FIVE, and said so as a fact: "there is NO infant / psgTpCd
# 6: SRT has no infant type and the string infantCnt appears nowhere in the app".
# That was true of the v2.0.41 offline bundle and FALSE of the live server. The
# mistake is worth naming because it is repeatable: it read "absent from the
# bundle" as "absent from the protocol".
#
# `psgTpCd` 6 is 청소년, and it is in NEITHER copy of commCode.js -- not v2.0.41,
# not the live /js/commCode.js fetched 2026-07-26, both of which stop at 5. It
# exists only in what the server renders on the 공공할인 path, where the 승차인원
# 선택 popup reveals a seventh counter (`passenger7`, display:none unless the
# 공공할인 code is "04") and the 할인 승차권 page maps it to
# psgTpCd6/psgInfoPerPrnb6 (setPassenger_callback).
#
# 유아 is NOT here, and its absence is the app's rule rather than an omission: an
# infant has no psgTpCd of its own. It is folded into the 어린이 slot's COUNT and
# declared separately as `infantCnt`. See PassengerCounts.child_slot_count and
# _passenger_slot_counts below.
#
# BOTH RULES ARE LIVE-VERIFIED (2026-07-26), by the cheapest possible read: the
# search route echoes the request back in its own commandMap.
#   * adult=1, child=2, infant=3 came back as psgTpCd2="5",
#     psgInfoPerPrnb2="5" and infantCnt="3" -- the fold and the separate
#     declaration, both, from one infant count;
#   * adult=1, youth=1 came back as psgTpCd2="6", psgInfoPerPrnb2="1".
# Both searches returned ten train rows, so the server processed them normally
# and rejected neither the folded count nor psgTpCd 6.
PASSENGER_TYPE_CODES = (
    ("adult", "1"),
    ("disability_1_to_3", "2"),
    ("disability_4_to_6", "3"),
    ("senior", "4"),
    # NOT `child`: the count this slot carries is child + infant.
    ("child_slot_count", "5"),
    ("youth", "6"),
)
# How many psgTpCd slots the padded (search / fare) forms transmit.
#
# FIVE is what the booking page sends: goRevFn loops `i = 1..5` and leaves the
# psgTpCd6 input it has in the DOM untouched (the two lines that would reset it
# are commented out in the live page). That five-slot body is the one verified
# byte-for-byte against the live server in the 2026-07-25 reserve->cancel round
# trip, so it is what a party with no 청소년 keeps sending, unchanged.
#
# SIX is what the page that CAN express 청소년 sends: ARA0301V builds an `oData`
# of six slots and writes all six to the form. A party with a 청소년 needs the
# sixth slot to exist, and is by definition on that page's path.
#
# So the slot count follows which of the two pages the party could have been
# assembled on, and a party without a 청소년 is bit-identical to before.
PADDED_PASSENGER_SLOTS = 5
PADDED_PASSENGER_SLOTS_WITH_YOUTH = 6
# 유아, declared separately from the 어린이 slot it was folded into. The live
# booking form carries this field ALWAYS, `infantCnt=0` included; this library
# emits it only when it is non-zero, so that a party with no infant produces the
# exact body the live round trip verified. Sending a field the server already
# defaults to 0 would buy nothing and would retire that evidence.
INFANT_COUNT_FIELD = "infantCnt"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def station_selector_payload(
    departure_name: str,
    arrival_name: str,
    departure_code: str,
    arrival_code: str,
) -> dict[str, str]:
    # The app's station picker posts only these keys (ara0101v.js:158-165); it does
    # not send chk_rtrp / page / boolRtrp.
    return {
        "reqCode": "1",
        "sDptStnNm": _required_text(departure_name, "departure_name"),
        "sArvStnNm": _required_text(arrival_name, "arrival_name"),
        "sDptStnCd": _required_text(departure_code, "departure_code"),
        "sArvStnCd": _required_text(arrival_code, "arrival_code"),
        "sNowSel": "1",
    }


def station_map_selector_payload() -> dict[str, str]:
    # Mirrors the station picker's param set (ara0101v.js:158-165) minus the
    # station-name/code fields: no chk_rtrp / page / boolRtrp.
    return {
        "reqCode": "2",
        "sNowSel": "1",
    }


def date_selector_payload(date: str) -> dict[str, str]:
    if not isinstance(date, str) or len(date) != 8 or not date.isdigit():
        raise ValueError("date must use YYYYMMDD")
    # The app's date-picker request carries only reqCode/selectDay/selectDt; the SRT
    # picker returns a date only, so there is no selectTime field (ara0101v.js:187-191).
    return {
        "reqCode": "3",
        "selectDay": "",
        "selectDt": date,
    }


def reservation_list_payload(page_no: int = 0) -> dict[str, str]:
    """The body of the 예약/발권 목록 read (``/atc/selectListAtc14016_n.do``).

    One field, ``pageNo``, and that is the whole form. It is the same parameter
    the app puts in the query string when its WebView opens this path
    (``SRForegroundDialogActivity.java:31``,
    ``https://app.srail.co.kr/neo/atc/selectListAtc14016_n.do?pageNo=0``; and the
    leftover ``data-url`` on ``sub/ticketList.html:405``) and the same body srtgo
    POSTs (``srt.py`` ``get_reservations``: ``data = {"pageNo": "0"}``). The live
    server echoed it back verbatim on 2026-07-26 as
    ``commandMap: {"pageNo": "0"}``, which is the strongest available
    confirmation that the field name is right: the response quotes the request.

    ``page_no`` is stringified rather than validated against a range, because
    the response tells the caller how many pages exist (``totPageCnt``) and
    nothing in the bundle or in any observed response bounds it from our side.
    A negative or non-integer value is refused, since neither can mean a page.
    """
    if type(page_no) is not int or page_no < 0:
        raise ValueError("page_no must be a non-negative non-boolean integer")
    return {"pageNo": str(page_no)}


def passenger_selector_payload(passengers: PassengerCounts) -> dict[str, str]:
    # passengerN here is the POPUP's own numbering, which is NOT psgTpCd and not
    # the wire numbering used anywhere else in this module:
    #   1=어른, 2=중증 장애인, 3=경증 장애인, 4=경로, 5=어린이, 6=유아, 7=청소년.
    # Read off the live popup's labels and its returnPassenger (2026-07-26); the
    # bundle's request/callback pair is ara0101v.js:213-238 / :795-804.
    #
    # Note especially that `passenger5` is the UNFOLDED 어린이 count and
    # `passenger6` is 유아 as its own counter -- the fold into psgTpCd 5 happens
    # on the page that RECEIVES this popup's answer, not in the popup. So this
    # builder must send `passengers.child`, never `child_slot_count`; sending the
    # folded number would seed the picker with infants counted twice.
    #
    # 6 and 7 are emitted ONLY when non-zero, which keeps a party without either
    # byte-identical to what this builder sent before they existed.
    #
    # WHAT THE LIVE SERVER DOES WITH THEM, probed 2026-07-26: it ACCEPTS them and
    # echoes them in the page's own commandMap dump --
    #   {reqCode=6, isOrg=2, passenger1=1, ..., totalPessnger=2, passenger6=1, sNowSel=1}
    # -- and does NOT seed them back into the DOM, because the seeding branch
    # writes only passenger1..5. So the rendered counters for 유아 and 청소년 come
    # back at 0 no matter what is sent. Sending them is therefore honest rather
    # than effective: the request carries what the caller asked for, and the popup
    # is a picker whose answer the caller was going to replace anyway.
    #
    # The 청소년 row additionally stays `display:none` regardless, because the page
    # reveals it only when the SERVER renders `pblDiscCd == "04"` into it -- an
    # account-level fact, not a request parameter. Confirmed on the same probe.
    fields = {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": str(passengers.adult),
        "passenger2": str(passengers.disability_1_to_3),
        "passenger3": str(passengers.disability_4_to_6),
        "passenger4": str(passengers.senior),
        "passenger5": str(passengers.child),
        "totalPessnger": str(passengers.total),
    }
    if passengers.infant:
        fields["passenger6"] = str(passengers.infant)
    if passengers.youth:
        fields["passenger7"] = str(passengers.youth)
    return fields


def seat_option_selector_payload(
    request_seat_attr_code: str = "015",
    location_seat_attr_code: str = "000",
    seat_name: str = "일반/기본",
) -> dict[str, str]:
    return {
        "reqCode": "5",
        "rqSeatAttCd": _required_text(request_seat_attr_code, "request_seat_attr_code"),
        "locSeatAttCd": _required_text(location_seat_attr_code, "location_seat_attr_code"),
        "seatAttNm": _required_text(seat_name, "seat_name"),
    }


def train_group_selector_payload(
    train_group_code: SrtTrainGroupCode = "109",
    train_group_name: str = "전체",
) -> dict[str, str]:
    if train_group_code not in TRAIN_GROUP_OPTIONS:
        raise ValueError("train_group_code must be one of 300, 900, or 109")
    return {
        "reqCode": "7",
        "trnGpCd": train_group_code,
        "trnGpCdNm": _required_text(train_group_name, "train_group_name"),
    }


def _passenger_slot_counts(passengers: PassengerCounts) -> list[tuple[str, int]]:
    """All six (psgTpCd, count) pairs in canonical order, 유아 already folded in.

    The one place the fold happens. Slot 5's count is
    ``PassengerCounts.child_slot_count`` (어린이 + 유아), never ``child``, so no
    caller downstream can accidentally emit the unfolded number.
    """
    return [
        (type_code, getattr(passengers, attribute))
        for attribute, type_code in PASSENGER_TYPE_CODES
    ]


def _padded_slot_count(passengers: PassengerCounts) -> int:
    # See PADDED_PASSENGER_SLOTS: five for a party the booking page could have
    # assembled, six once a 청소년 is present and only the 할인 승차권 page could.
    return (
        PADDED_PASSENGER_SLOTS_WITH_YOUTH
        if passengers.youth
        else PADDED_PASSENGER_SLOTS
    )


def _compact_passenger_slots(passengers: PassengerCounts) -> list[tuple[str, int]]:
    # The app packs only the count>0 passenger types into contiguous slots, in
    # canonical psgTpCd order (ara0101v.js:824-836 for five, ARA0301V's
    # setPassenger_callback for the same loop over six):
    #   idx=1; for i in 1..N: if psgInfoPerPrnb[i] > 0: psgTpCd[idx]=code[i];
    #                                                   psgInfoPerPrnb[idx]=count[i]; idx++
    # Returns the (psgTpCd, count) pairs for the filled slots, in order. Shared by
    # the search psgTpCd builder (B1), the fare builder (B3) and the reservation
    # builder, so all three fold 유아 identically and order 청소년 last.
    #
    # A party of infants and no children still fills slot 5, because the app tests
    # the SUM: `if(passenger != '' && passenger != '0')` runs after
    # `passenger = passenger + passenger6`.
    return [
        (type_code, count)
        for type_code, count in _passenger_slot_counts(passengers)
        if count > 0
    ]


def _passenger_fields(
    passengers: PassengerCounts,
    hydrated_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    # Emit the COMPACTED psgTpCd1..N / psgInfoPerPrnb1..N, then leave the trailing slots
    # empty. The app seeds them all as psgTpCd="" / psgInfoPerPrnb="0" and overwrites
    # only the first N filled ones (ara0101v.js:808-836), so the trailing slots are SENT
    # (psgTpCd="", psgInfoPerPrnb="0"), not omitted.
    #
    # `infantCnt` is NOT emitted here, because this builder is shared with the fare
    # request and the fare request does not carry it: the live fare params are
    # psgTpCd1..6/psgInfoPerPrnb1..6 and nothing else from the passenger family. The
    # search call sites add it themselves.
    hydrated_fields = hydrated_fields or {}
    slots = _compact_passenger_slots(passengers)
    fields: dict[str, str] = {}
    for index in range(1, _padded_slot_count(passengers) + 1):
        if index <= len(slots):
            type_code, count = slots[index - 1]
            hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")
            fields[f"psgTpCd{index}"] = hydrated_code or type_code
            fields[f"psgInfoPerPrnb{index}"] = str(count)
        else:
            fields[f"psgTpCd{index}"] = ""
            fields[f"psgInfoPerPrnb{index}"] = "0"
    return fields


def _infant_count_field(passengers: PassengerCounts) -> dict[str, str]:
    # 유아 is declared a second time, next to the 어린이 slot it was folded into
    # (`$('#infantCnt').val(passenger6)` on the booking page,
    # `$("#infantCnt").val(obj.passenger6)` on the 할인 승차권 page).
    #
    # Emitted only when non-zero. The live form always carries `infantCnt=0`, and
    # sending that would change every existing body by one field while telling the
    # server exactly what it already assumes -- retiring the byte-for-byte evidence
    # from the 2026-07-25 live reserve->cancel round trip in exchange for nothing.
    return {INFANT_COUNT_FIELD: str(passengers.infant)} if passengers.infant else {}


def _distinct_passenger_type_count(passengers: PassengerCounts) -> int:
    # psgGridcnt is the number of distinct passenger TYPES with count>0, NOT the head
    # count: the app sets psgGridcnt=idx-1 (occupied type count, ara0101v.js:826-836)
    # and srtgo uses len(combined_passengers) (srt.py:191). Reuse the compaction helper
    # so psgGridcnt always equals the number of filled psgTpCd slots (B1).
    #
    # A 유아 therefore does NOT add a type -- it was folded into 어린이 -- while a
    # 청소년 does, being psgTpCd 6 in its own right.
    return len(_compact_passenger_slots(passengers))


def search_page_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    transfer: bool = False,
) -> dict[str, str]:
    """Build the Ara10007 hydration GET that seeds the booking form.

    ``transfer=True`` changes exactly the two fields the app's 환승 toggle
    changes, and nothing else: ``jrnyTpCd`` ``"11"`` -> ``"14"`` (환승편도) and
    ``jrnyCnt`` ``"1"`` -> ``"2"``. That single ``lfn_setRsv`` call is the whole
    toggle (``ara0101v.js:302-303``, emitted at ``:310-311``); notably it does
    NOT touch ``jrnySqno2`` or any other slot-2 key, so neither does this.
    """
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = {
        "jobId": "1101",
        "jrnyTpCd": JOURNEY_TYPE_TRANSFER if transfer else JOURNEY_TYPE_ONE_WAY,
        "jrnyCnt": JOURNEY_COUNT_TRANSFER if transfer else JOURNEY_COUNT_ONE_WAY,
        "grpDv": "0",
        "rtnDv": "0",
        "stlbTrnClsfCd1": service_class,
        "stndFlg": "N",
        "jrnySqno1": "001",
        "jrnySqno2": "",
        "trnGpCd1": query.train_group_code,
        "trnGpCd2": "",
        "trnGpNm1": group_name,
        "trnGpNm2": "",
        "dptRsStnCd1": query.departure_station_code,
        "dptRsStnCd2": "",
        "dptRsStnCdNm1": query.departure_station_name or query.departure_station_code,
        "dptRsStnCdNm2": "",
        "arvRsStnCd1": query.arrival_station_code,
        "arvRsStnCd2": "",
        "arvRsStnCdNm1": query.arrival_station_name or query.arrival_station_code,
        "arvRsStnCdNm2": "",
        "dptDt1": query.departure_date,
        "dptTm1": query.departure_time,
        "dptTm2": "",
        "arvDt1": "",
        "arvTm1": "",
        "totPrnb": str(query.passengers.total),
        "totPrnbNm": f"{query.passengers.total}명",
        "psgGridcnt": str(_distinct_passenger_type_count(query.passengers)),
        "smkSeatAttCd1": "000",
        "dirSeatAttCd1": "009",
        "locSeatAttCd1": "000",
        "rqSeatAttCd1": query.seat_attr_code,
        "etcSeatAttCd1": "000",
        "seatAttNm1": "일반/기본",
        "seatAttCd": query.seat_attr_code,
        "netfunnelKey": netfunnel_key,
        "adjStnScdlOfrFlg": "N",
        "pnrNo": "",
        "JRNYLIST_KEY": "",
    }
    payload.update(_passenger_fields(query.passengers))
    payload.update(_infant_count_field(query.passengers))
    for leg in (1, 2):
        for index in range(1, 10):
            payload[f"seatNo{leg}_{index}"] = ""
    return payload


def search_ajax_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    hydrated_fields: dict[str, str],
    transfer: bool = False,
) -> dict[str, str]:
    """Build the Ara10007 search POST.

    ``transfer=True`` sets ``chtnDvCd`` to ``"2"`` (환승) instead of ``"1"``
    (직통), and that is the ENTIRE request delta. The app derives the field the
    same way and sends the same body either way::

        var sChtnDvCd = lfn_getRsv("jrnyTpCd") == "11" ? "1" : "2"; //직통:1, 환승:2

    (``ara1001l.js:98``, sent at ``:159``). The URL does not change with it —
    ``:174-181`` picks the endpoint from ``grpDv`` alone, so 직통 and 환승 share
    ``/ara/selectListAra10007_n.do`` (and ``Ara10082`` for a group). ``chtnDvCd``
    is also a COLUMN on every returned row (``:1206``), which is how a caller can
    tell what it got back.
    """
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = dict(hydrated_fields)
    payload.update(
        {
            "chtnDvCd": (
                SEARCH_CONNECTION_TRANSFER if transfer else SEARCH_CONNECTION_DIRECT
            ),
            "dptDt": query.departure_date,
            "dptTm": query.departure_time,
            "dptDt1": query.departure_date,
            "dptTm1": query.departure_time,
            "dptRsStnCd": query.departure_station_code,
            "arvRsStnCd": query.arrival_station_code,
            "stlbTrnClsfCd": service_class,
            "trnGpCd": query.train_group_code,
            "trnGpNm1": group_name,
            "trnNo": "",
            "psgNum": str(query.passengers.total),
            "seatAttCd": query.seat_attr_code,
            "arriveTime": "N",
            "tkDptDt": "",
            "tkDptTm": "",
            "tkTrnNo": "",
            "tkTripChgFlg": "",
            "dlayTnumAplFlg": "Y",
            "netfunnelKey": netfunnel_key,
            "disability": "N",
            "adjStnScdlOfrFlg": "N",
        }
    )
    payload.update(_passenger_fields(query.passengers, hydrated_fields))
    payload.update(_infant_count_field(query.passengers))
    payload.pop("fllwPgExt", None)
    return payload


def group_search_ajax_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    hydrated_fields: dict[str, str],
) -> dict[str, str]:
    # The app requires a group booking to be >=10 people and rejects it client-side
    # otherwise (ara0101v.js:551-554 alerts and returns without sending a request). It
    # never bumps psgNum: psgNum is always == totPrnb == passengers.total for both
    # individual and group searches (ara1001l.js:104 sPsgNum=lfn_getRsv("totPrnb"), :165
    # "psgNum":sPsgNum). Mirror the app's own guard instead of silently clamping psgNum to
    # 10 while totPrnb stays below it (which would emit a psgNum!=totPrnb payload the app
    # would never send).
    if query.passengers.total < GROUP_MIN_PARTY_SIZE:
        raise ValueError(
            "group search requires at least "
            f"{GROUP_MIN_PARTY_SIZE} passengers (totPrnb >= {GROUP_MIN_PARTY_SIZE})"
        )
    payload = search_ajax_payload(query, netfunnel_key, hydrated_fields=hydrated_fields)
    payload["grpDv"] = "1"
    payload["psgNum"] = str(query.passengers.total)
    return payload


def search_continuation_payload(
    hydrated_ajax_payload: dict[str, str],
    last_departure_time: str | None,
) -> dict[str, str]:
    departure_time = _required_digits(
        last_departure_time,
        "last_departure_time",
        length=6,
    )
    payload = dict(hydrated_ajax_payload)
    payload.pop("fllwPgExt", None)
    payload["dptTm"] = departure_time[:5] + "1"
    payload["trnNo"] = ""
    return payload


def _required_digits(
    value: str | None,
    name: str,
    *,
    length: int | None = None,
    max_length: int | None = None,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(character < "0" or character > "9" for character in value)
    ):
        raise ValueError(f"{name} must contain only digits")
    if length is not None and len(value) != length:
        raise ValueError(f"{name} must contain exactly {length} digits")
    if max_length is not None and len(value) > max_length:
        raise ValueError(f"{name} must contain at most {max_length} digits")
    return value


def seat_page_payload(
    train: TrainSummary,
    cabin_class: str = "1",
    seat_count: str = "1",
    *,
    seat_attr_code: str = "015",
) -> dict[str, str]:
    if train.train_group_code != "300":
        raise ValueError("train_group_code must be 300 for an SRT seat page")
    if cabin_class not in {"1", "2"}:
        raise ValueError("cabin_class must be '1' (일반실) or '2' (특실)")
    # choiceSeatCount is the total passenger count (app: lfn_getRsv("totPrnb"),
    # ara1001l.js:1511), not a fixed '1'; validate it as a positive integer.
    if not isinstance(seat_count, str) or re.fullmatch(r"[1-9][0-9]*", seat_count) is None:
        raise ValueError("seat_count must be a positive integer")
    train_no = _required_digits(train.train_no, "train_no", max_length=5).zfill(5)
    return {
        "reqCode": "9",
        "runDt": _required_digits(train.run_date, "run_date", length=8),
        "dptDt": _required_digits(train.departure_date, "departure_date", length=8),
        "trnNo": train_no,
        "dptTm": _required_digits(train.departure_time, "departure_time", length=6),
        "trnGpCd": "300",
        "dptRsStnCd": _required_digits(
            train.departure_station_code,
            "departure_station_code",
            length=4,
        ),
        "arvRsStnCd": _required_digits(
            train.arrival_station_code,
            "arrival_station_code",
            length=4,
        ),
        "psrmClCd": cabin_class,
        # seatAttCd is sourced from the REQUEST side, not the search-response row: the
        # app sends seatAttCd = lfn_getRsv("rqSeatAttCd1"), which is seeded to the
        # constant "015" (ara1001l.js:1508; ara0101v.js:132). srtgo confirms the design
        # -- it hardcodes rqSeatAttCd1="015" (srt.py:193) and its row parser never reads
        # a row seatAttCd. So we default to "015" and let a caller pass the
        # seat-attribute code they searched with.
        #
        # CORRECTION, live capture 2026-07-26: this comment used to add that "real
        # dsOutput1 rows omit seatAttCd" and that the field "is not carried by
        # genuine responses". That is FALSE. Every one of the 40 live rows
        # carried seatAttCd, and every one carried "015" -- the value the request
        # had just sent. The row is echoing our own request back, which is why
        # reading it would be circular and why the request-side sourcing above is
        # still the right design. The claim was wrong; the behaviour was not.
        "seatAttCd": _required_digits(seat_attr_code, "seat_attr_code", length=3),
        "dptStnRunOrdr": _required_digits(
            train.departure_run_order,
            "departure_run_order",
        ),
        "arvStnRunOrdr": _required_digits(
            train.arrival_run_order,
            "arrival_run_order",
        ),
        "choiceSeatCount": seat_count,
    }


# The five-character 열차번호 the seat routes require, and the app's own reason
# for it. main.html:642-661 defines lfn_getTrNoData with the comment
# "열차번호를 5자리로 채워서 가져옴" ("get the train number padded to 5 digits")
# and pads a 3- or 4-character number with leading zeros; ara1001l.js:1461 is
# the one place trnNo1 is written, and it writes lfn_getTrNoData(item.trnNo).
# The seat page's own inline script re-does the same padding before serialising
# trnScarSeatFrm.
#
# THIS IS THE GATE ON THE SEAT GRID, live-confirmed 2026-07-26: the identical
# request with trnNo=315 returns a 147-byte alert shell, and with trnNo=00315
# returns the seat grid (25,930 bytes, 74 cells). Referer and route length
# change nothing; the padding is the whole difference. The alert text that
# comes back unpadded ("출발 20분 전부터 좌석이 자동배정됩니다...") reads like a
# timing rule and is not one -- it is what this server says when it cannot find
# the train, and believing it is what kept this endpoint closed.
SEAT_TRAIN_NUMBER_LENGTH = 5


def seat_grid_payload(
    train: TrainSummary,
    car_number: str,
    cabin_class: str = "1",
    seat_count: str = "1",
    *,
    seat_attr_code: str = "015",
) -> dict[str, str]:
    """Build the 좌석배치도 request for ``/arc/selectListArc02011_n.do``.

    This is ``trnScarSeatFrm`` serialised, which is what the seat page's own
    inline script does when a 호차 is picked::

        trnScarSeatFrm.trnNo.value = <trnNo padded to 5>
        params = $("#trnScarSeatFrm").serialize();
        $.ajax({type: "POST", url: "/arc/selectListArc02011_n.do",
                data: params, dataType: "html", ...})

    Eleven fields, in the order the live page declares them. Two independent
    offline records agree on that set: the 2026-07-15 structural capture
    retained as ``tests/fixtures/seat_page_schema_v2_evidence.json`` (which also
    pins the route and the POST) and the 2026-07-26 live read of the page
    itself. The route and the form are both 0-hit in the v2.0.41 bundle — they
    exist only in what the server renders.

    The fields are the seat PAGE's fields minus ``reqCode``, ``dptDt`` and
    ``dptTm``, plus ``scarNo`` — the 호차 being opened, which the page leaves
    empty until one is chosen. ``dptStnRunOrdr``/``arvStnRunOrdr`` come from the
    train row, exactly as they do for the seat page; taking them from anywhere
    else is what made an earlier hand-built probe fail.

    See :data:`SEAT_TRAIN_NUMBER_LENGTH` for the zero-padding, which is the
    single fact that separates a seat grid from an alert shell.
    """
    if train.train_group_code != "300":
        raise ValueError("train_group_code must be 300 for an SRT seat grid")
    if cabin_class not in {"1", "2"}:
        raise ValueError("cabin_class must be '1' (일반실) or '2' (특실)")
    if not isinstance(seat_count, str) or re.fullmatch(r"[1-9][0-9]*", seat_count) is None:
        raise ValueError("seat_count must be a positive integer")
    return {
        "trnGpCd": "300",
        "runDt": _required_digits(train.run_date, "run_date", length=8),
        # THE GATE. See SEAT_TRAIN_NUMBER_LENGTH above.
        "trnNo": _required_digits(train.train_no, "train_no", max_length=5).zfill(
            SEAT_TRAIN_NUMBER_LENGTH
        ),
        "scarNo": _required_digits(car_number, "car_number", max_length=3),
        "psrmClCd": cabin_class,
        "dptRsStnCd": _required_digits(
            train.departure_station_code,
            "departure_station_code",
            length=4,
        ),
        "arvRsStnCd": _required_digits(
            train.arrival_station_code,
            "arrival_station_code",
            length=4,
        ),
        # Request-side, like the seat page's: the app sends
        # lfn_getRsv("rqSeatAttCd1"), seeded "015" (ara0101v.js:132).
        "seatAttCd": _required_digits(seat_attr_code, "seat_attr_code", length=3),
        "dptStnRunOrdr": _required_digits(
            train.departure_run_order,
            "departure_run_order",
        ),
        "arvStnRunOrdr": _required_digits(
            train.arrival_run_order,
            "arrival_run_order",
        ),
        "choiceSeatCount": seat_count,
    }


# getStlbTrnClsfCdNm(), lifted verbatim from the LIVE search page served on
# 2026-07-26 by GET /ara/selectListAra10007_n.do. It maps 역무차종별코드
# (stlbTrnClsfCd) to the display name the timetable and fare forms transmit as
# trnSort. srtgo's TRAIN_NAME table (srt.py:82) agrees on "17" -> "SRT".
STLB_TRAIN_CLASS_NAMES = {
    "00": "KTX",
    "01": "새마을호",
    "02": "무궁화호",
    "03": "통근열차",
    "04": "누리로",
    "05": "전체열차",
    "06": "공항직통",
    "07": "KTX-산천",
    "08": "ITX-새마을",
    "09": "ITX-청춘",
    "10": "KTX-산천",
    "15": "ITX-청춘",
    "16": "KTX-이음",
    "17": "SRT",
    "18": "ITX-마음",
    "19": "KTX-청룡",
}


def stlb_train_class_name(code: str | None) -> str:
    """``getStlbTrnClsfCdNm``: the display name for a 역무차종별코드.

    Returns ``""`` for an unknown code, exactly as the live function's trailing
    ``else return "";`` does.
    """
    return STLB_TRAIN_CLASS_NAMES.get(code or "", "")


def _train_sort(train: TrainSummary) -> str:
    """The ``trnSort`` the app puts on the timetable and fare forms.

    **The live server refutes what this used to do, and this is the correction.**
    Our source said ``trnSort = item.trnClsfCd`` (열차종별코드), citing
    ``ara1001l.js:1184`` and ``:1217`` in the v2.0.41 offline bundle. The page
    the server actually served on 2026-07-26 says otherwise, in both call sites::

        function trainSchedule(trnSortNm, num, stTrnNm, dsTrnNm, qryDtFrom) {
            var trnSortName = getStlbTrnClsfCdNm(trnSortNm);
            var params = { stnCourseNm: ..., trnSort: trnSortName + "", ... }

        var params = {
            ...,
            trnSort: getStlbTrnClsfCdNm(ds_list[rowIndex].stlbTrnClsfCd),
            ...
        }

    So ``trnSort`` is a display NAME derived from ``stlbTrnClsfCd`` — "SRT" for
    an SRT train — not a raw class code, and certainly not ``trnClsfCd``.

    That distinction was invisible offline and expensive in practice: across all
    40 dsOutput1 rows of the same capture, ``trnClsfCd`` was sent ZERO times.
    The field simply is not in a search row. So ``train.train_class_code`` was
    always ``None`` and every timetable and fare request we have ever issued
    carried ``trnSort=`` empty — a value the app never sends.

    ``train_class_code`` is still honoured as a fallback for a caller who set it
    explicitly; it just no longer decides the common case.
    """
    name = stlb_train_class_name(train.service_class_code)
    return name or str(train.train_class_code or "")


def _station_course(train: TrainSummary) -> str:
    # The app always builds stnCourseNm = getStnNameByCd(dptRsStnCd) + "-" +
    # getStnNameByCd(arvRsStnCd) (ara1001l.js:1176-1185 timetable, :1203-1218 fare): a
    # dash-joined pair of station NAMES resolved from the codes, so the "-" and both
    # segments are always present. Prefer a name already carried on the search
    # row/context; otherwise resolve it from the code via the static getStnNameByCd table
    # (stations.py), which yields "" for an unknown code — matching the app — rather than
    # dropping the segment or its separator.
    departure = train.departure_station_name or station_name_by_code(
        train.departure_station_code
    )
    arrival = train.arrival_station_name or station_name_by_code(
        train.arrival_station_code
    )
    return f"{departure}-{arrival}"


def _query_date(train: TrainSummary) -> str:
    """The date the timetable and fare forms carry as ``runDt``.

    **The live server's own page says this is the DEPARTURE date, not the
    operating date.** From the search page served 2026-07-26::

        trainSchedule(trnSortNm, num, stTrnNm, dsTrnNm, qryDtFrom)
            ... runDt: qryDtFrom ...              (the queried date)

        var params = { ..., runDt: ds_list[rowIndex].dptDt,
                            runDt1: ds_list[rowIndex].dptDt, ... }

    We sent ``run_date or departure_date``. The two are identical for a same-day
    service — they were in every row of the capture — so this has never produced
    a wrong request, and it is corrected rather than left because the one case
    where they differ (a past-midnight departure, where runDt is the previous
    day) is exactly the case a fare or timetable lookup would get wrong.

    Note this does NOT generalise to the reserve form, which the same bundle
    shows sending ``runDt1: item.runDt`` alongside ``dptDt1: item.dptDt`` —
    two different row fields, deliberately. ``personal_reservation_payload``
    keeps using the operating date, and that stays right.
    """
    return train.departure_date or train.run_date or ""


def timetable_payload(train: TrainSummary) -> dict[str, str]:
    return {
        "stnCourseNm": _station_course(train),
        "trnSort": _train_sort(train),
        "runDt": _query_date(train),
        "trnNo": train.train_no.zfill(5),
    }


# The live fare form carries SIX passenger slots, one more than the five SRT
# passenger types. Slot 6 is transmitted EMPTY -- "psgTpCd6":"" with
# "psgInfoPerPrnb6":"" (empty, not "0") -- which is exactly how the search
# response's own commandMap echoed it back on 2026-07-26. It is a form slot, not
# a sixth passenger type: SRT still has no infant type, and no code ever fills
# it.
_FARE_TRAILING_SLOT = 6


def fare_payload(train: TrainSummary, passengers: PassengerCounts) -> dict[str, str]:
    """Build the 운임요금 (Ara13010) form the live app transmits.

    **Corrected against the live server on 2026-07-26.** This builder used to
    send ``passenger1..5``, and its comment stated flatly that the form "carries
    no psgTpCd*/psgInfoPerPrnb*/infantCnt", citing ``ara1001l.js:1219-1223``.
    The page the server actually served says the opposite -- there is no
    ``passenger1`` anywhere in it, and both fare call sites send::

        var params = {
            stnCourseNm: getStnNameByCd(dptRsStnCd) + "-" + getStnNameByCd(arvRsStnCd) + "",
            trnSort: getStlbTrnClsfCdNm(stlbTrnClsfCd),
            runDt: dptDt, trnNo: code, chtnDvCd: "1",
            dptRsStnCd1: dptRsStnCd, arvRsStnCd1: arvRsStnCd,
            runDt1: dptDt, trnNo1: code,
            psgTpCd1: $('#psgTpCd1').val(), psgInfoPerPrnb1: $("#psgInfoPerPrnb1").val(),
            ... through psgTpCd6 / psgInfoPerPrnb6 ...
            dptRsStnCd2: '', arvRsStnCd2: '', runDt2: '', trnNo2: ''
        }

    Those DOM inputs are the compacted slots the booking screen seeds, which is
    what ``_passenger_fields`` already produces, so the compaction reasoning was
    right all along -- only the field NAMES were wrong.

    **And the server was silently ignoring them.** The old form was never
    rejected, because the tariff TABLE (adult/child/senior x special/standard)
    does not depend on the party at all -- which is exactly why the divergence
    survived every live smoke run. But the same page also renders an estimated
    TOTAL, and sending the corrected form on 2026-07-26 changed the server's
    answer for the identical journey::

        - <p> 기준</p>                                     <- no party at all
        - <span class="s-tit">특 &nbsp; 실</span><span>0원</span>
        - <span class="s-tit">일반실</span><span>0원</span>
        + <p>어른 1명 기준</p>
        + <span class="s-tit">특 &nbsp; 실</span><span>16,300원</span>
        + <span class="s-tit">일반실</span><span>11,200원</span>

    With ``passenger1..5`` the server saw a party of NOBODY and computed a total
    of zero. The ``trnSort`` correction shows in the same diff: the response
    gained the train-class name it previously had nowhere to render.

    (Both blocks sit inside markup this parser does not surface, so no caller
    was ever shown the 0원 -- but the request was wrong, and only a live
    round trip could show it.)
    """
    run_date = _query_date(train)
    train_no = train.train_no.zfill(5)
    payload = {
        "stnCourseNm": _station_course(train),
        "trnSort": _train_sort(train),
        "runDt": run_date,
        "trnNo": train_no,
        "chtnDvCd": "1",
        "dptRsStnCd1": train.departure_station_code or "",
        "arvRsStnCd1": train.arrival_station_code or "",
        "runDt1": run_date,
        "trnNo1": train_no,
        "dptRsStnCd2": "",
        "arvRsStnCd2": "",
        "runDt2": "",
        "trnNo2": "",
    }
    payload.update(_passenger_fields(passengers))
    # Slot 6 is the fare form's always-EMPTY trailing slot -- UNLESS a 청소년 is
    # aboard, in which case psgTpCd6 is that passenger's real slot and blanking it
    # would drop them from the quote. _passenger_fields has already filled it in
    # that case; only an unfilled slot 6 gets the fare form's "" / "" pair (note
    # psgInfoPerPrnb6 is "" here, not the "0" the search form's unfilled slots use).
    if not payload.get(f"psgTpCd{_FARE_TRAILING_SLOT}"):
        payload[f"psgTpCd{_FARE_TRAILING_SLOT}"] = ""
        payload[f"psgInfoPerPrnb{_FARE_TRAILING_SLOT}"] = ""
    return payload


def _general_seat_available(train: TrainSummary) -> bool:
    # srtgo general_seat_available(): "예약가능" in gnrmRsvPsbStr (srt.py:486-487).
    return "예약가능" in (train.general_seat_availability or "")


def _special_seat_available(train: TrainSummary) -> bool:
    # srtgo special_seat_available(): "예약가능" in sprmRsvPsbStr (srt.py:489-490).
    return "예약가능" in (train.special_seat_availability or "")


def _require_availability(value: str | None, *, seat_type: SeatType, field: str) -> str:
    """Refuse to guess a seat class when the row never stated availability.

    ``None`` here means the search row carried no availability field at all --
    not that the class is sold out. The two were folded together, and the fold
    was expensive: ``"예약가능" in (None or "")`` is ``False``, so
    ``GENERAL_FIRST`` read a missing field as "general is gone" and booked
    특실 instead. That is reachable through the plain
    ``search_trains()`` -> ``reserve()`` path, it costs the caller the fare
    difference, and on ``reserve_transfer`` it applies to both legs because
    slot 2 shares slot 1's decision.

    The app does not make this mistake: ``ara1001l.js:1430-1432`` sets
    ``sPsrmClCd`` to ``1`` or ``2`` only when the matching image says so, and
    leaves it EMPTY otherwise -- never ``2``. srtgo cannot reach the state at
    all, since it reads the availability key without a guard.

    A ``*_FIRST`` seat type is by definition "decide from live availability".
    With no availability to read there is no decision to make, so this raises
    rather than picking a class on the caller's behalf. ``GENERAL_ONLY`` and
    ``SPECIAL_ONLY`` state the class outright and are unaffected.
    """
    if value is None:
        raise SrtProtocolError(
            f"SRT {seat_type.name} needs the train's {field}, and this search "
            "row did not carry it. A missing availability field is not the "
            "same as a sold-out class -- guessing would silently change which "
            "fare is booked. Pass seat_type=SeatType.GENERAL_ONLY or "
            "SeatType.SPECIAL_ONLY to state the class explicitly."
        )
    return value


#: The 요구좌석속성 codes SRT itself dispatches on. 015 is the ordinary seat the
#: search form is seeded with (ara0101v.js:132); 021 and 028 are 휠체어 and
#: 전동휠체어, which ara0101v.js:611-628 gates behind their own consent dialog --
#: they are values a real user reaches, not dead constants. commCode.js lists
#: more, but the rest are the shared KORAIL set with no SRT call site.
SRT_REQUEST_SEAT_ATTR_CODES = frozenset({"015", "021", "028"})
#: 같은 셋의 정적 타입은 :data:`~srt_mobile_api.models.SrtSeatAttrCode` 다. 두
#: 형태가 어긋나지 않는지는 ``tests/test_literal_aliases.py`` 가 검사한다.


def _inherited_seat_attr_code(train: TrainSummary, explicit: str | None) -> str:
    """The 요구좌석속성 to reserve with: the caller's, else the row's, else 015.

    Closing the OTHER half of the discard :func:`_validated_seat_attr_code`
    describes. Validating the value fixed the builders, but the API above them
    still defaulted the argument to the literal "015", so
    ``search_trains(query(seat_attr_code="021"))`` followed by ``reserve(row)``
    went on quietly booking an ordinary seat out of wheelchair inventory --
    the same silent substitution, moved up one layer.

    ``TrainSummary.seat_attr_code`` is parsed from the row's own ``seatAttCd``
    (parsers.py), so the row remembers what it was found with. A caller who
    passes the argument still wins outright; ``None`` means "whatever this row
    is", and only a row that carried nothing falls back to 015.
    """
    if explicit is not None:
        return explicit
    return train.seat_attr_code or "015"


def _validated_seat_attr_code(value: str) -> str:
    """Check a 요구좌석속성 code before it goes into a reservation body.

    This used to be the literal "015" in both reservation builders while the
    SEARCH builders honoured TrainSearchQuery.seat_attr_code. Searching for
    wheelchair inventory with "021" and then reserving a row from those results
    silently sent "015": the same value respected on the way in and discarded on
    the way out, with no warning. Wheelchair and powered-wheelchair seats were
    unreachable through reserve() and reserve_transfer() as a result.

    Note this closes the BUILDER layer only; :func:`_inherited_seat_attr_code`
    is what stops the API layer from re-introducing the same discard through
    its default argument.
    """
    if value not in SRT_REQUEST_SEAT_ATTR_CODES:
        raise SrtProtocolError(
            f"SRT seat_attr_code must be one of "
            f"{sorted(SRT_REQUEST_SEAT_ATTR_CODES)} (015 ordinary, 021 "
            f"wheelchair, 028 powered wheelchair); got {value!r}"
        )
    return value


def _resolve_special_seat(train: TrainSummary, seat_type: SeatType) -> bool:
    # srtgo is_special_seat dispatch (srt.py:955-960): *_ONLY force a class;
    # *_FIRST fall back based on the train's live availability strings.
    if not isinstance(seat_type, SeatType):
        raise ValueError("seat_type must be a SeatType")
    if seat_type is SeatType.GENERAL_ONLY:
        return False
    if seat_type is SeatType.SPECIAL_ONLY:
        return True
    if seat_type is SeatType.GENERAL_FIRST:
        _require_availability(
            train.general_seat_availability,
            seat_type=seat_type,
            field="gnrmRsvPsbStr (general seat availability)",
        )
        return not _general_seat_available(train)
    _require_availability(
        train.special_seat_availability,
        seat_type=seat_type,
        field="sprmRsvPsbStr (special seat availability)",
    )
    return _special_seat_available(train)


def _reservation_passenger_fields(
    passengers: PassengerCounts,
    *,
    special_seat: bool,
    window_seat: bool | None,
    seat_attr_code: str = "015",
) -> dict[str, str]:
    # Mirrors srtgo Passenger.get_passenger_dict (srt.py:179-204): the seat/class
    # constants plus ONLY the filled psgTpCd/psgInfoPerPrnb slots (enumerate over
    # the combined passengers) — NOT the 5 padded slots the search payload sends.
    slots = _compact_passenger_slots(passengers)
    fields: dict[str, str] = {
        "totPrnb": str(passengers.total),
        "psgGridcnt": str(len(slots)),
        "locSeatAttCd1": _WINDOW_SEAT_CODES.get(window_seat, "000"),
        "rqSeatAttCd1": _validated_seat_attr_code(seat_attr_code),
        "dirSeatAttCd1": "009",
        "smkSeatAttCd1": "000",
        "etcSeatAttCd1": "000",
        "psrmClCd1": "2" if special_seat else "1",
    }
    for index, (type_code, count) in enumerate(slots, start=1):
        fields[f"psgTpCd{index}"] = type_code
        fields[f"psgInfoPerPrnb{index}"] = str(count)
    fields.update(_infant_count_field(passengers))
    return fields


def _standby_row_image(train: TrainSummary) -> str:
    # The raw search row is kept on TrainSummary.raw, which is where the app's
    # own standby signal lives; nothing on the typed surface carries it, because
    # gnrmRsvPsbImg is a UI asset name and was never worth promoting to a field.
    raw = train.raw
    if not isinstance(raw, dict):
        return ""
    image = raw.get("gnrmRsvPsbImg")
    return image if isinstance(image, str) else ""


def _refuse_ineligible_standby(train: TrainSummary) -> None:
    """Refuse ``standby=True`` on a row the app would never offer 예약대기 for.

    The app has no "standby rejected" dialog to copy, because the choice is not
    the user's: fn_moveRsv reads the SELECTED row's general-cabin image and
    emits ``jobId=1102`` only when it is the 예약대기 image (ara1001l.js:1447).
    Sending 1102 for any other row is sending a body the app cannot produce, and
    this repository's rule is to send what the app sends -- the same reasoning
    that makes ``personal_reservation_payload`` refuse a non-SRT train.

    Absence is NOT ineligibility. A row that carries no ``gnrmRsvPsbImg`` at all
    is accepted: a hand-built :class:`~srt_mobile_api.models.TrainSummary`, or a
    response shape that drops the column, would otherwise make standby
    unreachable for reasons that have nothing to do with the train. That is the
    same "blank, not an error" treatment ``arvDt1`` gets. Only a row that HAS
    the field and disagrees is refused, which is the only case where we have
    positive evidence the app would not offer standby.
    """
    image = _standby_row_image(train)
    if image and image not in _STANDBY_ROW_IMAGES:
        raise ValueError(
            "standby (jobId 1102) requires a 예약대기 train: the search row's "
            f"gnrmRsvPsbImg is {image!r}, not one of {sorted(_STANDBY_ROW_IMAGES)}"
        )


def _seat_designation_fields(
    designation: SeatDesignation,
    *,
    passenger_total: int,
) -> dict[str, str]:
    """The 좌석지정 field family, read line by line off ara0101v.js:866-882.

    The app's seat-selection popup returns
    ``obj = {scarSeatNo: "2,7,10", scarSeatNm: "1B,2C,3B", scarNo: 1}`` — BOTH
    identifier lists and the car — and the 편도 branch does this with it::

        var scarSeatArr = obj.scarSeatNm.split(",");          // :870
        for (...) oSeatData1["seatNo1_" + (i+1)] = scarSeatArr[i];  // :872-874
        oSeatData1["scarGridcnt1"] = scarSeatArr.length;      // :876
        oSeatData1["scarGridcnt2"] = 0;                       // :877
        oSeatData1["scarNo1"] = obj.scarNo;                   // :878
        oSeatData1["scarNo2"] = "";                           // :879

    **The field spelled ``seatNo`` carries the seat's NAME.** It is built from
    ``scarSeatNm``, the PRINTED labels, and ``scarSeatNo`` — the internal seat
    numbers — is received and then never used. That is worth stating loudly
    because the sibling korail client has the mirror-image convention, and
    comparing the wrong one against a reservation detail once made it look as
    though a server had ignored a seat map entirely.

    **Slot 2 is blanked, not omitted**: ``scarGridcnt2="0"`` and ``scarNo2=""``
    are written explicitly on the one-way path. 여정 slot 2 belongs to a 환승
    second leg (see :func:`transfer_reservation_payload`), and a seat-designated
    one-way journey has none — so the app clears it rather than leaving whatever
    was there, and so does this.

    The party-size rule is enforced here because this is the one place both
    halves are in scope. ``choiceSeatCount`` on the seat page and the grid is
    ``totPrnb`` (``ara1001l.js:1511``), i.e. the app asks the seat map for
    exactly as many seats as there are passengers; sending a different number
    of ``seatNo1_*`` fields is a body the app cannot produce, and the failure it
    would produce live is a real hold with the wrong seats on it.
    """
    if type(designation) is not SeatDesignation:
        raise ValueError("designated_seats must be a SeatDesignation")
    seat_count = len(designation.seats)
    if seat_count != passenger_total:
        raise ValueError(
            "designated seats must match the passenger count: "
            f"{seat_count} seat(s) for {passenger_total} passenger(s)"
        )
    fields = {
        f"seatNo1_{index}": label
        for index, label in enumerate(designation.printed_seat_labels, start=1)
    }
    fields["scarGridcnt1"] = str(seat_count)
    # Explicitly zero / empty, exactly as the 편도 branch writes them.
    fields["scarGridcnt2"] = "0"
    fields["scarNo1"] = designation.car_number
    fields["scarNo2"] = ""
    return fields


def personal_reservation_payload(
    train: TrainSummary,
    passengers: PassengerCounts,
    *,
    seat_type: SeatType = SeatType.GENERAL_FIRST,
    netfunnel_key: str,
    window_seat: bool | None = None,
    standby: bool = False,
    round_trip: bool = False,
    designated_seats: SeatDesignation | None = None,
    seat_attr_code: str | None = None,
    membership_number: str = "",
) -> dict[str, str]:
    """Build the 개인예약 / 예약대기 reservation form (``/arc/selectListArc05013_n.do``).

    Reproduces the srtgo ``_reserve`` wire for ``jobId=1101`` (srt.py:962-997)
    EXACTLY, sourcing the train/station/time/order fields from ``train`` and the
    passenger dict from ``passengers`` (mapped to SRT psgTpCd via the same
    compaction the search payloads use). ``netfunnel_key`` is placed verbatim
    into ``netfunnelKey``. ``mblPhone`` is omitted -- srtgo passes ``None``,
    which requests drops from the wire, and the string has ZERO hits across the
    whole v2.0.41 bundle, so there is nothing to add it back from.

    Two keyword-only variants ride the same form; both default to off, so a call
    that does not name them produces the byte-for-byte form that was
    live-verified on 2026-07-25.

    ``standby=True`` switches ``jobId`` to ``1102`` (예약대기). Three things
    change together, and all three come from the one branch that produces 1102:

    * ``jobId`` becomes ``"1102"`` (ara1001l.js:1445-1448).
    * ``psrmClCd1`` is forced to ``"1"`` (일반실). ara1001l.js:1431 is the only
      line that can pair a 예약대기 row with a cabin class, and it assigns 1;
      the 특실 branch on the next line tests only the two 예약가능 images, so a
      특실-standby simply has no representation in the app. Forcing matters
      because the default ``SeatType.GENERAL_FIRST`` resolves to 특실 whenever
      the general cabin reads as not "예약가능" -- which is exactly what a
      standby row looks like. Without the override, asking for standby ordered
      a first-class seat.

      The override is applied BEFORE the class is resolved, not after. Once
      ``_require_availability`` landed, a standby row that carried no
      ``gnrmRsvPsbStr`` at all stopped resolving to 특실 and started RAISING
      instead -- past an override placed below it. Deciding first is what
      makes both failure modes impossible; nothing on this path reads the
      availability string, because the app settles a 예약대기 row's cabin
      from the image field alone.
    * ``reserveType`` is DROPPED. srtgo sets it only for a personal reservation
      (srt.py:990-991). The field is 0-hit in our bundle, so srtgo is the only
      source there is and it is followed rather than guessed past.

    The caller-facing eligibility rule is in :func:`_refuse_ineligible_standby`.
    Note that ``stndFlg`` stays ``"N"``: it is 입석여부 (standing-room), a
    different thing from 예약대기, and the app never changes it (2 hits total,
    the seed at ara0101v.js:96 and a null-check read at ara1001l.js:1656).

    ``round_trip=True`` sets ``rtnDv`` to ``"1"`` (왕복). That is the ENTIRE wire
    delta, and the reason is that SRT does not model a round trip as one
    multi-leg reservation. ara1001l.js:1580-1596: with ``rtnDv=1`` the app
    reserves the 가는열차 first, stores the result, re-searches with the
    stations swapped and the ``back_dptDt1``/``back_dptTm1`` date and time
    (:110-115), and reserves the 오는열차 as a SECOND, separate POST to the same
    endpoint, whose leg-1 fields (``dptRsStnCd1`` ... ``trnNo1``) are overwritten
    with the return train's row (:1454-1470). So each leg is one call here too.

    ``jrnyCnt`` therefore stays ``"1"`` for both legs, and this is worth being
    exact about because it is easy to assume otherwise. ``jrnyCnt`` has three
    hits in the entire bundle: the seed ``"1"`` (ara0101v.js:92), a null-check
    read (ara1001l.js:1654), and ONE write -- the 환승 (transfer) toggle, which
    sets ``jrnyCnt="2"`` together with ``jrnyTpCd="14"`` (ara0101v.js:288-311).
    Nothing on the 왕복 path touches it, and 환승 and 왕복 are mutually exclusive
    anyway (:296-298, :333). So ``jrnyCnt="2"`` means TRANSFER, not round trip.

    By extension the ``...2`` suffix in this form family indexes the 여정
    (journey) slot, not a passenger and not the return leg. The app's own gloss
    is ``여정일련번호1(001:선행, 002:후행)`` (ara0101v.js:97, echoed at
    ara1001l.js:1611 ``0001 : 선행, 0002 : 후행``): slot 2 is the FOLLOWING leg of
    a transfer. A round trip never fills it -- the one-way seat callback
    explicitly blanks it (``scarGridcnt2=0``, ``scarNo2=""``, ara0101v.js:875-878),
    the 왕복 seat callbacks write no slot at all (:884-892), and the return
    train arrives in slot 1 on the second POST. Passengers are counted in a
    different family entirely (``psgTpCd1..5``/``psgInfoPerPrnb1..5``, indexed by
    passenger TYPE), which is the reading this suffix is most often confused
    with.

    ``round_trip=True`` is refused, before anything is built, for two
    conditions the app's own 왕복 checkbox handler checks and this repository
    now reproduces. Both live in the SAME handler, ``case "chk_rtrp"``
    (ara0101v.js:317-341), and both follow the identical shape: call
    ``callbackChkRtrp()`` (:903-906, force-unchecks ``#chk_rtrp``), show an
    alert, and ``return`` -- which is BEFORE the code that ever sets
    ``rtnDv="1"`` (:381). That is the same uncheck-alert-return control flow
    as the already-implemented 환승×왕복 mutual exclusion above (:296-299,
    :331-334), so both are refused here rather than merely documented:

    * **코레일 전용역.** :337-341 calls ``lfn_isKorailStn`` (offline
      ``sub/main.html:568-578``) on both the departure and arrival station.
      That function scans ``stationList`` (``js/stationInfo.js``) for an entry
      whose ``gubun`` is ``"SRT"`` and the matching code; a hit returns
      ``False`` and anything else -- including a real station this library
      otherwise knows the name of -- returns ``True``. If EITHER station comes
      back ``True`` the app shows "코레일 열차는 왕복 열차 예약을 이용하실 수
      없습니다." and returns. See :data:`~srt_mobile_api.stations.SRT_STATION_CODES`
      for the 17-code set this reproduces.
    * **국회의원 후급 회원.** :319-326: the page-global ``mbCrdNo`` -- non-empty
      and not ``null`` -- is checked with ``mbCrdNo.substr(0,2) == "11"``. On a
      match the app shows "왕복승차권은 국회의원 후급 적용으로 이용하실 수
      없습니다 … 가는 열차와 오는 열차를 각각 편도로 예매 후 발권하여 주시기
      바랍니다." and returns. ``mbCrdNo`` itself is never assigned inside the
      offline bundle (it is seeded by the server-rendered ``ara0101v.do`` page,
      which this repository does not have), so the binding to
      :attr:`~srt_mobile_api.models.SrtSession.membership_number` is an
      inference from the shared name and the shared 회원카드번호 concept
      (``ara0101v.js:52-62``'s ``gds_userInfo.MB_CRD_NO``) -- the SAME
      inference :func:`card_payment_payload` already makes for the wire field
      it sends under the identical name ``mbCrdNo`` -- rather than something
      read directly off this handler. Pass ``membership_number=""`` (the
      default) to skip this check entirely, e.g. for a guest session that
      carries none.

    ``designated_seats`` (좌석지정) switches ``jobId`` to ``1103`` (시트맵예약)
    and appends the seat family — ``seatNo1_1..N``, ``scarGridcnt1``,
    ``scarGridcnt2``, ``scarNo1``, ``scarNo2`` — built by
    :func:`_seat_designation_fields`, which is where the per-field evidence is.
    Three things about it are worth reading before sending one live:

    * **The BODY is bundle-evidenced; the TARGET is inferred.** See
      :data:`RESERVE_SEATMAP_JOBID`. Every field and value comes from
      ara0101v.js:866-882; the endpoint comes from the commented-out
      ``//Sr.ara1001l.fn_callReserv();`` beside the ``fn_submit()`` call, and
      ``fn_submit`` itself is defined in a page the bundle does not contain.
    * **It does not compose with ``standby``.** ``jobId`` cannot be both
      ``1102`` and ``1103``, and the app never offers the choice: fn_moveRsv
      assigns ``1103`` on the ARC0201C (좌석선택) branch and ``1101``/``1102``
      on the ARC0102C branch, which are different destinations
      (ara1001l.js:1435-1449).
    * **It does not compose with ``round_trip`` either**, and this one is a
      restriction rather than a contradiction. 좌석지정 왕복 exists in the app
      (``POP_REQ_SEATSELECT_GO_BACK``, const.js:10) but its callback writes NO
      seat fields at all — it just calls ``fn_callReserv()``
      (ara0101v.js:884-892). Only the 편도 branch (:866-882) produces the field
      family, so a 왕복 designated body is a shape this repository has no
      evidence for, and guessing it would mean guessing on a route that creates
      real holds.

    ``reserveType`` stays ``"11"`` for a designated reservation. It is
    srtgo-only and 0-hit in the bundle (see below), srtgo has no seat-map
    reservation at all, and nothing indicates it tracks ``jobId`` — so it is
    left where the live-verified personal path put it rather than dropped or
    changed on a hunch.
    """
    if type(train) is not TrainSummary:
        raise ValueError("reservation requires an exact TrainSummary")
    if designated_seats is not None and standby:
        raise ValueError(
            "seat designation (jobId 1103) and standby (jobId 1102) are "
            "different job types on different app branches "
            "(ara1001l.js:1435-1449); a reservation cannot be both"
        )
    if designated_seats is not None and round_trip:
        raise ValueError(
            "seat designation is implemented for 편도 only: the app's 왕복 "
            "seat callback writes no seat fields at all (ara0101v.js:884-892), "
            "so the 왕복 designated body is unevidenced"
        )
    # standby × round_trip is deliberately NOT refused, unlike the two
    # combinations above, and this says so because the asymmetry otherwise
    # reads as an oversight. Checked in the bundle on 2026-07-27: jobId 1102
    # is assigned from the 예약대기 image inside the SAME branch that assigns
    # 1101 (ara1001l.js:1445-1448), and every rtnDv read
    # (:47, :1248, :1472-1476, :1581) tests rtnDv alone without consulting
    # jobId. So the app has no rule against the pair, and inventing one here
    # would refuse something SRT permits.
    #
    # Related, and settled the same way: ara0101v.js:379 disables the
    # #btn_trnGpCd BUTTON when 왕복 is checked. That locks the SELECTOR, not
    # the value -- the previously chosen trnGpCd stays in the form and is
    # still sent -- so writing train_group_code on a round trip is correct
    # and does not need a round_trip branch.
    # 왕복 × 국회의원 후급 배제. ara0101v.js:317-326's `case "chk_rtrp"` reads
    # the page-global `mbCrdNo` and, when it is non-empty and its first two
    # characters are "11", calls callbackChkRtrp() (:322, unchecks the box,
    # defined :903-906) then srtAlertBoxDivShow(...) and `return`s (:325) --
    # BEFORE the code that ever sets rtnDv="1" (:381). Same uncheck-alert-
    # return shape as the already-implemented 환승×왕복 exclusion below
    # (:296-299, :331-334), so it is refused here too.
    is_assembly_member_number = (
        isinstance(membership_number, str) and membership_number.startswith("11")
    )
    if round_trip and is_assembly_member_number:
        raise ValueError(
            "round trip is refused for a 국회의원 후급 member (membership "
            "number prefix '11'): the app's 왕복 checkbox handler force-"
            "unchecks the box and shows '왕복승차권은 국회의원 후급 적용으로 "
            "이용하실 수 없습니다 … 가는 열차와 오는 열차를 각각 편도로 예매 "
            "후 발권하여 주시기 바랍니다.' before ever setting rtnDv=1 "
            "(ara0101v.js:317-326; uncheck at callbackChkRtrp, :903-906)"
        )
    if not isinstance(netfunnel_key, str):
        raise ValueError("netfunnel_key must be a string")
    # SRT-only guard (srtgo train_name != "SRT" check): stlbTrnClsfCd must be the
    # SRT class code "17".
    if train.service_class_code != _SRT_TRAIN_CLASS_CODE:
        raise ValueError(
            "reservation requires an SRT train (service_class_code '17')"
        )

    train_no = _required_digits(train.train_no, "train_no", max_length=5).zfill(5)
    departure_date = _required_digits(train.departure_date, "departure_date", length=8)
    departure_time = _required_digits(train.departure_time, "departure_time", length=6)
    arrival_time = _required_digits(train.arrival_time, "arrival_time", length=6)
    # 운행일자 (operating date), which the app keeps DISTINCT from the departure
    # date: ara1001l.js:1460 is `"runDt1": item.runDt` while :1462 is
    # `"dptDt1": item.dptDt`, two different row fields written in the same block.
    # srtgo sends train.dep_date for both only because SRTTrain has no separate
    # run date to send; that is indistinguishable for a same-day service and
    # wrong for a train whose operating date differs from the boarding date
    # (a past-midnight departure). We do parse the operating date
    # (TrainSummary.run_date <- row runDt), and seat_page_payload,
    # timetable_payload and fare_payload already use it, so this builder was the
    # only one substituting the departure date. Fall back to the departure date
    # only when the row omits runDt, matching what those builders do.
    run_date = (
        _required_digits(train.run_date, "run_date", length=8)
        if train.run_date
        else departure_date
    )
    # 도착일자. The app writes it in the same block as dptDt1/dptTm1/arvTm1
    # (ara1001l.js:1464 `"arvDt1": item.arvDt`), and srtgo omits it only because
    # SRTTrain has no arrival date to send -- cross-validation-2026-07-21.md
    # §"srtgo posts a trimmed body" already records that divergence explicitly.
    # This is the one mutation route whose shape can be checked statically, so
    # the field is closed rather than left as an unverified omission.
    #
    # Blank when the row omits arvDt, NOT an error: the app's own #rsvForm seed
    # ships arvDt1="" (ara0101v.js, mirrored by search_payload above), the server
    # demonstrably accepts a body without the key at all (the 2026-07-25 live
    # round trip sent srtgo's trimmed form), and refusing to build the form would
    # mean a reservation that cannot be made. Validated when present.
    arrival_date = (
        _required_digits(train.arrival_date, "arrival_date", length=8)
        if train.arrival_date
        else ""
    )
    departure_station_code = _required_digits(
        train.departure_station_code, "departure_station_code", length=4
    )
    arrival_station_code = _required_digits(
        train.arrival_station_code, "arrival_station_code", length=4
    )
    # 왕복 × 코레일 전용역 배제. ara0101v.js:337-341's same `case "chk_rtrp"`
    # handler calls lfn_isKorailStn (offline sub/main.html:568-578) on both
    # stations; that function scans stationList (js/stationInfo.js) for an
    # entry whose gubun is "SRT" matching the code, returning False only on a
    # hit and True otherwise. If EITHER station comes back True the app
    # force-unchecks #chk_rtrp and shows "코레일 열차는 왕복 열차 예약을
    # 이용하실 수 없습니다." before returning -- again before rtnDv="1" is
    # ever set (:381). SRT_STATION_CODES is the 17-code set (stationInfo.js:
    # 29-45) this reproduces.
    if round_trip and (
        departure_station_code not in SRT_STATION_CODES
        or arrival_station_code not in SRT_STATION_CODES
    ):
        raise ValueError(
            "round trip is refused when either station is Korail-only, not "
            "one of the 17 stations SRT actually serves (ara0101v.js:337-341"
            f" lfn_isKorailStn; departure={departure_station_code!r}, "
            f"arrival={arrival_station_code!r})"
        )
    departure_consist_order = _required_digits(
        train.departure_consist_order, "departure_consist_order"
    )
    arrival_consist_order = _required_digits(
        train.arrival_consist_order, "arrival_consist_order"
    )
    departure_run_order = _required_digits(
        train.departure_run_order, "departure_run_order"
    )
    arrival_run_order = _required_digits(
        train.arrival_run_order, "arrival_run_order"
    )
    departure_station_name = train.departure_station_name or station_name_by_code(
        train.departure_station_code
    )
    arrival_station_name = train.arrival_station_name or station_name_by_code(
        train.arrival_station_code
    )

    if standby:
        # 예약대기 is a 일반실 waitlist in this app: ara1001l.js:1431 assigns
        # sPsrmClCd=1 for the 예약대기 image, and the 특실 branch immediately
        # after tests only the two 예약가능 images. See the docstring for why
        # this has to override rather than defer to seat_type.
        #
        # Decided BEFORE _resolve_special_seat rather than after it, because
        # _resolve_special_seat does not merely return the wrong answer for a
        # standby row -- it can RAISE past the override. A *_FIRST seat_type
        # (GENERAL_FIRST is the default) sends it through _require_availability,
        # which refuses a row that carried no gnrmRsvPsbStr. That refusal is
        # right when the field decides the class and wrong here, where nothing
        # reads it: the app settles a 예약대기 row's cabin from the IMAGE field
        # alone (ara1001l.js:1430-1432), and _refuse_ineligible_standby's own
        # contract is that a row which dropped columns is still waitlistable.
        # Resolving first refused a train the app would have queued.
        #
        # seat_type is still type-validated, since the raise below is the same
        # one _resolve_special_seat performs.
        if not isinstance(seat_type, SeatType):
            raise ValueError("seat_type must be a SeatType")
        _refuse_ineligible_standby(train)
        special_seat = False
    else:
        special_seat = _resolve_special_seat(train, seat_type)
    # type(...) is SeatDesignation, not truthiness: a wrong type must still
    # reach the dedicated validator below and get its own message.
    if type(designated_seats) is SeatDesignation and designated_seats.cabin_class:
        # The seat numbers and the cabin code must describe the same cabin. They
        # were decided independently before: the grid was fetched with a
        # cabin_class the designation did not remember, and psrmClCd1 came from
        # seat_type alone, so picking 특실 seats and leaving seat_type at its
        # GENERAL_FIRST default sent 일반실 as the class with 특실 car and seat
        # numbers beside it. The app cannot express that -- ara1001l.js:1427-1436
        # settles the cabin and the seat-map jobId in one transition -- so there
        # is no evidence for how the server would treat it, which is reason
        # enough not to send it.
        designated_special = designated_seats.cabin_class == "2"
        if designated_special != special_seat:
            raise SrtProtocolError(
                "SRT seat designation cabin does not match the reservation "
                f"class: the grid was read as psrmClCd={designated_seats.cabin_class!r} "
                f"but {seat_type.name} resolved to "
                f"psrmClCd={'2' if special_seat else '1'!r}. Fetch the grid for "
                "the cabin you intend to book, or pass "
                "seat_type=SeatType.SPECIAL_ONLY / GENERAL_ONLY to match it."
            )
    # Seat fields are built BEFORE the form, so a party/seat-count mismatch or a
    # non-selectable seat raises while nothing exists yet -- the same reason
    # every other validation in this builder runs before the dict is assembled.
    seat_fields = (
        _seat_designation_fields(
            designated_seats, passenger_total=passengers.total
        )
        if designated_seats is not None
        else {}
    )
    if designated_seats is not None:
        job_id = RESERVE_SEATMAP_JOBID
    elif standby:
        job_id = RESERVE_STANDBY_JOBID
    else:
        job_id = RESERVE_PERSONAL_JOBID

    payload = {
        "jobId": job_id,
        "jrnyCnt": "1",
        "jrnyTpCd": "11",
        "jrnySqno1": "001",
        "stndFlg": "N",
        # ara1001l.js:1440 sends item.trnGpCd -- the search row's own value.
        # Every fixture observed so far pairs stlbTrnClsfCd=="17" with
        # trnGpCd=="300", and this builder already refuses a non-17 train, so
        # the constant has never been wrong. Prefer the row's value anyway: the
        # seat routes at :724-725 and :830-831 already enforce this same field
        # off the train, and reading it in one place while ignoring it in
        # another is how the two drift apart.
        "trnGpCd1": train.train_group_code or "300",
        "trnGpCd": "109",
        # 단체구분. Always "0" here: this library builds personal reservations
        # only, and grpDv="1" is the 단체 branch whose booking was removed on
        # 2026-07-26 (see docs/IMPLEMENTATION_PROGRESS.md, "단체 (group)
        # booking: removed"). group_search_ajax_payload still flips it for the
        # group SEARCH, which is a read.
        "grpDv": "0",
        # 왕복구분 (ara0101v.js:94, written at :381/:390).
        "rtnDv": "1" if round_trip else "0",
        "stlbTrnClsfCd1": train.service_class_code,
        "dptRsStnCd1": departure_station_code,
        "dptRsStnCdNm1": departure_station_name,
        "arvRsStnCd1": arrival_station_code,
        "arvRsStnCdNm1": arrival_station_name,
        "dptDt1": departure_date,
        "dptTm1": departure_time,
        # arvDt1 sits between dptTm1 and arvTm1, the app's own field position
        # (ara1001l.js:1462-1465).
        "arvDt1": arrival_date,
        "arvTm1": arrival_time,
        "trnNo1": train_no,
        "runDt1": run_date,
        "dptStnConsOrdr1": departure_consist_order,
        "arvStnConsOrdr1": arrival_consist_order,
        "dptStnRunOrdr1": departure_run_order,
        "arvStnRunOrdr1": arrival_run_order,
        "netfunnelKey": netfunnel_key,
    }
    if not standby:
        # reserveType is set only for a personal reservation (srtgo srt.py:990-991),
        # so a 예약대기 body omits it entirely. The field is 0-hit in our v2.0.41
        # bundle -- it is not in the #rsvForm seed and nothing in the app writes it
        # -- so srtgo is the only source for both its presence and its absence, and
        # following it in both directions is the only self-consistent choice. Our
        # 2026-07-25 live round trip sent it and was accepted, which pins the
        # personal case; the standby case stays srtgo-attested.
        payload["reserveType"] = "11"
    payload.update(
        _reservation_passenger_fields(
            passengers,
            special_seat=special_seat,
            window_seat=window_seat,
            seat_attr_code=_inherited_seat_attr_code(train, seat_attr_code),
        )
    )
    # LAST, so that a body without designated seats is byte-for-byte and
    # order-for-order the one the 2026-07-25 live round trip sent. Where the
    # server-rendered #rsvForm actually puts these inputs is not knowable
    # offline (it is the same page fn_submit lives in), so appending is a
    # position this repository chose rather than one it read; the app writes
    # them into the gds_rsv store, not into an ordered form, so nothing in the
    # bundle fixes their place either.
    payload.update(seat_fields)
    return payload


def _second_journey_slot_fields(
    leg: TrainSummary,
    *,
    special_seat: bool,
    window_seat: bool | None,
    seat_attr_code: str = "015",
) -> dict[str, str]:
    """The 여정 slot-2 half of a 환승 reservation form.

    Every key is slot 1's key from ``personal_reservation_payload`` with the
    suffix changed to ``2``, and every VALUE is derived from ``leg`` exactly the
    way slot 1 derives its own from the selected row (``ara1001l.js:1453-1468``)
    — same validators, same zero-padding, same "blank when the row omits it"
    rule for ``arvDt``. :data:`TRANSFER_SLOT2_FIELD_EVIDENCE` records, per key,
    whether the ``...2`` spelling is attested in the web bundle, in the native
    offline-ticket model, only on the hydration page, or not at all.

    The seat-attribute keys are the one part where the app writes slot 2 itself,
    and it writes it with slot 1's values: the 좌석옵션 popup callback sets
    ``rqSeatAttCd1``/``locSeatAttCd1``/``dirSeatAttCd1``/``seatAttNm1`` and then
    the identical ``...2`` quartet from the same ``arrCode``/``sText``
    (``ara0101v.js:769-778``). So one seat preference covers both legs, and this
    mirrors ``special_seat``/``window_seat`` across rather than exposing a
    per-leg option the app has no way to express.

    ``seatAttNm2`` (좌석속성명2) is deliberately NOT emitted even though the app
    seeds and writes it: ``personal_reservation_payload`` does not emit
    ``seatAttNm1`` either — srtgo's accepted body omits the display-name fields —
    and slot 2 is kept a strict mirror of slot 1 rather than a superset.
    """
    train_no = _required_digits(leg.train_no, "second leg train_no", max_length=5).zfill(5)
    departure_date = _required_digits(
        leg.departure_date, "second leg departure_date", length=8
    )
    departure_time = _required_digits(
        leg.departure_time, "second leg departure_time", length=6
    )
    arrival_time = _required_digits(leg.arrival_time, "second leg arrival_time", length=6)
    run_date = (
        _required_digits(leg.run_date, "second leg run_date", length=8)
        if leg.run_date
        else departure_date
    )
    arrival_date = (
        _required_digits(leg.arrival_date, "second leg arrival_date", length=8)
        if leg.arrival_date
        else ""
    )
    departure_station_code = _required_digits(
        leg.departure_station_code, "second leg departure_station_code", length=4
    )
    arrival_station_code = _required_digits(
        leg.arrival_station_code, "second leg arrival_station_code", length=4
    )
    return {
        "jrnySqno2": JOURNEY_SEQUENCE_FOLLOWING,
        "stlbTrnClsfCd2": leg.service_class_code or "",
        "dptRsStnCd2": departure_station_code,
        "dptRsStnCdNm2": leg.departure_station_name
        or station_name_by_code(leg.departure_station_code),
        "arvRsStnCd2": arrival_station_code,
        "arvRsStnCdNm2": leg.arrival_station_name
        or station_name_by_code(leg.arrival_station_code),
        "dptDt2": departure_date,
        "dptTm2": departure_time,
        "arvDt2": arrival_date,
        "arvTm2": arrival_time,
        "trnNo2": train_no,
        "runDt2": run_date,
        "dptStnConsOrdr2": _required_digits(
            leg.departure_consist_order, "second leg departure_consist_order"
        ),
        "arvStnConsOrdr2": _required_digits(
            leg.arrival_consist_order, "second leg arrival_consist_order"
        ),
        "dptStnRunOrdr2": _required_digits(
            leg.departure_run_order, "second leg departure_run_order"
        ),
        "arvStnRunOrdr2": _required_digits(
            leg.arrival_run_order, "second leg arrival_run_order"
        ),
        "trnGpCd2": leg.train_group_code or "300",
        "psrmClCd2": "2" if special_seat else "1",
        "locSeatAttCd2": _WINDOW_SEAT_CODES.get(window_seat, "000"),
        "rqSeatAttCd2": _validated_seat_attr_code(seat_attr_code),
        "dirSeatAttCd2": "009",
        "smkSeatAttCd2": "000",
        "etcSeatAttCd2": "000",
    }


def transfer_reservation_payload(
    itinerary: TransferItinerary,
    passengers: PassengerCounts,
    *,
    seat_type: SeatType = SeatType.GENERAL_FIRST,
    netfunnel_key: str,
    window_seat: bool | None = None,
    seat_attr_code: str | None = None,
) -> dict[str, str]:
    """Build the 환승 (transfer) reservation form: ONE body, TWO journey slots.

    Unlike a round trip — which SRT models as two separate reservations of one
    journey each — a transfer is a single reservation carrying two 여정. The
    app's 환승 toggle says both halves of that in one call::

        sJrnyTp = "14"; // 환승
        nJrnyCnt = "2"; // 2건

    (``ara0101v.js:302-303``, emitted at ``:310-311``). ``jrnyCnt="2"`` is
    written in exactly one place in the whole v2.0.41 bundle and this is it.

    The form is therefore ``personal_reservation_payload`` for the FIRST leg,
    with three values changed and one slot appended:

    * ``jrnyTpCd`` ``"11"`` -> ``"14"`` (편도 -> 환승편도, ``commCode.js:296-309``),
    * ``jrnyCnt`` ``"1"`` -> ``"2"``,
    * ``rtnDv`` pinned to ``"0"`` — see the exclusion below,
    * the slot-2 keys from :func:`_second_journey_slot_fields`, appended after
      the existing keys so that slot 1's key ORDER is byte-for-byte what it was.

    ``jrnySqno1`` stays ``"001"`` and ``jrnySqno2`` is ``"002"``, which is the
    app's own vocabulary: ``//여정일련번호1(001:선행, 002:후행)``
    (``ara0101v.js:97``), repeated at ``ara1001l.js:1611`` as
    ``0001 : 선행, 0002 : 후행``.

    **환승 and 왕복 are mutually exclusive, and the app enforces it in BOTH
    directions.** Selecting 환승 while 왕복 is ticked alerts "환승은 왕복예약이
    불가능 합니다." and returns without sending (``ara0101v.js:296-299``);
    ticking 왕복 while 환승 is selected alerts the same string and returns
    (``:331-334``). This builder therefore takes no ``round_trip`` argument at
    all — the exclusion is expressed structurally rather than raised at call
    time — and pins ``rtnDv="0"``.

    (For completeness, because it cuts the other way: the app's ticket-kind
    table does contain 환승단체왕편권 / 환승단체복편권 (``tkKndCd`` 28/29,
    ``commCode.js:1597-1612``), so such a TICKET exists as an SRT product. The
    refusal above is a client-side booking rule in this app; it is not proof the
    server would refuse. We send what the app sends.)

    **No ``standby``.** ``jobId=1102`` is chosen from ONE selected row's
    general-cabin image (``ara1001l.js:1445-1448``), and a transfer itinerary
    has two rows. The app has no rule for what a 예약대기 on one leg of two
    means, so there is nothing to reproduce, and inventing one would be exactly
    the guess this repository refuses to make.

    **No ``group``.** 단체환승 is a real thing to SRT — the app names it
    (``eventTrainInfo.js:12``, ``:19`` "4.단체환승") and stocks a ticket kind for
    it (환승단체권, ``tkKndCd`` 27, ``commCode.js:1591-1596``) — and nothing in
    the app forbids the combination the way it forbids 단체+왕복. It is left out
    because this library does not book 단체 at all: group booking is a payment
    flow rather than a reservation hold, and it was removed on 2026-07-26 (see
    docs/IMPLEMENTATION_PROGRESS.md, "단체 (group) booking: removed"). Only the
    group SEARCH survives, and a search row cannot be booked.

    **No seat selection.** 좌석지정 fills ``scarNo1``/``seatNo1_*`` and
    explicitly BLANKS the slot-2 equivalents — ``scarGridcnt2 = 0``,
    ``scarNo2 = ""`` (``ara0101v.js:875-879``) — and no path in the bundle ever
    fills them. That is the transfer-specific reason: 좌석지정 (jobId 1103) IS
    implemented — see :data:`RESERVE_SEATMAP_JOBID` — but it designates seats on
    one journey slot, and the bundle shows no path that designates them on a
    transfer's second leg.

    **Passengers are NOT per-leg** and are emitted once, unchanged. The
    ``psgTpCd1..5``/``psgInfoPerPrnb1..5`` family is indexed by passenger TYPE,
    not by journey slot (``ara0101v.js:117-127``, compacted at ``:824-836``) —
    the same party rides both legs. This is the reading the ``...2`` suffix is
    most often confused with, and the two families genuinely coexist in this one
    form.

    Both legs are validated as SRT (``stlbTrnClsfCd == "17"``), the same guard
    ``personal_reservation_payload`` applies to the single leg. That means this
    builds SRT->SRT transfers only; an SRT->KTX itinerary would need the
    non-SRT guard relaxed, which no evidence here supports.

    NOT LIVE-VERIFIED, and the honest summary of what that means is in
    :data:`TRANSFER_SLOT2_FIELD_EVIDENCE`: the ``#rsvForm`` this mirrors is
    server-rendered and absent from the bundle, so five slot-2 key NAMES are an
    inference from slot 1's names rather than something read anywhere.
    """
    if type(itinerary) is not TransferItinerary:
        raise ValueError(
            "transfer reservation requires a TransferItinerary carrying both "
            f"legs — {TRANSFER_BOTH_LEGS_MESSAGE}"
        )
    # Resolved ONCE, here, off the first leg. Both slots must carry the same
    # 요구좌석속성 (below), so leaving it None for each of the two call sites
    # would let them inherit from different rows -- slot 1 from first_leg and
    # slot 2 from nothing at all.
    resolved_seat_attr_code = _inherited_seat_attr_code(
        itinerary.first_leg, seat_attr_code
    )
    payload = personal_reservation_payload(
        itinerary.first_leg,
        passengers,
        seat_type=seat_type,
        netfunnel_key=netfunnel_key,
        window_seat=window_seat,
        # Both legs of one reservation carry the same 요구좌석속성: the app's
        # seat-option callback writes rqSeatAttCd1 AND rqSeatAttCd2 from the
        # same obj.seatOption (ara0101v.js:759-778).
        seat_attr_code=resolved_seat_attr_code,
    )
    if itinerary.second_leg.service_class_code != _SRT_TRAIN_CLASS_CODE:
        raise ValueError(
            "reservation requires an SRT train (service_class_code '17'); the "
            "second transfer leg is "
            f"{itinerary.second_leg.service_class_code!r}"
        )
    payload["jrnyTpCd"] = JOURNEY_TYPE_TRANSFER
    payload["jrnyCnt"] = JOURNEY_COUNT_TRANSFER
    # Restated rather than assumed: personal_reservation_payload already writes
    # "0" here because this builder passes no round_trip, and 환승+왕복 is
    # refused by the app in both directions (ara0101v.js:296-299, :331-334).
    payload["rtnDv"] = "0"
    payload.update(
        _second_journey_slot_fields(
            itinerary.second_leg,
            # The cabin and window preference slot 1 actually resolved to, not
            # the raw seat_type: a SeatType.*_FIRST can fall back, and both legs
            # must then agree. ara0101v.js:769-778 writes slot 2 from slot 1's
            # own values for exactly this reason.
            special_seat=payload["psrmClCd1"] == "2",
            window_seat=window_seat,
            seat_attr_code=resolved_seat_attr_code,
        )
    )
    return payload


# Reservation-change number on the cancel form. srtgo sends the constant "0"
# (srt.py:1138). UNVERIFIED here: `rsvChgTno` has 0 hits across all 21,673 files
# of our v2.0.41 offline bundle (docs/analysis/cross-validation-2026-07-21.md),
# so nothing in our own app corroborates either the field or its value.
CANCEL_RESERVATION_CHANGE_NUMBER = "0"

# The jrnyCnt (여정건수) our cancel form defaults to. See
# unpaid_reservation_cancel_payload for why it is a default and not derived.
# It is the same wire field the booking form carries, so it takes its value from
# the same constant rather than repeating the literal -- a 환승 hold's 여정건수
# is 2, and _cancel_journey_count is where that matters.
_SINGLE_JOURNEY_COUNT = JOURNEY_COUNT_ONE_WAY


def _cancel_journey_count(journey_count: str | None) -> str:
    """Normalize a journey count for the cancel form; never refuse.

    Applies the korail lesson (korail commit 3d7e8a5): there, the analogous
    field came back from a live reserve zero-padded (``h_jrny_cnt="0001"``)
    while the cancel builder demanded exactly ``"1"``. It refused, the
    auto-cancel never ran, and a real unpaid hold was left dangling. So compare
    NUMERICALLY, tolerate zero-padding and surrounding whitespace, and fall back
    to the single-journey default for anything unusable rather than raising: a
    cancel form that cannot be built means a hold that cannot be released, which
    is strictly worse than sending the value srtgo attests works.

    "Never raises" is absolute, including for inputs no server would send. The
    zero padding is stripped textually before any numeric conversion, so an
    absurdly padded value normalizes without CPython's int/str conversion limit
    ever coming into play, and a value still too long to convert falls back
    instead of propagating the ``ValueError``.
    """
    if type(journey_count) is not str:
        return _SINGLE_JOURNEY_COUNT
    candidate = journey_count.strip()
    if not candidate or any(
        character < "0" or character > "9" for character in candidate
    ):
        return _SINGLE_JOURNEY_COUNT
    # Textual de-padding: "0001" -> "1", "0002" -> "2", "0000" -> "" (no
    # journey at all, so the default). str(int(...)) would do the same, but
    # only for inputs int() accepts.
    significant = candidate.lstrip("0")
    if not significant:
        return _SINGLE_JOURNEY_COUNT
    try:
        count = int(significant)
    except ValueError:
        # int() refuses a decimal string with more than
        # sys.int_info.str_digits_check_threshold (4300) significant digits.
        # A journey count that long is not a journey count; refusing to build
        # the form over it would orphan the hold.
        return _SINGLE_JOURNEY_COUNT
    return str(count)


def _foreign_reservation_message(value: object) -> str:
    """The refusal message for something that is not a hold or a PNR string.

    An ``int`` gets its own wording because it is the one refusal a caller is
    likely to think is pedantic: ``str(int(pnr))`` would silently drop leading
    zeros and cancel the wrong reservation, or none, so the fix is to pass the
    PNR as a string rather than to loosen the check.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return (
            "cancel requires the PNR as a string, not an int: converting a "
            "numeric PNR drops any leading zeros, which would cancel the "
            "wrong reservation or none at all"
        )
    return "cancel requires an SrtReservationHold or a PNR string"


def unpaid_reservation_cancel_payload(
    reservation: SrtReservationHold | str,
    *,
    journey_count: str | None = None,
) -> dict[str, str]:
    """Build the cancel (예약취소) form for a created-but-unpaid reservation.

    **Provenance — the SERVER's own page now corroborates this body, and that is
    new as of 2026-07-26.** The three fields came from srtgo (``srt.py:1138``;
    our notes at ``docs/analysis/ref-srtgo_plus.md`` §7.1) and have ZERO hits
    across all 21,673 files of our v2.0.41 offline decompile
    (``docs/analysis/cross-validation-2026-07-21.md``). Our long-standing note
    that "nothing in our own bundle corroborates them" was true of the BUNDLE and
    is no longer the whole story: the ticket-list page the live server renders
    (GET ``/atc/selectListAtc14017_n.do``) ships this, inline, on both the
    authenticated and the signed-out response::

        //예약대기 취소 버튼
        function cncConfirm(v_pnrNo, v_rsvChgTno, v_jrnyCnt) {
            var params = { pnrNo: v_pnrNo, rsvChgTno: v_rsvChgTno, jrnyCnt: v_jrnyCnt };
            $.ajax({ type: "POST", url: "/ard/selectListArd02045_n.do",
                     data: params, dataType: "json",
                     success: function (data) {
                         var msg = data.resultMap[0].msgTxt;
                         if (data.resultMap[0].strResult == "SUCC") { ... }

    That is the route, all three field names, and the response envelope
    (``resultMap[0].strResult`` / ``msgTxt``) attested by the app itself rather
    than by srtgo alone. Note the honest caveat the comment carries: it labels
    the button 예약대기 취소 (cancelling a WAITLIST entry), not specifically an
    unpaid hold, so it corroborates the wire shape rather than the exact use.

    On top of that, one operator-run round trip POSTed exactly this form on
    2026-07-25 and released a real unpaid hold (``SUCC`` / ``IRG000000``). That
    covered a SINGLE-journey, one-adult hold, so ``jrnyCnt="1"`` is confirmed for
    that case and the multi-leg value remains uncaptured. ``ara0101v.js:92``
    hard-codes ``"jrnyCnt":"1"`` (여정건수), corroborating the VALUE
    independently.

    ``reservation`` accepts an :class:`~srt_mobile_api.models.SrtReservationHold`
    or a bare PNR string: a caller recovering from a partial failure may have
    nothing but the PNR, and that path must work or the reservation cannot be
    released. Only the PNR is mandatory — with none there is nothing to cancel.

    ``jrnyCnt`` DEFAULTS to ``"1"`` rather than being derived from the hold,
    because the hold has no journey count to derive from. The reserve response
    our parser validates carries ``reservListMap[0].totSeatNum`` — a SEAT count
    — and no journey-count field at all (see
    :func:`~srt_mobile_api.parsers.parse_reservation_attempt_response`), so
    :class:`SrtReservationHold` exposes ``total_seat_count`` and nothing else
    countable; deriving ``jrnyCnt`` from it would be a category error (two seats
    on one journey is still one journey).

    It used to say here that ``"1"`` is what every hold this library can create
    actually is. That was false: ``transfer_reservation_payload`` sends
    ``jrnyCnt="2"`` and ``reserve_transfer`` returns a hold made from it. The
    hold now RECORDS the count it was created with
    (:attr:`SrtReservationHold.journey_count`), so passing the hold is enough
    and an explicit ``journey_count`` is only needed when cancelling by bare
    PNR. It is still normalized numerically and never refused (see
    :func:`_cancel_journey_count`), because a cancel form that cannot be built
    is a hold that cannot be released.
    """
    # isinstance, not `type(...) is`: a SrtReservationHold subclass is still a
    # hold and a str subclass is still a PNR, and refusing one over its exact
    # type is the formatting technicality that leaves a hold unreleasable. An
    # int PNR stays refused, though — see _foreign_reservation_message.
    if isinstance(reservation, SrtReservationHold):
        pnr_no = reservation.pnr_no
        # The hold knows what it was created as. An explicit journey_count still
        # wins, so a caller who has better information is never overridden.
        if journey_count is None:
            journey_count = reservation.journey_count
    elif isinstance(reservation, str):
        pnr_no = reservation
    else:
        raise ValueError(_foreign_reservation_message(reservation))
    if not isinstance(pnr_no, str):
        raise ValueError(_foreign_reservation_message(pnr_no))
    if not pnr_no.strip():
        raise ValueError("cancel requires a non-empty PNR")
    return {
        # Surrounding whitespace is stripped rather than transmitted; a PNR is
        # never itself whitespace-delimited.
        "pnrNo": pnr_no.strip(),
        "jrnyCnt": _cancel_journey_count(journey_count),
        "rsvChgTno": CANCEL_RESERVATION_CHANGE_NUMBER,
    }


# --- Card payment (카드결제) --------------------------------------------------
#
# PROVENANCE, and it is weaker than anything else in this module. Read this
# before trusting a single field name below.
#
# THE ROUTE IS NOT IN OUR APP. `/ata/selectListAta09036_n.do` has ZERO hits
# across all 21,673 files of our v2.0.41 offline decompile; so does the token
# `Ata09036`, and so does every `Ata09*` route. The only `/ata/` route the
# bundle contains at all is `/ata/selectListAta01032_n.do`. What our app
# actually does to pay is a different flow entirely: ara1001l.js:1550 serialises
# `#rsvForm` and :1599/:1608 point it at `/ard/selectListArd02018_n.do` (group)
# or `/ard/selectListArd02017_n.do` (personal), which are server-rendered
# WebView pages, and the app then runs the charge through the TransKey secure
# keypad (com.softsecurity.transkey, analysis/jadx/resources/AndroidManifest.xml:143;
# bridge.js:2,31,66-68) and RaonSecure FIDO (com.raon.fido.*,
# analysis/jadx/resources/AndroidManifest.xml:315). None of that is HTTP form fields.
#
# So this plaintext endpoint is a path the app itself does not take. It HAS now
# been tested: on 2026-07-26 this exact form charged a real card against the real
# server (SUCC / IRT000000, 7,500 KRW, 수서 -> 동탄, one adult), after a free
# probe with a fake card had already drawn a proper business envelope
# (FAIL / WRT100170) rather than a 404. It is a legacy path the server still
# honours. What that run did NOT do is corroborate the fields it never
# exercised: it was one single-journey, one-adult ticket on one personal card in
# one lump sum, so group, multi-leg, corporate cards and instalments below are
# still srtgo-attested only.
#
# THE TWO REFERENCE LIBRARIES ARE ONE SOURCE, NOT TWO. This was verified rather
# than assumed, by diffing their payment bodies directly: srtgo's 31-field dict
# is character-for-character identical to ryanking13/SRT's once the latter's
# Korean trailing comments are stripped -- same keys, same values, same
# non-alphabetical ORDER, same local variable names, same indentation, and the
# same method signature down to its unusual parameter order. srtgo's git history
# says why: it depended on `SRTrain` (ryanking13/SRT's PyPI name) until commit
# 8423f90 "Internalize SRT" (2024-12-13) deleted the dependency and added
# srtgo/srt.py in one move, with the payment dict already fully formed. srtgo's
# README credits ryanking13 under MIT; ryanking13/SRT credits nobody. Their
# agreement therefore corroborates NOTHING -- it is one implementation counted
# twice. (srtgo_plus is a third copy: its srt.py is byte-identical to srtgo's.)
#
# WHAT THE BUNDLE DOES AND DOES NOT CORROBORATE. The blanket claim "every field
# name is 0-hit" is FALSE, and the precise version is more useful. Three of the
# 32 names do appear in our own bundle, all in the reservation JS and none of
# them on an Ata09036 form:
#   * `mbCrdNo`  -- ara0101v.js:319,321, a client-side variable holding the
#                   회원카드번호, branched on its "11" prefix for 국회의원 후급.
#   * `totPrnb`  -- ara1001l.js:104,368,1511,1655 and ara0101v.js:114,501,...,
#                   the 총인원수 the booking screen already sends.
#   * `jrnyCnt`  -- ara0101v.js:92,311, the 여정건수, hard-coded "1".
# The other 28 -- including every card field (stlCrCrdNo1, vanPwd1, crdVlidTrm1,
# athnVal1, athnDvCd1, crdInpWayCd1, ismtMnthNum1), every settlement field
# (stlDmnDt, stlMnsSqno1, ststlGridcnt, totNewStlAmt, mnsStlAmt1, stlMnsCd1),
# and ctlDvCd/cgPsId/strJobId/inrecmnsGridcnt/chgMcs/dptStnConsOrdr2/
# arvStnConsOrdr2 -- are genuinely 0-hit (3 + 28 = 31). So the three that hit tell us the app
# uses those NAMES for those CONCEPTS; they say nothing about this form.

# Fixed values the payment form carries, with the meaning each documents. Kept
# as named data rather than inline literals so a test can assert the constant
# set without re-listing magic strings, and so the "1 고정값인듯" guesswork in
# the reference implementation is not silently promoted to fact here.
PAYMENT_MEANS_CREDIT_CARD = "02"  # 결제수단코드 (02 신용카드, 11 전자지갑, 12 포인트)
PAYMENT_CARD_INPUT_WAY = "@"  # 카드입력방식 (@ 신용카드/OK포인트, "" 전자지갑)
PAYMENT_CONTROL_DIVISION_CODE = "3102"  # ctlDvCd / strJobId
PAYMENT_CHARGE_PERSON_ID = "korail"  # cgPsId
PAYMENT_TRAIN_GROUP_CODE = "300"  # trnGpCd
PAYMENT_STATION_CONSIST_ORDER = "000000"  # dptStnConsOrdr2 / arvStnConsOrdr2


def _payment_amount(value: object, name: str) -> str:
    """Normalise a settlement amount, refusing anything that is not one.

    AMOUNT FIDELITY. This is the field korail got wrong: it sent a DISPLAY total
    instead of the amount actually collectable, and the gap only showed up on a
    special-class ticket (``h_tot_prc`` 59,800 against ``h_tot_rcvd_amt``
    83,700). The same trap is available here -- the reference implementation's
    own ticket model parses ``rcvdAmt`` (수납금액, post-discount, collectable)
    alongside ``stdrPrc`` (기준운임, the list price) and ``dcntPrc`` (할인) --
    so which one feeds the payment is a real choice and not a formality.

    We take ``rcvdAmt``, the collectable one, and only ever that; see
    :func:`card_payment_payload` for where it comes from and why no override
    exists. The list price is reachable in this library only through the fare
    page, a completely different read, and it is deliberately not wired to this
    builder.

    Leading zeros are stripped. The server sends this value zero-padded
    (``"00000036900"``) and the two reference implementations diverge on what to
    do about it: ryanking13/SRT posts the padded string back verbatim, while
    srtgo casts it to ``int`` and therefore posts ``36900``. Only srtgo's form
    is attested by the live runs this whole route rests on, so that is the one
    reproduced. UNRESOLVED, and recorded as such.

    Refuses a missing, non-numeric or zero amount rather than substituting a
    default. Unlike the cancel form -- where refusing to build means a hold that
    cannot be released, so the builder never raises -- refusing to build a
    payment means no payment, which is the safe outcome.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"card payment requires {name}; the reservation carried none, and "
            "an amount is never defaulted or inferred"
        )
    amount = _required_digits(value.strip(), f"card payment {name}").lstrip("0")
    if not amount:
        raise ValueError(f"card payment {name} must not be zero")
    return amount


def _payment_passenger_count(
    reservation: SrtReservationSummary,
    passenger_count: str | None,
) -> str:
    """Resolve ``totPrnb`` (승차인원) for the payment form.

    Sourced from ``SrtReservationSummary.ticket_special_number`` (``tkSpecNum``),
    which is what the reference implementation uses. Its fallback is NOT copied:
    it reads ``tkSpecNum or int(seatNum)``, and ``seatNum`` is modelled here as
    ``seat_number``, a seat IDENTIFIER. Substituting a seat number for a
    passenger count is the same category error as deriving a journey count from
    a seat count, and on a payment form it would mis-state how many people are
    being settled for. So a missing ``tkSpecNum`` is refused, and
    ``passenger_count`` is the explicit override for a caller who knows the true
    figure -- the same shape as ``cancel``'s ``journey_count``.
    """
    if passenger_count is not None:
        # .strip() to match how ticket_special_number below is handled; without
        # it the EXPLICIT override was stricter than the inferred value, so
        # " 4 " raised while a reservation carrying " 4 " did not.
        count = _required_digits(
            passenger_count.strip() if isinstance(passenger_count, str) else passenger_count,
            "passenger_count",
        ).lstrip("0")
        if not count:
            raise ValueError("passenger_count must be a positive integer string")
        return count
    value = reservation.ticket_special_number
    if not isinstance(value, str) or not value.strip().isdigit():
        raise ValueError(
            "card payment requires the reservation's ticket_special_number "
            "(tkSpecNum) as totPrnb, or an explicit passenger_count; "
            "seat_number is a seat identifier and is never substituted for a "
            "passenger count"
        )
    count = _required_digits(value.strip(), "ticket_special_number").lstrip("0")
    if not count:
        raise ValueError("card payment totPrnb must not be zero")
    return count


def card_payment_payload(
    reservation: SrtReservationSummary,
    card: SrtPaymentCard,
    *,
    membership_number: str,
    settlement_date: str,
    passenger_count: str | None = None,
) -> dict[str, str]:
    """Build the card-payment (카드결제) form for a reserved-but-unpaid PNR.

    **LIVE-VERIFIED 2026-07-26** (``SUCC`` / ``IRT000000``, 7,500 KRW, 수서 →
    동탄, one adult), and ``payment`` is in
    :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`, so this form
    really can charge a card. **Read the module comment above this function
    before relying on any field the run did not exercise.** In short: the route
    has zero hits in our v2.0.41 bundle, our app pays through a WebView page plus
    a TransKey keypad and FIDO instead, and the two reference libraries that
    document this form are one vendored source counted twice. The run settled
    the route and the single-journey one-adult personal-card lump-sum case; the
    group, multi-leg, corporate-card and instalment fields below remain
    srtgo-attested only.

    Every value goes on the wire as a string. The 31 fields, their order and
    their constants reproduce what the reference implementation's live runs
    used.

    ``reservation`` is an
    :class:`~srt_mobile_api.models.SrtReservationSummary`, i.e. one row of
    :meth:`~srt_mobile_api.client.SrtClient.get_reservations`, which is the read
    that can actually name an unpaid PNR. Five of its fields feed this form —
    ``pnr_no``, ``received_amount``, ``ticket_special_number``,
    ``departure_time`` and ``arrival_time`` — and that read has its OWN
    provenance problem worth restating: only its EMPTY response is live-verified
    (2026-07-26, ``trainListMap: []`` / ``payListMap: []``), so every populated
    row field name below is srtgo-attested too. Both containers' field names are
    unconfirmed against a real populated response.

    Each of those is required and none is defaulted. ``SrtReservationSummary``
    makes every field but ``pnr_no`` optional because a missing field there
    means "the server did not send this name", and guessing an amount, a
    passenger count or a departure time onto a payment form is exactly how a
    caller ends up settling the wrong figure.

    ``membership_number`` is ``mbCrdNo``; take it from
    :attr:`~srt_mobile_api.models.SrtSession.membership_number` rather than from
    the caller. ``settlement_date`` is ``stlDmnDt``, ``yyyyMMdd``, passed in
    rather than read from a clock here so this module stays pure and a test can
    pin an exact body.
    """
    if type(reservation) is not SrtReservationSummary:
        raise ValueError(
            "card payment requires an SrtReservationSummary row from "
            "get_reservations"
        )
    if type(card) is not SrtPaymentCard:
        raise ValueError("card payment requires an SrtPaymentCard")
    pnr_no = reservation.pnr_no
    if not isinstance(pnr_no, str) or not pnr_no.strip():
        raise ValueError("card payment requires a non-empty PNR")
    if not isinstance(membership_number, str) or not membership_number.strip():
        raise ValueError(
            "card payment requires the account's membership number (mbCrdNo)"
        )
    settlement_date = _required_digits(settlement_date, "settlement_date", length=8)
    departure_time = _required_digits(
        reservation.departure_time, "departure_time", length=6
    )
    arrival_time = _required_digits(reservation.arrival_time, "arrival_time", length=6)
    # ONE amount, used for both fields, exactly as the reference implementation
    # does: totNewStlAmt (총 신규 결제금액) and mnsStlAmt1 (결제수단별 결제금액)
    # are the same figure because there is exactly one payment means on this
    # form (ststlGridcnt / inrecmnsGridcnt / stlMnsSqno1 are all "1"). Computing
    # them independently would invent a split this form cannot express.
    amount = _payment_amount(reservation.received_amount, "received_amount (rcvdAmt)")
    return {
        "stlDmnDt": settlement_date,
        "mbCrdNo": membership_number.strip(),
        "stlMnsSqno1": "1",
        "ststlGridcnt": "1",
        "totNewStlAmt": amount,
        "athnDvCd1": card.card_type,
        "vanPwd1": card.card_password,
        "crdVlidTrm1": card.card_expire_date,
        "stlMnsCd1": PAYMENT_MEANS_CREDIT_CARD,
        "rsvChgTno": "0",
        "chgMcs": "0",
        "ismtMnthNum1": str(card.installment_months),
        "ctlDvCd": PAYMENT_CONTROL_DIVISION_CODE,
        "cgPsId": PAYMENT_CHARGE_PERSON_ID,
        "pnrNo": pnr_no.strip(),
        "totPrnb": _payment_passenger_count(reservation, passenger_count),
        "mnsStlAmt1": amount,
        "crdInpWayCd1": PAYMENT_CARD_INPUT_WAY,
        "athnVal1": card.card_validation_number,
        "stlCrCrdNo1": card.card_number,
        "jrnyCnt": _SINGLE_JOURNEY_COUNT,
        "strJobId": PAYMENT_CONTROL_DIVISION_CODE,
        "inrecmnsGridcnt": "1",
        "dptTm": departure_time,
        "arvTm": arrival_time,
        "dptStnConsOrdr2": PAYMENT_STATION_CONSIST_ORDER,
        "arvStnConsOrdr2": PAYMENT_STATION_CONSIST_ORDER,
        "trnGpCd": PAYMENT_TRAIN_GROUP_CODE,
        "pageNo": "-",
        "rowCnt": "-",
        "pageUrl": "",
    }


# --- Refund (환불) -------------------------------------------------------------

# The cancellation-reason literal the refund form carries verbatim.
REFUND_CANCEL_REASON = "승차권 환불로 취소"


def refund_payload(info: SrtRefundTicketInfo) -> dict[str, str]:
    """Build the refund (환불) form for an already-issued ticket — step 2 of 2.

    Step 1 is :meth:`~srt_mobile_api.client.SrtClient.get_refund_ticket_info`,
    which produces the ``info`` this consumes. The two are separate methods on
    purpose; see that method for why they are not fused into one call.

    **LIVE-VERIFIED 2026-07-26**, and the origin is unchanged. This exact form
    refunded a real, paid ticket against the real server (``SUCC`` /
    ``IRT200277``, 수서 → 동탄, one adult, 7,500 KRW; the account was then
    confirmed empty of both reservations and tickets from a separate session).
    Where it came from is still worth knowing, and is still the thinnest chain
    in this module: the payment route at least has one implementation copied
    into two libraries, while this one exists in exactly ONE — ryanking13/SRT
    has no refund at all (no ``reserve_info``, no ``getListAtc14087``, no
    ``selectListAtc02063``, no ``tkRetPwd``), and srtgo added both steps from
    scratch four days after vendoring its SRT support (2024-12-17, "FIX: SRT
    refund needs new API"). There is no upstream to have agreed with it,
    ``Atc02063`` is 0-hit across all 21,673 files of our v2.0.41 offline
    decompile, and there is no ``Atc02*`` family in the bundle at all. One live
    success is live-server evidence, not static corroboration, and it covered
    one single-journey, one-adult ticket.

    **THE DISPUTED FIELD NAMES ARE NOW SETTLED — srtgo's spellings are the ones
    the server takes.** Two of the seven used to be spelled differently by the
    only two sources we had:

    * ``tkRetPwd`` (srtgo's request field) against ``retPwd`` — the spelling our
      OWN app uses at ``analysis/jadx/sources/kr/co/srail/newapp/webview/b.java:645``.
    * ``psgNm`` (srtgo) against ``buyPsNm`` — our app's spelling at the same
      site, ``b.java:648``.

    A CACHE FIELD NAME IS NOT AN API FIELD NAME, and here we can say exactly
    what that b.java site is rather than guessing: it reads the SharedPreferences
    key ``"ticketListOffline"``, base64-decodes it and parses it as JSON
    (``b.java:613,624-632``), then copies keys out into a display model. It is
    deserialisation of a LOCAL OFFLINE TICKET CACHE, not an outbound request. It
    also spells the PNR ``pnrNo`` (camelCase) where srtgo's refund form says
    ``pnr_no``, which was a third disagreement.

    That argument is now demonstrated rather than argued: the 2026-07-26 run
    sent ``tkRetPwd``, ``psgNm`` and ``pnr_no`` and the server refunded the
    ticket. The cache spellings ``retPwd``/``buyPsNm``/``pnrNo`` are not this
    endpoint's field names.

    Why the caution was not theoretical, and why the outcome is worth stating
    explicitly: this project already shipped srtgo's misspelling of a korail
    refund field — ``txtPrnNo`` for ``txtPnrNo`` — a transposition that came
    from the same class of single-source trust. srtgo was wrong THERE and right
    HERE, which is the actual lesson: single-source field names have to be
    tested one at a time, not trusted or distrusted as a class.

    Note also srtgo's own internal renaming, which is a hand-written fingerprint
    rather than a server contract: step 1 returns ``ogtkRetPwd`` and ``buyPsNm``
    while step 2 sends them as ``tkRetPwd`` and ``psgNm``, and the body mixes
    snake_case (``pnr_no``, ``cnc_dmn_cont``) with camelCase (``saleDt``,
    ``saleWctNo``, ``saleSqno``) in one dict.
    """
    if type(info) is not SrtRefundTicketInfo:
        raise ValueError(
            "refund requires an SrtRefundTicketInfo from get_refund_ticket_info"
        )
    if not isinstance(info.pnr_no, str) or not info.pnr_no.strip():
        raise ValueError("refund requires a non-empty PNR")
    # Every remaining field is required: each one is part of the ticket identity
    # the server matches on, and a refund built from a partial identity is a
    # request whose failure mode nobody here can predict. Refusing to build it
    # costs nothing -- unlike the cancel form, a refund that cannot be built
    # strands nothing.
    missing = [
        name
        for name, value in (
            ("saleDt", info.sale_date),
            ("saleWctNo", info.sale_window_number),
            ("saleSqno", info.sale_sequence_number),
            ("tkRetPwd", info.return_password),
            ("psgNm", info.buyer_name),
        )
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        raise ValueError(
            "refund requires the complete step-1 ticket identity; missing: "
            + ", ".join(missing)
        )
    return {
        "pnr_no": info.pnr_no.strip(),
        "cnc_dmn_cont": REFUND_CANCEL_REASON,
        "saleDt": info.sale_date.strip(),
        "saleWctNo": info.sale_window_number.strip(),
        "saleSqno": info.sale_sequence_number.strip(),
        # srtgo's names, not our app's cache spellings -- the disagreement is
        # settled in srtgo's favour by the 2026-07-26 live refund. See docstring.
        "tkRetPwd": info.return_password.strip(),
        "psgNm": info.buyer_name.strip(),
    }


# 할인쿠폰 등록. The two fields of #couponInfo on the live coupon page
# (/apa/selectListApa03020_n.do, 2026-07-26), in the order the page renders
# them -- which is the order $.serialize() would emit.
COUPON_NUMBER_FIELD = "dscp_no"
COUPON_PASSWORD_FIELD = "dscp_pwd"
# maxlength="10" on the number input, maxlength="4" on the password input.
COUPON_NUMBER_MAX_LENGTH = 10
COUPON_PASSWORD_MAX_LENGTH = 4


def coupon_registration_payload(
    request: SrtCouponRegistrationRequest,
) -> dict[str, str]:
    """Build the 할인쿠폰 등록 form for ``POST /arb/selectListArb02A01_n.do``.

    **The whole body is two fields**, and that is not a simplification: the
    page's own handler serialises exactly one form and that form holds exactly
    two inputs::

        var params = $("#couponInfo").serialize();
        $.ajax({ type:"POST", url:"/arb/selectListArb02A01_n.do",
                 data:params, dataType:"json", ... });

    with

        <form name="couponInfo" id="couponInfo">
          <input type="number"   id="c_txt" name="dscp_no"  maxlength="10">
          <input type="password" id="c_pw"  name="dscp_pwd" maxlength="4">
        </form>

    No PNR, no member number, no NetFunnel key: the session is the only thing
    that says WHOSE account the coupon lands on. Read live on 2026-07-26 and
    0-hit in the v2.0.41 offline bundle, which knows no ``/arb/`` route.

    **Validation is the page's, restated.** ``dscp_no`` is digits only and at
    most ten, because the page's ``keyup`` handler strips every non-digit and
    truncates to ten and the input says ``maxlength="10"``; ``dscp_pwd`` is at
    most four characters and is NOT constrained to digits, because the page
    constrains only the number field. Both must be non-empty -- ``couponReg()``
    refuses a blank one before it sends (``mysrt006``/``mysrt007``), and so does
    this. Nothing here trims or pads: a value the page would not have produced
    is refused rather than repaired, since the repair would be a guess about a
    credential.

    Exactly two keys come out, so ``assert_no_card_secrets`` and the mutation
    route/category binding have nothing to disagree with, and a
    :class:`~srt_mobile_api.consent.MutationPreview` of the result is two
    ``[REDACTED]`` values -- both keys are in
    :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS`.
    """
    if type(request) is not SrtCouponRegistrationRequest:
        raise ValueError(
            "coupon registration requires an SrtCouponRegistrationRequest"
        )
    number = request.coupon_number
    password = request.coupon_password
    if not isinstance(number, str) or not number:
        raise ValueError("coupon registration requires a non-empty coupon number")
    if any(character < "0" or character > "9" for character in number):
        raise ValueError("coupon number must contain only digits")
    if len(number) > COUPON_NUMBER_MAX_LENGTH:
        raise ValueError(
            "coupon number must contain at most "
            f"{COUPON_NUMBER_MAX_LENGTH} digits"
        )
    if not isinstance(password, str) or not password:
        raise ValueError("coupon registration requires a non-empty coupon password")
    if len(password) > COUPON_PASSWORD_MAX_LENGTH:
        raise ValueError(
            "coupon password must be at most "
            f"{COUPON_PASSWORD_MAX_LENGTH} characters"
        )
    return {
        COUPON_NUMBER_FIELD: number,
        COUPON_PASSWORD_FIELD: password,
    }


# 할인 승차권 검색. The nine constants the 조회결과 page server-renders into
# #seatSearchForm and never touches, in the order the form declares them.
PUBLIC_DISCOUNT_SEARCH_CONSTANTS = {
    "menuId": "41",
    "owayRtrpCrclDvCd": "01",
    "psgNum1": "0",
    "psgNum2": "0",
    "dirtChtnDvCd": "1",
    "cgPsId": "korail",
    "medDvCd": "03",
    "subCnt": "0",
}
# 대상판정여부. The 할인 승차권 page sets it to "Y" on EVERY branch it can reach
# -- both the multi-approval branch and the single-approval one end with
# $("#TGT_DTRM_YN").val("Y") -- so it is a constant here rather than an option.
PUBLIC_DISCOUNT_TARGET_DETERMINED = "Y"


def public_discount_search_payload(
    query: TrainSearchQuery,
    discount: PublicDiscountSelection,
    *,
    page_cursor: str = "",
) -> dict[str, str]:
    """Build the 할인 승차권 search POST for ``/ara/selectListAra10131_n.do``.

    **This is the ajax leg, and the ajax leg is the search.** The route has two:
    the 할인 승차권 page's ``goSubmit()`` retargets ``#rsvForm`` here and
    NAVIGATES (that form is ``method="get"``), and the 조회결과 page it returns
    then POSTs ``#seatSearchForm`` to the same path with ``dataType:"json"`` and
    renders the rows from the reply. Only the second one fetches anything.

    Every field below is ``#seatSearchForm`` verbatim, from a live read of the
    조회결과 page on 2026-07-26. The route and all three ``pblDisc*`` fields are
    0-hit across the 21,673 files of the v2.0.41 offline bundle.

    **How this differs from the ordinary search**, which is the whole reason it
    is a separate builder:

    * three extra fields — ``pblDiscCd``, ``pblDiscMgNo``, ``tgtDtrmYn``. Note
      the spelling: the PAGE form carries ``PBL_DISC_CD``/``PBL_DISC_MG_NO``/
      ``TGT_DTRM_YN`` and the AJAX form carries the camelCase pair. There is no
      ``pblDiscNm``: the discount's display name is never transmitted.
    * **no ``netfunnelKey``.** Neither form on this route has the field at all,
      although ``goSubmit()`` still waits behind ``NetFunnel_Action`` and the
      result page calls ``NetFunnel_Complete()``. The queue gate is on the
      NAVIGATION, not on the request.
    * **no passenger type mix.** The ordinary ajax carries ``psgTpCd1..N`` and
      ``psgInfoPerPrnb1..N``; this one carries ``psgNum`` — the head count — and
      nothing else about the party. So a 청소년 or a 유아 in ``query.passengers``
      affects the total here and nothing more, even though the 할인 승차권 PAGE
      form is the one place in the whole app that can express ``psgTpCd6``.
      Whether the server needs the mix, or takes it from the navigation, is
      unknown; see the client method.
    * **paging is by cursor, not by clock.** The ordinary search advances by
      bumping ``dptTm``; here the result page's own handler does
      ``$("#gdNo").val(data.dsCmdMap.gdNo)`` and re-posts the otherwise identical
      body. ``page_cursor`` is that value, empty for the first page.
    * ``chtnDvCd`` is fixed at ``"1"`` (직통). The page has no 환승 toggle: its
      ``#rsvForm`` renders ``jrnyTpCd="11"`` and the result page derives
      ``chtnDvCd`` from it as ``"" == "11" ? "1" : "2"``.
    * ``trnNo`` is always empty. ``onload()`` never assigns it.

    **The party-size rule is the page's and is enforced here.** Both the 할인
    승차권 page and the 승차인원선택 popup refuse 다자녀 (``01``) and 3세대
    동행할인 (``06``) below three passengers, in identical words —
    ``if((pblDiscCd == "01" || pblDiscCd == "06") && totalPessnger < 3)`` →
    ``rsv071`` "승객인원 3명이상 선택하십시오." Mirroring it follows
    :func:`group_search_ajax_payload`, which mirrors the app's own ten-person
    group guard rather than silently sending a body the app would never send.

    ``stlbTrnClsfCd`` and ``trnGpCd`` are derived from ``query.train_group_code``
    through :data:`TRAIN_GROUP_OPTIONS`, exactly as
    :func:`search_ajax_payload` derives them. **The page's own default disagrees
    with that pairing** — it server-renders ``trnGpCd1="109"`` (전체) beside
    ``stlbTrnClsfCd1="17"`` (SRT), which is not a pair this table produces — and
    that discrepancy is recorded rather than reproduced: which of the two the
    server honours is unknown, and following the library's existing derivation
    at least keeps the caller in control of both.
    """
    if type(query) is not TrainSearchQuery:
        raise ValueError("public discount search requires a TrainSearchQuery")
    if type(discount) is not PublicDiscountSelection:
        raise ValueError(
            "public discount search requires a PublicDiscountSelection"
        )
    if discount.code not in PUBLIC_DISCOUNT_CODES:
        raise ValueError(
            "public discount code must be one of "
            + ", ".join(sorted(PUBLIC_DISCOUNT_CODES))
        )
    minimum = PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE.get(discount.code)
    if minimum is not None and query.passengers.total < minimum:
        raise ValueError(
            f"공공할인 {discount.code} requires at least {minimum} passengers "
            f"(the page's own rsv071 guard); got {query.passengers.total}"
        )
    management_no = discount.management_no
    if not isinstance(management_no, str):
        raise ValueError("public discount management number must be a string")
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    del group_name  # not transmitted on this form, unlike the ordinary search
    payload = dict(PUBLIC_DISCOUNT_SEARCH_CONSTANTS)
    payload.update(
        {
            "gdNo": page_cursor,
            "chtnDvCd": SEARCH_CONNECTION_DIRECT,
            "dptDt": query.departure_date,
            "dptTm": query.departure_time,
            "dptRsStnCd": query.departure_station_code,
            "arvRsStnCd": query.arrival_station_code,
            "stlbTrnClsfCd": service_class,
            "trnGpCd": query.train_group_code,
            "trnNo": "",
            "psgNum": str(query.passengers.total),
            "seatAttCd": query.seat_attr_code,
            "arriveTime": "N",
            "pblDiscCd": discount.code,
            "pblDiscMgNo": management_no,
            "tgtDtrmYn": PUBLIC_DISCOUNT_TARGET_DETERMINED,
        }
    )
    return payload
