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
# Success is keyed off the 3-digit status code (kSuccess=200,
# kTsErrorAComplete=502), never off the echoed response type.
SUCCESS_CODES = frozenset({"200", "502"})


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
    if not key:
        raise SrtNetFunnelError(
            None,
            "NetFunnel response did not include a non-empty key parameter",
            raw=body,
        )
    return NetFunnelToken(action=action, key=key, raw_type=raw_type, code=code, params=params)
