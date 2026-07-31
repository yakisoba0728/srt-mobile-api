"""요청이 프로세스를 떠나기 전에 통과해야 하는 검사들.

구조:
- :data:`READ_ONLY_ROUTES` 허용목록 바깥의 읽기 → 거절.
- :data:`SRT_MUTATION_ROUTES` 5개, 범주당 하나 → 범주/경로 교차 사용 불가.
- 경로별 정확계약(좌석·좌석배치도·공공할인·NetFunnel) → 본문 형태 고정.
- :func:`assert_no_card_secrets` → 카드 비밀값은 ``payment`` 경로만.
- :data:`SRT_LIVE_MUTATION_CATEGORIES` → consent 와 별개의 전송 차단 스위치.
"""

import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

import httpx

from .config import APP_ORIGIN, NETFUNNEL_ORIGIN, SrtConfig
from .errors import SrtProtocolError


@dataclass(frozen=True)
class ReadOnlyRoute:
    method: str
    host_kind: str
    path: str


@dataclass(frozen=True)
class MutationRoute:
    method: str
    host_kind: str
    path: str


SEAT_PAGE_PATH = "/arc/selectListArc02012_n.do"
# 환불 1단계 — 본문 없는 POST (PNR은 Referer). 본문 검사가 없으면 카드번호·반환
# 비밀번호가 이 읽기 경로로 빠져나간다. _assert_empty_body_request 참고.
REFUND_TICKET_INFO_PATH = "/atc/getListAtc14087.do"
SEAT_PAGE_FIELDS = frozenset(
    {
        "reqCode",
        "runDt",
        "dptDt",
        "trnNo",
        "dptTm",
        "trnGpCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "psrmClCd",
        "seatAttCd",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "choiceSeatCount",
    }
)
SEAT_PAGE_FIXED_VALUES = {
    "reqCode": "9",
    "trnGpCd": "300",
}
# 좌석배치도 — 좌석 페이지의 후속 POST 읽기. 서버 렌더 페이지의 #trnScarSeatFrm 이
# serialize()해 보낸다. v2.0.41 번들 0-hit (서버 렌더). READ — 좌석 지도 반환, 생성 없음.
SEAT_GRID_PATH = "/arc/selectListArc02011_n.do"
# 할인쿠폰조회/등록 페이지. pageMove('/apa/selectListApa03020_n.do') — GET only.
# Live-read 2026-07-26 (77,056B). v2.0.41 번들 0-hit (서버 렌더 메뉴).
# GET-only가 중요: 같은 페이지가 등록 폼을 가지고 있지만 submit은
# COUPON_REGISTRATION_PATH(POST, mutation)로 간다. GET만 허용해야 쿠폰번호·비밀번호가
# 읽기 경로로 움직일 수 없다.
COUPON_LIST_PATH = "/apa/selectListApa03020_n.do"
# 할인쿠폰 등록 (MUTATION). 쿠폰 페이지의 couponReg() → POST {dscp_no, dscp_pwd}.
# 근거: tests/fixtures/discount_coupons_empty.html L132 (live 2026-07-26).
# v2.0.41 번들 0-hit (라우트·필드 모두). 번들이 뒷받침하는 것: messages.js:111-113
# mysrt006/007/008 (클라이언트 검증 문구), sub/main.html:475 DSCP_YN 플래그.
#
# "coupon" 범주, SRT_LIVE_MUTATION_CATEGORIES 밖 — preview만, 전송 불가.
COUPON_REGISTRATION_PATH = "/arb/selectListArb02A01_n.do"
# 할인 승차권 (공공할인) 페이지. pageMove — GET only. Live-read 2026-07-26 (206,268B).
# GET-only가 중요: 페이지 자체가 검색 폼(#rsvForm)이고 submit은
# PUBLIC_DISCOUNT_SEARCH_PATH(POST)로 간다. v2.0.41 번들 0-hit.
PUBLIC_DISCOUNT_PAGE_PATH = "/common/ARA/ARA0301V/view.do"
# 할인 승차권 검색 (공공할인 POST read). 정확계약 적용. Live 2026-07-26.
# GET 레그는 의도적으로 미등록 — 빈 hydration 페이지만 돌려주고 ~146필드를 허용해야
# 하므로. POST 레그만 등록: 조회결과 페이지의 #seatSearchForm.
# v2.0.41 번들 0-hit (라우트, pblDisc* 필드 전부).
PUBLIC_DISCOUNT_SEARCH_PATH = "/ara/selectListAra10131_n.do"
PUBLIC_DISCOUNT_SEARCH_FIELDS = frozenset(
    {
        # 서버 렌더 상수 9개
        "menuId",
        "owayRtrpCrclDvCd",
        "psgNum1",
        "psgNum2",
        "dirtChtnDvCd",
        "cgPsId",
        "medDvCd",
        "subCnt",
        # 페이징 커서 (첫 페이지 빈 문자열, 이후 gdNo=data.dsCmdMap.gdNo)
        "gdNo",
        # 여정
        "chtnDvCd",
        "dptDt",
        "dptTm",
        "dptRsStnCd",
        "arvRsStnCd",
        "stlbTrnClsfCd",
        "trnGpCd",
        "trnNo",
        "psgNum",
        "seatAttCd",
        "arriveTime",
        # 공공할인 전용 3개 (camelCase — 페이지 폼의 PBL_DISC_CD 등과 다른 철자)
        "pblDiscCd",
        "pblDiscMgNo",
        "tgtDtrmYn",
    }
)
PUBLIC_DISCOUNT_SEARCH_FIXED_VALUES = {
    "menuId": "41",
    "owayRtrpCrclDvCd": "01",
    "psgNum1": "0",
    "psgNum2": "0",
    "dirtChtnDvCd": "1",
    "cgPsId": "korail",
    "medDvCd": "03",
    "subCnt": "0",
    "arriveTime": "N",
    # 직통 고정. 할인 승차권 페이지에 환승 토글 없음 (jrnyTpCd="11" → chtnDvCd="1").
    "chtnDvCd": "1",
    # 항상 빈 문자열 — onload() 미할당, 페이징은 gdNo로.
    "trnNo": "",
}
PUBLIC_DISCOUNT_SEARCH_VALUE_PATTERNS = {
    "dptDt": r"[0-9]{8}",
    "dptTm": r"[0-9]{6}",
    "dptRsStnCd": r"[0-9]{4}",
    "arvRsStnCd": r"[0-9]{4}",
    # 역무차종별코드: 05 전체, 17 SRT, 00 KTX+SRT
    "stlbTrnClsfCd": r"(?:00|05|17)",
    "trnGpCd": r"(?:109|300|900)",
    "seatAttCd": r"[0-9]{3}",
    "psgNum": r"[1-9][0-9]*",
    # 공공할인코드 01..08 (페이지가 8개 분기)
    "pblDiscCd": r"0[1-8]",
    # 서버 발급 승인번호 — 불투명, 길이·문자 제한. 빈 문자열 허용.
    "pblDiscMgNo": r"[A-Za-z0-9-]{0,32}",
    "tgtDtrmYn": r"Y",
    "gdNo": r"[A-Za-z0-9-]{0,32}",
}
SEAT_GRID_FIELDS = frozenset(
    {
        "trnGpCd",
        "runDt",
        "trnNo",
        "scarNo",
        "psrmClCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "seatAttCd",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "choiceSeatCount",
    }
)
SEAT_GRID_FIXED_VALUES = {"trnGpCd": "300"}
SEAT_GRID_VALUE_PATTERNS = {
    "runDt": r"[0-9]{8}",
    # 정확히 5자리 제로패딩. 이것이 좌석배치도/알림셸 분기 조건이라 엄격 적용.
    "trnNo": r"[0-9]{5}",
    "scarNo": r"[0-9]{1,3}",
    "psrmClCd": r"[12]",
    "dptRsStnCd": r"[0-9]{4}",
    "arvRsStnCd": r"[0-9]{4}",
    "seatAttCd": r"[0-9]{3}",
    "dptStnRunOrdr": r"[0-9]+",
    "arvStnRunOrdr": r"[0-9]+",
    "choiceSeatCount": r"[1-9][0-9]*",
}
SEAT_PAGE_VALUE_PATTERNS = {
    "runDt": r"[0-9]{8}",
    "dptDt": r"[0-9]{8}",
    "trnNo": r"[0-9]{5}",
    "dptTm": r"[0-9]{6}",
    "dptRsStnCd": r"[0-9]{4}",
    "arvRsStnCd": r"[0-9]{4}",
    # psrmClCd: 1=일반실, 2=특실 (ara1001l.js: lfn_getRsv("psrmClCd1"))
    "psrmClCd": r"[12]",
    "seatAttCd": r"[0-9]{3}",
    "dptStnRunOrdr": r"[0-9]+",
    "arvStnRunOrdr": r"[0-9]+",
    # choiceSeatCount: totPrnb (ara1001l.js:1511)
    "choiceSeatCount": r"[1-9][0-9]*",
}


READ_ONLY_ROUTES = frozenset(
    {
        ReadOnlyRoute("GET", "app", "/login/login.do"),
        ReadOnlyRoute("POST", "app", "/apb/selectListApb01080_n.do"),
        ReadOnlyRoute("GET", "app", "/main/main.do"),
        ReadOnlyRoute("GET", "app", "/ara/ara0101v.do"),
        ReadOnlyRoute("POST", "app", "/main/noticeList.do"),
        ReadOnlyRoute("GET", "app", "/atc/selectListAtc14017_n.do"),
        # 예약/발권 목록 JSON. POST=XHR JSON, GET=HTML(미등록). Live 2026-07-26.
        # 근거: SRForegroundDialogActivity.java:31, sub/ticketList.html:405.
        ReadOnlyRoute("POST", "app", "/atc/selectListAtc14016_n.do"),
        # 환불 1단계 (refund step 1) — READ 분류는 추론.
        # 근거: 본문 없는 POST, 응답은 발권 식별 정보, getList 접두사, live-confirmed
        # 2026-07-26 (WRT300005 → 정상 업무 봉투). v2.0.41 번들 0-hit. 단일 출처(srtgo).
        # SrtClient.refund는 이 경로를 직접 부르지 않아 거절된 환불이 부수 요청을 내지 않음.
        ReadOnlyRoute("POST", "app", REFUND_TICKET_INFO_PATH),
        ReadOnlyRoute("GET", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10130_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10082_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra12009_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra13010_n.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0501P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0502P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0401P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0901P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0701P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0201V/view.do"),
        ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH),
        ReadOnlyRoute("POST", "app", SEAT_GRID_PATH),
        # 쿠폰 페이지 GET only — 등록 submit은 COUPON_REGISTRATION_PATH(mutation).
        ReadOnlyRoute("GET", "app", COUPON_LIST_PATH),
        # 공공할인 페이지 GET only — 검색 submit은 PUBLIC_DISCOUNT_SEARCH_PATH.
        ReadOnlyRoute("GET", "app", PUBLIC_DISCOUNT_PAGE_PATH),
        # 공공할인 검색 POST only — 정확계약 적용. GET 레그 미등록(빈 hydration).
        ReadOnlyRoute("POST", "app", PUBLIC_DISCOUNT_SEARCH_PATH),
        ReadOnlyRoute("GET", "netfunnel", "/ts.wseq"),
    }
)


# 상태변경 경로 5개, 범주당 1:1. READ_ONLY_ROUTES 밖 — 읽기 경로로 도달 불가.
# 근거: srtgo API_ENDPOINTS (srt.py:89-103), live 쿠폰 페이지 couponReg().
# 불변식: 라이브 활성화 4개는 consent+dry_run=False 아래서만 전송됨.
# 5번째(coupon)는 preview만 — SRT_LIVE_MUTATION_CATEGORIES 밖.
SRT_MUTATION_ROUTES = frozenset(
    {
        # reserve — v2.0.41 번들 O, live-verified 2026-07-25 (SUCC/IRR000018)
        MutationRoute("POST", "app", "/arc/selectListArc05013_n.do"),
        # cancel — 번들 0-hit, srtgo, live-verified 2026-07-25 (SUCC/IRG000000)
        MutationRoute("POST", "app", "/ard/selectListArd02045_n.do"),
        # payment — 번들 0-hit, srtgo/ryanking13(단일 출처), live 2026-07-26 (SUCC/IRT000000)
        MutationRoute("POST", "app", "/ata/selectListAta09036_n.do"),
        # refund — 번들 0-hit, srtgo 단일 출처, live 2026-07-26 (SUCC/IRT200277)
        MutationRoute("POST", "app", "/atc/selectListAtc02063_n.do"),
        # coupon — 번들 0-hit, live page couponReg(), preview ONLY, 미전송
        MutationRoute("POST", "app", COUPON_REGISTRATION_PATH),
    }
)

# 실제 전송이 허용된 범주 — 각각 live round trip으로 확인됨.
#   reserve — 2026-07-25 (SUCC/IRR000018)
#   cancel  — 2026-07-25 (SUCC/IRG000000)
#   payment — 2026-07-26 (SUCC/IRT000000, 수서→동탄 7,500원)
#   refund  — 2026-07-26 (SUCC/IRT200277)
# "coupon" 미포함 — 전송된 적 없음. test_mutation_live_paths 가 canary로 고정.
# payment는 PAN 평문 전송 → CARD_SECRET_FIELDS 본문 검사가 부가 보호.
# http.py 에서 import cycle 없이 쓰도록 순수 데이터.
SRT_LIVE_MUTATION_CATEGORIES: frozenset[str] = frozenset(
    {"reserve", "cancel", "payment", "refund"}
)

# 경로→범주 바인딩. 전송 시점에 caller의 category와 교차 검증.
SRT_MUTATION_ROUTE_CATEGORIES = {
    "/arc/selectListArc05013_n.do": "reserve",
    "/ard/selectListArd02045_n.do": "cancel",
    "/ata/selectListAta09036_n.do": "payment",
    "/atc/selectListAtc02063_n.do": "refund",
    COUPON_REGISTRATION_PATH: "coupon",
}


def assert_mutation_route(method: str, path: str) -> None:
    """등록된 상태변경 경로가 아니면 거절. 스킴·호스트·질의 붙으면 역시 거절."""
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise SrtProtocolError(
            "SRT request target is not a registered relative path: "
            f"{parsed.path}"
        )
    route = MutationRoute(method.upper(), "app", parsed.path)
    if route not in SRT_MUTATION_ROUTES:
        raise SrtProtocolError(
            f"SRT mutation route is not allowed: {route.method} {route.path}"
        )


def assert_mutation_route_category(path: str, category: str) -> None:
    """경로와 범주가 짝이 맞는지 검증 — 예약 consent로 환불 경로 사용 불가."""
    parsed_path = urlsplit(path).path
    expected = SRT_MUTATION_ROUTE_CATEGORIES.get(parsed_path)
    if expected is None:
        raise SrtProtocolError(
            f"SRT mutation route is not allowed: POST {parsed_path}"
        )
    if category != expected:
        raise SrtProtocolError(
            f"SRT mutation category {category!r} does not match route "
            f"{parsed_path} (expected {expected!r})"
        )


def _same_origin(left: httpx.URL, right: httpx.URL) -> bool:
    return (
        left.scheme,
        left.host,
        left.port or (443 if left.scheme == "https" else 80),
    ) == (
        right.scheme,
        right.host,
        right.port or (443 if right.scheme == "https" else 80),
    )


def _assert_exact_form_contract(
    request: httpx.Request,
    *,
    context: str,
    fields: frozenset[str],
    fixed_values: dict[str, str],
    value_patterns: dict[str, str],
) -> None:
    """POST 읽기 본문이 등록된 폼 계약과 정확히 일치하는지 검사.

    필드 집합 완전 일치, 중복 거절, 고정값 일치, 동적값 정규식 fullmatch.
    URL 인코딩 폼 필수, 질의 문자열 금지.
    """
    if b"?" in request.url.raw_path:
        raise SrtProtocolError(f"SRT {context} request must not use URL query parameters")
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise SrtProtocolError(f"SRT {context} request must use URL-encoded form data")
    try:
        body = request.content.decode("ascii")
        items = parse_qsl(body, keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        raise SrtProtocolError(f"SRT {context} form encoding is invalid") from None
    counts = Counter(name for name, _value in items)
    # frozenset 비교 — pyright strict 호환 (set vs frozenset 경고 회피)
    if frozenset(counts) != fields or any(count != 1 for count in counts.values()):
        raise SrtProtocolError(f"SRT {context} form keys do not match the registered contract")
    values = dict(items)
    if any(values.get(name) != value for name, value in fixed_values.items()):
        raise SrtProtocolError(
            f"SRT {context} fixed form values do not match the registered contract"
        )
    if any(
        re.fullmatch(pattern, values.get(name, "")) is None
        for name, pattern in value_patterns.items()
    ):
        raise SrtProtocolError(f"SRT {context} dynamic form values are malformed")


def _assert_seat_page_request(request: httpx.Request) -> None:
    _assert_exact_form_contract(
        request,
        context="seat page",
        fields=SEAT_PAGE_FIELDS,
        fixed_values=SEAT_PAGE_FIXED_VALUES,
        value_patterns=SEAT_PAGE_VALUE_PATTERNS,
    )


def _assert_seat_grid_request(request: httpx.Request) -> None:
    _assert_exact_form_contract(
        request,
        context="seat grid",
        fields=SEAT_GRID_FIELDS,
        fixed_values=SEAT_GRID_FIXED_VALUES,
        value_patterns=SEAT_GRID_VALUE_PATTERNS,
    )


def _assert_public_discount_search_request(request: httpx.Request) -> None:
    _assert_exact_form_contract(
        request,
        context="public discount search",
        fields=PUBLIC_DISCOUNT_SEARCH_FIELDS,
        fixed_values=PUBLIC_DISCOUNT_SEARCH_FIXED_VALUES,
        value_patterns=PUBLIC_DISCOUNT_SEARCH_VALUE_PATTERNS,
    )


# NetFunnel 대기열 — opcode별 정확 쿼리 계약.
# 근거: netfunnel.js getTidChkEnterProc / chkEnterProc / TsClient.setComplete.
# 차이점:
#   5101: key 없음 (아직 없으니까)
#   5002: key 필수, ttl 선택 (직전 201의 ttl>0일 때, prefix와 sid 사이)
#   5004: key 필수, sid/aid 없음 (유일하게 생략하는 빌더)
# js=yes — 번들 표기. srtgo/ryanking13는 js=true를 쓰지만 앱 번들이 우선.
# key 상한 512 — live 2026-07-26 캡처된 act_10 key가 256자 hex.
NETFUNNEL_KEY_RE = re.compile(r"[A-Za-z0-9_.:@~-]{1,512}")
_NETFUNNEL_COMMON = {
    "nfid": "0",
    "js": "yes",
}
_NETFUNNEL_ACT_10 = {
    "sid": "service_1",
    "aid": "act_10",
}
NETFUNNEL_QUERY_CONTRACTS = {
    "5101": {
        **_NETFUNNEL_COMMON,
        **_NETFUNNEL_ACT_10,
        "prefix": "NetFunnel.gRtype=5101;",
    },
    "5002": {
        **_NETFUNNEL_COMMON,
        **_NETFUNNEL_ACT_10,
        "prefix": "NetFunnel.gRtype=5002;",
    },
    "5004": {
        **_NETFUNNEL_COMMON,
        "prefix": "NetFunnel.gRtype=5004;",
    },
}
# key를 실는 opcode / ttl을 실을 수 있는 opcode.
NETFUNNEL_KEYED_OPCODES = frozenset({"5002", "5004"})
NETFUNNEL_TTL_OPCODES = frozenset({"5002"})


def _assert_netfunnel_request(url: httpx.URL) -> None:
    items = url.params.multi_items()
    params = dict(items)
    opcode = params.get("opcode", "")
    required = NETFUNNEL_QUERY_CONTRACTS.get(opcode)
    if required is None:
        raise SrtProtocolError(
            "SRT NetFunnel opcode is not one of the registered queue "
            "operations (5101 getTidChkEnter, 5002 chkEnter, 5004 setComplete)"
        )
    # 앱이 덧붙이는 타임스탬프: "&" + Date.getTime() → 이름=epoch, 값=빈 문자열
    timestamp_keys = [name for name, value in items if name.isdigit() and value == ""]
    expected_count = len(required) + 2  # + opcode + timestamp
    optional_names: list[str] = []
    if opcode in NETFUNNEL_KEYED_OPCODES:
        optional_names.append("key")
        expected_count += 1
        if NETFUNNEL_KEY_RE.fullmatch(params.get("key", "")) is None:
            raise SrtProtocolError(
                "SRT NetFunnel key parameter is missing or malformed"
            )
    if opcode in NETFUNNEL_TTL_OPCODES and "ttl" in params:
        optional_names.append("ttl")
        expected_count += 1
        ttl = params["ttl"]
        # netfunnel.js: ttl>0 일 때만 전송, TS_MAX_TTL=5 로 제한
        if not ttl.isdigit() or not 1 <= int(ttl) <= 5:
            raise SrtProtocolError(
                "SRT NetFunnel ttl parameter is outside the app's 1..5 range"
            )
    if (
        any(params.get(name) != value for name, value in required.items())
        or len(timestamp_keys) != 1
        or len(items) != expected_count
        or any(
            sum(name == item_name for item_name, _value in items) != 1
            for name in ("opcode", *required, *optional_names)
        )
    ):
        raise SrtProtocolError(
            f"SRT NetFunnel request is not the registered opcode-{opcode} contract"
        )


# 카드 비밀 필드 — 본문 기반 검사. 경로/범주 규칙으로는 막을 수 없는 빈틈을 메운다:
# 수제 결제 폼을 읽기 경로나 reserve consent에 실어 보내는 것을 차단.
# payment 라이브화 이후 이 검사가 유일한 방어선.
CARD_SECRET_FIELDS = frozenset(
    {
        "stlCrCrdNo1",  # PAN
        "vanPwd1",  # 카드 비밀번호 앞 2자리
        "crdVlidTrm1",  # 유효기간 YYMM
        "athnVal1",  # 생년월일 YYMMDD / 사업자등록번호
    }
)


def _carried_card_secret_fields(request: httpx.Request) -> set[str]:
    """본문·질의에 나타난 카드 비밀 필드명을 날바이트 부분문자열로 찾는다."""
    haystack = request.url.raw_path + b"\n" + request.content
    return {
        name for name in CARD_SECRET_FIELDS if name.encode("ascii") in haystack
    }


def assert_no_card_secrets(request: httpx.Request) -> None:
    """카드 비밀정보가 결제 외 경로로 나가는 것을 막는다."""
    carried = _carried_card_secret_fields(request)
    if carried:
        raise SrtProtocolError(
            "SRT request carries card-secret fields ("
            + ", ".join(sorted(carried))
            + ") on a route that is not the card payment; a PAN, card PIN, "
            "expiry or cardholder birthdate may travel only as a payment "
            "mutation, on the payment route, under a payment consent"
        )


def _assert_empty_body_request(request: httpx.Request) -> None:
    """환불 1단계(REFUND_TICKET_INFO_PATH)의 계약: 본문 없는 POST.

    PNR은 Referer로 전달되고 본문은 비어야 한다. 이 검사 없이는 읽기 경로에
    카드번호·반환 비밀번호가 그대로 실린다.
    """
    if request.content:
        raise SrtProtocolError(
            "SRT refund ticket info request must carry no body; the PNR travels "
            "in the Referer and this route must never be used to transmit form "
            "data"
        )
    if b"?" in request.url.raw_path:
        raise SrtProtocolError(
            "SRT refund ticket info request must not use URL query parameters"
        )


def assert_read_only_request(request: httpx.Request, config: SrtConfig) -> None:
    if config.base_url != APP_ORIGIN or config.netfunnel_url != NETFUNNEL_ORIGIN:
        raise SrtProtocolError("SRT request configuration does not use canonical origins")
    method = request.method
    url = request.url
    app = httpx.URL(APP_ORIGIN)
    netfunnel = httpx.URL(NETFUNNEL_ORIGIN)
    host_kind = (
        "app"
        if _same_origin(url, app)
        else "netfunnel"
        if _same_origin(url, netfunnel)
        else ""
    )
    path = url.path
    raw_path = url.raw_path.partition(b"?")[0]
    try:
        canonical_raw_path = path.encode("ascii")
    except UnicodeEncodeError:
        raise SrtProtocolError(
            "SRT request path must use the exact ASCII route spelling"
        ) from None
    if raw_path != canonical_raw_path:
        raise SrtProtocolError(
            "SRT request path must not use percent-encoded route characters"
        )
    route = ReadOnlyRoute(method.upper(), host_kind, path)
    if route not in READ_ONLY_ROUTES:
        raise SrtProtocolError(
            f"SRT request route is not allowed: {method.upper()} {path}"
        )
    # 카드 비밀정보는 어떤 읽기 경로에서도 금지.
    assert_no_card_secrets(request)
    if route == ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH):
        _assert_seat_page_request(request)
        return
    if route == ReadOnlyRoute("POST", "app", SEAT_GRID_PATH):
        _assert_seat_grid_request(request)
        return
    if route == ReadOnlyRoute("POST", "app", PUBLIC_DISCOUNT_SEARCH_PATH):
        _assert_public_discount_search_request(request)
        return
    if route == ReadOnlyRoute("POST", "app", REFUND_TICKET_INFO_PATH):
        _assert_empty_body_request(request)
        return
    if host_kind != "netfunnel":
        return
    _assert_netfunnel_request(url)


EXCLUDED_API_DOMAINS = frozenset(
    {
        "reservation",
        "ard-payment-entry",
        "payment",
        "refund",
        "cancellation",
        "ata-detail",
        "native-bridge",
        "external-seatmap",
    }
)

SAFETY_STATEMENTS = (
    "No user credentials, cookies, NetFunnel keys, raw response bodies, or payment "
    "tokens are stored here.",
    "Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, "
    "or card-shaped values in the repository.",
    "Library rule: do not implement real card approval in the core client.",
)
