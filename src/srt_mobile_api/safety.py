from dataclasses import dataclass
import httpx

from .config import APP_ORIGIN, NETFUNNEL_ORIGIN, SrtConfig
from .errors import SrtProtocolError


@dataclass(frozen=True)
class ReadOnlyRoute:
    method: str
    host_kind: str
    path: str


READ_ONLY_ROUTES = frozenset(
    {
        ReadOnlyRoute("GET", "app", "/login/login.do"),
        ReadOnlyRoute("POST", "app", "/apb/selectListApb01080_n.do"),
        ReadOnlyRoute("GET", "app", "/main/main.do"),
        ReadOnlyRoute("GET", "app", "/ara/ara0101v.do"),
        ReadOnlyRoute("POST", "app", "/main/noticeList.do"),
        ReadOnlyRoute("GET", "app", "/atc/selectListAtc14017_n.do"),
        ReadOnlyRoute("GET", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10007_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10130_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra10082_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra12009_n.do"),
        ReadOnlyRoute("POST", "app", "/ara/selectListAra13010_n.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0501P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0502P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0403P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0901P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0701P/view.do"),
        ReadOnlyRoute("POST", "app", "/common/ARA/ARA0201V/view.do"),
        ReadOnlyRoute("GET", "netfunnel", "/ts.wseq"),
    }
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


def assert_read_only_request(method: str, url: httpx.URL, config: SrtConfig) -> None:
    if config.base_url != APP_ORIGIN or config.netfunnel_url != NETFUNNEL_ORIGIN:
        raise SrtProtocolError("SRT request configuration does not use canonical origins")
    app = httpx.URL(APP_ORIGIN)
    netfunnel = httpx.URL(NETFUNNEL_ORIGIN)
    host_kind = "app" if _same_origin(url, app) else "netfunnel" if _same_origin(url, netfunnel) else ""
    path = url.path
    raw_path = url.raw_path.partition(b"?")[0]
    try:
        canonical_raw_path = path.encode("ascii")
    except UnicodeEncodeError:
        raise SrtProtocolError("SRT request path must use the exact ASCII route spelling") from None
    if raw_path != canonical_raw_path:
        raise SrtProtocolError("SRT request path must not use percent-encoded route characters")
    route = ReadOnlyRoute(method.upper(), host_kind, path)
    if route not in READ_ONLY_ROUTES:
        raise SrtProtocolError(f"SRT request route is not allowed: {method.upper()} {path}")
    if host_kind != "netfunnel":
        return

    items = url.params.multi_items()
    params = dict(items)
    timestamp_keys = [name for name, value in items if name.isdigit() and value == ""]
    required = {
        "opcode": "5101",
        "nfid": "0",
        "prefix": "NetFunnel.gRtype=5101;",
        "sid": "service_1",
        "aid": "act_10",
        "js": "true",
    }
    if (
        any(params.get(name) != value for name, value in required.items())
        or len(timestamp_keys) != 1
        or len(items) != len(required) + 1
        or any(sum(name == item_name for item_name, _value in items) != 1 for name in required)
    ):
        raise SrtProtocolError("SRT NetFunnel request is not the registered act_10 contract")


EXCLUDED_API_DOMAINS = frozenset(
    {
        "reservation",
        "netfunnel-act-19",
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
    "No user credentials, cookies, NetFunnel keys, raw response bodies, or payment tokens are stored here.",
    "Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or card-shaped values in the repository.",
    "Library rule: do not implement real card approval in the core client.",
)
