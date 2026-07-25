import re

from .errors import SrtNetFunnelError
from .models import NetFunnelToken


RESULT_ASSIGNMENT_RE = re.compile(
    r"\s*"
    r"(?:NetFunnel\.gRtype\s*=\s*\d+\s*;\s*)?"
    r"NetFunnel\.gControl\.result\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)"
    r"(?:\s*;\s*(?:NetFunnel\.gControl\._showResult\(\)\s*;\s*)?|\s*)"
)
# NetFunnel.RetVal parses the wire token as RRRR:CCC:params (4-digit response
# type at offset 0, 3-digit status code at offset 5, params from offset 9).
# Success is keyed off the 3-digit status code, never off the echoed response type.
#
# We only issue getTidChkEnter (opcode 5101 = act_10). The app dispatches that
# reply through _showResultChkEnter (netfunnel.js:60477), whose switch proceeds
# (sets the pass cookie) only for kSuccess=200 (onSuccess) and kTsBypass=300
# (onBypass, no queue needed -- and no key; see parse_netfunnel_response).
# kContinue=201/kContinueDebug=202 mean keep-polling
# (onContinued); this parser is single-shot and does not model a polling loop, so
# 201/202 are treated as non-success. kTsErrorAComplete=502 falls to the switch
# default -> onError for chkEnter; 502-as-success only holds for setComplete (5004,
# _showResultSetComplete), which our read-only client never issues, so 502 must NOT
# be accepted here (netfunnel.js:84 code table).
# kTsBypass. Handled separately from kSuccess below because it is the one pass
# that legitimately carries NO key: see the key check in parse_netfunnel_response.
BYPASS_CODE = "300"
SUCCESS_CODES = frozenset({"200", BYPASS_CODE})


def build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str:
    return (
        f"{netfunnel_url.rstrip('/')}/ts.wseq"
        "?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        f"&sid=service_1&aid=act_10&js=yes&{timestamp_ms}"
    )


def parse_netfunnel_response(body: str, *, action: str) -> NetFunnelToken:
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
    if code not in SUCCESS_CODES:
        raise SrtNetFunnelError(code or None, "NetFunnel response did not report success", raw=body)
    params: dict[str, str] = {}
    for item in param_text.split("&"):
        if "=" in item:
            key, val = item.split("=", 1)
            params[key] = val
    key = params.get("key", "")
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
    if not key and code != BYPASS_CODE:
        raise SrtNetFunnelError(
            None,
            "NetFunnel response did not include a non-empty key parameter",
            raw=body,
        )
    return NetFunnelToken(action=action, key=key, raw_type=raw_type, code=code, params=params)
