"""할인 코드표 —— 서버가 보낸 할인 코드를 사람이 읽는 이름으로 바꿉니다.

성격이 다른 두 표가 있습니다.

**할인종류코드(``dcntKndCd``)** 는 앱 코드표(``js/commCode.js``)의 ``dcntKndCd``
구간을 그대로 옮긴 173개입니다. 예매 페이지가 ``<input type="hidden"
name="dcntKndCd">`` 로 실제 전송하는 필드이지만, 이 라이브러리는 그 값을
**설정하지 않습니다** —— 할인을 요청하는 기능이 없습니다. 표는 돌아온 값을 해독하는
용도이고, :func:`discount_kind_name` 로 읽습니다.

알아 둘 두 가지입니다.

* ``133`` 기본 특별할인(기준)과 ``191`` 정차역 할인은 원본에 그룹 키
  (``code_group_cd``)가 아예 없습니다(``commCode.js:487-495``). 다만 ``132`` 와
  ``192`` 사이, ``dcntKndCd`` 구간 한가운데에 있어 원본의 누락으로 보고
  포함했습니다.
* 코드는 안정적이지만 이름은 그렇지 않습니다. 서버가 현재 배포하는 같은 파일에서는
  ``205``/``206`` 이 "장애의정도가심한장애인 할인"/"장애의정도가심하지않은장애인
  할인" 으로 바뀌어 있습니다(``psgTpCd`` 2·3 의 개명과 같고, 숫자는 그대로입니다).
  이 표는 근거로 커밋된 v2.0.41 번들의 표기를 유지하므로, 사람에게 보여 줄
  이름이라면 더 새 표기가 올 수 있음을 감안해야 합니다.

**공공할인코드(``PBL_DISC_CD``)** 는 앱 번들에 없습니다 —— 코드도 값도 v2.0.41
어디에도 나오지 않습니다. 출처는 서버가 인증된 세션에 렌더링해 주는 승차인원선택
팝업(``POST /common/ARA/ARA0901P/view.do``)이고, 그 페이지의 ``setPassenger``
함수가 대응표를 주석으로 적어 둡니다::

    //다자녀             //01
    //임산부             //02
    //기초생활           //03
    //청소년             //04
    //모범 납세자        //05
    //3세대 동행할인      //06

할인 승차권 페이지(``/common/ARA/ARA0301V/view.do``)에는 ``07``·``08`` 분기도
있지만 이름을 밝히는 페이지가 없어 지어내지 않고 비워 두었습니다.
:func:`public_discount_name` 로 읽습니다.
"""

# 할인종류코드. Generated from the ``dcntKndCd`` run of
# ``analysis/raw/base/assets/offline/js/commCode.js``; do not hand-edit.
DISCOUNT_KIND_NAMES_BY_CODE: dict[str, str] = {
    '000': '일반',
    '101': '탄력운임기준할인',
    '105': '자유석 할인',
    '106': '입석 할인',
    '107': '역방향석 할인',
    '108': '출입구석 할인',
    '109': '가족석 일반전환 할인',
    '111': '구간별 특정운임',
    '112': '열차별 특정운임',
    '113': '구간별 비율할인(기준)',
    '114': '열차별 비율할인(기준)',
    '121': '공항직결 수색연결운임',
    '131': '구간별 특별할인(기준)',
    '132': '열차별 특별할인(기준)',
    '133': '기본 특별할인(기준)',
    '191': '정차역 할인',
    '192': '매체 할인',
    '201': '어린이 할인',
    '202': '동반유아 할인',
    '204': '경로 할인',
    '205': '1-3급 장애인 할인',
    '206': '4-6급 장애인할인',
    '207': '국가유공자 할인',
    '208': '장애보호자 할인',
    '209': '1급 국가유공 보호자할인',
    '210': '인도견 할인',
    '211': '1-3급 공상 보호자할인',
    '212': '1-3급 공상자',
    '213': '순직가족',
    '250': '유아동반석 할인',
    '251': '휠체어석 할인',
    '252': 'ITX청춘 특별할인',
    '253': '가족석 할인',
    '254': '세종시 열차할인',
    '255': '특실 업그레이드 할인',
    '301': '특별단체할인',
    '303': '일반단체할인',
    '304': '군전세 객차할인(특정열차)',
    '305': '군전세 열차할인',
    '306': '군전세 객차할인',
    '307': '군수송권',
    '365': 'KTX 365 할인',
    '401': '할인증할인A Type',
    '402': '할인증할인B Type',
    '403': '할인증할인C Type',
    '404': '할인증할인D Type',
    '405': '정액할인A Type',
    '406': '정액할인B Type',
    '407': '정액할인C Type',
    '408': '정액할인D Type',
    '411': '무임증할인',
    '412': '직원가족 무임증할인',
    '413': '계약수송할인',
    '414': '모범납세자할인',
    '430': '후급 단체할인',
    '431': '후급 일반할인',
    '432': '군장병 할인',
    '433': '군후급 할인',
    '441': '가족애카드 할인',
    '451': '파격가할인',
    '501': '열차상품02',
    '502': '파격가02',
    '503': '열차상품01',
    '504': '열차상품03',
    '505': '조건할인02',
    '506': '조건할인01',
    '507': '조건할인03',
    '508': '청소년02',
    '509': '청소년01',
    '510': '청소년03',
    '511': '파격가01',
    '512': '파격가03',
    '513': '조건할인(요금)',
    '700': 'KTX 환승할인',
    '701': '공항철도 환승할인',
    '703': '매체 첫거래할인',
    '711': '공항철도 정액할인',
    '712': '지연할인증할인',
    '722': '구간별 비율할인(영업)',
    '723': '열차별 비율할인(영업)',
    '724': '구간별 정액할인(영업)',
    '725': '열차별 정액할인(영업)',
    '901': '입력할인',
    '902': '입력할인(최저운임할인)',
    'A11': '어린이',
    'B11': '예매',
    'B2B': '비즈니스카드',
    'B2C': '동반카드',
    'B2S': '경로카드',
    'B2Y': '청소년카드',
    'C06': '직원가족할인',
    'G00': '단체',
    'G31': '군인후급단체',
    'G33': '경찰병력후급단체',
    'G34': '경비교도대후급단체',
    'M11': '철도회원',
    'P11': '청소년',
    'P21': '1-3급장애인',
    'P22': '4-6급장애인',
    'P31': '군인(이전)',
    'P32': '국련군',
    'P33': '경찰병력',
    'P34': '경비교도대',
    'P41': '경로',
    'P51': '동반유아',
    'P60': '증구분',
    'P61': '1?3급장애인보호자',
    'P62': '1급국가유공자보호자',
    'P63': '인도견',
    'P64': '1-3급공상자보호자',
    'P71': '경찰청',
    'P72': '해양경찰청',
    'P73': '군장병',
    'P91': '일반할인',
    'P92': '특별할인',
    'S01': '특정01',
    'S02': '특정02',
    'S03': '특정03',
    'S04': '특정04',
    'S05': '특정05',
    'S06': '특정06',
    'S07': '특정07',
    'S08': '특정08',
    'S09': '특정09',
    'S10': '특정10',
    'S11': '특정11',
    'S12': '특정12',
    'S13': '특정13',
    'S14': '특정14',
    'S15': '특정15',
    'S16': '특정16',
    'S17': '특정17',
    'S18': '특정18',
    'S19': '특정19',
    'S20': '특정20',
    'S21': '특정21',
    'S22': '특정22',
    'S23': '특정23',
    'S24': '특정24',
    'S25': '특정25',
    'S26': '특정26',
    'S27': '특정27',
    'S28': '특정28',
    'S29': '특정29',
    'S30': '특정30',
    'S31': '특정31',
    'S32': '특정32',
    'S33': '특정33',
    'S34': '특정34',
    'S35': '특정35',
    'S36': '특정36',
    'S37': '특정37',
    'S38': '특정38',
    'S39': '특정39',
    'S40': '특정40',
    'S41': '특정41',
    'S42': '특정42',
    'S43': '특정43',
    'S44': '특정44',
    'S45': '특정45',
    'S46': '특정46',
    'S47': '특정47',
    'S48': '특정48',
    'S49': '특정49',
    'S50': '특정50',
    'ZZ1': '승객할인',
    'ZZ2': '공공할인',
    'ZZ3': '영업할인1',
    'ZZ4': '영업할인2',
    'ZZ5': '영업할인3',
    'ZZ6': '영업할인4',
    'ZZ7': '영업할인5',
    'ZZ8': '영업할인6',
}


# 공공할인코드 -> name. See the module docstring: this is the live 승차인원선택
# popup's own comment block, not bundle data.
PUBLIC_DISCOUNT_NAMES_BY_CODE: dict[str, str] = {
    "01": "다자녀",
    "02": "임산부",
    "03": "기초생활",
    "04": "청소년",
    "05": "모범 납세자",
    "06": "3세대 동행할인",
}

# The two 공공할인 types that refuse a party smaller than three. Both the 할인
# 승차권 page and the 승차인원선택 popup enforce it in the same words --
# ``if((pblDiscCd == "01" || pblDiscCd == "06") && totalPessnger < 3)`` -> the
# message keyed ``rsv071``, "승객인원 3명이상 선택하십시오." -- which is why it is
# recorded as data rather than restated in prose.
PUBLIC_DISCOUNT_MINIMUM_PARTY_SIZE: dict[str, int] = {"01": 3, "06": 3}

# 청소년, the one 공공할인 that changes the PASSENGER vocabulary rather than the
# price. Under it the 승차인원선택 popup reveals a seventh counter (``passenger7``,
# hidden on every other path) and the 할인 승차권 page sends it as
# ``psgTpCd6``/``psgInfoPerPrnb6``.
#
# ``psgTpCd`` 6 is NOT in ``commCode.js`` -- not in the v2.0.41 bundle and not in
# the live copy fetched 2026-07-26, both of which stop at 5. It exists only in
# what the server renders on this one path.
#
# CORRECTION (2026-07-26): this comment used to end "and NOT wired into
# PassengerCounts, because emitting it would change the reservation payload for a
# discount no account in this project can hold". It IS wired in now --
# ``PassengerCounts.youth`` -- and the reason the old caveat gave was answered
# rather than ignored: with ``youth=0`` every builder emits exactly what it
# emitted before, so nothing changed for a caller who does not ask for it.
#
# A second correction belongs here too, and it cuts the other way: the 할인
# 승차권 SEARCH does not transmit ``psgTpCd6`` either. Its ajax form
# (``#seatSearchForm``) carries ``psgNum``, the head count, and no passenger type
# mix at all -- only the PAGE form carries the six slots. So the one route that
# can express a 청소년 in a search is the navigation, not the query. See
# :func:`~srt_mobile_api.payloads.public_discount_search_payload`.
PUBLIC_DISCOUNT_YOUTH_CODE = "04"
YOUTH_PASSENGER_TYPE_CODE = "6"


def discount_kind_name(code: str | None) -> str:
    """할인종류 코드를 이름으로 바꿉니다. 모르는 코드는 ``""`` 입니다.

    :func:`~srt_mobile_api.stations.station_name_by_code` 와 같은 규약으로,
    예외를 던지지 않습니다. 처음 보는 할인코드 하나에 클라이언트가 죽는 것이 이름을
    못 보여 주는 것보다 나쁘기 때문입니다. ``code`` 가 문자열이 아니어도 ``""``
    입니다.
    """
    if not isinstance(code, str):
        return ""
    return DISCOUNT_KIND_NAMES_BY_CODE.get(code.strip(), "")


def public_discount_name(code: str | None) -> str:
    """공공할인 코드를 이름으로 바꿉니다. 모르는 코드는 ``""`` 입니다.

    ``07``·``08`` 은 일부러 모르는 값으로 둡니다. 할인 승차권 페이지에 두 코드의
    분기는 있지만 이름을 밝히는 페이지는 아직 없습니다.
    """
    if not isinstance(code, str):
        return ""
    return PUBLIC_DISCOUNT_NAMES_BY_CODE.get(code.strip(), "")
