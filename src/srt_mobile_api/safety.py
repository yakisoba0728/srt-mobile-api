from collections import Counter
from dataclasses import dataclass
import re
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
SEAT_PAGE_VALUE_PATTERNS = {
    "runDt": r"[0-9]{8}",
    "dptDt": r"[0-9]{8}",
    "trnNo": r"[0-9]{5}",
    "dptTm": r"[0-9]{6}",
    "dptRsStnCd": r"[0-9]{4}",
    "arvRsStnCd": r"[0-9]{4}",
    # psrmClCd is the cabin-class code sent dynamically by the app
    # (arc02012: psrmClCd = lfn_getRsv("psrmClCd1"); 1=일반실, 2=특실).
    # Validated as a member of {1, 2} rather than pinned to a fixed value.
    "psrmClCd": r"[12]",
    "seatAttCd": r"[0-9]{3}",
    "dptStnRunOrdr": r"[0-9]+",
    "arvStnRunOrdr": r"[0-9]+",
    # choiceSeatCount is the total passenger count sent dynamically by the app
    # (arc02012: choiceSeatCount = lfn_getRsv("totPrnb"), ara1001l.js:1511).
    # Validated as a positive integer rather than pinned to a fixed value.
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
        # 예약/발권 목록 (JSON). The app's own WebView loads this path as an HTML
        # page (SRForegroundDialogActivity.java:31 and the leftover
        # data-url="/srail-app/atc/selectListAtc14016_n.do?pageNo=0" on
        # sub/ticketList.html:405, both GET-shaped), while srtgo POSTs it as an
        # XHR and gets JSON back. Both are true of the live server -- a probe on
        # 2026-07-26 got 99,246 bytes of 승차권 확인 HTML from the GET and a
        # 338-byte JSON object from the POST -- and only the JSON is machine
        # readable, so only the POST is registered. This mirrors
        # /ara/selectListAra10007_n.do, whose GET (hydration page) and POST
        # (ajax) are two different reads of one path; here we simply do not need
        # the HTML one, since get_ticket_list already reads the atc14017 page.
        ReadOnlyRoute("POST", "app", "/atc/selectListAtc14016_n.do"),
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
        ReadOnlyRoute("GET", "netfunnel", "/ts.wseq"),
    }
)


# Documentation-level tiering of the state-changing routes. These are the four
# core SRT mutation endpoints (one per category), taken from srtgo API_ENDPOINTS
# (srt.py:89-103). They are deliberately kept OUT of READ_ONLY_ROUTES so the
# read-only allowlist and its guarantee stay fully intact:
# ``assert_read_only_request`` rejects every one of these (none is reachable via
# a read path). This is a classification only.
#
# Three separate things are true here and must not be conflated:
#   * "has a ``SrtClient`` method" — reserve and cancel do
#     (``SrtClient.reserve``, ``SrtClient.cancel``); payment and refund have no
#     client method at all.
#   * "can be transmitted" — reserve and cancel can, as of the two-category
#     opening of :data:`SRT_LIVE_MUTATION_CATEGORIES` below, and ONLY under an
#     explicit per-category ``MutationConsent`` with ``dry_run=False``. payment
#     and refund still cannot: the send path
#     (``SrtHttpClient.post_mutation_form``) refuses every category outside
#     that set, at both the ``post_mutation_form`` gate and again at the
#     ``_send_mutation_request`` send boundary.
#   * "the shape is confirmed" — a method existing, and a category being
#     transmittable, still say nothing about the form being the one the server
#     accepts. For reserve and cancel that question was answered on 2026-07-25 by
#     one live round trip (SUCC / IRR000018 for reserve, SUCC / IRG000000 for
#     cancel), for the single-journey one-adult case only. payment and refund
#     remain unanswered: no method, no live run, and both wire formats are 0-hit
#     in the offline bundle.
#
# So the current invariant is: payment and refund cannot leave the process as a
# live request no matter how permissive the caller's consent is, while reserve
# and cancel can — deliberately, so the pair can be verified live — and every
# one of these four routes remains unreachable through the read-only path.
#
# Each host is "app" (POST). The trailing comment names the consent category the
# route gates.
SRT_MUTATION_ROUTES = frozenset(
    {
        # reserve (client method exists, preview by default; LIVE-ENABLED;
        # route present in the v2.0.41 bundle, live wiring verified 2026-07-25)
        MutationRoute("POST", "app", "/arc/selectListArc05013_n.do"),
        # cancel (client method exists, preview by default; LIVE-ENABLED;
        # srtgo-sourced shape, 0-hit in v2.0.41, live-verified 2026-07-25)
        MutationRoute("POST", "app", "/ard/selectListArd02045_n.do"),
        # payment (tiered only; no client method; not live-enabled)
        MutationRoute("POST", "app", "/ata/selectListAta09036_n.do"),
        # refund (tiered only; no client method; not live-enabled)
        MutationRoute("POST", "app", "/atc/selectListAtc02063_n.do"),
    }
)

# Consent categories whose requests are permitted to actually reach the network.
#
# EXACTLY TWO: "reserve" and "cancel". They are enabled together, and only
# together, because they are the two halves of one reversible operation:
#
#   * ``SrtClient.reserve`` creates an unpaid hold.
#   * ``SrtClient.cancel`` releases one, from a full
#     :class:`~srt_mobile_api.models.SrtReservationHold` or from a bare PNR
#     string.
#
# Enabling reserve without cancel would mean a mistake or a crash mid-flow
# strands a real reservation on a real account with no programmatic way out.
# Enabling cancel alone is harmless but useless. So the pair is the smallest
# unit that is safe to open, and this set is what makes the operator-run
# reserve->cancel round trip (``scripts/verify_reserve_cancel_roundtrip.py``,
# with ``scripts/recover_hold.py`` as its safety net) physically possible.
#
# WHAT OPENING THE GATE DID AND DID NOT CLAIM. It was opened as a decision about
# recoverability, not evidence — it is what made the verification physically
# possible. That verification has since happened: on 2026-07-25 one operator-run
# round trip reserved and cancelled a real hold against the real server
# (reserve ``SUCC``/``IRR000018``, cancel ``SUCC``/``IRG000000``, and the ticket
# list afterwards carried no trace of the PNR). So both halves are now confirmed
# on the live server for the case that was exercised: ONE single-journey,
# one-adult, general-seat reservation. Multi-leg (``jrnyCnt`` > 1), group and
# standby were not exercised, and the cancel shape is still 0-hit across all
# 21,673 files of our v2.0.41 offline bundle — it came from srtgo, and one live
# success does not make it statically corroborated.
#
# payment AND refund STAY OUT, and adding either is a two-part job, not a
# one-line edit here:
#   1. Implementation — neither has a client method at all today.
#   2. Live verification of that category's own wire format, which (like
#      cancel's) has zero hits in the offline bundle.
# A payment additionally transmits a PAN in the clear, which is why
# ``post_mutation_form`` keeps a separate ``fake_card_only`` gate behind this
# one. Adding "payment" or "refund" to this set without both parts done is a
# safety regression; ``test_mutation_live_paths`` carries a canary that pins
# this set to exactly {"reserve", "cancel"} and so fails loudly on either
# addition.
#
# Kept as pure data in this module (no imports) so http.py can enforce it
# without creating an import cycle.
SRT_LIVE_MUTATION_CATEGORIES: frozenset[str] = frozenset({"reserve", "cancel"})

# The consent category each mutation route belongs to. The mutation send path
# cross-checks the caller-supplied category against the route so a consent for
# one category (e.g. "reserve") can never be used to POST a different category's
# route (e.g. the refund route).
SRT_MUTATION_ROUTE_CATEGORIES = {
    "/arc/selectListArc05013_n.do": "reserve",
    "/ard/selectListArd02045_n.do": "cancel",
    "/ata/selectListAta09036_n.do": "payment",
    "/atc/selectListAtc02063_n.do": "refund",
}


def assert_mutation_route(method: str, path: str) -> None:
    """Allow only the four evidenced state-changing routes (host "app", POST).

    This is the mutation counterpart to :func:`assert_read_only_request`, used
    solely by the dedicated mutation send path. A route must be an exact member
    of :data:`SRT_MUTATION_ROUTES`; anything else — including a read-only route —
    is rejected, so the mutation send path can never be repurposed to reach an
    arbitrary or read endpoint.
    """
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
    """Ensure ``category`` is the one that owns mutation route ``path``.

    Raises :class:`SrtProtocolError` when the path is not a known mutation route
    or when the caller's category does not match the route's category, so a
    per-category consent cannot be redirected to a different category's route.
    """
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


def _assert_seat_page_request(request: httpx.Request) -> None:
    if b"?" in request.url.raw_path:
        raise SrtProtocolError("SRT seat page request must not use URL query parameters")
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise SrtProtocolError("SRT seat page request must use URL-encoded form data")
    try:
        body = request.content.decode("ascii")
        items = parse_qsl(body, keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        raise SrtProtocolError("SRT seat page form encoding is invalid") from None
    counts = Counter(name for name, _value in items)
    if set(counts) != SEAT_PAGE_FIELDS or any(count != 1 for count in counts.values()):
        raise SrtProtocolError("SRT seat page form keys do not match the registered contract")
    values = dict(items)
    if any(values.get(name) != value for name, value in SEAT_PAGE_FIXED_VALUES.items()):
        raise SrtProtocolError("SRT seat page fixed form values do not match the registered contract")
    if any(
        re.fullmatch(pattern, values.get(name, "")) is None
        for name, pattern in SEAT_PAGE_VALUE_PATTERNS.items()
    ):
        raise SrtProtocolError("SRT seat page dynamic form values are malformed")


# The NetFunnel queue protocol, one exact query contract per opcode.
#
# This is deliberately three named contracts rather than one loosened contract:
# the guard used to accept getTidChkEnter (5101) and nothing else, and the way
# to add the other two halves of the protocol is to REGISTER them, not to stop
# checking. Every field below is taken from the corresponding builder in the
# bundle's own netfunnel.js -- getTidChkEnterProc, chkEnterProc and
# TsClient.prototype.setComplete -- and the differences between them are the
# app's, not ours:
#
#   * 5101 getTidChkEnter: no key (there is none yet to send).
#   * 5002 chkEnter: adds `key`, and OPTIONALLY `ttl` -- present only when the
#     previous 201 sent a non-zero one, and positioned between `prefix` and
#     `sid`, which is where the app concatenates it.
#   * 5004 setComplete: adds `key` and DROPS `sid` and `aid` entirely. It is the
#     only one of the four builders in netfunnel.js that never appends
#     "&sid=" + service_id + "&aid=" + action_id.
#
# `js=yes` is pinned for all three. srtgo and ryanking13/SRT both send
# `js=true`; the bundle we ship says `yes`, and the bundle is the app.
#
# The key is opaque and server-issued, so it is validated by SHAPE rather than
# by value: a non-empty run of the characters a NetFunnel key is made of. That
# keeps the parameter from becoming a free-text field a bug could smuggle
# anything through.
#
# The 512 bound is a ceiling, not a guess. A real act_10 key captured on
# 2026-07-26 is 256 characters of uppercase hex; an earlier 128 bound here made
# every setComplete fail this check, and because a failed release is swallowed
# by design (SrtClient._release_netfunnel_slots) it failed SILENTLY -- the live
# run is what exposed it, which is exactly the class of bug a fixture cannot.
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
# Opcodes whose request carries the queue key, and (separately) the one opcode
# that may carry a ttl. Kept as data next to the contracts so "which opcode has
# which optional field" is answerable by reading, not by tracing the checker.
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
    # The unkeyed timestamp the app appends as `"&" + Date.getTime()`. httpx
    # parses it as a parameter whose NAME is the epoch and whose value is empty.
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
        # netfunnel.js only appends ttl `if (NetFunnel.ttl > 0)` and caps it at
        # mConfig.max_ttl (TS_MAX_TTL = 5), so a ttl outside 1..5 is not a shape
        # the app can produce.
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
    if route == ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH):
        _assert_seat_page_request(request)
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
    "No user credentials, cookies, NetFunnel keys, raw response bodies, or payment tokens are stored here.",
    "Do not store credentials, cookies, NetFunnel keys, raw response bodies, PNRs, or card-shaped values in the repository.",
    "Library rule: do not implement real card approval in the core client.",
)
