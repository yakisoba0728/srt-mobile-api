"""NetFunnel 대기열(``act_10``)의 URL 생성과 응답 토큰 파싱.

열차 검색과 예약은 SRT 서버에 닿기 전에 별도 호스트(``nf.letskorail.com``)의
대기열을 통과합니다. 이 모듈은 그 세 요청 —— 키 발급(``getTidChkEnter``, 5101),
입장 확인(``chkEnter``, 5002), 자리 반납(``setComplete``, 5004) —— 의 URL 을 앱
번들(``netfunnel.js``)이 만드는 순서 그대로 만들고, ``NetFunnel.gControl.result``
한 줄로 오는 응답을 :class:`~srt_mobile_api.models.NetFunnelToken` 으로 쪼갭니다.
HTTP 전송과 폴링 루프는 :class:`~srt_mobile_api.client.SrtClient` 쪽에 있습니다.

**성공은 3자리 상태코드로만 판정합니다.** 5101 요청의 답이 5002 로 되돌아오므로
응답이 에코하는 4자리 타입은 믿지 않습니다. 코드의 뜻은 어느 요청에 대한
답이냐에 따라 다릅니다: 200 통과, 300 우회(키 없음), 201/202 대기, 301/302 거부
(:class:`~srt_mobile_api.errors.SrtQueueRejectedError`), 502 는 ``setComplete``
에서만 성공입니다.

폴링 간격 상한 :data:`MAX_TTL_SECONDS` 는 앱의 ``TS_MAX_TTL`` 이지만, 하한
:data:`MIN_TTL_SECONDS` 와 총량 상한 :data:`QUEUE_POLL_LIMIT` ·
:data:`QUEUE_WAIT_LIMIT_SECONDS` 는 이 라이브러리가 정한 값입니다. 앱과 달리
무한히 기다리지 않습니다.
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

# The three request types we issue, spelled exactly as netfunnel.js:84 defines
# them:
#
#   NetFunnel.RTYPE_CHK_ENTER=5002;  NetFunnel.RTYPE_SET_COMPLETE=5004;
#   NetFunnel.RTYPE_GET_TID_CHK_ENTER=5101;
#
# RTYPE_ALIVE_NOTICE (5003), RTYPE_INIT (5105) and RTYPE_STOP (5106) exist in
# the same table and are deliberately NOT implemented: aliveNotice only matters
# for a long-lived popup we do not render, and init/stop are administrative.
RTYPE_CHK_ENTER = "5002"
RTYPE_SET_COMPLETE = "5004"
RTYPE_GET_TID_CHK_ENTER = "5101"
NETFUNNEL_OPCODES = frozenset(
    {RTYPE_CHK_ENTER, RTYPE_SET_COMPLETE, RTYPE_GET_TID_CHK_ENTER}
)

# NetFunnel.RetVal parses the wire token as RRRR:CCC:params (4-digit response
# type at offset 0, 3-digit status code at offset 5, params from offset 9).
# Success is keyed off the 3-digit status code, never off the echoed response type.
#
# The codes below are netfunnel.js:84's own names. What each MEANS depends on
# which request it answers, because the app dispatches by response type into a
# different handler per type (_showResult, netfunnel.js:60477):
#
#   _showResultChkEnter   (5002 and 5101, whose reply is retyped to 5002)
#       kSuccess=200        -> onSuccess, stores the pass cookie
#       kTsBypass=300       -> onBypass, no queue needed -- and NO key
#       kContinue=201 /
#       kContinueDebug=202  -> onContinued: still queued, poll again after ttl
#       everything else, 502 included, falls to the switch default -> onError
#
#   _showResultSetComplete (5004)
#       kSuccess=200        -> onSuccess
#       everything else     -> onError
#
# 502 (kTsErrorAComplete, "already complete") is therefore NOT success in
# either of the app's switches. We nonetheless accept it for setComplete ONLY,
# and that is an inference, not something the bundle states: the goal of a
# setComplete is that our slot is no longer held, and a server answering
# "already complete" has told us exactly that. NetFunnel_setComplete itself
# treats the equivalent local condition -- nothing left to complete -- as
# success without sending anything, synthesizing 5004:200 and calling
# _showResultSetComplete directly (netfunnel.js, NetFunnel_setComplete). For
# chkEnter/getTidChkEnter 502 stays an error, matching the switch.
SUCCESS_CODE = "200"
BYPASS_CODE = "300"
SUCCESS_CODES = frozenset({SUCCESS_CODE, BYPASS_CODE})
CONTINUE_CODES = frozenset({"201", "202"})
ALREADY_COMPLETE_CODE = "502"

# kTsBlock=301 and kTsIpBlock=302, netfunnel.js:84. The app does NOT fold these
# into its generic error path: _showResultChkEnter gives each its own event
# ("onBlock", "onIpBlock") beside "onError", which is the bundle's own statement
# that "the waiting room refused you" is a different fact from "the waiting room
# malfunctioned". Both still raise here -- neither is a wait, and a wait is the
# only non-failure that is not a pass -- but they raise SrtQueueRejectedError so
# a caller can tell them apart without reading the numeric code.
#
# 303 kTsExpressNumber also has its own event ("onExpressnumber") and is
# deliberately NOT mapped: it is an admission, not a refusal (the app stores the
# pass cookie and proceeds), we have never observed one, and guessing it into
# either bucket would be worse than leaving it in the generic error path.
QUEUE_REJECTED_CODES = frozenset({"301", "302"})

# netfunnel.js TS_MAX_TTL = 5 ("Default max ttl (second) 5~30"), applied in
# _showResultChkEnter as `if (ttl > max_ttl) ttl = max_ttl` before the retry
# timer is armed with `setTimeout(..., ttl * 1000)`. So the app never waits
# longer than this between polls however large a ttl the server sends, and
# neither do we.
MAX_TTL_SECONDS = 5
# Our floor. The app has none -- a ttl of 0 disarms its timer entirely, because
# the timer is only armed `if (a > 0)`. A polling loop cannot do that, so a
# missing or zero ttl becomes one second rather than a spin.
MIN_TTL_SECONDS = 1

# HARD caps on the polling loop, ours and not the app's. The app polls
# indefinitely behind a visible wait popup a human can close; this client has no
# such escape hatch, so an engaged queue must end in a bounded time either way.
# Whichever limit is reached first ends the wait with SrtNetFunnelError.
QUEUE_POLL_LIMIT = 20
QUEUE_WAIT_LIMIT_SECONDS = 60.0


# WHAT THE LIVE QUEUE ACTUALLY ANSWERED, 2026-07-26 (key redacted)::
#
#   NetFunnel.gRtype=4999;NetFunnel.gControl.result='5002:200:key=<256 hex>&
#   nwait=0&nnext=0&tps=0.000000&ttl=0&ip=rnf14.letskorail.com&port=443&
#   vwr_html=...&live_message=&chk_enter_cnt=1&vwr_type=&sticky=nf4';
#   NetFunnel.gControl._showResult();
#
# Three things in that are worth carrying:
#
#   * the reply to our 5101 comes back typed 5002. That is the app's own
#     retyping (`if (retval.getReqType() == RTYPE_GET_TID_CHK_ENTER)
#     retval.setReqType(RTYPE_CHK_ENTER)` in _showResult), and it is why success
#     has always been keyed off the 3-digit code rather than the echoed type.
#   * ttl=0 and nwait=0: at normal load the queue does not engage, so the 201
#     polling path has never been exercised against the real server and load was
#     deliberately not synthesised to force it.
#   * ip/port name a SPECIFIC queue node (rnf14.letskorail.com:443), and the app
#     would send its chkEnter/setComplete THERE rather than to the configured
#     host -- chkEnterProc and setComplete both build their base as
#     `if (ip && port && !config_use) proto://ip:port/` and TS_CONFIG_USE is
#     false. We deliberately do NOT follow that redirection: the whole client is
#     pinned to two canonical origins (SrtConfig, assert_read_only_request), and
#     following a server-named host would mean letting a response choose where
#     the next request goes. The live run says we do not have to -- a setComplete
#     sent to nf.letskorail.com for a key issued by rnf14 answered
#     `5004:200`, i.e. the front door released the slot fine.
def _ts_wseq(netfunnel_url: str) -> str:
    return f"{netfunnel_url.rstrip('/')}/ts.wseq"


def build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str:
    """대기열 키를 처음 발급받는 ``getTidChkEnter``(5101) URL 을 만듭니다.

    필드 순서는 앱의 ``getTidChkEnterProc``(``netfunnel.js``) 가 문자열을 잇는
    순서 그대로입니다::

        ...?opcode=5101&nfid=<id>&prefix=NetFunnel.gRtype=5101;
        [&ttl=<NetFunnel.ttl> if > 0] &sid=<service_id>&aid=<action_id>&js=yes
        [&user_data=<...>] &<Date.getTime()>

    첫 요청이므로 ``ttl`` 은 붙지 않고, ``user_data`` 의 출처인 ``srailSID``
    쿠키(``TS_USER_DATA_KEYS``)를 SRT 앱이 만들지 않으므로 그것도 없습니다.
    ``js=yes`` 는 오타가 아니라 앱 번들의 표기입니다(srtgo 와 ryanking13/SRT 는
    ``js=true``). ``timestamp_ms`` 는 앱의 ``Date.getTime()`` 자리로 캐시
    무력화용입니다.
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
    """"이제 들어가도 되나" 를 다시 묻는 ``chkEnter``(5002) URL 을 만듭니다.

    ``chkEnterProc``(``netfunnel.js``) 의 연결 순서입니다::

        ...?opcode=5002&key=<key>&nfid=<id>&prefix=NetFunnel.gRtype=5002;
        [&ttl=<NetFunnel.ttl> if > 0] &sid=<service_id>&aid=<action_id>
        [&user_data=<...>] &js=yes &<Date.getTime()>

    ``ttl`` 은 끝이 아니라 ``prefix`` 와 ``sid`` **사이**에 오며 0보다 클 때만
    붙습니다. 값은 직전 201 응답의 ttl 을 ``TS_MAX_TTL`` 로 자른 것으로
    (``_showResultChkEnter``), :func:`queue_wait_seconds` 가 계산합니다.
    ``key`` 는 불투명한 문자열이라 percent 인코딩해 넣고, 비어 있으면
    :class:`ValueError` 입니다.
    """
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
    """차지한 대기열 자리를 반납하는 ``setComplete``(5004) URL 을 만듭니다.

    ``TsClient.prototype.setComplete``(``netfunnel.js``) 의 연결 순서입니다::

        ...?opcode=5004&key=<key>&nfid=<id>&prefix=NetFunnel.gRtype=5004;
        [&user_data=<...>] &js=yes &<Date.getTime()>

    **``sid`` 도 ``aid`` 도 ``ttl`` 도 붙지 않습니다.** 앱의 네 빌더 중 ``sid``·
    ``aid`` 를 잇지 않는 것은 이것 하나뿐이고, 자리를 식별하는 것은 ``key``
    하나입니다.

    반납은 필수입니다. 보내지 않으면 자리가 타임아웃까지 잡혀 있습니다(앱도
    ``TS_AUTO_COMPLETE = true`` 로 자동 반납). ``key`` 가 비어 있으면
    :class:`ValueError` 입니다.
    """
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
    """통과도 대기도 아닌 상태코드를 알맞은 예외 객체로 바꿉니다.

    301·302(:data:`QUEUE_REJECTED_CODES`)는 대기열이 거부한 것이므로
    :class:`~srt_mobile_api.errors.SrtQueueRejectedError`, 나머지는
    :class:`~srt_mobile_api.errors.SrtNetFunnelError` 입니다. 반환만 하고 던지지는
    않습니다.
    """
    subclass = (
        SrtQueueRejectedError
        if token.code in QUEUE_REJECTED_CODES
        else SrtNetFunnelError
    )
    return subclass(token.code or None, message, raw=body)


def _parse_result_token(body: str, *, action: str) -> NetFunnelToken:
    """응답 한 줄을 타입·코드·파라미터로 쪼갭니다. 코드의 성패는 판정하지 않습니다.

    ``NetFunnel.gControl.result='<타입>:<코드>:<k=v&k=v...>'`` 형태가 아니거나
    타입이 숫자가 아니면 :class:`~srt_mobile_api.errors.SrtNetFunnelError` 이고,
    이때 ``code`` 는 ``None`` 입니다.

    성패 판정을 하지 않는 이유는 성공 코드 집합이 요청 종류마다 다르기
    때문입니다. 판정은 호출하는 :func:`parse_queue_response` ·
    :func:`parse_set_complete_response` 쪽에 있습니다.
    """
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
    """한 번에 통과한 응답만 받아들입니다 —— 200(키 있음) 또는 300(우회, 키 없음).

    대기(201/202)도 실패로 보고 :class:`~srt_mobile_api.errors.SrtNetFunnelError`
    를 냅니다. 즉시 입장하거나 끝내야 하는 호출자를 위한 엄격한 읽기입니다.

    클라이언트가 실제로 쓰는 것은 대기를 대기로 돌려주는
    :func:`parse_queue_response` 쪽입니다.
    """
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
    # A BYPASS carries no key, and demanding one made the accepted code
    # unreachable. kTsBypass means the queue was bypassed entirely -- there is no
    # place in line, so there is nothing to issue a key for -- and the app's own
    # chkEnter handler proves a key is not part of that branch:
    #
    #   case NetFunnel.kTsBypass:
    #       this._mStatus = NetFunnel.PS_N_RUNNING;
    #       e.setItem(this.mConfig.cookie_id, this.result, ...);
    #       this.fireEvent(null, this, "onBypass", {...});
    #       break;                       (netfunnel.js, _showResultChkEnter)
    #
    # It sets the running state and fires onBypass without reading getValue("key")
    # anywhere; the caller simply proceeds. Raising here instead aborted the whole
    # search, because the error escapes SrtClient._get_act10_key with code None and
    # the NET000001 retry in _search_with_retry matches only that code.
    #
    # Deliberately NOT relaxed for kSuccess (200): a queue pass is identified BY
    # its key, so a 200 without one is anomalous and still refused.
    #
    # Downstream, an empty key is inert rather than a deferred failure. Verified
    # in every builder that consumes one: search_page_payload,
    # search_ajax_payload / group_search_ajax_payload and
    # personal_reservation_payload all place the value verbatim into
    # "netfunnelKey" with no non-empty requirement, yielding netfunnelKey="" --
    # which is also what our own app sends, since the bundle's NetFunnel
    # integration is commented out (ara0101v.js:651-655, ara1001l.js:1734-1739
    # call netfunnel_callback() directly) and the string "netfunnelKey" appears
    # nowhere in the bundle at all; the field is srtgo-sourced. Nor does
    # assert_read_only_request constrain it. If a server nonetheless rejects the
    # keyless body it answers msgCd NET000001, which _search_with_retry already
    # retries once with a fresh acquisition.
    if not token.key and token.code != BYPASS_CODE:
        raise SrtNetFunnelError(
            None,
            "NetFunnel response did not include a non-empty key parameter",
            raw=body,
        )


def parse_queue_response(body: str, *, action: str) -> NetFunnelToken:
    """``getTidChkEnter``/``chkEnter`` 응답을 읽습니다. "아직 대기 중" 도 정상입니다.

    통과(200/300)와 대기(201/202) 모두 토큰을 돌려줍니다. 둘의 구분은
    :func:`is_queued` 입니다. 나머지 코드 —— 301 kTsBlock, 302 kTsIpBlock,
    502 kTsErrorAComplete, 그 밖의 5xx/9xx —— 는 앱에서 ``onError`` 로 가는
    코드이고 여기서도 예외입니다(거부 두 개는
    :class:`~srt_mobile_api.errors.SrtQueueRejectedError`).

    **대기 응답에는 키를 요구하지 않습니다.** 201 은 보통 폴링에 쓸 ``key`` 와
    ``ttl``/``nwait`` 를 같이 보내지만, 호출자는 이미 키를 들고 있으므로 에코가
    빠졌다고 검색을 중단시키지 않습니다. 통과(200)는 키를 요구합니다 —— 300 우회만
    예외이고, 우회는 줄을 서지 않았으니 자리를 가리킬 키도 없습니다.
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
    """``setComplete``(5004) 응답을 읽습니다 —— 자리가 풀렸는지만 봅니다.

    200(반납됨)과 502(kTsErrorAComplete, "이미 완료")를 성공으로 받습니다. 502 를
    성공으로 보는 것은 추론입니다: 앱의 ``_showResultSetComplete`` 는 502 를
    ``onError`` 로 보내지만, 여기서 묻는 것은 "내 자리가 풀렸나" 이고 두 답 모두
    풀렸다는 뜻입니다. ``chkEnter`` 쪽에서는 502 가 그대로 실패입니다.

    키는 요구하지 않습니다. 이 응답이 싣는 것은 ``utime`` 이고, 반납이 끝난
    시점에 식별할 자리도 남아 있지 않습니다.
    """
    token = _parse_result_token(body, action=action)
    if token.code not in {SUCCESS_CODE, ALREADY_COMPLETE_CODE}:
        raise _queue_failure(
            token,
            "NetFunnel setComplete did not release the queue slot",
            body,
        )
    return token


def is_queued(token: NetFunnelToken) -> bool:
    """대기열이 "나중에 다시 오라" 고 답했는지(201 kContinue / 202 kContinueDebug)."""
    return token.code in CONTINUE_CODES


def queue_wait_seconds(token: NetFunnelToken) -> int:
    """다음 ``chkEnter`` 까지 쉴 초. 서버의 ``ttl`` 을 위아래로 자른 값입니다.

    위로는 :data:`MAX_TTL_SECONDS`(앱의 ``TS_MAX_TTL``), 아래로는
    :data:`MIN_TTL_SECONDS` 로 자릅니다. 하한은 이 라이브러리가 붙였습니다 —— 앱은
    ttl 이 0이면 재시도 타이머를 아예 걸지 않지만, 폴링 루프에서 0은 바쁜
    대기이기 때문입니다. ``ttl`` 이 없거나 숫자가 아니면 0으로 읽습니다.

    이 값은 다음 요청의 ``ttl`` 파라미터로 그대로 되나갑니다
    (:func:`build_chk_enter_url`).
    """
    raw = token.params.get("ttl", "")
    ttl = int(raw) if raw.isdigit() else 0
    return max(MIN_TTL_SECONDS, min(ttl, MAX_TTL_SECONDS))
