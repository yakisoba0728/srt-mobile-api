from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SrtSession:
    login_id: str | None = field(default=None, repr=False)
    user_map: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class PassengerCounts:
    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0
    infant: int = 0

    def __post_init__(self) -> None:
        values = (
            self.adult,
            self.child,
            self.senior,
            self.disability_1_to_3,
            self.disability_4_to_6,
            self.infant,
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
            + self.infant
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
    train_group_code: str = "900"
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


@dataclass(frozen=True)
class TrainSearchResult:
    trains: list[TrainSummary]
    result: dict[str, Any] = field(default_factory=dict, repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class MutualVerificationResult:
    message_code: str
    status: str
    message: str = field(default="", repr=False)
    verification_code: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class HtmlPage:
    text: str = field(repr=False)
    raw: str = field(repr=False)


@dataclass(frozen=True)
class SeatSelectionPage(HtmlPage):
    pass


@dataclass(frozen=True)
class TimetableRow:
    station_name: str
    times: tuple[str, ...]
    raw_text: str


@dataclass(frozen=True)
class TimetablePage(HtmlPage):
    rows: tuple[TimetableRow, ...] = ()


@dataclass(frozen=True)
class FareItem:
    label: str
    amount: int
    raw_amount: str


@dataclass(frozen=True)
class FarePage(HtmlPage):
    items: tuple[FareItem, ...] = ()


@dataclass(frozen=True)
class SearchPageState:
    hidden_fields: dict[str, str] = field(default_factory=dict, repr=False)
    raw: str = field(default="", repr=False)
