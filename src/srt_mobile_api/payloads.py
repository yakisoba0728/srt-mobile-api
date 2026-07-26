import re

from .models import (
    PassengerCounts,
    SeatType,
    SrtPaymentCard,
    SrtRefundTicketInfo,
    SrtReservationHold,
    SrtReservationSummary,
    TrainSearchQuery,
    TrainSummary,
)
from .stations import station_name_by_code


# jobId for a personal (개인예약) reservation (srtgo RESERVE_JOBID["PERSONAL"],
# srt.py:31). STANDBY (1102) is intentionally NOT implemented here.
RESERVE_PERSONAL_JOBID = "1101"

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
# The five SRT passenger types in positional psgTpCd order (commCode.js:55-88 lists
# psgTpCd 1..5 only; the picker object seeds psgTpCd1..5 = "1".."5" at
# ara0101v.js:795-804). There is NO infant / psgTpCd "6": SRT has no infant type and
# the string `infantCnt` appears nowhere in the app.
PASSENGER_TYPE_CODES = (
    ("adult", "1"),
    ("disability_1_to_3", "2"),
    ("disability_4_to_6", "3"),
    ("senior", "4"),
    ("child", "5"),
)


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
    # passengerN is keyed by SRT passenger type code N (commCode.js psgTpCd:
    # 1=adult, 2=disability_1_to_3, 3=disability_4_to_6, 4=senior, 5=child).
    # See ara0101v.js:213-238 (request) and :795-804 (callback). There is no
    # passenger6 slot; infant is not a picker type.
    return {
        "reqCode": "6",
        "isOrg": "2",
        "passenger1": str(passengers.adult),
        "passenger2": str(passengers.disability_1_to_3),
        "passenger3": str(passengers.disability_4_to_6),
        "passenger4": str(passengers.senior),
        "passenger5": str(passengers.child),
        "totalPessnger": str(passengers.total),
    }


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
    train_group_code: str = "109",
    train_group_name: str = "전체",
) -> dict[str, str]:
    if train_group_code not in TRAIN_GROUP_OPTIONS:
        raise ValueError("train_group_code must be one of 300, 900, or 109")
    return {
        "reqCode": "7",
        "trnGpCd": train_group_code,
        "trnGpCdNm": _required_text(train_group_name, "train_group_name"),
    }


def _compact_passenger_slots(passengers: PassengerCounts) -> list[tuple[str, int]]:
    # The app packs only the count>0 passenger types into contiguous slots, in
    # canonical psgTpCd order (ara0101v.js:824-836):
    #   idx=1; for i in 1..5: if psgInfoPerPrnb[i] > 0: psgTpCd[idx]=code[i];
    #                                                    psgInfoPerPrnb[idx]=count[i]; idx++
    # Returns the (psgTpCd, count) pairs for the filled slots, in order. Infant is not a
    # psgTpCd type and is never emitted. Shared by the search psgTpCd builder (B1) and
    # the fare passenger1..5 builder (B3) so they stay consistent.
    return [
        (type_code, getattr(passengers, attribute))
        for attribute, type_code in PASSENGER_TYPE_CODES
        if getattr(passengers, attribute) > 0
    ]


def _passenger_fields(
    passengers: PassengerCounts,
    hydrated_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    # Emit the COMPACTED psgTpCd1..N / psgInfoPerPrnb1..N, then leave the trailing slots
    # empty over exactly 5 slots. The app seeds all five as psgTpCd="" / psgInfoPerPrnb="0"
    # and overwrites only the first N filled ones (ara0101v.js:808-836), so the trailing
    # slots are SENT (psgTpCd="", psgInfoPerPrnb="0"), not omitted. No psgTpCd6 / infantCnt
    # (SRT has no infant type; commCode.js psgTpCd is 1..5 only).
    hydrated_fields = hydrated_fields or {}
    slots = _compact_passenger_slots(passengers)
    fields: dict[str, str] = {}
    for index in range(1, len(PASSENGER_TYPE_CODES) + 1):
        if index <= len(slots):
            type_code, count = slots[index - 1]
            hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")
            fields[f"psgTpCd{index}"] = hydrated_code or type_code
            fields[f"psgInfoPerPrnb{index}"] = str(count)
        else:
            fields[f"psgTpCd{index}"] = ""
            fields[f"psgInfoPerPrnb{index}"] = "0"
    return fields


def _distinct_passenger_type_count(passengers: PassengerCounts) -> int:
    # psgGridcnt is the number of distinct passenger TYPES with count>0, NOT the head
    # count: the app sets psgGridcnt=idx-1 (occupied type count, ara0101v.js:826-836)
    # and srtgo uses len(combined_passengers) (srt.py:191). Reuse the compaction helper
    # so psgGridcnt always equals the number of filled psgTpCd slots (B1). Infant is not
    # a psgTpCd type, so it is excluded.
    return len(_compact_passenger_slots(passengers))


def search_page_payload(query: TrainSearchQuery, netfunnel_key: str) -> dict[str, str]:
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = {
        "jobId": "1101",
        "jrnyTpCd": "11",
        "jrnyCnt": "1",
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
    for leg in (1, 2):
        for index in range(1, 10):
            payload[f"seatNo{leg}_{index}"] = ""
    return payload


def search_ajax_payload(
    query: TrainSearchQuery,
    netfunnel_key: str,
    *,
    hydrated_fields: dict[str, str],
) -> dict[str, str]:
    group_name, service_class = TRAIN_GROUP_OPTIONS[query.train_group_code]
    payload = dict(hydrated_fields)
    payload.update(
        {
            "chtnDvCd": "1",
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
    if query.passengers.total < 10:
        raise ValueError("group search requires at least 10 passengers (totPrnb >= 10)")
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
    payload[f"psgTpCd{_FARE_TRAILING_SLOT}"] = ""
    payload[f"psgInfoPerPrnb{_FARE_TRAILING_SLOT}"] = ""
    return payload


def _general_seat_available(train: TrainSummary) -> bool:
    # srtgo general_seat_available(): "예약가능" in gnrmRsvPsbStr (srt.py:486-487).
    return "예약가능" in (train.general_seat_availability or "")


def _special_seat_available(train: TrainSummary) -> bool:
    # srtgo special_seat_available(): "예약가능" in sprmRsvPsbStr (srt.py:489-490).
    return "예약가능" in (train.special_seat_availability or "")


def _resolve_special_seat(train: TrainSummary, seat_type: SeatType) -> bool:
    # srtgo is_special_seat dispatch (srt.py:955-960): *_ONLY force a class;
    # *_FIRST fall back based on the train's live availability strings.
    if not isinstance(seat_type, SeatType):
        raise ValueError("seat_type must be a SeatType")
    return {
        SeatType.GENERAL_ONLY: False,
        SeatType.SPECIAL_ONLY: True,
        SeatType.GENERAL_FIRST: not _general_seat_available(train),
        SeatType.SPECIAL_FIRST: _special_seat_available(train),
    }[seat_type]


def _reservation_passenger_fields(
    passengers: PassengerCounts,
    *,
    special_seat: bool,
    window_seat: bool | None,
) -> dict[str, str]:
    # Mirrors srtgo Passenger.get_passenger_dict (srt.py:179-204): the seat/class
    # constants plus ONLY the filled psgTpCd/psgInfoPerPrnb slots (enumerate over
    # the combined passengers) — NOT the 5 padded slots the search payload sends.
    slots = _compact_passenger_slots(passengers)
    fields: dict[str, str] = {
        "totPrnb": str(passengers.total),
        "psgGridcnt": str(len(slots)),
        "locSeatAttCd1": _WINDOW_SEAT_CODES.get(window_seat, "000"),
        "rqSeatAttCd1": "015",
        "dirSeatAttCd1": "009",
        "smkSeatAttCd1": "000",
        "etcSeatAttCd1": "000",
        "psrmClCd1": "2" if special_seat else "1",
    }
    for index, (type_code, count) in enumerate(slots, start=1):
        fields[f"psgTpCd{index}"] = type_code
        fields[f"psgInfoPerPrnb{index}"] = str(count)
    return fields


def personal_reservation_payload(
    train: TrainSummary,
    passengers: PassengerCounts,
    *,
    seat_type: SeatType = SeatType.GENERAL_FIRST,
    netfunnel_key: str,
    window_seat: bool | None = None,
) -> dict[str, str]:
    """Build the personal (개인예약) reservation form, mirroring srtgo _reserve.

    Reproduces the srtgo ``_reserve`` wire for ``jobId=1101`` (srt.py:962-997)
    EXACTLY, sourcing the train/station/time/order fields from ``train`` and the
    passenger dict from ``passengers`` (mapped to SRT psgTpCd via the same
    compaction the search payloads use). ``netfunnel_key`` is placed verbatim
    into ``netfunnelKey``. ``mblPhone`` is omitted (srtgo passes ``None``, which
    requests drops from the wire for a personal reservation).
    """
    if type(train) is not TrainSummary:
        raise ValueError("reservation requires an exact TrainSummary")
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

    special_seat = _resolve_special_seat(train, seat_type)

    payload = {
        "jobId": RESERVE_PERSONAL_JOBID,
        "jrnyCnt": "1",
        "jrnyTpCd": "11",
        "jrnySqno1": "001",
        "stndFlg": "N",
        "trnGpCd1": "300",
        "trnGpCd": "109",
        "grpDv": "0",
        "rtnDv": "0",
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
        # reserveType is set only for a personal reservation (srtgo srt.py:990-991).
        "reserveType": "11",
    }
    payload.update(
        _reservation_passenger_fields(
            passengers,
            special_seat=special_seat,
            window_seat=window_seat,
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
_SINGLE_JOURNEY_COUNT = "1"


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
    on one journey is still one journey). Defaulting to ``"1"`` is also what
    every hold this library can create actually is: ``personal_reservation_payload``
    only ever sends ``jrnyCnt="1"``. ``journey_count`` remains as the override
    for the day a live SRT response does carry one — it is normalized
    numerically and never refused (see :func:`_cancel_journey_count`).
    """
    # isinstance, not `type(...) is`: a SrtReservationHold subclass is still a
    # hold and a str subclass is still a PNR, and refusing one over its exact
    # type is the formatting technicality that leaves a hold unreleasable. An
    # int PNR stays refused, though — see _foreign_reservation_message.
    if isinstance(reservation, SrtReservationHold):
        pnr_no = reservation.pnr_no
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
# keypad (com.softsecurity.transkey, AndroidManifest.xml:143;
# bridge.js:2,31,66-68) and RaonSecure FIDO (com.raon.fido.*,
# AndroidManifest.xml:315). None of that is HTTP form fields.
#
# So this plaintext endpoint may be a legacy path the server still honours, or
# it may be dead for our app version. NOBODY HAS TESTED IT. No request has ever
# been sent from this repository, and payment is not live-enabled
# (safety.SRT_LIVE_MUTATION_CATEGORIES), so none can be.
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

    **UNVERIFIED. Read the module comment above this function before relying on
    any field here.** In short: the route has zero hits in our v2.0.41 bundle,
    our app pays through a WebView page plus a TransKey keypad and FIDO instead,
    the two reference libraries that document this form are one vendored source
    counted twice, and nobody has ever sent this request. Nothing in this
    library can send it either — ``payment`` is outside
    :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`.

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

    **UNVERIFIED, and by a thinner margin than the payment.** The payment route
    at least has one implementation copied into two libraries. This one exists
    in exactly ONE: ryanking13/SRT has no refund at all — no ``reserve_info``,
    no ``getListAtc14087``, no ``selectListAtc02063``, no ``tkRetPwd`` — and
    srtgo added both steps from scratch four days after vendoring its SRT
    support (2024-12-17, "FIX: SRT refund needs new API"). There is no upstream
    to have agreed with it. ``Atc02063`` is 0-hit across all 21,673 files of our
    v2.0.41 offline decompile; there is no ``Atc02*`` family in the bundle at
    all.

    **THE FIELD NAMES ARE DISPUTED, AND THIS LIBRARY HAS BEEN BURNED HERE
    BEFORE.** Two of the seven are spelled differently by the only two sources
    we have:

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
    ``pnr_no``, which is a third disagreement and one more reason not to read
    the cache as an API schema.

    So this is genuinely unresolved. We send srtgo's spelling, because srtgo's
    is the only spelling attested by a live run of THIS endpoint, and the cache
    is not evidence about this endpoint at all. The doubt is recorded rather
    than resolved.

    Why that caution is not theoretical: this project already shipped srtgo's
    misspelling of a korail refund field — ``txtPrnNo`` for ``txtPnrNo`` — a
    transposition that came from the same class of single-source trust. If this
    route is ever exercised and rejected, the field names above are the first
    place to look, and ``retPwd``/``buyPsNm``/``pnrNo`` are the first
    alternatives to try.

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
        # DISPUTED SPELLINGS -- see the docstring. srtgo's names, not our app's.
        "tkRetPwd": info.return_password.strip(),
        "psgNm": info.buyer_name.strip(),
    }
