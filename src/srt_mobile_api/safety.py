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

    items = url.params.multi_items()
    params = dict(items)
    timestamp_keys = [name for name, value in items if name.isdigit() and value == ""]
    required = {
        "opcode": "5101",
        "nfid": "0",
        "prefix": "NetFunnel.gRtype=5101;",
        "sid": "service_1",
        "aid": "act_10",
        "js": "yes",
    }
    if (
        any(params.get(name) != value for name, value in required.items())
        or len(timestamp_keys) != 1
        or len(items) != len(required) + 1
        or any(
            sum(name == item_name for item_name, _value in items) != 1
            for name in required
        )
    ):
        raise SrtProtocolError(
            "SRT NetFunnel request is not the registered act_10 contract"
        )


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
