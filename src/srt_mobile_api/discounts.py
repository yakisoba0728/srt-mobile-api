"""SRT 할인 (discount) code tables, taken from the app's own code table.

Two independent tables live here, from two different kinds of evidence, and the
difference matters more than their contents:

**할인종류코드 (``dcntKndCd``)** is a direct copy of the ``dcntKndCd`` run in the
app's client-side code table (offline ``js/commCode.js``, the same file
``stations.py``'s neighbour ``stationInfo.js`` sits beside). It is what the
server means by a ``dcntKndCd`` value, and ``dcntKndCd`` is a real transmitted
field: the booking form carries ``<input type="hidden" name="dcntKndCd">`` on
every SRT reservation page this project has fetched. This library does not SET
it -- nothing here asks for a discount -- so the table is here to DECODE what
comes back, which is the only use a read-only client has for it.

Three facts about the copy, all of them the source's and not ours:

* 173 codes, not 171. Two rows -- ``133`` 기본 특별할인(기준) and ``191``
  정차역 할인 -- carry no ``code_group_cd`` key at all in ``commCode.js``
  (:lines 487-495). They sit INSIDE the ``dcntKndCd`` run, between ``132`` and
  ``192``, and every neighbour on both sides is a ``dcntKndCd``, so the omission
  is a hole in the source rather than a different group. They are included, and
  this sentence is why.
* 25 of the rows carry ``"rmk": "V"``. What ``V`` marks is not stated anywhere
  in the bundle, so nothing is built on it and no accessor exposes it. Guessing
  would be the kind of inference this repository writes down rather than ships.
* The codes are stable but four of the NAMES are not. A live fetch of
  ``/js/commCode.js`` on 2026-07-26 -- the server's current copy of this same
  file -- had renamed ``205``/``206`` from "1-3급 장애인 할인"/"4-6급 장애인할인"
  to "장애의정도가심한장애인 할인"/"장애의정도가심하지않은장애인 할인", matching the
  same rename on ``psgTpCd`` 2 and 3. The numeric codes did not move. This table
  keeps the v2.0.41 bundle's wording because the bundle is the committed
  evidence; a caller displaying a name to a human should expect the newer one.

**공공할인코드 (``PBL_DISC_CD``)** is NOT in the bundle at all -- neither the code
nor its values appear anywhere in v2.0.41. It comes from a page the live server
renders to our own authenticated session: the 승차인원선택 popup
(``POST /common/ARA/ARA0901P/view.do``) writes the whole mapping out as a
comment block in its own ``setPassenger`` function, fetched 2026-07-26::

    //다자녀             //01
    //임산부             //02
    //기초생활           //03
    //청소년             //04
    //모범 납세자        //05
    //3세대 동행할인      //06

The 할인 승차권 page (``/common/ARA/ARA0301V/view.do``) branches on ``07`` and
``08`` as well; nothing on any page this project has fetched names them, so they
are absent here rather than invented.
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
# what the server renders on this one path. It is recorded here, and NOT wired
# into :class:`~srt_mobile_api.models.PassengerCounts`, because emitting it would
# change the reservation payload for a discount no account in this project can
# hold. See docs/IMPLEMENTATION_PROGRESS.md, "공공할인 is a passenger vocabulary".
PUBLIC_DISCOUNT_YOUTH_CODE = "04"
YOUTH_PASSENGER_TYPE_CODE = "6"


def discount_kind_name(code: str | None) -> str:
    """Return the 할인종류 name for ``code``, or ``""`` if unknown.

    Follows ``stations.station_name_by_code``: unknown is ``""`` rather than an
    exception, because this decodes values the SERVER chose and a client that
    crashes on an unrecognised discount code is worse than one that shows none.
    """
    if not isinstance(code, str):
        return ""
    return DISCOUNT_KIND_NAMES_BY_CODE.get(code.strip(), "")


def public_discount_name(code: str | None) -> str:
    """Return the 공공할인 name for ``code``, or ``""`` if unknown.

    ``07`` and ``08`` are deliberately unknown here: the 할인 승차권 page has
    branches for them and no page this project has fetched says what they are.
    """
    if not isinstance(code, str):
        return ""
    return PUBLIC_DISCOUNT_NAMES_BY_CODE.get(code.strip(), "")
