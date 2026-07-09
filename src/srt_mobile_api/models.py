from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SrtSession:
    login_id: str | None = None
    user_map: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PassengerCounts:
    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0
    infant: int = 0

    @property
    def total(self) -> int:
        return self.adult + self.child + self.senior + self.disability_1_to_3 + self.disability_4_to_6 + self.infant


@dataclass(frozen=True)
class NetFunnelToken:
    action: str
    key: str
    raw_type: str
    code: str
    params: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainSearchQuery:
    departure_station_code: str
    arrival_station_code: str
    departure_date: str
    departure_time: str = "060000"
    passengers: PassengerCounts = field(default_factory=PassengerCounts)
    train_group_code: str = "900"
    seat_attr_code: str = "015"


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
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainSearchResult:
    trains: list[TrainSummary]
    result: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HtmlPage:
    text: str
    raw: str
