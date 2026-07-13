import re

from .errors import SrtNetFunnelError
from .models import NetFunnelToken


RESULT_ASSIGNMENT_RE = re.compile(
    r"\s*"
    r"(?:NetFunnel\.gRtype\s*=\s*4999\s*;\s*)?"
    r"NetFunnel\.gControl\.result\s*=\s*"
    r"(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)"
    r"(?:\s*;\s*(?:NetFunnel\.gControl\._showResult\(\)\s*;\s*)?|\s*)"
)
RESULT_PREFIX = "NetFunnel.gRtype=5101"
SUCCESS_PAIRS = frozenset({("5101", "5101"), ("5002", "200")})


def build_act10_url(netfunnel_url: str, *, timestamp_ms: int) -> str:
    return (
        f"{netfunnel_url.rstrip('/')}/ts.wseq"
        "?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        f"&sid=service_1&aid=act_10&js=true&{timestamp_ms}"
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
    if ";" in value:
        prefix, token_part = value.split(";", 1)
        if prefix != RESULT_PREFIX or ";" in token_part:
            raise SrtNetFunnelError(None, "NetFunnel response used an invalid result prefix", raw=body)
    else:
        token_part = value
    parts = token_part.split(":", 2)
    raw_type = parts[0] if parts else ""
    if len(parts) == 2:
        code = raw_type
        param_text = parts[1]
    elif len(parts) >= 3:
        code = parts[1]
        param_text = parts[2]
    else:
        raise SrtNetFunnelError(None, "NetFunnel response used an invalid result token", raw=body)
    if not raw_type.isdigit():
        raise SrtNetFunnelError(None, "NetFunnel response used an invalid result type", raw=body)
    if (raw_type, code) not in SUCCESS_PAIRS:
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
