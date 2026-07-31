"""NetFunnel 대기열(``act_10``)의 URL 생성과 응답 토큰 파싱.

검색·예약 전에 ``nf.letskorail.com`` 대기열을 통과해야 한다.
세 요청: 키 발급(5101), 입장 확인(5002), 자리 반납(5004).
성공은 3자리 상태코드로만 판정(200 통과, 300 우회, 201/202 대기, 301/302 거부).
HTTP 전송·폴링은 :class:`~srt_mobile_api.client.SrtClient` 쪽.
근거: ``offline/js/common/netfunnel.js`` (netfunnel.js:84 코드표).
"""

import re
from urllib.parse import quote

from .errors import SrtNetFunnelError, SrtQueueRejectedError
from .models import NetFunnelToken


RESULT_ASSIGNMENT_RE = re.compile(
    r"\s*"
    r"(?:NetFunnel\.gRtype\s*=\s*\d+\s*;\s*)?"
    r"NetFunnel\.gControl\.result\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)"
    r"(?:\s*;\s*(?:NetFunnel\.gControl\._showResult\(\)\s*;\s*)?|\s*)"
)

# netfunnel.js:84 opcode 정의. ALIVE_NOTICE(5003), INIT(5105), STOP(5106)은
# 의도적 미구현 (장시간 팝업 / 관리용).
RTYPE_CHK_ENTER = "5002"
RTYPE_SET_COMPLETE = "5004"
RTYPE_GET_TID_CHK_ENTER = "5101"
NETFUNNEL_OPCODES = frozenset(
    {RTYPE_CHK_ENTER, RTYPE_SET_COMPLETE, RTYPE_GET_TID_CHK_ENTER}
)

# netfunnel.js:84 상태코드. 의미는 요청 종류에 따라 다름 (_showResult 디스패치).
# chkEnter/getTidChkEnter: 200 통과, 300 우회(키 없음), 201/202 대기, 나머지 에러.
# setComplete: 200 성공, 나머지 에러. 502(already complete)는 setComplete에서만
# 추론적 성공으로 처리 — 목표(자리 반납)가 달성된 것이므로.
SUCCESS_CODE = "200"
BYPASS_CODE = "300"
SUCCESS_CODES = frozenset({SUCCESS_CODE, BYPASS_CODE})
CONTINUE_CODES = frozenset({"201", "202"})
ALREADY_COMPLETE_CODE = "502"

# kTsBlock=301, kTsIpBlock=302: 대기열 거부 (onBlock/onIpBlock 이벤트).
# 303 kTsExpressNumber은 입장이라 매핑 안 함.
QUEUE_REJECTED_CODES = frozenset({"301", "302"})

# TS_MAX_TTL=5 (netfunnel.js:18). 앱은 이 이상 기다리지 않음.
MAX_TTL_SECONDS = 5
# 하한(ours). 앱은 ttl=0이면 타이머 안 걸지만 폴링 루프에서 0은 바쁜 대기.
MIN_TTL_SECONDS = 1

# 폴링 상한 (ours). 앱은 무한 대기(팝업 닫기로 탈출); 여기선 유한.
QUEUE_POLL_LIMIT = 20
QUEUE_WAIT_LIMIT_SECONDS = 60.0


# Live 2026-07-26 관측:
# - 5101 응답이 5002 타입으로 돌아옴 (앱의 retyping, _showResult)
# - ttl=0, nwait=0: 정상 부하에서 대기열 미작동 (201 폴링 미검증)
# - ip/port가 특정 노드(rnf14) 가리킴. 리다이렉트 미따름 — 정규 오리진 고정 정책.
#   live setComplete가 nf.letskorail.com으로 보내도 5004:200 응답 확인.
def _ts_wseq(netfunnel_url: str) -> str:
    return f"{netfunnel_url.rstrip('/')}/ts.wseq"


def build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str:
    """``getTidChkEnter``(5101) URL. 필드 순서는 getTidChkEnterProc 그대로.

    첫 요청이라 ttl·user_data 없음. js=yes는 앱 번들 표기(srtgo는 js=true).
    """
    return (
        f"{_ts_wseq(netfunnel_url)}"
        "?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        f"&sid=service_1&aid=act_10&js=yes&{timestamp_ms}"
    )


def build_chk_enter_url(
    netfunnel_url: str,
    *,
    key: str,
    timestamp_ms: int,
    ttl: int | None = None,
) -> str:
    """``chkEnter``(5002) URL. ttl은 prefix와 sid 사이, >0일 때만 붙음."""
    if not key:
        raise ValueError("chkEnter requires the key the queue issued")
    ttl_part = f"&ttl={ttl}" if ttl is not None and ttl > 0 else ""
    return (
        f"{_ts_wseq(netfunnel_url)}"
        f"?opcode=5002&key={quote(key, safe='')}"
        "&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B"
        f"{ttl_part}"
        f"&sid=service_1&aid=act_10&js=yes&{timestamp_ms}"
    )


def build_set_complete_url(
    netfunnel_url: str,
    *,
    key: str,
    timestamp_ms: int,
) -> str:
    """``setComplete``(5004) URL. sid/aid/ttl 없음 — key만으로 자리 식별."""
    if not key:
        raise ValueError("setComplete requires the key whose slot is released")
    return (
        f"{_ts_wseq(netfunnel_url)}"
        f"?opcode=5004&key={quote(key, safe='')}"
        "&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B"
        f"&js=yes&{timestamp_ms}"
    )


def _queue_failure(
    token: NetFunnelToken,
    message: str,
    body: str,
) -> SrtNetFunnelError:
    """통과도 대기도 아닌 코드를 적절한 예외로 변환. 301/302는 QueueRejected."""
    subclass = (
        SrtQueueRejectedError
        if token.code in QUEUE_REJECTED_CODES
        else SrtNetFunnelError
    )
    return subclass(token.code or None, message, raw=body)


def _parse_result_token(body: str, *, action: str) -> NetFunnelToken:
    """응답을 타입·코드·파라미터로 분해. 성패 판정은 호출자 몫."""
    match = RESULT_ASSIGNMENT_RE.fullmatch(body)
    if not match:
        raise SrtNetFunnelError(
            None,
            "NetFunnel response did not include a result token",
            raw=body,
        )
    value = match.group("value")
    parts = value.split(":", 2)
    if len(parts) < 3:
        raise SrtNetFunnelError(None, "NetFunnel response used an invalid result token", raw=body)
    raw_type, code, param_text = parts
    if not raw_type.isdigit():
        raise SrtNetFunnelError(None, "NetFunnel response used an invalid result type", raw=body)
    params: dict[str, str] = {}
    for item in param_text.split("&"):
        if "=" in item:
            key, val = item.split("=", 1)
            params[key] = val
    return NetFunnelToken(
        action=action,
        key=params.get("key", ""),
        raw_type=raw_type,
        code=code,
        params=params,
    )


def parse_netfunnel_response(body: str, *, action: str) -> NetFunnelToken:
    """즉시 통과(200/300)만 허용하는 엄격 파서. 대기(201/202)도 실패."""
    token = _parse_result_token(body, action=action)
    if token.code not in SUCCESS_CODES:
        raise _queue_failure(
            token,
            "NetFunnel response did not report success",
            body,
        )
    _require_pass_key(token, body)
    return token


def _require_pass_key(token: NetFunnelToken, body: str) -> None:
    # 300(우회)은 key 없이 통과 — 줄을 서지 않았으니 key도 없음.
    # 200은 key 필수. 빈 key로 downstream에 가면 netfunnelKey=""가 되고,
    # 서버가 거절하면 NET000001 → _search_with_retry에서 1회 재시도.
    if not token.key and token.code != BYPASS_CODE:
        raise SrtNetFunnelError(
            None,
            "NetFunnel response did not include a non-empty key parameter",
            raw=body,
        )


def parse_queue_response(body: str, *, action: str) -> NetFunnelToken:
    """getTidChkEnter/chkEnter 응답 파서. 통과(200/300)와 대기(201/202) 모두 토큰 반환.

    대기 응답에는 key 미요구 (호출자가 이미 보유). 301/302는 QueueRejectedError.
    """
    token = _parse_result_token(body, action=action)
    if token.code in CONTINUE_CODES:
        return token
    if token.code not in SUCCESS_CODES:
        raise _queue_failure(
            token,
            "NetFunnel response did not report success",
            body,
        )
    _require_pass_key(token, body)
    return token


def parse_set_complete_response(body: str, *, action: str) -> NetFunnelToken:
    """setComplete(5004) 파서. 200(반납됨)과 502(이미 완료) 모두 성공. key 미요구."""
    token = _parse_result_token(body, action=action)
    if token.code not in {SUCCESS_CODE, ALREADY_COMPLETE_CODE}:
        raise _queue_failure(
            token,
            "NetFunnel setComplete did not release the queue slot",
            body,
        )
    return token


def is_queued(token: NetFunnelToken) -> bool:
    """대기 중(201/202)인지."""
    return token.code in CONTINUE_CODES


def queue_wait_seconds(token: NetFunnelToken) -> int:
    """다음 chkEnter까지 쉴 초. 서버 ttl을 [MIN_TTL, MAX_TTL]로 클램프."""
    raw = token.params.get("ttl", "")
    ttl = int(raw) if raw.isdigit() else 0
    return max(MIN_TTL_SECONDS, min(ttl, MAX_TTL_SECONDS))
