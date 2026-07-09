import re

from .errors import SrtNetFunnelError
from .models import NetFunnelToken


def parse_netfunnel_response(body: str, *, action: str) -> NetFunnelToken:
    match = re.search(r"'([^']*(?:5101|5002):[^']*)'", body)
    if not match:
        match = re.search(r'"([^"]*(?:5101|5002):[^"]*)"', body)
    if not match:
        raise SrtNetFunnelError("NetFunnel response did not include a result token")
    value = match.group(1)
    token_part = value.rsplit(";", 1)[-1]
    parts = token_part.split(":", 2)
    raw_type = parts[0] if parts else ""
    if len(parts) == 2:
        code = raw_type
        param_text = parts[1]
    elif len(parts) >= 3:
        code = parts[1]
        param_text = parts[2]
    else:
        code = ""
        param_text = ""
    params: dict[str, str] = {}
    for item in param_text.split("&"):
        if "=" in item:
            key, val = item.split("=", 1)
            params[key] = val
    return NetFunnelToken(action=action, key=params.get("key", ""), raw_type=raw_type, code=code, params=params)
