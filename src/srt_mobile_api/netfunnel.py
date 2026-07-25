import re
from urllib.parse import quote

from .errors import SrtNetFunnelError
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
    """The ``getTidChkEnter`` (5101) URL, in the app's own field order.

    ``getTidChkEnterProc`` (netfunnel.js) concatenates::

        ...?opcode=5101&nfid=<id>&prefix=NetFunnel.gRtype=5101;
        [&ttl=<NetFunnel.ttl> if > 0] &sid=<service_id>&aid=<action_id>&js=yes
        [&user_data=<...>] &<Date.getTime()>

    ``NetFunnel.ttl`` is undefined until a 201 sets it, so the FIRST request of
    a conversation carries no ``ttl`` -- which is what this builds. ``user_data``
    is omitted because the app's only configured source is a ``srailSID`` cookie
    (``TS_USER_DATA_KEYS``) the SRT app never sets, leaving ``getUserdata()``
    empty.

    ``js=yes`` is deliberate and is NOT a typo for ``js=true``: srtgo and
    ryanking13/SRT both send ``true``, and the bundle we ship says ``yes``.
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
    """The ``chkEnter`` (5002) URL: "am I admitted yet?".

    ``chkEnterProc`` (netfunnel.js) concatenates::

        ...?opcode=5002&key=<key>&nfid=<id>&prefix=NetFunnel.gRtype=5002;
        [&ttl=<NetFunnel.ttl> if > 0] &sid=<service_id>&aid=<action_id>
        [&user_data=<...>] &js=yes &<Date.getTime()>

    Note where ``ttl`` sits: BETWEEN ``prefix`` and ``sid``, not appended at the
    end, and present only when non-zero. It is not a constant either -- it is
    the ttl the previous 201 sent back, capped at ``TS_MAX_TTL``
    (``_showResultChkEnter`` does ``NetFunnel.ttl = a`` right before arming the
    retry timer with the same value). So ``ttl`` is the server's own "come back
    in N seconds", echoed to it.

    ``key`` is opaque and server-supplied, so it is percent-encoded rather than
    interpolated raw; the app interpolates raw because its keys are alphanumeric.
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
    """The ``setComplete`` (5004) URL: "I am done, release my slot".

    ``TsClient.prototype.setComplete`` (netfunnel.js) concatenates::

        ...?opcode=5004&key=<key>&nfid=<id>&prefix=NetFunnel.gRtype=5004;
        [&user_data=<...>] &js=yes &<Date.getTime()>

    **It carries NO ``sid`` and NO ``aid``**, unlike every other request type in
    this file, and no ``ttl`` either. That is the bundle's own construction --
    ``setComplete`` is the only builder of the four that never appends
    ``"&sid=" + service_id + "&aid=" + action_id`` -- and it is worth stating
    plainly because it contradicts the obvious assumption that all four share a
    query shape. The key alone identifies the slot, which is presumably why the
    service/action pair is redundant here.

    Sending this is not optional politeness: without it our place in line is
    held until it times out, and at peak load that is queue pollution we caused.
    ``TS_AUTO_COMPLETE = true`` in the bundle's own config, so the app releases
    automatically too.
    """
    if not key:
        raise ValueError("setComplete requires the key whose slot is released")
    return (
        f"{_ts_wseq(netfunnel_url)}"
        f"?opcode=5004&key={quote(key, safe='')}"
        "&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B"
        f"&js=yes&{timestamp_ms}"
    )


def _parse_result_token(body: str, *, action: str) -> NetFunnelToken:
    """Split the wire token into type/code/params WITHOUT judging the code.

    Every caller below applies its own status policy on top, because "success"
    is not one set of codes: it depends on which request the token answers (see
    the code table at the top of this module).
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
    """A single-shot PASS: 200 (with a key) or 300 (bypass, no key).

    This is the strict, non-polling reading, kept for callers that must either
    be admitted immediately or fail. :func:`parse_queue_response` is the one the
    client uses now, because a 201 is a wait rather than a failure.
    """
    token = _parse_result_token(body, action=action)
    if token.code not in SUCCESS_CODES:
        raise SrtNetFunnelError(
            token.code or None,
            "NetFunnel response did not report success",
            raw=body,
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
    """A ``getTidChkEnter``/``chkEnter`` reply, including "still queued".

    Returns the token for a pass (200/300) **and** for a wait (201/202); the
    caller distinguishes them with :func:`is_queued`. Every other code -- 301
    kTsBlock, 302 kTsIpBlock, 502 kTsErrorAComplete, the 5xx/9xx errors -- falls
    to the app's ``onError`` branch and raises here too.

    A 201 carries the key to poll with (``chkEnterCont(retval.getValue("key"))``)
    and normally the ``ttl``/``nwait`` pair as well, but this does NOT require a
    key on a wait: the caller already holds one, and refusing a wait over a
    missing echo would abort a search that was merely queued.
    """
    token = _parse_result_token(body, action=action)
    if token.code in CONTINUE_CODES:
        return token
    if token.code not in SUCCESS_CODES:
        raise SrtNetFunnelError(
            token.code or None,
            "NetFunnel response did not report success",
            raw=body,
        )
    _require_pass_key(token, body)
    return token


def parse_set_complete_response(body: str, *, action: str) -> NetFunnelToken:
    """A ``setComplete`` (5004) reply.

    Accepts 200 (released) and 502 (kTsErrorAComplete, "already complete"). The
    second is an inference and is labelled as such at the top of this module:
    the app's ``_showResultSetComplete`` routes 502 to ``onError``, but our
    caller's question is "is my slot released?", and both answers mean yes. No
    key is required -- the reply to a setComplete carries ``utime``, not a key,
    and there is nothing left to identify anyway.
    """
    token = _parse_result_token(body, action=action)
    if token.code not in {SUCCESS_CODE, ALREADY_COMPLETE_CODE}:
        raise SrtNetFunnelError(
            token.code or None,
            "NetFunnel setComplete did not release the queue slot",
            raw=body,
        )
    return token


def is_queued(token: NetFunnelToken) -> bool:
    """Whether the queue told us to come back later (kContinue/kContinueDebug)."""
    return token.code in CONTINUE_CODES


def queue_wait_seconds(token: NetFunnelToken) -> int:
    """How long to wait before the next ``chkEnter``, clamped as the app clamps.

    The server's ``ttl`` (seconds), capped at ``TS_MAX_TTL`` exactly as
    ``_showResultChkEnter`` caps it, and floored at one second so a missing or
    zero ttl cannot turn the loop into a spin. The same value goes back out on
    the next request's ``ttl`` parameter, which is what the app does with
    ``NetFunnel.ttl``.
    """
    raw = token.params.get("ttl", "")
    ttl = int(raw) if raw.isdigit() else 0
    return max(MIN_TTL_SECONDS, min(ttl, MAX_TTL_SECONDS))
