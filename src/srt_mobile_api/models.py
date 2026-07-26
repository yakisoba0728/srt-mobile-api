from dataclasses import dataclass, field, replace
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

    def for_return_leg(
        self,
        departure_date: str,
        departure_time: str = "000000",
    ) -> "TrainSearchQuery":
        """Build the 오는열차 (return-leg) search query for a round trip.

        Exactly what the app does when it re-searches for the return train:
        swap the departure and arrival stations and search from
        ``back_dptDt1`` / ``back_dptTm1`` instead of ``dptDt1`` / ``dptTm1``
        (``ara1001l.js:110-115``, the ``fv_sRtnCd == "2"`` branch of
        ``fn_search``). Everything else — party, train group, seat attribute —
        is carried over, because the app carries it over too: the return leg is
        a re-search of the same booking form, not a new one.

        The station SWAP is the part worth having in code. A round trip in SRT
        is not one request with two legs; it is two ordinary one-way searches
        and two ordinary one-way reservations (see
        :meth:`~srt_mobile_api.client.SrtClient.reserve`), and the only thing
        that makes the second one a "return" is that the stations are reversed
        and both reservations carry ``rtnDv=1``. Getting that reversal wrong is
        silent — it books a second outbound.

        ``departure_time`` defaults to ``"000000"``, the app's own seed for
        ``back_dptTm1`` (``ara0101v.js:111``), rather than to this query's own
        departure time: a return train that must leave after the outbound train
        arrives is the normal case, and starting the return search at midnight
        of the return date shows every candidate. The app refuses a return date
        earlier than the outbound date, and a same-date return earlier than the
        outbound time (``ara0101v.js:593-603``); those are dialogs on a form
        this library does not render, and both would be rejected by the operator
        long before a request, so they are documented here rather than enforced.
        """
        return replace(
            self,
            departure_station_code=self.arrival_station_code,
            arrival_station_code=self.departure_station_code,
            departure_station_name=self.arrival_station_name,
            arrival_station_name=self.departure_station_name,
            departure_date=departure_date,
            departure_time=departure_time,
        )


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
class TransferItinerary:
    """A 환승 (transfer) itinerary: the 선행 leg and the 후행 leg, together.

    SRT models a transfer as ONE reservation carrying TWO journey slots, which
    is the opposite of how it models a round trip. The app's 환승 toggle writes
    both halves of that in a single call — ``jrnyTpCd="14"`` (환승편도) and
    ``jrnyCnt="2"`` (여정건수 2) — at ``ara0101v.js:302-303``, emitted at
    ``:310-311``. ``jrnyCnt="2"`` has exactly one write in the whole v2.0.41
    bundle and this is it, so ``jrnyCnt="2"`` means TRANSFER and nothing else;
    a round trip stays at ``"1"`` and is two separate reservations (see
    :meth:`~srt_mobile_api.client.SrtClient.reserve`).

    The two legs go into 여정 slots 1 and 2, and the app names the slot values
    itself: ``"jrnySqno1" : "001"  //여정일련번호1(001:선행, 002:후행)``
    (``ara0101v.js:97``, echoed as ``0001 : 선행, 0002 : 후행`` at
    ``ara1001l.js:1607``). So :attr:`first_leg` is 선행 (``jrnySqno1="001"``) and
    :attr:`second_leg` is 후행 (``jrnySqno2="002"``).

    **Why this type exists at all.** A transfer search row is HALF an itinerary.
    Nothing on a :class:`TrainSummary` says so — it looks exactly like a
    reservable direct train — so handing rows from a transfer search straight to
    :meth:`~srt_mobile_api.client.SrtClient.reserve` would book one leg of a
    two-leg journey and strand the traveller mid-route, silently and with a
    perfectly successful-looking PNR. Requiring both legs to be named at once,
    in a type that
    :meth:`~srt_mobile_api.client.SrtClient.reserve_transfer` is the only
    consumer of, is what makes half an itinerary unrepresentable rather than
    merely discouraged.

    Construction therefore validates the join, because a pair that does not
    connect is not an itinerary:

    * both legs must be exactly :class:`TrainSummary` (the same exact-type rule
      ``personal_reservation_payload`` applies, for the same reason: a subclass
      could re-derive any of these fields),
    * the first leg must ARRIVE where the second leg DEPARTS — that station is
      the 환승역, and getting it wrong is the failure this class exists to
      prevent,
    * the second leg must not depart before the first leg arrives, when both
      rows carry enough date/time to tell. The app applies exactly this
      comparison to the 왕복 second leg (``ara1001l.js:1258-1272``: 가는열차's
      arvDt/arvTm against 오는열차's dptDt/dptTm, refusing an earlier date and
      then an earlier same-date time), and a transfer needs it at least as much,
    * the two legs must not be the same train.

    The origin and destination of the whole journey are :attr:`first_leg`'s
    departure and :attr:`second_leg`'s arrival; the 환승역 in between is
    :attr:`transfer_station_code`.

    NOT LIVE-VERIFIED. Every field name and code above is read out of the
    v2.0.41 bundle, but no transfer search or reservation has been sent to the
    real server from this library.
    """

    first_leg: TrainSummary
    second_leg: TrainSummary

    def __post_init__(self) -> None:
        for name, leg in (("first_leg", self.first_leg), ("second_leg", self.second_leg)):
            if type(leg) is not TrainSummary:
                raise ValueError(f"{name} must be an exact TrainSummary")
        connection = self.first_leg.arrival_station_code
        if not connection or not self.second_leg.departure_station_code:
            raise ValueError(
                "a transfer itinerary needs the first leg's arrival station and "
                "the second leg's departure station to check that the legs connect"
            )
        if connection != self.second_leg.departure_station_code:
            raise ValueError(
                "transfer legs do not connect: the first leg arrives at "
                f"{connection} but the second departs from "
                f"{self.second_leg.departure_station_code}"
            )
        if (
            self.first_leg.train_no == self.second_leg.train_no
            and self.first_leg.run_date == self.second_leg.run_date
        ):
            raise ValueError(
                "a transfer itinerary needs two different trains; both legs are "
                f"train {self.first_leg.train_no}"
            )
        self._refuse_a_connection_that_runs_backwards()

    def _refuse_a_connection_that_runs_backwards(self) -> None:
        # Only checked when both sides are actually present. A hand-built
        # TrainSummary may carry no arrival date, and the reservation form
        # itself tolerates a blank arvDt1 (see personal_reservation_payload), so
        # an absent field is treated as "cannot tell", never as "invalid" --
        # the same rule the standby row-image guard follows.
        arrival_date = self.first_leg.arrival_date or self.first_leg.departure_date
        departure_date = self.second_leg.departure_date
        arrival_time = self.first_leg.arrival_time
        departure_time = self.second_leg.departure_time
        if not (arrival_date and departure_date and arrival_time and departure_time):
            return
        if (arrival_date, arrival_time) > (departure_date, departure_time):
            raise ValueError(
                "the second transfer leg departs before the first one arrives: "
                f"arrives {arrival_date} {arrival_time}, departs "
                f"{departure_date} {departure_time}"
            )

    @property
    def transfer_station_code(self) -> str:
        """The 환승역 the two legs meet at, validated equal at construction."""
        return self.first_leg.arrival_station_code or ""

    @property
    def origin_station_code(self) -> str:
        return self.first_leg.departure_station_code or ""

    @property
    def destination_station_code(self) -> str:
        return self.second_leg.arrival_station_code or ""

    @property
    def legs(self) -> tuple[TrainSummary, TrainSummary]:
        """Both legs in 여정 order: 선행 first, 후행 second."""
        return (self.first_leg, self.second_leg)


@dataclass(frozen=True)
class UnpairedTransferGroup:
    """Rows a 환승 search returned that could NOT be made into an itinerary.

    Kept rather than dropped. A transfer search's pairing is *our* inference —
    the server sends a flat row list and we group it — so when the inference
    does not fit, the rows have to go somewhere a caller can see. Dropping them
    silently would hide an itinerary that exists; pairing them anyway would hand
    back two trains that are not one journey, and that is the worse of the two.

    :attr:`reason` is a plain sentence, not a code: these are conditions we have
    never observed live, so a code vocabulary would be invented.
    """

    itinerary_no: str
    rows: tuple["TrainSummary", ...]
    reason: str


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
class TransferSearchResult:
    """The result of a 환승 search: itineraries, leftovers, and the raw rows.

    **The response shape is live-confirmed (2026-07-26).** A transfer search
    returns ONE ROW PER LEG in the ordinary ``dsOutput1`` list — the same column
    set a direct row has — and the legs of one itinerary share a ``trnOrdrNo``.
    On 동대구(0015) -> 광주송정(0036) the server sent 10 rows: ``trnOrdrNo=1`` was
    train 382 동대구->오송 plus train 411 오송->광주송정, ``trnOrdrNo=2`` was train
    14 동대구->천안아산 plus train 475 천안아산->광주송정, and so on. Every row
    carried ``chtnDvCd="2"``, and ``fllwPgExt2`` was ``null``.

    So ``trnOrdrNo`` is the ITINERARY index here, not a train ordering within
    the whole list. The ``...2`` columns do exist on every row and are empty
    strings (``trnNo2: ""``, ``dptRsStnCd2: ""``, ``jrnySqno: ""``) — because the
    second leg is a separate ROW, not a set of columns.

    :attr:`itineraries` are the groups that paired cleanly.
    :attr:`unpaired` are the groups that did not, each with a reason — read it
    if you care about completeness, because the count of itineraries alone
    cannot tell you whether anything was set aside. :attr:`search` is the
    untouched :class:`TrainSearchResult`, so the raw rows and the raw JSON stay
    reachable: the grouping above is our inference layer and a caller must be
    able to go behind it.
    """

    itineraries: tuple[TransferItinerary, ...]
    unpaired: tuple[UnpairedTransferGroup, ...]
    search: TrainSearchResult

    @property
    def rows(self) -> list["TrainSummary"]:
        """Every row the server sent, ungrouped and in server order."""
        return self.search.trains

    @property
    def raw(self) -> dict[str, Any]:
        """The whole response body, exactly as received."""
        return self.search.raw


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
    """The card fields a 카드결제 puts on the wire, validated before they go.

    **These values really can be transmitted.** ``payment`` joined
    :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` on 2026-07-26, so
    :meth:`~srt_mobile_api.client.SrtClient.pay_with_card` with
    ``dry_run=False`` and an unambiguous card-kind claim will charge this card.
    The default remains a redacted preview, and
    :data:`~srt_mobile_api.safety.CARD_SECRET_FIELDS` keeps these four names off
    every route that is not the payment route.

    The four SECRET fields — :attr:`card_number`, :attr:`card_password`,
    :attr:`card_validation_number`, :attr:`card_expire_date` — are each
    ``repr=False`` AND registered under their own names in
    :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS`, so both ``repr()`` and
    :func:`~srt_mobile_api.redaction.redact_value` mask them. Masking by name
    rather than by pattern is deliberate: ``CARD_RE`` only matches a 13-19 digit
    run, which a 2-digit PIN, a ``YYMM`` expiry and a ``YYMMDD`` birthdate all
    slip past.

    :attr:`installment_months` and :attr:`card_type` are deliberately NOT
    hidden: neither is a secret, and seeing "36-month installment, corporate
    card" in a ``repr`` is useful. Note the asymmetry this creates — their WIRE
    spellings ``ismtMnthNum1`` and ``athnDvCd1`` *are* in ``SENSITIVE_KEYS``, so
    a :class:`~srt_mobile_api.consent.MutationPreview` masks them while this
    object's ``repr`` does not. That is intended: a preview is a whole card
    form, where the safe default is to mask everything adjacent to the PAN.

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

    **LIVE-VERIFIED 2026-07-26**: one real charge answered ``SUCC`` /
    ``IRT000000`` and one fake-card probe answered ``FAIL`` / ``WRT100170``, so
    both branches below have been read off the wire. The origin is unchanged —
    the route, the body and this envelope came from the reference
    implementations' live runs only, the route ``Ata09036`` has zero hits across
    all 21,673 files of our v2.0.41 offline decompile, and our own app does not
    use this path at all (see
    :func:`~srt_mobile_api.parsers.parse_card_payment_response`).

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
class SrtRefundTicketInfo:
    """The issued-ticket identity a 환불 needs, from refund step 1.

    Read from ``POST /atc/getListAtc14087.do`` (no body, Referer-gated) at
    ``outDataSets.dsOutput1[0]`` — note ``dsOutput1``, not the ``dsOutput0``
    every other read here uses. See
    :func:`~srt_mobile_api.parsers.parse_refund_ticket_info_response` for the
    provenance: this route exists in ONE reference library, not two, and is
    live-verified as of 2026-07-26.

    :attr:`return_password` is the credential that authorises the refund and is
    hidden from ``repr``; it and :attr:`buyer_name` and :attr:`pnr_no` are
    redacted by :func:`~srt_mobile_api.redaction.redact_payload`. The three sale
    identifiers are deliberately not, because with the password masked they
    authorise nothing and a fully-redacted preview says nothing at all.
    """

    pnr_no: str = field(repr=False)
    sale_date: str = ""  # ogtkSaleDt
    sale_window_number: str = ""  # ogtkSaleWctNo
    sale_sequence_number: str = ""  # ogtkSaleSqno
    return_password: str = field(default="", repr=False)  # ogtkRetPwd
    buyer_name: str = field(default="", repr=False)  # buyPsNm
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SrtRefundResult:
    """The parsed envelope of a paid-ticket refund (환불).

    **LIVE-VERIFIED 2026-07-26**: ``SUCC`` / ``IRT200277`` for a real ticket,
    after which the account was confirmed empty from a separate session. The
    origin is unchanged and still the thinnest here. Unlike the payment — which
    at least has one implementation copied into two libraries — this route
    exists in exactly ONE reference implementation, was added there four days
    after it vendored its SRT support from elsewhere, and has no upstream at
    all. The route is 0-hit across all 21,673 files of our v2.0.41 offline
    decompile, so the run is live-server evidence and not static corroboration.

    The envelope itself is the ordinary SRT ``resultMap`` SUCC/FAIL one — the
    same as cancel's, and unlike the payment's ``outDataSets.dsOutput0``. A
    business failure is RETURNED, not raised: a caller asking "was my ticket
    refunded?" must be able to read the answer without exception handling.
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
