import re

from .models import PassengerCounts, TrainSearchQuery, TrainSummary
from .stations import station_name_by_code


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
    payload = search_ajax_payload(query, netfunnel_key, hydrated_fields=hydrated_fields)
    payload["grpDv"] = "1"
    payload["psgNum"] = str(max(query.passengers.total, 10))
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
    train: TrainSummary, cabin_class: str = "1", seat_count: str = "1"
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
        "seatAttCd": _required_digits(train.seat_attr_code, "seat_attr_code", length=3),
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
