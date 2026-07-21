import re

from .models import PassengerCounts, TrainSearchQuery, TrainSummary


TRAIN_GROUP_OPTIONS = {
    "300": ("SRT", "17"),
    "900": ("KTX+SRT", "00"),
    "109": ("전체", "05"),
}
PASSENGER_SLOTS = (
    ("adult", "1"),
    ("child", "5"),
    ("senior", "4"),
    ("disability_1_to_3", "2"),
    ("disability_4_to_6", "3"),
    ("infant", "6"),
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


def _passenger_fields(
    passengers: PassengerCounts,
    hydrated_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    hydrated_fields = hydrated_fields or {}
    fields: dict[str, str] = {}
    for index, (attribute, type_code) in enumerate(PASSENGER_SLOTS, start=1):
        count = getattr(passengers, attribute)
        hydrated_code = hydrated_fields.get(f"psgTpCd{index}", "")
        fields[f"psgTpCd{index}"] = (hydrated_code or type_code) if count else ""
        fields[f"psgInfoPerPrnb{index}"] = str(count)
    fields["infantCnt"] = str(passengers.infant)
    return fields


def _distinct_passenger_type_count(passengers: PassengerCounts) -> int:
    # psgGridcnt is the number of distinct passenger TYPES with count>0, NOT the head
    # count: the app sets psgGridcnt=idx-1 (occupied type count, ara0101v.js:826-836)
    # and srtgo uses len(combined_passengers) (srt.py:191). Infant is not a psgTpCd
    # picker type, so it is excluded from the count.
    return sum(
        1
        for attribute, _type_code in PASSENGER_SLOTS
        if attribute != "infant" and getattr(passengers, attribute) > 0
    )


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
    names = [train.departure_station_name or "", train.arrival_station_name or ""]
    return "-".join(name for name in names if name)


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
    # Ara13010 carries counts under passenger1..passenger5 (= psgInfoPerPrnb1..5),
    # keyed by the same canonical type codes as the selector (ara1001l.js:1219-1223).
    # It does NOT take psgTpCd*/psgInfoPerPrnb*/infantCnt.
    payload["passenger1"] = str(passengers.adult)
    payload["passenger2"] = str(passengers.disability_1_to_3)
    payload["passenger3"] = str(passengers.disability_4_to_6)
    payload["passenger4"] = str(passengers.senior)
    payload["passenger5"] = str(passengers.child)
    return payload
