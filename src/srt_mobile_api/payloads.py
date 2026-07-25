import re

from .models import (
    PassengerCounts,
    SeatType,
    SrtReservationHold,
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
        # a row seatAttCd. Real dsOutput1 rows omit seatAttCd, so we default to "015" and
        # let a caller pass the seat-attribute code they searched with. Do NOT read
        # train.seat_attr_code here (that field is not carried by genuine responses).
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


def _train_sort(train: TrainSummary) -> str:
    # The app sends trnSort = item.trnClsfCd (열차종별코드) from the search row,
    # distinct from stlbTrnClsfCd/service_class_code (ara1001l.js:1184 & :1217).
    return str(train.train_class_code or "")


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


def timetable_payload(train: TrainSummary) -> dict[str, str]:
    return {
        "stnCourseNm": _station_course(train),
        "trnSort": _train_sort(train),
        "runDt": train.run_date or train.departure_date or "",
        "trnNo": train.train_no.zfill(5),
    }


def fare_payload(train: TrainSummary, passengers: PassengerCounts) -> dict[str, str]:
    run_date = train.run_date or train.departure_date or ""
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
    # Ara13010 sends passenger1..5 = lfn_getRsv("psgInfoPerPrnb1..5"), i.e. the COMPACTED
    # gds_rsv counts (ara1001l.js:1219-1223): only count>0 types packed contiguously in
    # canonical psgTpCd order, with the trailing slots padded "0" (compaction at
    # ara0101v.js:824-836). NOT one fixed slot per type. Example (1 adult + 1 child):
    # passenger1=1, passenger2=1, passenger3=0, passenger4=0, passenger5=0. It carries no
    # psgTpCd*/psgInfoPerPrnb*/infantCnt.
    compacted = [count for _type_code, count in _compact_passenger_slots(passengers)]
    for index in range(1, len(PASSENGER_TYPE_CODES) + 1):
        count = compacted[index - 1] if index <= len(compacted) else 0
        payload[f"passenger{index}"] = str(count)
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

    **Provenance — this exact body was accepted live on 2026-07-25.** The three
    fields came from srtgo (``srt.py:1138``; our notes at
    ``docs/analysis/ref-srtgo_plus.md`` §7.1) and have ZERO hits across all
    21,673 files of our v2.0.41 offline decompile
    (``docs/analysis/cross-validation-2026-07-21.md``) — nothing in our own
    bundle corroborates them, apart from ``jrnyCnt``: our app hard-codes
    ``"jrnyCnt":"1"`` (여정건수) at ``ara0101v.js:92``, which corroborates the
    VALUE but not this route's use of it, and ``rsvChgTno`` which is 0-hit
    entirely. One operator-run round trip then POSTed exactly this form to the
    real server and released a real unpaid hold (``SUCC`` / ``IRG000000``). That
    covered a SINGLE-journey, one-adult hold, so ``jrnyCnt="1"`` is confirmed
    for that case and the multi-leg value remains uncaptured.

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
