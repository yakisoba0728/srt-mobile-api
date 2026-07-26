from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _is_digits(value: object) -> bool:
    """True for a non-empty ASCII decimal string.

    ``str.isdigit`` is not enough on its own: it accepts superscripts and other
    Unicode digit forms that are not wire-legal, and these values all end up in
    a form body.
    """
    return (
        isinstance(value, str)
        and bool(value)
        and all("0" <= character <= "9" for character in value)
    )


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

    @property
    def membership_number(self) -> str:
        """The account's 회원번호, read from the login response's ``userMap``.

        This is NOT newly captured: :class:`SrtSession` has always kept the whole
        ``userMap`` the login returned, and ``MB_CRD_NO`` is one of its keys
        (``docs/analysis/full-api-analysis-2026-07-20.md:431``, which also
        records the app's own convention that an EMPTY ``MB_CRD_NO`` means "not
        logged in"). This property only surfaces it, so a caller never has to
        reach into ``user_map`` or supply the number by hand.

        It exists because the card-payment form carries it as ``mbCrdNo``. Both
        halves of that are worth separating: the NAME ``mbCrdNo`` is the app's
        own — ``ara0101v.js:319,321`` reads a client-side ``mbCrdNo`` and
        branches on its ``"11"`` prefix for 국회의원 후급 — while its presence on
        the ``Ata09036`` payment body is attested only by the reference
        implementations' live runs (see
        :func:`~srt_mobile_api.payloads.card_payment_payload`).

        Returns ``""`` when the key is absent or not a string, which is also how
        the app spells "no membership number".
        """
        value = self.user_map.get("MB_CRD_NO")
        return value if isinstance(value, str) else ""


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
    # NOTE the asymmetry, which is the server's and not ours. The two fields
    # above carry gnrmRsvPsbStr/sprmRsvPsbStr, which really are availability
    # STRINGS ("예약가능" / "매진"). The two below carry rsvWaitPsbCd and
    # stmpRsvPsbFlgCd, which are CODES: the live capture of 2026-07-26 saw
    # rsvWaitPsbCd=" 0" (leading space included, as sent) and
    # stmpRsvPsbFlgCd="YY". Their human-readable counterparts are the *_name
    # fields below; a caller asking "can I join the waitlist?" wants
    # reservation_wait_availability_name ("신청하기" / "매진"), not " 0".
    reservation_wait_availability: str | None = None
    standing_availability: str | None = None
    # The 상태명 columns of the same four availabilities. Present in every live
    # dsOutput1 row and previously dropped outright, which left the waitlist and
    # standing states readable only as opaque codes. The group search
    # (Ara10082) omits rsvWaitPsbCdNm and stndRsvPsbCdNm entirely, so all four
    # stay optional.
    general_seat_availability_name: str | None = None
    special_seat_availability_name: str | None = None
    reservation_wait_availability_name: str | None = None
    standing_availability_name: str | None = None
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
class SrtReservationSummary:
    """One row of the 예약/발권 목록 (``/atc/selectListAtc14016_n.do``).

    Built by zipping two parallel containers by index — ``trainListMap[i]``
    (journey identity) with ``payListMap[i]`` (settlement state) — which is how
    srtgo reads this endpoint (``srt.py:1069-1082``).

    **Only ``pnr_no`` is required.** It is the identity that feeds
    :meth:`~srt_mobile_api.client.SrtClient.cancel` and
    ``scripts/recover_hold.py``, and it is the entire reason this read exists.
    Every other field is optional and defaults to ``None``, because the
    NON-EMPTY row shape has never been observed by this repository: the account
    used for live verification has no reservations, so the 2026-07-26 probe saw
    ``trainListMap: []`` / ``payListMap: []``. The field names below therefore
    come from srtgo's live runs, NOT from our v2.0.41 bundle — where
    ``payListMap``, ``tkSpecNum``, ``iseLmtTm`` and ``stlFlg`` all have zero
    hits. ``iseLmtDt``, ``rcvdAmt``, ``seatNum``, ``pnrNo``, ``rsvChgTno`` and
    ``jrnyCnt`` DO appear, in the live 승차권 확인 page's own inline JavaScript
    (``gotoDetailARD02018(...)``, ``gotoDetailARD0201V(...)``), so those names
    are corroborated by the app while their placement in these two containers is
    not.

    Treat a ``None`` here as "the server did not send this field under this
    name", not as "the reservation has no such value", and read
    :attr:`raw_train` / :attr:`raw_pay` when you need the ground truth.
    """

    pnr_no: str = field(repr=False)
    # trainListMap[i] — srtgo srt.py:1069-1082
    received_amount: str | None = None  # rcvdAmt
    ticket_special_number: str | None = None  # tkSpecNum
    seat_number: str | None = field(default=None, repr=False)  # seatNum
    # payListMap[i] — srtgo srt.py:1069-1082
    service_class_code: str | None = None  # stlbTrnClsfCd
    train_no: str | None = None  # trnNo
    departure_date: str | None = None  # dptDt
    departure_time: str | None = None  # dptTm
    departure_station_code: str | None = None  # dptRsStnCd
    arrival_time: str | None = None  # arvTm
    arrival_station_code: str | None = None  # arvRsStnCd
    payment_limit_date: str | None = None  # iseLmtDt
    payment_limit_time: str | None = None  # iseLmtTm
    settlement_flag: str | None = None  # stlFlg
    raw_train: dict[str, Any] = field(default_factory=dict, repr=False)
    raw_pay: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SrtReservationListResult:
    """The parsed 예약/발권 목록, plus the envelope the server sent with it.

    ``reservations`` is empty for an account with nothing booked. That case is
    live-verified (2026-07-26) and is NOT spelled the way an empty train search
    is: the search answers ``strResult=FAIL`` / ``WRG000000``, whereas this
    endpoint answers ``resultMap[0].strResult="SUCC"`` / ``IRZ000005`` /
    "조회할 자료가 없습니다." with genuinely empty arrays. See
    :func:`~srt_mobile_api.parsers.parse_reservation_list_response` for the
    second envelope (``rsMap``) that says FAIL on the very same response, and
    why it is deliberately not read as a failure.

    ``row_count`` / ``total_page_count`` are ``rowCnt`` / ``totPageCnt``, sent as
    JSON integers (both ``0`` in the observed empty response); they are ``None``
    when absent.
    """

    reservations: tuple[SrtReservationSummary, ...]
    status: str
    message_code: str = ""
    message: str = field(default="", repr=False)
    row_count: int | None = None
    total_page_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def pnr_numbers(self) -> tuple[str, ...]:
        """Every PNR in the list, in server order.

        The recovery-shaped view: ``scripts/recover_hold.py --list`` prints
        exactly this, so an operator who lost a PNR can get it back without
        knowing anything about the row layout.
        """
        return tuple(item.pnr_no for item in self.reservations)


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


#: Installment terms the payment form documents for ``ismtMnthNum1``: 일시불 (0)
#: or 2..12 or 24 months. Kept as data so the validator and the tests read the
#: same list.
INSTALLMENT_MONTH_OPTIONS = frozenset({0, *range(2, 13), 24})


@dataclass(frozen=True)
class SrtPaymentCard:
    """The card fields a 카드결제 puts on the wire, validated but never sent here.

    **Nothing in this library can transmit these values.** ``payment`` is
    outside :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`, so
    :meth:`~srt_mobile_api.client.SrtClient.pay_with_card` can only ever return
    a redacted preview. This type exists so the form can be BUILT and checked.

    Every field is ``repr=False`` and every field NAME is registered in
    :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS`, so both ``repr()`` and
    :func:`~srt_mobile_api.redaction.redact_value` mask them. Masking by name
    rather than by pattern is deliberate: ``CARD_RE`` only matches a 13-19 digit
    run, which a 2-digit PIN, a ``YYMM`` expiry and a ``YYMMDD`` birthdate all
    slip past.

    ``card_type`` is ``"J"`` (개인) or ``"S"`` (법인), and it decides what
    ``card_validation_number`` must be: a ``YYMMDD`` birthdate for ``"J"``, a
    10-digit 사업자등록번호 for ``"S"``. ``card_password`` is the FIRST TWO
    DIGITS of the card PIN, not the whole PIN.
    """

    card_number: str = field(repr=False)
    card_password: str = field(repr=False)
    card_validation_number: str = field(repr=False)
    card_expire_date: str = field(repr=False)
    installment_months: int = 0
    card_type: str = "J"

    def __post_init__(self) -> None:
        if self.card_type not in {"J", "S"}:
            raise ValueError("card_type must be 'J' (개인) or 'S' (법인)")
        if type(self.installment_months) is not int or (
            self.installment_months not in INSTALLMENT_MONTH_OPTIONS
        ):
            raise ValueError(
                "installment_months must be 0 (일시불), 2..12, or 24"
            )
        # The PAN travels in the clear, so it is checked for shape rather than
        # by a Luhn digit: a deliberately synthetic test PAN must stay
        # constructible, and this library must never be the thing that tells a
        # caller whether a card number is real.
        if not _is_digits(self.card_number) or not 12 <= len(self.card_number) <= 19:
            raise ValueError("card_number must be 12-19 digits, no separators")
        if not _is_digits(self.card_password) or len(self.card_password) != 2:
            raise ValueError(
                "card_password must be the first TWO digits of the card PIN"
            )
        if not _is_digits(self.card_expire_date) or len(self.card_expire_date) != 4:
            raise ValueError("card_expire_date must use YYMM")
        if not "01" <= self.card_expire_date[2:] <= "12":
            raise ValueError("card_expire_date month must be 01..12")
        expected = 6 if self.card_type == "J" else 10
        if (
            not _is_digits(self.card_validation_number)
            or len(self.card_validation_number) != expected
        ):
            raise ValueError(
                "card_validation_number must be a YYMMDD birthdate for card_type "
                "'J' or a 10-digit 사업자등록번호 for 'S'"
            )


@dataclass(frozen=True)
class SrtPaymentResult:
    """The parsed envelope of a card payment (카드결제).

    **UNVERIFIED, and differently unverified from every other envelope here.**
    The route, the body and this envelope come from the reference
    implementations' live runs only; the route ``Ata09036`` has zero hits across
    all 21,673 files of our v2.0.41 offline decompile, and our own app does not
    use this path at all (see
    :func:`~srt_mobile_api.parsers.parse_card_payment_response`). No request has
    ever been sent, so no response has ever been seen by this repository.

    ``succeeded`` and ``failed`` are NOT complements, and that is the point. The
    reference implementations treat only an explicit ``"FAIL"`` as a failure and
    let every other value fall through as success; this type refuses to make
    that call for an unrecognised status, because for a payment both mistakes
    are expensive. A status that is neither ``"SUCC"`` nor ``"FAIL"`` means
    **unknown**: read :attr:`raw`, confirm out of band whether the card was
    charged, and do NOT retry blindly — a retried payment can charge twice.
    """

    status: str
    message_code: str = ""
    message: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCC"

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"


@dataclass(frozen=True)
class HtmlPage:
    text: str = field(repr=False)
    raw: str = field(repr=False)


@dataclass(frozen=True)
class SeatCarOption:
    """One 호차 the seat page offers, with the seats it still has free.

    Read from the page's ``<select id="selectScarNo">`` — the only inventory the
    seat page itself carries. The seat GRID is not in this response at all: the
    real page leaves ``<div id="trnScarSeatInfo">`` empty and fetches the grid
    separately once a car is chosen.
    """

    car_number: str
    label: str
    available_seat_count: int | None = None


@dataclass(frozen=True)
class SeatSelectionPage(HtmlPage):
    # The 호차 list in document order. Empty for a page that carried no car
    # select at all; see parsers.parse_seat_selection_page, which refuses the
    # server's error shell outright rather than returning it as an empty page.
    cars: tuple[SeatCarOption, ...] = ()


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
