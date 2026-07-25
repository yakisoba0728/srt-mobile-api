from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SeatType(Enum):
    """Seat-class preference for a reservation, mirroring srtgo (srt.py:413-417).

    ``*_FIRST`` prefer one class but fall back to the other based on the train's
    live availability; ``*_ONLY`` force one class regardless.
    """

    GENERAL_FIRST = 1  # 일반실 우선
    GENERAL_ONLY = 2  # 일반실만
    SPECIAL_FIRST = 3  # 특실 우선
    SPECIAL_ONLY = 4  # 특실만


@dataclass(frozen=True)
class SrtSession:
    login_id: str | None = field(default=None, repr=False)
    user_map: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class PassengerCounts:
    # SRT has exactly five passenger types (psgTpCd 1..5, commCode.js:55-88); there is
    # NO infant type (`infantCnt` appears nowhere in the app). Every head-count field
    # (totPrnb/totalPessnger/psgNum) must equal sum(psgInfoPerPrnb1..5), the invariant
    # getPsgTotCnt() guarantees (ara0101v.js:35), so no field outside the five types may
    # feed `total`.
    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0

    def __post_init__(self) -> None:
        values = (
            self.adult,
            self.child,
            self.senior,
            self.disability_1_to_3,
            self.disability_4_to_6,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("passenger counts must be non-negative integers")
        if sum(values) < 1:
            raise ValueError("at least one passenger is required")

    @property
    def total(self) -> int:
        return (
            self.adult
            + self.child
            + self.senior
            + self.disability_1_to_3
            + self.disability_4_to_6
        )


@dataclass(frozen=True)
class NetFunnelToken:
    action: str
    key: str = field(repr=False)
    raw_type: str
    code: str
    params: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class TrainSearchQuery:
    departure_station_code: str
    arrival_station_code: str
    departure_date: str
    departure_time: str = "060000"
    passengers: PassengerCounts = field(default_factory=PassengerCounts)
    # 열차그룹코드. "109" (전체) is the app's own booking-screen default, seeded
    # twice on load: ara0101v.js:85-86 sets the picker button
    # ($("#btn_trnGpCd").val("109"), text "전체", with the comment
    # "300: SRT, 900: KTX+SRT, 109: 전체") and :98-99 seeds the reservation state
    # ("trnGpCd1": "109", "trnGpNm1": "전체"). All three values are legitimate on
    # the wire, so this is a default CHOICE, not a wire correctness question --
    # and the app's choice is 전체. It also removes an internal inconsistency:
    # SrtClient.get_train_group_selector and train_group_selector_payload
    # already default to "109"/"전체". TRAIN_GROUP_OPTIONS pairs it with
    # stlbTrnClsfCd "05" (역무차종별코드 05:전체), which is what ara0101v.js:87
    # seeds alongside it.
    train_group_code: str = "109"
    seat_attr_code: str = "015"
    departure_station_name: str | None = None
    arrival_station_name: str | None = None

    def __post_init__(self) -> None:
        if not self.departure_station_code.strip() or not self.arrival_station_code.strip():
            raise ValueError("departure and arrival station codes are required")
        if len(self.departure_date) != 8 or not self.departure_date.isdigit():
            raise ValueError("departure_date must use YYYYMMDD")
        if len(self.departure_time) != 6 or not self.departure_time.isdigit():
            raise ValueError("departure_time must use HHMMSS")
        if self.train_group_code not in {"300", "900", "109"}:
            raise ValueError("train_group_code must be one of 300, 900, or 109")


@dataclass(frozen=True)
class TrainSummary:
    train_no: str
    train_group_code: str | None = None
    service_class_code: str | None = None
    run_date: str | None = None
    departure_date: str | None = None
    departure_time: str | None = None
    arrival_date: str | None = None
    arrival_time: str | None = None
    departure_station_code: str | None = None
    arrival_station_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    departure_station_name: str | None = None
    arrival_station_name: str | None = None
    departure_run_order: str | None = None
    arrival_run_order: str | None = None
    seat_attr_code: str | None = None
    run_time: str | None = None
    train_run_order: int | None = None
    departure_consist_order: str | None = None
    arrival_consist_order: str | None = None
    current_delay: int | None = None
    expected_delay: str | None = None
    general_seat_availability: str | None = None
    special_seat_availability: str | None = None
    reservation_wait_availability: str | None = None
    standing_availability: str | None = None
    received_amount: str | None = None
    discount_rate: str | None = None
    received_fare: str | None = None
    train_composition_codes: tuple[str, ...] = ()
    # 열차종별코드 (trnClsfCd) from the dsOutput1 search row — the app's trnSort
    # value for timetable/fare; distinct from service_class_code (stlbTrnClsfCd).
    train_class_code: str | None = None


@dataclass(frozen=True)
class TrainSearchMetadata:
    message_code: str
    status: str
    query_count: int
    has_following_page: bool | None = None
    message: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class TrainSearchResult:
    trains: list[TrainSummary]
    result: dict[str, Any] = field(default_factory=dict, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    metadata: TrainSearchMetadata | None = None


@dataclass(frozen=True)
class MutualVerificationResult:
    # msgCd is informational and absent from the documented Ara10130 dsOutput0 schema;
    # the app never reads it (ara1001l.js:234-241), so it may be None on a valid response.
    message_code: str | None
    status: str
    message: str = field(default="", repr=False)
    verification_code: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ReservationRecord:
    pnr_number: str = field(repr=False)
    journey_list_key: str = field(repr=False)
    arrival_date: str
    arrival_station_code: str
    arrival_time: str
    delay_acceptance_flag: str
    departure_date: str
    departure_station_code: str
    departure_time: str
    lump_settlement_target_number: str = field(repr=False)
    provisional_settlement_target_flag: str
    service_class_code: str
    total_seat_count: str
    train_group_code: str
    train_number: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ReservationTrain:
    seat_number: str = field(repr=False)
    car_number: str = field(repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ReservationAttemptResult:
    message_code: str
    status: str
    total_received_amount: str
    reservation: ReservationRecord
    train: ReservationTrain
    message: str = field(repr=False)
    temporary_job_sequence: str = field(repr=False)
    command: dict[str, Any] = field(repr=False)
    raw: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class SrtReservationHold:
    """A created-but-unpaid reservation hold produced by a live ``reserve``.

    Mirrors the identity srtgo keeps from a successful reserve
    (``reservListMap[0].pnrNo``, srt.py:1006): the PNR that later feeds cancel or
    payment. ``pnr_no`` and ``journey_list_key`` are secret-shaped and hidden
    from ``repr``. A dry-run reserve returns a :class:`MutationPreview` instead;
    this hold is only ever built on the (not-exercised-here) live send path.
    """

    pnr_no: str = field(repr=False)
    journey_list_key: str = field(default="", repr=False)
    total_seat_count: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SrtCancelResult:
    """The parsed envelope of an unpaid-reservation cancel (예약취소).

    The shape is the standard SRT ``resultMap`` envelope, successful when
    ``strResult == "SUCC"``. The live server produced exactly that on
    2026-07-25 (``SUCC`` / ``IRG000000``) for a single-journey unpaid hold — see
    :func:`~srt_mobile_api.parsers.parse_unpaid_cancel_response`, which also
    records why the container handling stays permissive: the route came from
    srtgo and is 0-hit in our v2.0.41 offline bundle, so only that one observed
    response corroborates it.

    A business failure is carried here as data (``succeeded`` False plus the
    server's ``message_code``), not raised: a caller asking "was my hold
    released?" must be able to read the answer without exception handling.
    ``message`` and ``raw`` are excluded from ``repr`` because the raw envelope
    echoes reservation identity.
    """

    status: str
    message_code: str = ""
    message: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCC"


@dataclass(frozen=True)
class HtmlPage:
    text: str = field(repr=False)
    raw: str = field(repr=False)


@dataclass(frozen=True)
class SeatSelectionPage(HtmlPage):
    pass


@dataclass(frozen=True)
class Notice:
    is_main: str
    page_id: str
    body: str = field(repr=False)
    post_no: int = 0
    create_date: str = ""
    is_notice: str = ""
    subject: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class NoticeListResult:
    notices: tuple[Notice, ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class TimetableRow:
    station_name: str
    times: tuple[str, ...]
    raw_text: str = field(repr=False)
    # 정차역 코드, read from the row's own
    # `getStationNameByCode('XXXX')` script — the only place the real timetable
    # page names a stop, since the name cell is rendered empty and filled in
    # client-side (see parsers.parse_timetable_page). station_name is this code
    # resolved through stations.station_name_by_code; the code itself is kept
    # because it is stable machine-readable identity the response carries, and
    # it was previously discarded.
    station_code: str = ""


@dataclass(frozen=True)
class TimetablePage(HtmlPage):
    rows: tuple[TimetableRow, ...] = ()


@dataclass(frozen=True)
class FareItem:
    label: str
    amount: int | None
    raw_amount: str
    available: bool = True
    status: str | None = None

    def __post_init__(self) -> None:
        if self.amount is None and self.available:
            object.__setattr__(self, "available", False)


@dataclass(frozen=True)
class FarePage(HtmlPage):
    items: tuple[FareItem, ...] = ()
    semantic_items: tuple[FareItem, ...] = ()

    @property
    def available_items(self) -> tuple[FareItem, ...]:
        return self.items


@dataclass(frozen=True)
class SearchPageState:
    hidden_fields: dict[str, str] = field(default_factory=dict, repr=False)
    raw: str = field(default="", repr=False)
