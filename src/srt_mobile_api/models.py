"""요청 입력과 응답 결과의 값 타입 전부.

SRT 앱은 WebView 껍데기라 서버가 돌려주는 것이 대개 렌더링된 HTML 입니다.
:mod:`srt_mobile_api.parsers` 가 그 HTML 에서 뽑아낸 값이 여기 있는 frozen
dataclass 로 들어옵니다. 원본 페이지가 필요할 때를 위해 :class:`HtmlPage` 계열이
따로 있습니다.

여기 있는 것은 값 객체일 뿐이라 아무것도 전송하지 않습니다. 상태를 바꾸려면
:class:`~srt_mobile_api.consent.MutationConsent` 로 범주를 열어야 합니다.

민감한 필드 — 카드번호, 카드 비밀번호, 생년월일, PNR, 쿠폰번호, NetFunnel
키 — 는 ``repr`` 에서 빠지므로 객체를 그대로 찍어도 값이 새지 않습니다.

전선에 실릴 값은 만들 때 검사합니다. 역코드·날짜·시각 같은 자리는 ASCII
숫자열이어야 하고(:func:`_is_digits`), 코드값 셋(:data:`SrtTrainGroupCode`,
:data:`SrtSeatAttrCode`)은 ``Literal`` 별칭이면서 런타임에서도 다시 좁혀집니다.
"""

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Literal


#: 열차그룹코드(``trnGpCd``) — 예약 화면의 열차 종류 선택이 보내는 세 값.
#: ``"300"`` SRT, ``"900"`` KTX+SRT, ``"109"`` 전체. 앱이 자기 코드에 단 주석이
#: 그대로 이 셋입니다(``ara0101v.js:85-86``). :class:`TrainSearchQuery` 의
#: ``__post_init__`` 과 :func:`~srt_mobile_api.payloads.train_group_selector_payload`
#: 가 런타임에서도 이 셋만 받습니다 — 별칭은 자동완성용이고 검사를 대신하지 않습니다.
SrtTrainGroupCode = Literal["300", "900", "109"]

#: 예약 본문에 실리는 요구좌석속성(``seatAttCd``) — ``"015"`` 일반, ``"021"``
#: 휠체어, ``"028"`` 전동휠체어. 휠체어 두 값은 앱이 별도 동의 팝업 뒤에 두고 실제로
#: 보내는 값입니다(``ara0101v.js:611-628``).
#: :meth:`~srt_mobile_api.client.SrtClient.reserve` 와
#: :meth:`~srt_mobile_api.client.SrtClient.reserve_transfer` 의 ``seat_attr_code``
#: 가 이 셋만 받고, 런타임 검사는
#: :data:`~srt_mobile_api.payloads.SRT_REQUEST_SEAT_ATTR_CODES` 가 계속 합니다.
#: 검색 질의(:attr:`TrainSearchQuery.seat_attr_code`)와 좌석 페이지 인자는 세 자리
#: 숫자인지만 보므로 이 별칭을 쓰지 않습니다.
SrtSeatAttrCode = Literal["015", "021", "028"]


def _is_digits(value: object) -> bool:
    """비어 있지 않은 ASCII 십진 문자열이면 참.

    ``str.isdigit`` 만으로는 부족합니다. 그쪽은 위첨자를 비롯한 유니코드 숫자 형태까지
    받아들이는데, 여기서 검사하는 값은 전부 폼 본문에 실려 나가므로 ASCII ``0``-``9``
    가 아니면 서버가 알아듣지 못합니다.
    """
    return (
        isinstance(value, str)
        and bool(value)
        and all("0" <= character <= "9" for character in value)
    )


class SeatType(Enum):
    """예약할 좌석 등급 선호. srtgo 의 같은 열거형을 옮긴 것입니다(``srt.py:413-417``).

    ``*_FIRST`` 는 한쪽을 먼저 보되 그 열차의 잔여석에 따라 다른 쪽으로 넘어가고,
    ``*_ONLY`` 는 잔여석과 무관하게 한 등급만 고집합니다.
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
        """계정의 회원번호 — 로그인 응답 ``userMap`` 의 ``MB_CRD_NO`` 를 꺼내 줍니다.

        카드결제 폼이 ``mbCrdNo`` 로 이 값을 싣기 때문에 필요합니다.

        키가 없거나 문자열이 아니면 ``""`` 입니다. **빈 값이 곧 "로그인하지 않음"이라는
        것은 앱 자신의 관례입니다**
        (``docs/analysis/full-api-analysis-2026-07-20.md:431``).

        근거의 출처가 반씩 다릅니다. ``mbCrdNo`` 라는 이름은 앱의 것이고
        (``ara0101v.js:319,321``), 그것이 ``Ata09036`` 결제 본문에 실린다는 것은 참조
        구현들의 실제 전송에만 근거가 있습니다
        (:func:`~srt_mobile_api.payloads.card_payment_payload` 참고).
        """
        value = self.user_map.get("MB_CRD_NO")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class PassengerCounts:
    """승차인원 — 앱의 일곱 가지 승객 유형. 그중 다섯만 자기 슬롯으로 나갑니다.

    승차인원선택 팝업은 ``passenger1``..``passenger7`` 일곱 개를 세지만, 전송되는
    ``psgTpCd`` 슬롯은 다섯입니다.

    **유아는 자기 ``psgTpCd`` 가 없어 어린이 슬롯에 접힙니다.** 예약 페이지의
    ``goRevFn`` 이 한 자리에서 두 가지를 합니다::

        if(i==5){
            passenger = passenger + passenger6;   // 어린이 슬롯 인원에 더하고
            $('#infantCnt').val(passenger6);      // 따로 한 번 더 선언
        }

    그래서 유아는 어린이의 ``psgInfoPerPrnb`` 안에 세어지는 동시에 ``infantCnt`` 로도
    선언됩니다. ``totPrnb += passenger`` 가 접은 뒤에 실행되므로 :attr:`total` 에도
    유아가 포함됩니다. 접힌 수는 :attr:`child_slot_count` 이고, :attr:`child` 와
    이름을 갈라 두었습니다.

    **청소년은 슬롯이 있습니다 — ``psgTpCd`` 6.** 팝업의 ``passenger7`` 이고, 공공할인
    ``04`` 가 승인된 계정이 아니면 ``display:none`` 이며, 할인 승차권 페이지가
    ``psgTpCd6``/``psgInfoPerPrnb6`` 로 실어 보냅니다. 이 코드는 ``commCode.js`` 어느
    사본에도 없습니다 — v2.0.41 에도, 라이브 ``/js/commCode.js`` 에도 — 이 경로에만
    있습니다.

    ``youth`` 가 0 이 아니어도 자격을 확인하지 않고 받아들입니다. 폼을 만드는 쪽은
    그것을 알 방법이 없기 때문이며, 자격 확인은
    :meth:`~srt_mobile_api.client.SrtClient.get_public_discounts` 로 합니다.

    **확인된 범위.** 검색 요청은 응답의 ``commandMap`` 에 그대로 되돌아오므로 두 규칙을
    읽기만으로 확인할 수 있었습니다 — ``adult=1, child=2, infant=3`` 은
    ``psgTpCd2="5"``, ``psgInfoPerPrnb2="5"``, ``infantCnt="3"`` 으로 돌아왔고(접기와
    별도 선언 둘 다), ``adult=1, youth=1`` 은 ``psgTpCd2="6"`` 으로 돌아왔습니다. 즉
    서버가 두 값을 거절하지 않는다는 것까지입니다.

    **확인되지 않은 것: 청소년으로 실제 예약이 되는지, 운임이 다른지.** 그것을 보려면
    공공할인 ``04`` 를 가진 계정과 실제 예약이 필요합니다. 운임 조회는 대신이 되지
    않습니다 — 그쪽은 보낸 인원에 대한 견적이 아니라 유형별 가격표를 어느 인원
    구성에든 똑같이 돌려줍니다.
    """

    adult: int = 1
    child: int = 0
    senior: int = 0
    disability_1_to_3: int = 0
    disability_4_to_6: int = 0
    # Appended, not inserted, so every existing positional construction keeps its
    # meaning.
    infant: int = 0
    youth: int = 0

    def __post_init__(self) -> None:
        values = (
            self.adult,
            self.child,
            self.senior,
            self.disability_1_to_3,
            self.disability_4_to_6,
            self.infant,
            self.youth,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("passenger counts must be non-negative integers")
        if sum(values) < 1:
            raise ValueError("at least one passenger is required")

    @property
    def child_slot_count(self) -> int:
        """어린이 슬롯(``psgTpCd`` 5)에 실리는 수 — 어린이 + 유아.

        편의를 위한 합이 아니라 앱이 실제로 하는 접기입니다. 예약 페이지(``goRevFn``)도
        할인 승차권 페이지(``setPassenger_callback`` 의
        ``parseInt(obj.passenger5) + parseInt(obj.passenger6)``)도 똑같이 더합니다.

        **어린이 없이 유아만 있어도 이 슬롯은 채워집니다.** 앱의 검사가 합에 걸려
        있으므로(``if(passenger != '0')``) ``PassengerCounts(adult=1, infant=1)`` 은
        어린이 슬롯 1 과 ``infantCnt=1`` 을 함께 보냅니다. 페이지가 하는 그대로이고,
        여기서 다듬지 않습니다.
        """
        return self.child + self.infant

    @property
    def total(self) -> int:
        """총 인원(``totPrnb``) — 유아까지 포함한 머릿수.

        유아가 세어지는 것은 앱의 ``totPrnb += passenger`` 가 접기 **뒤에** 실행되기
        때문입니다. 팝업의 ``setTotalPassenger`` 도 ``i=1..7`` 을 전부 더합니다.

        따라서 ``getPsgTotCnt()``(``ara0101v.js:35``)가 보장하는 등식은 실제로 나가는
        슬롯들에 대해 ``totPrnb == sum(psgInfoPerPrnb…)`` 이고, 이 속성이 그 값입니다.
        """
        return (
            self.adult
            + self.disability_1_to_3
            + self.disability_4_to_6
            + self.senior
            + self.child_slot_count
            + self.youth
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
    train_group_code: SrtTrainGroupCode = "109"
    seat_attr_code: str = "015"
    departure_station_name: str | None = None
    arrival_station_name: str | None = None

    def __post_init__(self) -> None:
        if not self.departure_station_code.strip() or not self.arrival_station_code.strip():
            raise ValueError("departure and arrival station codes are required")
        if (
            self.departure_station_code.strip()
            == self.arrival_station_code.strip()
        ):
            # ara0101v.js:570-574 alerts "출발역과 도착역이 같습니다." and returns
            # without sending. What the server does with such a search is
            # unknown precisely because the app never asks it.
            raise ValueError(
                "departure and arrival stations must differ; got "
                f"{self.departure_station_code!r} for both"
            )
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
        """왕복의 오는열차 검색 질의를 만듭니다 — 출발역과 도착역을 뒤집습니다.

        앱이 오는열차를 다시 검색할 때 하는 것과 같습니다. 역을 맞바꾸고
        ``dptDt1``/``dptTm1`` 대신 ``back_dptDt1``/``back_dptTm1`` 로 찾습니다
        (``ara1001l.js:110-115``, ``fn_search`` 의 ``fv_sRtnCd == "2"`` 가지). 인원·
        열차그룹·좌석속성은 그대로 따라갑니다.

        **SRT 의 왕복은 요청 하나에 여정 둘이 아닙니다.** 평범한 편도 검색 둘과 평범한
        편도 예약 둘이며(:meth:`~srt_mobile_api.client.SrtClient.reserve` 참고), 두
        번째를 "오는" 것으로 만드는 것은 역이 뒤집혀 있다는 사실과 양쪽 예약이
        ``rtnDv=1`` 을 싣는다는 것뿐입니다.

        ``departure_time`` 기본값이 ``"000000"`` 인 것도 앱을 따른 것입니다
        (``back_dptTm1`` 의 초기값, ``ara0101v.js:111``). 돌아오는 날 자정부터 훑어야
        후보가 다 보이기 때문입니다.

        **날짜·시각의 앞뒤는 검사하지 않습니다.** 앱은 오는 날이 가는 날보다 이르거나
        같은 날인데 시각이 이르면 막지만(``ara0101v.js:593-603``) 그것은 이 라이브러리가
        그리지 않는 폼 위의 대화상자입니다.
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
    # The 할인 승차권 search's two extra columns: the 공공할인 rate this train
    # actually carries, per cabin class, as a whole-number percentage
    # ("30" -> "30% 할인"). APPENDED, so every existing positional construction
    # keeps its meaning, and defaulted to None because the ORDINARY search does
    # not send them — `gnrmBkclDcntRt` and `sprmBkclDcntRt` are 0-hit in the
    # v2.0.41 bundle AND absent from every live ordinary-search row captured
    # here, and appear only in the 조회결과 page the 할인 승차권 route renders.
    #
    # They are the point of that search: its result page treats a rate below 1
    # as "this train has no discount for you" and falls back to the plain
    # availability text, and only shows "NN% 할인" above it. NEVER OBSERVED
    # POPULATED — see parse_public_discount_search_response.
    general_class_discount_rate: str | None = None
    special_class_discount_rate: str | None = None


@dataclass(frozen=True)
class TransferItinerary:
    """환승 여정 — 선행 열차와 후행 열차를 한 쌍으로 묶은 것.

    **SRT 의 환승은 여정 슬롯 두 개를 실은 예약 하나입니다.** 왕복과 정반대입니다. 앱의
    환승 토글이 ``jrnyTpCd="14"``(환승편도)와 ``jrnyCnt="2"``(여정건수 2)를 한 번에
    씁니다(``ara0101v.js:302-303``, 전송은 ``:310-311``). v2.0.41 번들 전체에서
    ``jrnyCnt="2"`` 를 쓰는 자리는 여기 하나뿐이라 그 값은 곧 환승을 뜻합니다. 왕복은
    ``"1"`` 그대로에 예약이 둘입니다(:meth:`~srt_mobile_api.client.SrtClient.reserve`).

    두 열차는 여정 슬롯 1 과 2 로 들어갑니다 — ``"jrnySqno1" : "001"
    //여정일련번호1(001:선행, 002:후행)``(``ara0101v.js:97``, ``ara1001l.js:1611``).
    :attr:`first_leg` 가 선행(``jrnySqno1="001"``), :attr:`second_leg` 가
    후행(``jrnySqno2="002"``)입니다.

    **이 타입이 있는 이유: 환승 검색의 한 행은 여정의 절반입니다.**
    :class:`TrainSummary` 만 봐서는 예약 가능한 직통 열차와 구별되지 않습니다. 그래서
    환승 검색 결과의 행을 :meth:`~srt_mobile_api.client.SrtClient.reserve` 에 그대로
    넘기면 두 구간 중 한 구간만 예약되고, PNR 은 멀쩡해 보이는 채로 승객은 중간역에
    남습니다. :meth:`~srt_mobile_api.client.SrtClient.reserve_transfer` 는 이 타입만
    받으므로, 절반짜리 여정은 아예 표현할 수 없습니다.

    생성 시점에 이음새를 검사합니다.

    * 두 열차 모두 정확히 :class:`TrainSummary` 여야 합니다,
    * 선행이 **도착하는 역**이 후행이 **출발하는 역**이어야 합니다 — 그 역이 환승역이고,
      여기를 틀리는 것이 이 클래스가 막으려는 실패입니다,
    * 양쪽에 날짜·시각이 다 있을 때는 후행이 선행 도착보다 먼저 떠날 수 없습니다. 앱도
      왕복 두 번째 구간에 똑같은 비교를 합니다(``ara1001l.js:1258-1272``),
    * 두 구간이 같은 열차일 수 없습니다.

    전체 여정의 기점과 종점은 :attr:`first_leg` 의 출발과 :attr:`second_leg` 의
    도착이고, 사이의 환승역은 :attr:`transfer_station_code` 입니다.

    **환승 예약은 한 번도 보낸 적이 없습니다.** 위 ``jrnyTpCd``/``jrnyCnt``/``jrnySqno``
    값은 전부 v2.0.41 번들에서 읽은 것입니다. 환승 **검색** 응답의 모양은 확인됐습니다
    — :class:`TransferSearchResult` 참고.
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
        """두 구간이 만나는 환승역 코드. 생성 시점에 양쪽이 같음을 검사했습니다."""
        return self.first_leg.arrival_station_code or ""

    @property
    def origin_station_code(self) -> str:
        return self.first_leg.departure_station_code or ""

    @property
    def destination_station_code(self) -> str:
        return self.second_leg.arrival_station_code or ""

    @property
    def legs(self) -> tuple[TrainSummary, TrainSummary]:
        """두 구간을 여정 순서대로 — 선행이 앞, 후행이 뒤."""
        return (self.first_leg, self.second_leg)


@dataclass(frozen=True)
class UnpairedTransferGroup:
    """환승 검색이 준 행 중 여정으로 묶이지 못한 것들.

    버리지 않고 남깁니다. **쌍을 짓는 것은 서버가 아니라 이 라이브러리의 추론입니다**
    — 서버는 납작한 행 목록을 주고 ``trnOrdrNo`` 로 묶는 것은 이쪽입니다. 추론이 맞지
    않을 때 그 행들은 호출자가 볼 수 있는 곳에 있어야 하기 때문입니다.

    :attr:`reason` 은 코드가 아니라 문장입니다. 실제로 관측한 적 없는 상황들이라 코드
    어휘를 만들면 지어낸 것이 됩니다.
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
    """환승 검색 결과 — 묶인 여정, 남은 행, 그리고 손대지 않은 원본.

    **응답 모양은 확인됐습니다.** 환승 검색은 구간마다 한 행씩을 평범한 ``dsOutput1``
    목록에 담아 주고 — 직통 행과 열 구성이 같습니다 — 한 여정에 속하는 행들은
    ``trnOrdrNo`` 를 공유합니다. 동대구(0015) -> 광주송정(0036) 에서 서버가 준 10 행이
    그랬습니다: ``trnOrdrNo=1`` 은 382 열차 동대구->오송 과 411 열차 오송->광주송정
    하는 식입니다. 모든 행이 ``chtnDvCd="2"`` 를 달고 있었고 ``fllwPgExt2`` 는
    ``null`` 이었습니다.

    즉 여기서 ``trnOrdrNo`` 는 목록 안의 열차 순번이 아니라 **여정 번호**입니다.
    ``...2`` 로 끝나는 열들도 모든 행에 있기는 하지만 전부 빈 문자열입니다
    (``trnNo2: ""``, ``dptRsStnCd2: ""``, ``jrnySqno: ""``) — 후행 구간은 열이 아니라
    별도의 행이기 때문입니다.

    :attr:`itineraries` 는 깨끗이 묶인 것, :attr:`unpaired` 는 묶이지 못한 것이며
    각각 이유가 붙어 있습니다. **여정 개수만으로는 빠진 것이 있는지 알 수 없으니**
    빠짐없이 보려면 그쪽도 읽어야 합니다. :attr:`search` 는 손대지 않은
    :class:`TrainSearchResult` 라 원본 행과 원본 JSON 으로 언제든 되돌아갈 수
    있습니다.
    """

    itineraries: tuple[TransferItinerary, ...]
    unpaired: tuple[UnpairedTransferGroup, ...]
    search: TrainSearchResult

    @property
    def rows(self) -> list["TrainSummary"]:
        """서버가 준 행 전부 — 묶기 전, 서버가 준 순서 그대로."""
        return self.search.trains

    @property
    def raw(self) -> dict[str, Any]:
        """응답 본문 전체 — 받은 그대로."""
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
    """예약은 됐지만 아직 결제되지 않은 상태 — 실제로 전송된 ``reserve`` 의 결과.

    핵심은 :attr:`pnr_no` 입니다. 뒤이어 취소하거나 결제할 때 이 예약을 가리키는
    이름이고, srtgo 도 성공한 예약에서 같은 값을 챙깁니다(``reservListMap[0].pnrNo``,
    ``srt.py:1006``). :attr:`pnr_no` 와 :attr:`journey_list_key` 는 비밀에 준하므로
    ``repr`` 에 나오지 않습니다 — 값을 보려면 속성을 직접 읽어야 합니다.

    **dry-run 예약은 이것을 만들지 않습니다.** 그쪽은
    :class:`~srt_mobile_api.consent.MutationPreview` 를 돌려줍니다.
    """

    pnr_no: str = field(repr=False)
    journey_list_key: str = field(default="", repr=False)
    total_seat_count: str = ""
    #: 이 예약이 실제로 만들어진 ``jrnyCnt`` — 직통이나 왕복 한 건이면 ``"1"``,
    #: 환승이면 ``"2"``(``ara0101v.js:302-303``). 취소할 때 이 값이 필요한데 예약
    #: 결과 어디에도 남지 않아서 여기에 들고 있습니다. ``reserve_transfer`` 는 정말로
    #: ``jrnyCnt="2"`` 짜리를 만들므로, ``cancel()`` 이 ``"1"`` 을 기본값으로 쓰면
    #: 호출자가 직접 알려 주지 않는 한 틀립니다.
    journey_count: str = "1"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class SrtReservationSummary:
    """One row of the 예약/발권 목록 (``/atc/selectListAtc14016_n.do``).

    한 행은 서버가 따로 보낸 두 목록을 **인덱스로 짝지어** 만듭니다 —
    ``trainListMap[i]``(여정 정보)와 ``payListMap[i]``(결제 상태). srtgo 도 이
    엔드포인트를 그렇게 읽습니다(``srt.py:1069-1082``).

    **필수인 것은 :attr:`pnr_no` 하나입니다.**
    :meth:`~srt_mobile_api.client.SrtClient.cancel` 과 ``scripts/recover_hold.py`` 가
    쓰는 식별자입니다. 나머지는 전부 선택이고 기본값이 ``None`` 인데, **행이 채워진
    응답을 본 적이 없기 때문입니다** — 확인에 쓴 계정에 예약이 없어서
    ``trainListMap``/``payListMap`` 이 빈 배열로만 왔습니다.

    그래서 아래 필드명의 출처가 갈립니다. ``payListMap``, ``tkSpecNum``, ``iseLmtTm``,
    ``stlFlg`` 는 v2.0.41 번들에서 0회이고 srtgo 의 실제 전송 기록에만 있습니다.
    ``iseLmtDt``, ``rcvdAmt``, ``seatNum``, ``pnrNo``, ``rsvChgTno``, ``jrnyCnt`` 는
    승차권 확인 페이지의 인라인 스크립트에 나옵니다(``gotoDetailARD02018(...)``,
    ``gotoDetailARD0201V(...)``) — 이름은 앱이 뒷받침하지만 그것이 위 두 목록 중
    어디에 들어가는지는 아닙니다.

    따라서 ``None`` 은 "그 예약에 그런 값이 없다"가 아니라 **"서버가 이 이름으로 보내지
    않았다"**로 읽어야 합니다. 실제로 온 것은 :attr:`raw_train` / :attr:`raw_pay` 에
    있습니다.
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
    """파싱된 예약/발권 목록과 서버가 함께 보낸 봉투.

    **예약이 없는 계정은 빈 :attr:`reservations` 이지 예외가 아닙니다.** 빈 열차
    검색과 다릅니다 — 검색은 없음을 ``strResult=FAIL`` / ``WRG000000`` 으로
    선언하지만, 이 엔드포인트는 ``resultMap[0].strResult="SUCC"`` / ``IRZ000005`` /
    "조회할 자료가 없습니다." 에 진짜로 빈 배열을 줍니다. 같은 응답의 두 번째 봉투
    (``rsMap``)는 FAIL 이라고 말하는데 그것을 실패로 읽지 않는 이유는
    :func:`~srt_mobile_api.parsers.parse_reservation_list_response` 에 있습니다.

    :attr:`row_count` / :attr:`total_page_count` 는 ``rowCnt`` / ``totPageCnt`` 이며
    JSON 정수로 옵니다(빈 응답에서는 둘 다 ``0``). 없으면 ``None`` 입니다.
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
        """목록에 든 PNR 전부, 서버가 준 순서대로.

        PNR 을 잃어버렸을 때 행 구조를 몰라도 되찾을 수 있게 하는 것이 용도입니다.
        ``scripts/recover_hold.py --list`` 가 출력하는 것이 정확히 이 값입니다.
        """
        return tuple(item.pnr_no for item in self.reservations)


@dataclass(frozen=True)
class SrtCancelResult:
    """미결제 예약취소의 응답 봉투.

    SRT 의 일반적인 ``resultMap`` 봉투이고 ``strResult == "SUCC"`` 면 성공입니다. 여정
    한 건짜리 미결제 예약을 실제로 취소했을 때 ``SUCC`` / ``IRG000000`` 이 왔습니다.

    **업무상 실패는 예외가 아니라 데이터로 옵니다** — :attr:`succeeded` 가 ``False``
    이고 서버의 :attr:`message_code` 가 그대로 실립니다.

    :attr:`message` 와 :attr:`raw` 는 원본 봉투가 예약 식별자를 되울려 주므로 ``repr``
    에서 빠집니다.

    경로 자체는 srtgo 에서 왔고 v2.0.41 번들에서 0회입니다. 봉투 처리를 느슨하게 둔
    이유는 :func:`~srt_mobile_api.parsers.parse_unpaid_cancel_response` 에 있습니다.
    """

    status: str
    message_code: str = ""
    message: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCC"


#: 결제 폼이 ``ismtMnthNum1`` 에 허용하는 할부 개월 — 일시불(0), 2~12, 24.
#: 검증과 테스트가 같은 목록을 읽도록 데이터로 두었습니다.
INSTALLMENT_MONTH_OPTIONS = frozenset({0, *range(2, 13), 24})


@dataclass(frozen=True)
class SrtPaymentCard:
    """카드결제가 실어 보내는 카드 필드 — 나가기 전에 모양을 검사합니다.

    **여기 넣은 값은 실제로 전송될 수 있습니다.** ``payment`` 는 라이브 범주이므로
    :meth:`~srt_mobile_api.client.SrtClient.pay_with_card` 에 ``dry_run=False`` 와
    분명한 카드 종류 주장이 붙으면 이 카드로 청구됩니다. 기본값은 마스킹된
    미리보기이고, :data:`~srt_mobile_api.safety.CARD_SECRET_FIELDS` 가 결제 경로가
    아닌 모든 경로에서 이 네 이름을 막습니다.

    **필드가 무엇을 담는지가 이름만으로는 헷갈리는 자리입니다.**

    * :attr:`card_password` 는 카드 비밀번호 **앞 두 자리**입니다. 전체가 아닙니다.
    * :attr:`card_type` 이 ``"J"``(개인)냐 ``"S"``(법인)냐가
      :attr:`card_validation_number` 의 뜻을 결정합니다 — ``"J"`` 면 ``YYMMDD``
      생년월일, ``"S"`` 면 열 자리 사업자등록번호입니다.
    * :attr:`card_expire_date` 는 ``YYMM``.

    비밀 네 개(:attr:`card_number`, :attr:`card_password`,
    :attr:`card_validation_number`, :attr:`card_expire_date`)는 ``repr=False`` 인
    동시에 각자의 이름으로 :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS` 에 올라
    있어서 ``repr()`` 과 :func:`~srt_mobile_api.redaction.redact_value` 양쪽에서
    가려집니다. 패턴이 아니라 이름으로 가리는 이유는 ``CARD_RE`` 가 13~19 자리
    숫자열만 잡아서 두 자리 비밀번호도, ``YYMM`` 도, ``YYMMDD`` 도 다 빠져나가기
    때문입니다.

    :attr:`installment_months` 와 :attr:`card_type` 은 비밀이 아니라 일부러 가리지
    않습니다. 다만 이 둘의 전송용 이름 ``ismtMnthNum1``/``athnDvCd1`` 은
    ``SENSITIVE_KEYS`` 에 있으므로
    :class:`~srt_mobile_api.consent.MutationPreview` 에서는 가려집니다.

    **카드번호가 진짜인지는 검사하지 않습니다.** 자릿수와 숫자 여부만 봅니다. Luhn
    검사를 넣으면 합성 테스트 카드를 만들 수 없게 되고, 무엇보다 이 라이브러리가 어떤
    카드번호가 유효한지 알려 주는 물건이 됩니다.
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
        # 카드번호는 평문으로 나가므로 Luhn 이 아니라 모양만 본다. 합성 테스트
        # 카드번호가 계속 만들어져야 하고, 이 라이브러리가 카드번호의 진위를 알려
        # 주는 물건이 되어서는 안 된다.
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
    """카드결제의 응답 봉투.

    **:attr:`succeeded` 와 :attr:`failed` 는 서로의 부정이 아닙니다.** 그것이 이 타입의
    요점입니다. 결제에서는 양쪽 오판이 다 비싸므로 모르는 상태값에 대해 판단하지
    않습니다.

    ``"SUCC"`` 도 ``"FAIL"`` 도 아닌 상태는 **모름**입니다. :attr:`raw` 를 읽고, 카드가
    실제로 청구됐는지 다른 경로로 확인해야 하며, **무턱대고 재시도하면 안 됩니다** —
    다시 보낸 결제는 두 번 청구될 수 있습니다.

    확인된 두 가지는 실제 결제의 ``SUCC`` / ``IRT000000`` 과 가짜 카드의 ``FAIL`` /
    ``WRT100170`` 입니다. 경로 ``Ata09036`` 은 v2.0.41 오프라인 디컴파일 21,673 개 파일
    전체에서 0회이고 앱은 이 경로를 쓰지 않습니다 — 경로도 본문도 이 봉투 모양도 참조
    구현들의 실제 전송에만 근거가 있습니다
    (:func:`~srt_mobile_api.parsers.parse_card_payment_response` 참고).
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
    """환불에 필요한 발권 승차권 식별정보 — 환불 1단계의 결과.

    ``POST /atc/getListAtc14087.do``(본문 없음, PNR 은 Referer)의
    ``outDataSets.dsOutput1[0]`` 에서 읽습니다 — 여기만 ``dsOutput1`` 이고, 다른 읽기는
    전부 ``dsOutput0`` 을 씁니다.

    :attr:`return_password` 가 환불을 승인하는 자격증명이라 ``repr`` 에서 빠지고,
    :attr:`buyer_name`·:attr:`pnr_no` 와 함께
    :func:`~srt_mobile_api.redaction.redact_payload` 에서도 가려집니다. 판매 식별자 셋
    (:attr:`sale_date`, :attr:`sale_window_number`, :attr:`sale_sequence_number`)은
    일부러 가리지 않습니다 — 비밀번호가 가려진 이상 그것만으로는 아무것도 승인하지
    못하기 때문입니다.

    이 경로는 참조 구현 **하나**에만 있습니다. 자세한 내력은
    :func:`~srt_mobile_api.parsers.parse_refund_ticket_info_response` 참고.
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
    """발권된 승차권 환불의 응답 봉투.

    봉투는 SRT 의 평범한 ``resultMap`` SUCC/FAIL 입니다 — 예약취소와 같고, 결제의
    ``outDataSets.dsOutput0`` 과는 다릅니다.

    **업무상 실패는 예외가 아니라 값으로 돌아옵니다.** 실제 승차권 환불에서 ``SUCC`` /
    ``IRT200277`` 이 왔습니다.

    경로는 참조 구현 하나에만 있고, v2.0.41 오프라인 디컴파일 21,673 개 파일 전체에서
    0회입니다.
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
    """좌석 페이지가 고르라고 내놓은 호차 하나와 그 호차의 잔여석 수.

    페이지의 ``<select id="selectScarNo">`` 에서 읽습니다 — 좌석 페이지가 들고 있는
    재고 정보는 그것뿐입니다. **좌석배치도는 이 응답에 없습니다.** 실제 페이지도
    ``<div id="trnScarSeatInfo">`` 를 비워 두고, 호차를 고른 뒤에 배치도를 따로
    가져옵니다(:meth:`~srt_mobile_api.client.SrtClient.get_seat_grid`).
    """

    car_number: str
    label: str
    available_seat_count: int | None = None


@dataclass(frozen=True)
class SeatSelectionPage(HtmlPage):
    # 문서 순서대로의 호차 목록. 호차 select 가 아예 없던 페이지에서는 비어 있다.
    # 서버의 오류 껍데기를 빈 페이지로 돌려주지 않고 거절하는 것은
    # parsers.parse_seat_selection_page 다.
    cars: tuple[SeatCarOption, ...] = ()


@dataclass(frozen=True)
class SeatGridSeat:
    """좌석배치도의 좌석 한 칸 — 그 좌석의 이름 **두 개**를 다 들고 있습니다.

    ``/arc/selectListArc02011_n.do`` 가 주는 배치도의 각 칸이 이런 요소입니다::

        <div role="text" tabindex="0" aria-label="1C" id="scarSeat_1C"
             class="seatChoice015Y"
             onclick="choiceSeatNo('3', '1C', 'Y');"><span>1C</span></div>

    **좌석에는 이름이 둘 있고 서로 바꿔 쓸 수 없습니다.** ``choiceSeatNo`` 의 첫 인자는
    호차 안에서 1, 2, 3, 4, 5 … 로 이어지는 **내부 좌석번호**
    (:attr:`internal_seat_number`)이고, 둘째 인자는 승객이 좌석에서 읽는 **인쇄
    좌석명**(:attr:`printed_seat_label`, 1A, 1B, 1C, 1D, 2A …)입니다. 위 칸에서 내부
    ``3`` 번의 인쇄명이 ``1C`` 입니다. 요소의 ``id`` 와 ``aria-label`` 은 인쇄명으로
    만들어집니다.

    **예약 폼이 받는 것은 인쇄 좌석명입니다.** 앱의 좌석선택 콜백은
    ``{scarSeatNo: "2,7,10", scarSeatNm: "1B,2C,3B", scarNo: 1}`` 로 둘 다 받아 놓고,
    ``seatNo1_1..N`` 을 인쇄명 쪽인 ``scarSeatNm`` 으로 채우며 ``scarSeatNo`` 는
    버립니다(``ara0101v.js:868-878``). 이것은 번들 근거이고 실제 전송으로 확인된 것은
    아닙니다(:func:`~srt_mobile_api.payloads.personal_reservation_payload` 참고).

    :attr:`seat_attribute_code` 는 칸의 class(``seatChoice<코드><Y|N>``)에 박힌
    좌석속성코드입니다. 한 호차 안에 ``000``, ``015``, ``021``, ``028`` 이 모두
    나타났습니다. :attr:`selectable` 은 ``choiceSeatNo`` 의 셋째 인자가 ``Y`` 인지이며,
    ``N`` 칸도 그려지지만 고를 수 없습니다.
    """

    internal_seat_number: str
    printed_seat_label: str
    seat_attribute_code: str = ""
    selectable: bool = False


@dataclass(frozen=True)
class SeatDesignation:
    """호차 하나에서 호출자가 고른 좌석들 — 낱개가 아니라 묶음으로 검사됩니다.

    ``reserve(..., designated_seats=…)`` 가 받는 타입입니다. **손으로 만들지 말고**
    :meth:`SeatGrid.choose` 로 배치도에서 만드는 편이 좋습니다 — 그래야 좌석명이 서버가
    준 것이고 선택 가능 여부도 대조할 대상이 있습니다.

    생성 시점에 다음을 검사합니다.

    * 좌석이 최소 하나, 전부 정확히 :class:`SeatGridSeat`,
    * 모든 좌석이 :attr:`~SeatGridSeat.selectable` — ``N`` 칸은 서버가 그려는 주지만
      받지는 않습니다,
    * 같은 인쇄 좌석명이 두 번 나오지 않음(한 좌석이 인원 슬롯 둘을 먹고 한 사람이
      좌석 없이 남습니다),
    * 호차 번호가 숫자만 — ``scarNo1`` 로 그대로 나가는 값입니다.

    **인원수와 좌석수가 맞는지는 여기서 보지 않습니다.** 그 검사는 승차인원을 알아야
    하므로 양쪽이 다 보이는
    :func:`~srt_mobile_api.payloads.personal_reservation_payload` 에 있습니다.
    """

    car_number: str
    seats: tuple[SeatGridSeat, ...]
    #: 이 배치도를 **가져올 때 쓴** ``psrmClCd``("1" 일반실 / "2" 특실). 배치도를 거치지
    #: 않고 손으로 만들어 실을 모를 때는 ``""``. 특실 좌석번호에 일반실 코드가 붙는
    #: 짝을 막으려고 들고 다닙니다 — 이 사슬의 다른 어느 값도 배치도가 어느 실에서
    #: 왔는지 기억하지 않아서, 어긋나도 나중에 알아낼 방법이 없습니다. 앱에서는 애초에
    #: 어긋날 수 없습니다: ara1001l.js:1427-1436 이 실 코드와 좌석배치도 jobId 를 한
    #: 전이에서 함께 정합니다.
    cabin_class: str = ""

    def __post_init__(self) -> None:
        if not _is_digits(self.car_number):
            raise ValueError("designated seats need a digits-only car number (scarNo1)")
        if not isinstance(self.seats, tuple) or not self.seats:
            raise ValueError("a seat designation needs at least one seat")
        labels: list[str] = []
        for seat in self.seats:
            if type(seat) is not SeatGridSeat:
                raise ValueError("designated seats must be exact SeatGridSeat values")
            if not seat.printed_seat_label:
                raise ValueError("a designated seat needs its printed label")
            if not seat.selectable:
                raise ValueError(
                    "seat "
                    f"{seat.printed_seat_label} is not selectable "
                    "(the grid marked it 'N'); the server will refuse it"
                )
            labels.append(seat.printed_seat_label)
        duplicates = sorted({label for label in labels if labels.count(label) > 1})
        if duplicates:
            raise ValueError(
                "a seat may be designated only once; repeated: "
                + ", ".join(duplicates)
            )

    @property
    def printed_seat_labels(self) -> tuple[str, ...]:
        """``seatNo1_1..N`` 으로 나갈 순서 그대로의 인쇄 좌석명."""
        return tuple(seat.printed_seat_label for seat in self.seats)


@dataclass(frozen=True)
class SeatGrid(HtmlPage):
    """열차 하나, 호차 하나의 파싱된 좌석배치도.

    :attr:`car_number` 는 **요청할 때 지목한** 호차입니다. 이 라이브러리가 ``scarNo``
    로 보낸 값이지 응답에서 읽은 값이 아닙니다 — 배치도 조각은 자기가 몇 호차인지
    말하지 않습니다. :attr:`seats` 는 고를 수 있든 없든 문서 순서대로의 모든 칸입니다.

    좌석을 지정하려면 :meth:`choose` 로 :class:`SeatDesignation` 을 만들면 됩니다.
    """

    car_number: str = ""
    seats: tuple[SeatGridSeat, ...] = ()
    #: 이 배치도를 요청할 때 쓴 ``psrmClCd``. :meth:`choose` 가 좌석 지정에 그대로
    #: 찍어 주도록 남겨 둡니다.
    cabin_class: str = ""

    @property
    def selectable_seats(self) -> tuple[SeatGridSeat, ...]:
        return tuple(seat for seat in self.seats if seat.selectable)

    def choose(self, *printed_seat_labels: str) -> SeatDesignation:
        """인쇄 좌석명(``"1C"``, ``"2A"`` …)으로 좌석을 지정합니다.

        승객이 좌석에서 읽는 이름이자 예약 폼이 실제로 실어 보내는 이름이라
        (``ara0101v.js:868-878``) 이 인자를 받습니다. 내부 좌석번호가 아닙니다.

        **없는 좌석명은 조용히 버리지 않고 :class:`ValueError` 입니다.** 오타 하나가
        일행의 좌석 수를 소리 없이 줄이지 않게 하려는 것이고, 오류 메시지에 고를 수
        있는 좌석명이 함께 나옵니다.
        """
        by_label = {seat.printed_seat_label: seat for seat in self.seats}
        chosen: list[SeatGridSeat] = []
        for label in printed_seat_labels:
            seat = by_label.get(label)
            if seat is None:
                available = ", ".join(
                    sorted(seat.printed_seat_label for seat in self.selectable_seats)
                )
                raise ValueError(
                    f"seat {label!r} is not in car {self.car_number}'s grid; "
                    f"selectable seats are: {available}"
                )
            chosen.append(seat)
        return SeatDesignation(
            car_number=self.car_number,
            seats=tuple(chosen),
            cabin_class=self.cabin_class,
        )


@dataclass(frozen=True)
class PublicDiscountEntitlement:
    """공공할인 한 종류와, **이 계정이** 그것을 승인받았는지.

    :attr:`code` 는 ``PBL_DISC_CD``(``"01"``~``"08"``)이고, :attr:`name` 은
    :func:`~srt_mobile_api.discounts.public_discount_name` 이 풀어 준 이름입니다.
    ``07``, ``08`` 은 페이지에 분기는 있는데 이름이 어디에도 없어서 ``""`` 입니다.

    **코드와 슬롯의 대응은 추론입니다.** 페이지는 ``data1Check`` 부터 ``data8Check``
    까지 여덟 개의 플래그를 렌더링해 주면서 그 옆에 ``PBL_DISC_CD`` 를 한 번도 적지
    않습니다. 둘을 잇는 근거는 두 플래그를 한꺼번에 읽는 유일한 분기에 페이지가 직접
    단 주석뿐입니다 — ``if(data1Check == "Y" && data2Check == "Y")`` 위의
    *"다자녀(01)와 임산부(02)가 신청이 승인된 경우"*. 플래그도 코드도 정확히 여덟
    개이고, 아래쪽의 여덟 개 ``PBL_DISC_CD`` 분기가 ``01``~``08`` 순서로 늘어서
    있습니다. 나머지 여섯의 대응은 이것과 어긋나는 근거도, 뒷받침하는 근거도 없습니다.
    """

    code: str
    name: str = ""
    approved: bool = False


@dataclass(frozen=True)
class PublicDiscountPage(HtmlPage):
    """할인 승차권 페이지를 "이 계정이 어떤 공공할인을 가졌나"로 읽은 것.

    **아무것도 승인받지 못한 계정은 오류가 아니라 답입니다.** 그 경우 페이지는
    ``Sr.msgs.notice006``("할인승차권은 홈페이지를 통해 인증된 고객만 이용이
    가능합니다…")을 띄우고 메인으로 돌려보내지만, "가진 것이 없다"가 곧 물어본 것에
    대한 답이라 그대로 돌려줍니다 — :attr:`is_eligible` 이 ``False`` 이고
    :attr:`entitlements` 의 모든 행이 ``approved=False`` 입니다.

    **담지 않는 것: 승인된 할인의 관리번호(``PBL_DISC_MG_NO``)와 확인·만료 날짜.**
    그 값들은 페이지의 ``if/else if`` 분기 본문 안에 서버가 렌더링해 넣는데, 읽을 수
    있었던 계정에서는 여덟 분기가 전부 비어 있었습니다. 승인된 계정을 가진 호출자는
    :attr:`raw` 에서 직접 읽을 수 있습니다.
    """

    entitlements: tuple[PublicDiscountEntitlement, ...] = ()

    @property
    def approved(self) -> tuple[PublicDiscountEntitlement, ...]:
        return tuple(entry for entry in self.entitlements if entry.approved)

    @property
    def is_eligible(self) -> bool:
        """승인된 공공할인이 하나라도 있으면 참.

        페이지가 쓰는 조건 그대로입니다 — 여덟 플래그 중 하나라도 ``"Y"`` 면 검색 폼을
        보여 주고, 아니면 거절합니다.
        """
        return bool(self.approved)


@dataclass(frozen=True)
class PublicDiscountSelection:
    """어떤 공공할인으로 검색할지 — 코드와 승인번호.

    할인 승차권 검색에서 **호출자가 채우는 쪽**입니다. ajax 폼이 ``pblDiscCd`` 와
    ``pblDiscMgNo`` 로 싣는 두 값이고, 함께 가는 ``tgtDtrmYn`` 은 페이지가 늘 ``"Y"``
    로 두므로 선택지로 두지 않았습니다.

    :class:`PublicDiscountEntitlement` 와 타입을 나눈 것은 답하는 질문이 다르기
    때문입니다 — 자격은 *계정이 가진 것*이고, 선택은 *이번 검색이 무엇을 위한
    것인지*입니다.

    :attr:`code` 는 ``"01"``~``"08"`` 의 ``PBL_DISC_CD`` 이고
    :func:`~srt_mobile_api.discounts.public_discount_name` 이 그중 여섯의 이름을
    압니다.

    **:attr:`management_no` 는 값을 본 적이 없습니다.** ``PBL_DISC_MG_NO`` 는 서버가
    발급하는 승인번호로, 할인 승차권 페이지가 계정이 승인받은 할인의 분기 본문에
    렌더링해 넣습니다. 승인이 없는 계정에서는 그 분기 본문이 전부 비어 있어 기본값이
    ``""`` 입니다 — 승인된 계정을 가진 호출자는 자기 :attr:`PublicDiscountPage.raw`
    에서 읽어 넘기면 됩니다. 서버가 이 값을 요구하는지, 아니면 세션에서 알아내는지는
    모릅니다.

    **인원수 제한은 여기서 검사하지 않습니다.** 그것은 (코드, 인원) 쌍에 관한 사실이라
    :func:`~srt_mobile_api.payloads.public_discount_search_payload` 에 있습니다.
    """

    code: str
    management_no: str = ""

    @property
    def name(self) -> str:
        """공공할인의 한국어 이름. ``07``/``08`` 은 이름이 없어 ``""`` 입니다."""
        from .discounts import public_discount_name

        return public_discount_name(self.code)


@dataclass(frozen=True)
class DiscountCoupon:
    """계정이 가진 할인쿠폰 한 장 — 페이지가 찍어 준 글자 그대로.

    **모든 필드가 표시용 문자열이지 파싱된 값이 아닙니다.** :attr:`discount_rate` 는
    ``"45%"`` 이고 :attr:`remaining_uses` 는 ``"이용가능 횟수 : 1"`` 입니다. 숫자를
    원하면 호출자가 직접 뽑아야 합니다.

    그렇게 둔 이유는 채워진 행을 본 적이 없어서입니다. 빈 상태("보유한 쿠폰이
    없습니다.")는 확인됐지만 쿠폰을 가진 계정이 없었습니다. 필드명의 근거는 쿠폰
    페이지에 주석으로 남은 디자이너 템플릿이 전부입니다 — class 이름은 페이지의
    것이고 값은 예시입니다::

        <span class="rate">45%</span>
        <span class="boarding">탑승일기준</span>
        <span class="date">2099.01.01 ~ 2099.12.31</span>
        <span class="type"> 운임할인</span>
        <span class="num">9910000001</span>
        <span class="useCnt">이용가능 횟수 : 1</span>

    :attr:`discount_kind` 는 페이지가 맨 위에서 밝히는 두 갈래입니다 — 운임할인은
    운임을, 특실할인은 특실 추가금을 깎습니다.
    """

    coupon_number: str = ""
    discount_kind: str = ""
    discount_rate: str = ""
    validity: str = ""
    basis: str = ""
    remaining_uses: str = ""


@dataclass(frozen=True)
class DiscountCouponList(HtmlPage):
    """할인쿠폰조회/등록 페이지를 행으로 읽은 것.

    **쿠폰이 없는 계정은 빈 :attr:`coupons` 이지 파싱 실패가 아닙니다.** 반대로 쿠폰도
    없고 페이지 자신의 "보유한 쿠폰이 없습니다." 표시도 없는 응답은 빈 목록으로 여기
    도달하지 못하고 파서가 거절합니다. 그래서 "가진 것이 없다"와 "이 페이지를 이해하지
    못했다"가 절대 같아 보이지 않습니다.
    """

    coupons: tuple[DiscountCoupon, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.coupons


@dataclass(frozen=True)
class SrtCouponRegistrationRequest:
    """할인쿠폰 등록 한 건 — 쿠폰번호와 쿠폰 비밀번호.

    **이 둘은 무기명 자격증명입니다.** 번호와 비밀번호를 내미는 사람이 쿠폰을 쓰게
    되고, 등록하는 계정은 그저 먼저 물어본 쪽일 뿐입니다. 그래서 두 속성명과 두 전송용
    이름(``dscp_no``/``dscp_pwd``)이 모두
    :data:`~srt_mobile_api.redaction.SENSITIVE_KEYS` 에 있고, :attr:`coupon_number`
    도 비밀번호와 나란히 ``repr=False`` 입니다. 일반 규칙으로는 둘 다 걸리지 않습니다:
    ``dscp_pwd`` 는 문자 그대로의 ``password`` 가 아니고, 열 자리 ``dscp_no`` 는
    ``CARD_RE`` 가 잡기에 짧습니다.

    아래 두 제약은 ``/apa/selectListApa03020_n.do`` 페이지의 것입니다.

    * :attr:`coupon_number` — ``<input type="number" name="dscp_no"
      maxlength="10">`` 에 숫자가 아닌 것을 지우고 열 자리로 자르는 ``keyup`` 핸들러가
      붙어 있습니다. 즉 숫자만, 1~10 자리.
    * :attr:`coupon_password` — ``<input type="password" name="dscp_pwd"
      maxlength="4">``. 네 글자까지이고 **숫자로 제한하지 않습니다.** 페이지가
      강제하지 않는 문자 집합을 넘겨짚으면 앱이라면 받았을 쿠폰을 거절하게 됩니다.

    빈 값은 페이지가 거절하는 것과 같은 이유로 여기서 거절합니다
    (``mysrt006``/``mysrt007``, ``js/common/messages.js:111-112``).
    """

    coupon_number: str = field(repr=False)
    coupon_password: str = field(repr=False)


@dataclass(frozen=True)
class SrtCouponRegistrationResult:
    """The parsed envelope of a 할인쿠폰 등록.

    **이 응답을 본 적이 없습니다.** 아래 필드는 전부 쿠폰 페이지의 성공 핸들러에서 읽은
    것이고, 이 라이브러리가 쿠폰 등록을 보낸 적은 없으며, 경로는 v2.0.41 오프라인
    번들에서 0회입니다::

        var msg   = args.resultMap[0].MSG;
        var rtncd = args.resultMap[0].RTNCD;
        if(rtncd == "N"){ ...show msg... } else { ...show mysrt008... }

    **봉투가 다릅니다.** 다른 상태변경이 모두 ``strResult``/``msgCd``/``msgTxt`` 를
    돌려주는 데 반해 이쪽은 ``resultMap[0]`` 에 대문자 ``RTNCD``/``MSG`` 입니다. 익숙한
    모양으로 바꾸지 않고 페이지가 읽는 그대로 두었습니다.

    :attr:`succeeded` 도 페이지의 극성을 그대로 따릅니다. **``"N"`` 만 실패이고 나머지는
    전부 성공입니다.** 그래서 파서가 비어 있거나 없는 ``RTNCD`` 를 따로 거절합니다. 이
    규칙대로면 코드가 없는 응답이 성공으로 읽히기 때문입니다.

    **여기서 성공은 요청이 접수됐다는 뜻이지 쿠폰이 보인다는 뜻이 아닙니다.** 페이지의
    성공 문구가 그렇게 말합니다(``mysrt008``: "쿠폰등록 요청을 완료하였습니다 …
    쿠폰등록이 지연 될 경우 입력하신 쿠폰이 바로 조회 되지 않을 수 있습니다"). 등록
    직후 :meth:`~srt_mobile_api.client.SrtClient.get_discount_coupons` 를 불러 아무것도
    보이지 않는 것은 정상일 수 있습니다.

    :attr:`message` 와 :attr:`raw` 는 거절된 쿠폰번호가 되울려 나올 수 있어 ``repr``
    에서 빠집니다.
    """

    status: str
    message: str = field(default="", repr=False)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    #: 페이지가 실패로 보는 유일한 값.
    FAILURE_CODE = "N"

    @property
    def succeeded(self) -> bool:
        return self.status != self.FAILURE_CODE


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
