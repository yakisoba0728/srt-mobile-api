"""요청 폼을 만드는 곳 —— 나가는 바이트가 결정되는 자리.

:mod:`~srt_mobile_api.parsers` 가 받는 쪽이면 이쪽은 보내는 쪽입니다. 각 빌더는
``dict[str, str]`` 하나를 돌려주고 그것이 그대로 폼 본문이 됩니다. 아무것도
전송하지 않습니다 —— 전송은 :class:`~srt_mobile_api.http.SrtHttpClient` 의
일입니다.

**필드 이름과 순서는 앱이 만드는 그대로입니다.** 이 서버는 값뿐 아니라 어떤
필드가 있고 없느냐에도 반응하므로, 앱이 빈 문자열로 보내는 필드는 여기서도 빈
문자열로 보내고 앱이 싣지 않는 필드는 만들지 않습니다. 근거는 앱 번들의 파일·행
번호로 각 함수에 적어 두었습니다.

**모르는 값은 채우지 않습니다.** 검색 행에 필요한 필드가 없으면 그럴듯한
기본값을 넣는 대신 :class:`ValueError` 나
:class:`~srt_mobile_api.errors.SrtProtocolError` 를 냅니다. 특히 좌석 등급처럼
잘못 고르면 다른 운임이 결제되는 값은 추측하지 않습니다.

읽기 폼은 :func:`~srt_mobile_api.safety.assert_read_only_request` 의 필드 계약과
짝을 이룹니다. 상태를 바꾸는 폼(예약·취소·결제·환불)은 만들어지기만 하고, 실제
전송에는 :class:`~srt_mobile_api.consent.MutationConsent` 가 따로 필요합니다.
"""

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
    """예약/발권 목록 조회(``/atc/selectListAtc14016_n.do``)의 본문을 만듭니다.

    필드는 ``pageNo`` 하나이고 그것이 폼의 전부입니다. 앱이 이 경로를 WebView 로
    열 때 쿼리에 붙이는 파라미터와 같고(``SRForegroundDialogActivity.java:31``),
    서버는 응답의 ``commandMap`` 에 받은 값을 그대로 되비춥니다.

    상한 검사는 하지 않습니다. 페이지가 몇 개인지는 응답의 ``totPageCnt`` 가
    말해 주고, 이쪽에서 범위를 정할 근거가 없습니다. 음수나 정수가 아닌 값
    (``bool`` 포함)은 :class:`ValueError` 입니다.
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
    """여섯 개의 ``(psgTpCd, 인원)`` 을 정해진 순서로 줍니다. 유아는 이미 접혀 있습니다.

    유아를 어린이 칸에 합치는 일이 일어나는 유일한 곳입니다. 5번 칸의 값은
    :attr:`~srt_mobile_api.models.PassengerCounts.child_slot_count`(어린이 +
    유아)이지 ``child`` 가 아닙니다. 그래서 아래쪽 어느 빌더도 접히지 않은 숫자를
    실수로 내보낼 수 없습니다.
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
    """예매 폼을 채우는 준비 요청(Ara10007)의 필드를 만듭니다.

    검색 자체가 아니라, 검색 ajax 가 물려받을 숨은 필드를 서버에서 받아 오는
    앞 단계입니다. 여기서 받은 값이 :func:`search_ajax_payload` 의
    ``hydrated_fields`` 로 들어갑니다.

    ``transfer=True`` 는 앱의 환승 토글이 바꾸는 딱 두 필드만 바꿉니다 ——
    ``jrnyTpCd`` 가 ``"11"`` 에서 ``"14"``(환승편도)로, ``jrnyCnt`` 가 ``"1"``
    에서 ``"2"`` 로. 토글의 전부가 그 한 줄이고(``ara0101v.js:302-303``),
    ``jrnySqno2`` 를 비롯한 둘째 슬롯 키는 건드리지 않으므로 여기서도 그대로
    빈 값입니다.
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
    """열차 검색 POST(Ara10007)의 본문을 만듭니다.

    ``hydrated_fields`` 는 :func:`search_page_payload` 로 받아 둔 서버의 숨은
    필드입니다. 그 위에 이 질의의 역·날짜·시각·인원을 덮어씁니다.

    ``transfer=True`` 는 ``chtnDvCd`` 를 ``"1"``(직통) 대신 ``"2"``(환승)로
    둡니다. 그것이 요청의 **전부**다 —— 경로는 바뀌지 않습니다. 앱도 같은 방식으로
    이 값을 만들고 같은 주소로 보냅니다(``ara1001l.js:98``, :159). 경로를 가르는
    것은 단체 여부(``grpDv``)뿐입니다. ``chtnDvCd`` 는 돌아오는 행에도 실려 있어서
    무엇을 받았는지 확인할 수 있습니다.

    ``fllwPgExt`` 는 본문에서 지웁니다 —— 다음 페이지 여부는 응답이 말하는 것이지
    요청이 말하는 것이 아닙니다.
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
    """호차 하나의 좌석배치도 요청(``/arc/selectListArc02011_n.do``)을 만듭니다.

    좌석 페이지가 호차를 고를 때 직렬화해 보내는 ``trnScarSeatFrm`` 과 같은 열한
    필드입니다. 좌석 **페이지**의 필드에서 ``reqCode``·``dptDt``·``dptTm`` 을 빼고
    ``scarNo``(열려는 호차)를 더한 것으로, 경로도 폼도 앱 번들에는 없고 서버가
    렌더링해 주는 페이지에만 있습니다.

    ``trnNo`` 는 다섯 자리로 0 을 채웁니다 —— 채우지 않으면 서버가 배치도 대신 안내
    문구를 줍니다(:data:`SEAT_TRAIN_NUMBER_LENGTH`).
    ``dptStnRunOrdr``/``arvStnRunOrdr`` 는 검색 행에서 와야 하고, 다른 데서 만들어
    넣으면 요청이 거절됩니다.

    ``train_group_code`` 가 ``"300"``(SRT)이 아니거나, ``cabin_class`` 가
    ``"1"``(일반실)/``"2"``(특실)이 아니거나, ``seat_count`` 가 양의 정수 문자열이
    아니면 :class:`ValueError` 입니다.
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
    """역무차종별코드(``stlbTrnClsfCd``)를 화면에 쓰는 이름으로 바꿉니다.

    SRT 는 ``"17"`` 입니다. 모르는 코드는 ``""`` —— 서버 페이지의 같은 함수
    (``getStlbTrnClsfCdNm``)도 그렇게 끝납니다.
    """
    return STLB_TRAIN_CLASS_NAMES.get(code or "", "")


def _train_sort(train: TrainSummary) -> str:
    """시각표·운임 폼이 싣는 ``trnSort``.

    **코드가 아니라 이름입니다.** 서버가 렌더링하는 검색 페이지는 두 호출 지점
    모두에서 ``trnSort: getStlbTrnClsfCdNm(...stlbTrnClsfCd)`` 를 보냅니다 ——
    SRT 열차면 문자열 ``"SRT"`` 입니다.

    검색 행에는 열차종별코드(``trnClsfCd``)가 아예 실려 오지 않으므로, 그것으로
    이 필드를 만들면 언제나 빈 값이 됩니다. 그래서 역무차종별코드에서 이름을
    만들고, 호출자가 직접 채워 넣은 ``train_class_code`` 는 그 이름이 없을 때만
    씁니다.
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
    """시각표·운임 폼이 ``runDt`` 로 싣는 날짜 —— **출발일**이지 운행일이 아닙니다.

    서버가 렌더링하는 검색 페이지가 두 폼 모두에 행의 ``dptDt`` 를 싣습니다.
    같은 날 출발하는 열차에서는 운행일과 출발일이 같지만, 자정을 넘겨 출발하는
    열차에서는 운행일이 전날입니다 —— 운임·시각표 조회가 어긋나는 것은 바로 그
    경우입니다.

    **예약 폼에는 이 규칙을 옮기면 안 됩니다.** 그쪽은 ``runDt1`` 에 운행일을,
    ``dptDt1`` 에 출발일을 따로 싣습니다
    (:func:`personal_reservation_payload`).
    """
    return train.departure_date or train.run_date or ""


def timetable_payload(train: TrainSummary) -> dict[str, str]:
    """열차 시각표 조회 폼 —— 네 필드가 전부입니다.

    구간명(``stnCourseNm``)은 두 역 **이름**을 ``-`` 로 이은 문자열이고,
    ``trnSort`` 는 차종 이름(SRT 열차면 ``"SRT"``), ``runDt`` 는 출발일
    (:func:`_query_date`), ``trnNo`` 는 다섯 자리로 채운 열차번호입니다. 인원은
    싣지 않습니다 —— 시각표는 승객과 무관합니다.
    """
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
    """운임·요금 조회(Ara13010) 폼을 만듭니다.

    승객은 ``psgTpCd1``~``psgTpCd6`` 과 ``psgInfoPerPrnb1``~``6`` 으로 싣습니다 ——
    선택기 팝업이 쓰는 ``passenger1`` 계열이 아닙니다. 값은 검색·예약과 같은
    방식으로 압축한 슬롯입니다(유아는 어린이에 접히고 청소년이 마지막).

    **인원은 조회 결과를 바꿉니다.** 운임 **표**는 인원과 무관하지만 같은 페이지가
    렌더링하는 예상 **합계**는 인원을 보고 계산되어, 슬롯이 비면 서버는 0원이라고
    답합니다.

    슬롯 6 은 보통 비웁니다 —— ``psgTpCd6``/``psgInfoPerPrnb6`` 모두 ``""`` 이며,
    검색 폼의 빈 슬롯이 ``"0"`` 을 쓰는 것과 다릅니다. 청소년이 있으면 그 자리가
    실제 슬롯이라 비우지 않습니다.

    둘째 구간 필드(``dptRsStnCd2`` 등)는 언제나 빈 값입니다. 이 폼으로는 한 구간만
    물을 수 있습니다 —— 응답에서 그것이 왜 중요한지는
    :func:`~srt_mobile_api.parsers.parse_fare_page` 참고.
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
    """잔여석 정보가 없는 행에서 좌석 등급을 넘겨짚지 않습니다.

    ``None`` 은 "그 등급이 매진" 이 아니라 "행에 그 필드가 없었다" 는 뜻입니다.
    둘을 같이 취급하면 ``GENERAL_FIRST`` 가 필드 없음을 "일반실 매진" 으로 읽고
    특실을 예약합니다 —— 검색에서 예약으로 이어지는 평범한 경로에서 일어나고,
    운임 차액은 호출자가 뭅니다. 환승 예약에서는 둘째 구간이 첫 구간의 판단을
    따르므로 두 구간 모두 그렇게 됩니다.

    ``*_FIRST`` 는 "잔여석을 보고 정하라" 는 뜻이므로, 볼 것이 없으면 정할 것도
    없습니다. 그래서 :class:`~srt_mobile_api.errors.SrtProtocolError` 를 냅니다.
    등급을 못박은 ``GENERAL_ONLY``·``SPECIAL_ONLY`` 는 이 검사와 무관합니다.

    앱도 같은 실수를 하지 않습니다 —— 이미지가 말해 줄 때만 등급을 정하고,
    아니면 값을 비워 둡니다(``ara1001l.js:1430-1432``).
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
#: 같은 셋의 정적 타입은 :data:`~srt_mobile_api.models.SrtSeatAttrCode` 입니다.
#: 두 형태가 어긋나지 않는지는 ``tests/test_literal_aliases.py`` 가 검사합니다.


def _inherited_seat_attr_code(train: TrainSummary, explicit: str | None) -> str:
    """예약에 쓸 요구좌석속성 —— 호출자의 값, 없으면 행의 값, 그것도 없으면 015.

    ``021``(휠체어)로 검색해 놓고 예약할 때 조용히 ``015`` 로 바뀌는 일을 막는
    자리입니다. 검색 행은 자기가 어떤 속성으로 찾아졌는지
    :attr:`~srt_mobile_api.models.TrainSummary.seat_attr_code` 에 기억하고
    있으므로, 인자를 주지 않으면 그것을 물려받습니다.

    ``explicit`` 을 주면 무조건 그 값이 이깁니다. 값 자체가 유효한지는
    :func:`_validated_seat_attr_code` 가 봅니다.
    """
    if explicit is not None:
        return explicit
    return train.seat_attr_code or "015"


def _validated_seat_attr_code(value: str) -> str:
    """예약 본문에 들어가기 전에 요구좌석속성 코드를 검사합니다.

    :data:`SRT_REQUEST_SEAT_ATTR_CODES` —— ``015`` 일반, ``021`` 휠체어,
    ``028`` 전동휠체어 —— 밖의 값은
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다. SRT 가 실제로 분기하는
    코드가 이 셋뿐입니다.

    어떤 코드를 물려받을지는 :func:`_inherited_seat_attr_code` 가 정합니다.
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
    """앱이 예약대기를 내주지 않을 행에 ``standby=True`` 를 쓰면 막습니다.

    앱에는 "예약대기 거절" 대화상자가 없습니다. 선택이 사용자 몫이 아니기 때문입니다
    —— 고른 행의 일반실 이미지가 예약대기 이미지일 때만 ``jobId=1102`` 가 나갑니다
    (``ara1001l.js:1447``). 다른 행에 1102 를 보내는 것은 앱이 만들 수 없는
    본문을 보내는 것입니다.

    **필드가 없는 것은 부적격이 아닙니다.** ``gnrmRsvPsbImg`` 를 아예 싣지 않은
    행은 통과시킵니다. 손으로 만든
    :class:`~srt_mobile_api.models.TrainSummary` 나 그 열이 빠진 응답 때문에
    예약대기가 불가능해지는 것은 열차와 무관한 이유입니다. 필드가 **있는데**
    예약대기 이미지가 아닐 때만 :class:`ValueError` 입니다.
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
    """좌석지정 필드 묶음을 만듭니다(근거: ``ara0101v.js:866-882``).

    앱의 좌석 선택 팝업은 내부 좌석번호와 표시용 좌석명을 **둘 다** 돌려주는데,
    편도 분기는 그중 좌석명만 씁니다::

        var scarSeatArr = obj.scarSeatNm.split(",");          // :870
        for (...) oSeatData1["seatNo1_" + (i+1)] = scarSeatArr[i];  // :872-874
        oSeatData1["scarGridcnt1"] = scarSeatArr.length;      // :876
        oSeatData1["scarNo1"] = obj.scarNo;                   // :878

    **``seatNo`` 라는 이름의 필드에 들어가는 것은 좌석 "이름" 입니다.** 내부
    좌석번호는 받아만 놓고 쓰지 않습니다. 이 라이브러리의 KORAIL 쪽과 역할이 반대라
    헷갈리기 쉽습니다.

    **둘째 슬롯은 생략이 아니라 빈 값으로 명시합니다** —— ``scarGridcnt2="0"``,
    ``scarNo2=""``. 여정 슬롯 2 는 환승의 둘째 구간 자리이고
    (:func:`transfer_reservation_payload`), 좌석을 지정한 편도에는 그것이 없습니다.

    **좌석 수는 승객 수와 같아야 합니다**(``ara1001l.js:1511``). 다르면
    :class:`ValueError` 입니다 —— 그대로 보내면 엉뚱한 좌석이 잡힌 진짜 예약이
    생깁니다.
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
    """개인예약·예약대기·좌석지정 예약 폼(``/arc/selectListArc05013_n.do``)을 만듭니다.

    열차·역·시각·순서 필드는 ``train`` 에서, 승객 슬롯은 ``passengers`` 에서
    옵니다(검색 폼과 같은 압축 규칙). ``netfunnel_key`` 는 ``netfunnelKey`` 에
    그대로 들어가고, ``mblPhone`` 은 앱 번들에 이름이 없어 싣지 않습니다. 아래 셋을
    지정하지 않으면 실서버에서 확인된 개인예약 폼 그대로입니다.

    **``standby=True``(예약대기)** 는 ``jobId`` 를 ``"1102"`` 로 바꾸고, 함께
    ``psrmClCd1`` 이 ``"1"``(일반실)로 **고정**되며(``ara1001l.js:1431``; 특실
    예약대기는 앱에 표현이 없습니다) ``reserveType`` 이 빠집니다. 등급을 정하기
    **전에** 고정하므로 ``SeatType.GENERAL_FIRST`` 가 특실로 풀리지 않습니다. 걸 수
    있는 행인지는 :func:`_refuse_ineligible_standby` 가 보고, ``stndFlg`` 는 입석
    여부라 ``"N"`` 그대로입니다.

    **``round_trip=True``(왕복)** 는 ``rtnDv`` 를 ``"1"`` 로 두는 것이 전부입니다.
    앱도 오는 열차를 **같은 경로에 두 번째 POST** 로 예약하므로
    (``ara1001l.js:1580-1596``) 구간마다 한 번씩 부르면 됩니다. ``jrnyCnt`` 는 두
    구간 모두 ``"1"`` 이고, 이 폼의 ``jrnyCnt="2"`` 는 **환승**
    입니다. 필드 이름 끝의 ``2`` 도 돌아오는 편이 아니라 **여정 슬롯**입니다(앱
    주석 ``여정일련번호1(001:선행, 002:후행)``).

    왕복은 앱의 체크박스 처리(``ara0101v.js:317-341``)가 ``rtnDv`` 를 세우지 않는 두
    경우에 폼을 만들기 전 :class:`ValueError` 로 거절합니다: 출발·도착 중 하나라도
    :data:`~srt_mobile_api.stations.SRT_STATION_CODES` 밖인 **코레일 전용역**, 회원
    번호가 ``11`` 로 시작하는 **국회의원 후급 회원**(``membership_number`` 를 주지
    않으면 건너뜁니다).

    **``designated_seats``(좌석지정)** 는 ``jobId`` 를 ``"1103"``(시트맵예약)로
    바꾸고 좌석 필드 묶음(:func:`_seat_designation_fields`)을 덧붙입니다. 필드와
    값은 ``ara0101v.js:866-882`` 에서 왔지만 **이 본문이 어느 경로로 가는지 말해
    주는 코드는 번들에 없습니다**(:data:`RESERVE_SEATMAP_JOBID`). ``standby`` 와는
    ``jobId`` 가 겹쳐서, ``round_trip`` 과는 앱의 왕복 좌석지정 콜백이 좌석 필드를
    쓰지 않아서(``ara0101v.js:884-892``) 함께 쓸 수 없습니다. ``reserveType`` 은
    ``"11"`` 그대로입니다.

    :class:`ValueError` 인 경우: ``train`` 이
    :class:`~srt_mobile_api.models.TrainSummary` 가 아닐 때, SRT 열차가 아닐 때
    (``service_class_code`` != ``"17"``), 위의 조합 규칙을 어겼을 때, 필수 숫자
    필드가 없거나 자릿수가 맞지 않을 때. 잔여석 정보가 없으면
    :class:`~srt_mobile_api.errors.SrtProtocolError` 입니다(:func:`_require_availability`).
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
    """환승 예약 폼의 둘째 여정 슬롯 필드를 만듭니다.

    키는 :func:`personal_reservation_payload` 의 슬롯 1 키에서 접미사만 ``2`` 로
    바꾼 것이고, 값도 슬롯 1 과 같은 방식으로 ``leg`` 에서 뽑습니다 —— 같은 검사,
    같은 0 채우기, ``arvDt`` 가 없으면 빈 값으로 두는 규칙까지 같습니다. 어느 키의
    ``...2`` 철자에 근거가 있고 어느 것이 유추한 이름인지는
    :data:`TRANSFER_SLOT2_FIELD_EVIDENCE` 에 키별로 적어 두었습니다.

    좌석 속성 키는 앱이 직접 슬롯 2 를 쓰는 유일한 부분이고, 앱은 그것을 슬롯 1 과
    **같은 값**으로 씁니다(``ara0101v.js:769-778``). 그래서 좌석 선호는 구간마다
    따로 정할 수 없고 ``special_seat``/``window_seat`` 를 그대로 옮깁니다.

    ``seatAttNm2``(좌석속성명2)는 일부러 싣지 않습니다 —— 슬롯 1 도 ``seatAttNm1``
    을 싣지 않으므로 슬롯 2 를 슬롯 1 의 정확한 거울로 둡니다.
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
    """환승 예약 폼을 만듭니다 —— 본문 **하나**에 여정 **둘**이 들어갑니다.

    왕복은 한 여정짜리 예약 두 건이지만(:func:`personal_reservation_payload`),
    환승은 두 여정을 실은 예약 한 건입니다. 앱의 환승 토글이 그 둘을 함께 말합니다
    (``ara0101v.js:302-303``)::

        sJrnyTp = "14"; // 환승
        nJrnyCnt = "2"; // 2건

    그래서 이 폼은 **첫 구간의 개인예약 폼**에 값 셋을 바꾸고 슬롯 하나를 더한
    것입니다: ``jrnyTpCd`` 를 ``"14"``(환승편도)로, ``jrnyCnt`` 를 ``"2"`` 로,
    ``rtnDv`` 를 ``"0"`` 으로 두고 그 뒤에 :func:`_second_journey_slot_fields` 의
    키를 덧붙입니다. ``jrnySqno1`` 은 ``"001"``(선행), ``jrnySqno2`` 는
    ``"002"``(후행)입니다.

    **환승과 왕복은 함께 쓸 수 없습니다.** 앱이 양방향으로 막습니다("환승은
    왕복예약이 불가능 합니다."). 그래서 ``round_trip`` 인자가 아예 없고 ``rtnDv``
    는 ``"0"`` 고정입니다.

    **예약대기도 없습니다.** ``jobId=1102`` 는 선택된 **한 행**에서 정해지는데
    환승 여정에는 행이 둘이고, 둘 중 하나만 예약대기인 상태의 규칙이 앱에
    없습니다.

    **좌석지정도 없습니다.** 편도 좌석지정은 슬롯 2 의 좌석 필드를 오히려 비우고
    (``ara0101v.js:875-879``), 환승 둘째 구간에 좌석을 지정하는 경로는 번들에
    없습니다.

    **승객은 구간별이 아닙니다.** ``psgTpCd``/``psgInfoPerPrnb`` 묶음은 승객
    **유형**으로 번호가 매겨지므로 한 번만 나가고, 같은 일행이 두 구간을 탑니다.

    두 구간 모두 SRT 여야 합니다(``stlbTrnClsfCd == "17"``). 아니면
    :class:`ValueError` 입니다.

    **실서버로 보내 본 적이 없습니다.** 이 폼이 본뜬 ``#rsvForm`` 은 서버가
    렌더링하는 것이라 번들에 없고, 슬롯 2 키 이름 다섯 개는 슬롯 1 에서 유추한
    것입니다(:data:`TRANSFER_SLOT2_FIELD_EVIDENCE`).
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
    """취소 폼에 실을 여정건수를 다듬습니다. **절대 예외를 내지 않습니다.**

    앞뒤 공백과 앞의 0 을 떼고 숫자로 읽습니다 —— ``"0001"`` 도 ``"1"`` 입니다.
    쓸 수 없는 값은 단일 여정 기본값으로 물러섭니다. 취소 폼을 못 만드는 것은
    풀지 못하는 예약이 남는다는 뜻이고, 그것이 값 하나가 어긋나는 것보다 훨씬
    나쁩니다. 환승 예약이면 여기에 ``"2"`` 가 옵니다.

    0 을 문자로 먼저 떼기 때문에, 자릿수가 터무니없이 긴 값도 파이썬의 정수
    변환 한계에 걸리기 전에 정리됩니다. 그래도 변환되지 않으면 기본값입니다.
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
    """예약도 PNR 문자열도 아닌 값을 거절할 때 쓸 메시지를 고릅니다.

    정수에는 따로 문구를 줍니다. 까다롭게 구는 것처럼 보이기 쉬운 거절이기
    때문입니다 —— PNR 을 정수로 만들면 앞의 0 이 사라져 엉뚱한 예약이 취소되거나
    아무것도 취소되지 않습니다. 검사를 푸는 것이 아니라 문자열로 넘기는 것이
    답입니다.
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
    """결제 전 예약을 취소하는 폼을 만듭니다 —— 필드는 셋입니다.

    ``pnrNo``·``jrnyCnt``·``rsvChgTno`` 가 전부이고, 목적지는
    ``POST /ard/selectListArd02045_n.do`` 입니다. 서버가 렌더링하는 승차권 페이지의
    ``cncConfirm()`` 이 같은 경로에 같은 세 필드를 보냅니다 —— 그 버튼의 주석은
    예약대기 취소이므로 전송 모양만 증언합니다. 이 폼으로 실제 미결제 예약이 풀린
    것은 확인돼 있습니다.

    ``reservation`` 은 :class:`~srt_mobile_api.models.SrtReservationHold` 도, PNR
    문자열만도 받습니다 —— 중간에 실패한 호출자에게 PNR 밖에 없을 수 있기
    때문입니다. 정수로 넘기면 거절합니다: 앞의 0 이 사라져 엉뚱한 예약을 취소하게
    됩니다.

    ``jrnyCnt`` 는 예약 객체가 자기 값을 기억하므로
    (:attr:`~srt_mobile_api.models.SrtReservationHold.journey_count`) 예약을
    통째로 넘기면 알아서 맞고, 환승 예약이면 ``"2"`` 입니다. PNR 문자열로 취소할
    때만 ``journey_count`` 를 직접 줄 필요가 있고 주면 그쪽이 이깁니다. 좌석
    수에서 유추하지는 않습니다.

    PNR 이 비어 있으면 :class:`ValueError` 입니다. 그 밖에는 값이 이상해도 예외를
    내지 않습니다(:func:`_cancel_journey_count`).
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
    """결제금액을 정규화합니다. 금액이 아닌 것은 모두 거절합니다.

    **어느 금액이냐가 중요합니다.** 예약 행에는 수납금액(``rcvdAmt``, 할인이 적용된
    실제 청구액)과 기준운임(``stdrPrc``)·할인액(``dcntPrc``)이 함께 있고 특실
    승차권처럼 둘이 크게 어긋나는 경우가 있습니다. 이 폼에 들어가는 것은
    수납금액뿐입니다.

    앞의 0 은 뗍니다. 서버는 0 을 채워 보내지만(``"00000036900"``), 이 경로를
    증언하는 구현이 정수로 바꿔 보내고 그것이 실제로 통한 형태입니다.

    빠졌거나, 숫자가 아니거나, 0 인 금액은 기본값으로 때우지 않고
    :class:`ValueError` 를 냅니다. 취소 폼과 반대 판단입니다 —— 여기서는 폼을 못
    만들면 결제가 일어나지 않을 뿐이고 그것이 안전한 결과입니다.
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
    """결제 폼의 승차인원(``totPrnb``)을 정합니다.

    예약 행의 ``tkSpecNum``
    (:attr:`~srt_mobile_api.models.SrtReservationSummary.ticket_special_number`)
    에서 옵니다. 참고 구현은 그것이 없으면 좌석번호로 대신하지만 그 대체는 따라
    하지 않았습니다 —— 좌석번호는 좌석의 **이름**이지 사람 수가 아니고, 결제 폼에서
    그것을 인원으로 보내면 몇 사람 몫을 결제하는지가 틀어집니다.

    그래서 ``tkSpecNum`` 이 없으면 :class:`ValueError` 이고, 진짜 인원을 아는
    호출자는 ``passenger_count`` 로 직접 말합니다. 명시한 값이 언제나 이깁니다.
    앞뒤 공백은 양쪽 모두 무시합니다.
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
    """미결제 예약을 카드로 결제하는 폼(31필드)을 만듭니다.

    **이 폼은 진짜로 카드를 긁습니다.** ``payment`` 는
    :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` 에 들어 있습니다.

    확인된 것은 단일 여정·성인 1명·개인카드·일시불 한 건입니다. 단체, 여러 구간,
    법인카드, 할부 필드는 보내 본 적이 없습니다. 이 경로 자체가 앱 번들에 없다는
    점도 알아 두어야 합니다 —— 앱은 WebView 페이지와 보안 키패드로 결제하고, 이
    평문 경로는 서버가 여전히 받아 주는 옛 길입니다.

    ``reservation`` 은 :meth:`~srt_mobile_api.client.SrtClient.get_reservations` 가
    돌려주는 행 하나입니다. 이 폼이 쓰는 것은 PNR, 수납금액, 승차인원
    (``tkSpecNum``), 출발시각, 도착시각 다섯이고 **어느 것도 기본값이 없습니다**.
    행에 필드가 없다는 것은 "서버가 그 이름을 보내지 않았다" 는 뜻이지 0 이라는
    뜻이 아니며, 금액이나 인원을 추측하는 것이 곧 엉뚱한 금액을 결제하는 길입니다.

    ``membership_number``(``mbCrdNo``)는
    :attr:`~srt_mobile_api.models.SrtSession.membership_number` 에서 가져옵니다.
    ``settlement_date``(``stlDmnDt``, ``yyyyMMdd``)를 인자로 받는 것은 이 모듈이
    시계를 읽지 않기 위해서입니다.

    ``reservation``·``card`` 의 타입이 정확하지 않거나, PNR·회원번호가 비었거나,
    금액·인원·시각이 규격에 맞지 않으면 :class:`ValueError` 입니다.
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
    """이미 발권된 승차권을 환불하는 폼 —— 2단계 중 2단계입니다.

    1단계는 :meth:`~srt_mobile_api.client.SrtClient.get_refund_ticket_info` 이고,
    그 결과 ``info`` 가 여기 들어옵니다.

    필드는 일곱입니다: PNR, 취소사유 문구, 발권 식별자 셋(``saleDt``·
    ``saleWctNo``·``saleSqno``), 승차권 반환비밀번호(``tkRetPwd``), 구매자
    이름(``psgNm``). **하나라도 비어 있으면** :class:`ValueError` **입니다** ——
    반쪽짜리 신원으로 만든 환불 요청이 무엇을 하는지는 아무도 모르고, 만들지 못해도
    잃는 것은 없습니다. 취소 폼과 반대 판단입니다.

    **필드 이름은 요청용 철자를 씁니다.** 앱의 오프라인 승차권 캐시는 같은 값들을
    ``retPwd``/``buyPsNm``/``pnrNo`` 로 부르지만 그것은 로컬 저장소의 이름입니다.
    실제 환불이 성립한 철자는 ``tkRetPwd``·``psgNm``·``pnr_no`` 이고, 1단계 응답의
    ``ogtkRetPwd``/``buyPsNm`` 이 2단계에서 이름을 바꿔 나가는 것도 그대로 재현한
    것입니다.

    확인된 것은 단일 여정·성인 1명 승차권 한 건입니다. 이 경로를 증언하는 구현은
    하나뿐이고 앱 번들에는 흔적이 없습니다.
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
    """할인쿠폰 등록 폼(``POST /arb/selectListArb02A01_n.do``)을 만듭니다.

    **본문은 두 필드가 전부입니다.** 쿠폰 페이지의 처리기가 직렬화하는 폼에 입력이
    둘뿐입니다::

        <form name="couponInfo" id="couponInfo">
          <input type="number"   id="c_txt" name="dscp_no"  maxlength="10">
          <input type="password" id="c_pw"  name="dscp_pwd" maxlength="4">
        </form>

    PNR 도, 회원번호도, NetFunnel 키도 없습니다. 이 쿠폰이 **누구 계정에** 붙는지를
    말하는 것은 세션뿐입니다.

    검사는 페이지의 규칙을 그대로 옮긴 것입니다. 쿠폰번호는 숫자만 최대 열
    자리이고, 비밀번호는 최대 네 글자이며 숫자로 제한되지 않습니다. 둘 다 비어
    있으면 안 되고, 어긋난 값은 다듬지 않고 :class:`ValueError` 로 거절합니다 ——
    다듬는 것은 자격증명을 추측하는 일입니다.

    나가는 키가 정확히 둘이므로 :class:`~srt_mobile_api.consent.MutationPreview` 로
    보면 두 값 모두 ``[REDACTED]`` 입니다
    (:data:`~srt_mobile_api.redaction.SENSITIVE_KEYS`). **쿠폰번호는 소지자가 곧
    사용자인 자격증명입니다.**
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
    """할인 승차권 검색 POST(``/ara/selectListAra10131_n.do``)를 만듭니다.

    이 경로에는 폼이 둘인데 실제로 열차를 가져오는 것은 이 ajax 폼
    (``#seatSearchForm``)입니다. 다른 하나는 같은 주소로 **화면을 이동**시키는
    페이지 폼입니다.

    **일반 검색과 다른 점** —— 빌더를 따로 둔 이유입니다.

    * 필드 셋이 더 붙습니다: ``pblDiscCd``·``pblDiscMgNo``·``tgtDtrmYn``. 페이지
      폼은 같은 값을 대문자·밑줄(``PBL_DISC_CD`` 등)로 쓰지만 ajax 폼은 이
      camelCase 입니다. 할인 이름(``pblDiscNm``)은 전송되지 않습니다.
    * **NetFunnel 키가 없습니다.** 이 경로의 어느 폼에도 그 필드가 없습니다.
      대기열은 요청이 아니라 **화면 이동**에 걸려 있습니다.
    * **승객 유형 구성이 없습니다.** 일반 ajax 는 유형별 슬롯을 싣지만 이쪽은 인원
      합계 ``psgNum`` 하나라, 청소년이나 유아는 합계에만 반영됩니다.
    * **페이지 넘김이 시각이 아니라 커서입니다.** 응답의 ``dsCmdMap.gdNo`` 를
      그대로 다시 실어 보냅니다. ``page_cursor`` 가 그 값이고 첫 페이지는 빈
      문자열입니다.
    * ``chtnDvCd`` 는 ``"1"``(직통) 고정이고 ``trnNo`` 는 언제나 빈 값입니다. 이
      페이지에는 환승 토글이 없습니다.

    **인원 하한은 페이지의 규칙을 그대로 옮긴 것입니다.** 다자녀(``01``)와 3세대
    동행할인(``06``)은 3명 미만이면 페이지가 "승객인원 3명이상 선택하십시오." 라며
    보내지 않습니다. 여기서도 :class:`ValueError` 이고, 알 수 없는 할인코드나 타입이
    맞지 않는 인자도 마찬가지입니다.

    ``stlbTrnClsfCd``·``trnGpCd`` 는 일반 검색과 같은 방식으로
    ``query.train_group_code`` 에서 끌어옵니다. **페이지의 기본값은 그 짝과
    어긋납니다** —— 서버는 ``trnGpCd1="109"``(전체) 옆에 ``stlbTrnClsfCd1="17"``
    (SRT)를 렌더링하는데, 이 표로는 나오지 않는 조합입니다. 서버가 어느 것을
    따르는지 알 수 없어 호출자가 둘 다 통제하도록 두었습니다.
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
