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
# 환불 1단계. Its whole documented contract is "POST with NO body at all" — the
# Referer carries the PNR and the body is empty. That is enforced rather than
# merely written down, because this is the one read route whose neighbours in a
# caller's mind are a card payment and a refund: without a body check,
# ``post_form`` would happily send a PAN or a ticket return password to this
# path, which is allowlisted. See _assert_empty_body_request.
REFUND_TICKET_INFO_PATH = "/atc/getListAtc14087.do"
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
# 좌석배치도 (seat grid) for one 호차. The seat page's own inline script POSTs
# $("#trnScarSeatFrm").serialize() here; the route and the form are 0-hit in the
# v2.0.41 bundle and exist only in what the server renders. Registered as a READ
# on the same footing as SEAT_PAGE_PATH: it returns a seat map and creates
# nothing. Its exact field contract is enforced below, so this path cannot
# become a general-purpose POST.
SEAT_GRID_PATH = "/arc/selectListArc02011_n.do"
# 할인쿠폰조회/등록. Reached by the app's own MY SRT menu as
# pageMove('/apa/selectListApa03020_n.do'), and pageMove is
# `window.location = url` -- a plain GET with no parameters. Live-read
# 2026-07-26 (77,056 bytes, "보유한 쿠폰이 없습니다.").
#
# 0-hit in the v2.0.41 offline bundle, which knows no /apa/ route at all; the
# menu that names it is server-rendered into every authenticated page, which is
# why fetching a page we already read found a route static analysis could not.
#
# Registered as a READ and as GET ONLY, and the distinction is load-bearing
# rather than stylistic: this page is BOTH a coupon list and a coupon
# REGISTRATION form. The registration is not a POST to this path -- the page's
# own couponReg() posts {dscp_no, dscp_pwd} to COUPON_REGISTRATION_PATH -- so
# refusing everything but GET here is what keeps a coupon number and its
# password from ever travelling under a read. That other route is a MUTATION
# route (below), reachable only through post_mutation_form and only under a
# "coupon" consent, and it is not live-enabled.
COUPON_LIST_PATH = "/apa/selectListApa03020_n.do"
# 할인쿠폰 등록. The coupon page's own registration submit, and a MUTATION: it
# redeems a coupon against the account.
#
# Provenance is the live page and only the live page -- the route, the two
# fields and the response keys are all 0-hit across the 21,673 files of the
# v2.0.41 offline bundle. From couponReg() on /apa/selectListApa03020_n.do,
# fetched 2026-07-26:
#
#     var params = $("#couponInfo").serialize();
#     $.ajax({ type:"POST", url:"/arb/selectListArb02A01_n.do",
#              data:params, dataType:"json",
#              success:function(args){
#                  var msg   = args.resultMap[0].MSG;
#                  var rtncd = args.resultMap[0].RTNCD;
#                  ...
#
# #couponInfo is exactly two inputs, dscp_no and dscp_pwd.
#
# What the BUNDLE does corroborate is the vocabulary either side of the wire:
# js/common/messages.js:111-113 carries mysrt006/007/008 -- the two client-side
# validation refusals and the success text -- and sub/main.html:475 carries the
# member flag DSCP_YN, which the live session's own userMap also returns. So
# `dscp` is 할인쿠폰 in the app's own words; only the route is new.
#
# It is registered here and categorised as "coupon" below, and it is NOT in
# SRT_LIVE_MUTATION_CATEGORIES. That combination is deliberate and is the exact
# posture reserve/cancel/payment/refund each held before their own live run: a
# client method exists, a consent can preview it, and the send path refuses.
COUPON_REGISTRATION_PATH = "/arb/selectListArb02A01_n.do"
# 할인 승차권 (공공할인). Found the same way as COUPON_LIST_PATH and on the same
# menu -- pageMove('/common/ARA/ARA0301V/view.do') -- so a plain GET, and
# live-read 2026-07-26 (206,268 bytes).
#
# GET only, and this one has a sharper reason than the coupon page. The page it
# returns is a SEARCH FORM: #rsvForm, the same ~140-field form the booking page
# carries, plus PBL_DISC_CD / PBL_DISC_NM / PBL_DISC_MG_NO / TGT_DTRM_YN. Its
# submit goes to /ara/selectListAra10131_n.do, which this library does not
# implement and which is registered nowhere. Reading the page is a read;
# nothing here can turn it into a search, let alone a reservation.
#
# 0-hit in the v2.0.41 bundle in every part: the route, PBL_DISC_CD, and every
# one of its values.
PUBLIC_DISCOUNT_PAGE_PATH = "/common/ARA/ARA0301V/view.do"
SEAT_GRID_FIELDS = frozenset(
    {
        "trnGpCd",
        "runDt",
        "trnNo",
        "scarNo",
        "psrmClCd",
        "dptRsStnCd",
        "arvRsStnCd",
        "seatAttCd",
        "dptStnRunOrdr",
        "arvStnRunOrdr",
        "choiceSeatCount",
    }
)
SEAT_GRID_FIXED_VALUES = {"trnGpCd": "300"}
SEAT_GRID_VALUE_PATTERNS = {
    "runDt": r"[0-9]{8}",
    # FIVE digits, not "up to five". The zero-padding is the gate that decides
    # whether this route answers with a seat grid or an alert shell
    # (payloads.SEAT_TRAIN_NUMBER_LENGTH), so it is enforced at the boundary too
    # rather than trusted to the builder.
    "trnNo": r"[0-9]{5}",
    "scarNo": r"[0-9]{1,3}",
    "psrmClCd": r"[12]",
    "dptRsStnCd": r"[0-9]{4}",
    "arvRsStnCd": r"[0-9]{4}",
    "seatAttCd": r"[0-9]{3}",
    "dptStnRunOrdr": r"[0-9]+",
    "arvStnRunOrdr": r"[0-9]+",
    "choiceSeatCount": r"[1-9][0-9]*",
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
        # 환불 1단계: 원승차권 정보 조회 (refund step 1). Registered as a READ, and
        # that classification is an inference this comment states rather than
        # hides. What supports it: the request carries NO body at all, the
        # response is pure identity data (sale date / window / sequence /
        # return password / purchaser), the reference implementation calls it
        # `reserve_info` and uses it only to gather fields for the step-2 form,
        # and the `getList` prefix is the app's read-shaped naming. What does
        # NOT support it: nothing here can prove the server treats it as
        # side-effect free, and the app's own naming is not decisive --
        # /ard/selectListArd02045_n.do is a CANCEL despite the selectList
        # prefix.
        #
        # It is also 0-hit across all 21,673 files of our v2.0.41 offline bundle
        # (as is `Atc14087`; the nearest real routes are Atc14016/Atc14017), and
        # it is single-sourced: ryanking13/SRT has no refund at all, so unlike
        # the payment this is not even a claim two libraries make. The route
        # itself is no longer a guess, though: it answered a live probe on
        # 2026-07-26 with a proper business envelope for a non-existent PNR
        # (msgCd WRT300005, "조회자료가 없습니다."), and then returned a real
        # ticket's identity in the round trip that followed.
        #
        # Registering it does not put it in a refund's path by accident:
        # SrtClient.refund takes an already-fetched SrtRefundTicketInfo and
        # never calls this itself, precisely so that a refused refund cannot
        # cause a live request as a side effect of being refused, and so that
        # step 2 can only ever be built from an identity step 1 actually
        # returned. Reaching this route requires calling get_refund_ticket_info
        # deliberately.
        ReadOnlyRoute("POST", "app", REFUND_TICKET_INFO_PATH),
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
        # 좌석배치도. The seat page's follow-up read, live-confirmed 2026-07-26.
        ReadOnlyRoute("POST", "app", SEAT_GRID_PATH),
        # 할인쿠폰조회/등록. GET, and only GET: the same page carries a
        # registration form whose submit goes to a DIFFERENT route
        # (POST /arb/selectListArb02A01_n.do), which is a mutation and is not
        # registered anywhere in this module. See COUPON_LIST_PATH.
        ReadOnlyRoute("GET", "app", COUPON_LIST_PATH),
        # 할인 승차권 (공공할인 entitlements). GET, and only GET: the page IS a
        # search form, and its submit target /ara/selectListAra10131_n.do is
        # registered nowhere. See PUBLIC_DISCOUNT_PAGE_PATH.
        ReadOnlyRoute("GET", "app", PUBLIC_DISCOUNT_PAGE_PATH),
        ReadOnlyRoute("GET", "netfunnel", "/ts.wseq"),
    }
)


# Documentation-level tiering of the state-changing routes: the four core SRT
# mutation endpoints from srtgo API_ENDPOINTS (srt.py:89-103), plus the coupon
# registration the live coupon page names -- one per consent category. The 단체
# reservation endpoint /arc/selectListArc06014_n.do was here until 2026-07-26;
# it was UNREGISTERED when group booking was removed, because a route that no
# client method can reach has no business being transmittable
# (docs/IMPLEMENTATION_PROGRESS.md, "단체 (group) booking: removed"), and the
# coupon route is registered on the same principle read forwards. Route COUNT and
# category COUNT may still differ if a category ever
# grows a second endpoint; the category is what gates transmission. They are
# deliberately kept OUT of READ_ONLY_ROUTES so the read-only allowlist and its
# guarantee stay fully intact:
# ``assert_read_only_request`` rejects every one of these (none is reachable via
# a read path). This is a classification only.
#
# Three separate things are true here and must not be conflated, and the FIFTH
# route added on 2026-07-26 -- the coupon registration -- is the clearest
# illustration of why, because it satisfies the first and not the other two:
#   * "has a ``SrtClient`` method" — all five do: ``SrtClient.reserve``,
#     ``SrtClient.cancel``, ``SrtClient.pay_with_card``, ``SrtClient.refund``,
#     ``SrtClient.register_discount_coupon``.
#     This is the axis that says the LEAST, which is exactly why it is listed
#     first: having a method is not permission to send and is not evidence.
#   * "can be transmitted" — FOUR can, as of the 2026-07-26 opening of
#     :data:`SRT_LIVE_MUTATION_CATEGORIES` below, and ONLY under an explicit
#     per-category ``MutationConsent`` with ``dry_run=False``. The send path
#     (``SrtHttpClient.post_mutation_form``) still refuses every category
#     outside that set, at both the ``post_mutation_form`` gate and again at the
#     ``_send_mutation_request`` send boundary, and a payment additionally needs
#     an unambiguous card-kind claim. ``coupon`` is outside it, so a coupon
#     registration can be previewed and cannot be sent.
#   * "the shape is confirmed" — a method existing, and a category being
#     transmittable, still say nothing about the form being the one the server
#     accepts. That question was answered by two live round trips: reserve and
#     cancel on 2026-07-25 (SUCC / IRR000018 and SUCC / IRG000000), payment and
#     refund on 2026-07-26 (SUCC / IRT000000 and SUCC / IRT200277). Each covered
#     the single-journey one-adult case ONLY, and the two payment/refund routes
#     remain 0-hit in the offline bundle — the run is live-server evidence, not
#     static corroboration. The coupon route has had NO such run: its shape is
#     the live page's own couponReg(), which is strong evidence about the
#     REQUEST and none at all about the response.
#
# So the current invariant is: each of the four live-enabled categories may leave
# the process only under its own explicit consent, only onto its own route (the
# route/category binding below is re-asserted at the send boundary), only with
# ``dry_run=False``; the fifth may not leave at all — and every one of these five
# routes remains unreachable through the read-only path.
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
        # payment (client method exists, preview by default; LIVE-ENABLED;
        # srtgo/ryanking13-sourced shape -- one vendored source, not two --
        # 0-hit in v2.0.41, and our app pays via the Ard02017/18 WebView
        # instead; live-verified 2026-07-26, SUCC / IRT000000)
        MutationRoute("POST", "app", "/ata/selectListAta09036_n.do"),
        # refund (client method exists, preview by default; LIVE-ENABLED;
        # single-source srtgo shape with no upstream at all, 0-hit in v2.0.41;
        # live-verified 2026-07-26, SUCC / IRT200277)
        MutationRoute("POST", "app", "/atc/selectListAtc02063_n.do"),
        # coupon (client method exists, preview ONLY; NOT live-enabled; the
        # shape is the live coupon page's own couponReg(), 0-hit in v2.0.41;
        # never sent, by anyone, from here). Registered because a client method
        # can reach it -- the converse of why the 단체 route was UNregistered
        # when group booking was removed -- and because registration is what
        # binds it to its category, so a "coupon" consent can never be pointed
        # at the reserve route or vice versa. See COUPON_REGISTRATION_PATH.
        MutationRoute("POST", "app", COUPON_REGISTRATION_PATH),
    }
)

# Consent categories whose requests are permitted to actually reach the network.
#
# ALL FOUR, as of 2026-07-26. Each one is in this set because a live run
# answered it, and the entry below records what that entry rests on. Membership
# is never granted on the strength of an implementation existing; it is granted
# on the strength of a response from app.srail.or.kr.
#
#   * "reserve" — LIVE-VERIFIED 2026-07-25. ``SrtClient.reserve`` created a real
#     unpaid hold: ``SUCC`` / ``IRR000018``.
#   * "cancel" — LIVE-VERIFIED 2026-07-25. ``SrtClient.cancel`` released it:
#     ``SUCC`` / ``IRG000000``, and the ticket list afterwards carried no trace
#     of the PNR.
#   * "payment" — LIVE-VERIFIED 2026-07-26. ``SrtClient.pay_with_card`` charged
#     a real card for a real hold: ``SUCC`` / ``IRT000000``.
#   * "refund" — LIVE-VERIFIED 2026-07-26. The two-step ``SrtClient.
#     get_refund_ticket_info`` -> ``SrtClient.refund`` returned the ticket:
#     ``SUCC`` / ``IRT200277``, after which the account was verified empty of
#     both reservations and tickets from a separate session.
#
# reserve and cancel were opened FIRST and TOGETHER, before any of this was
# known, and that ordering was deliberate: they are the two halves of one
# reversible operation (reserve creates an unpaid hold, cancel releases one,
# from a hold object or a bare PNR string). Enabling reserve without cancel
# would mean a mistake or a crash mid-flow strands a real reservation on a real
# account with no programmatic way out. That pair is what made the operator-run
# round trip (``scripts/verify_reserve_cancel_roundtrip.py``, with
# ``scripts/recover_hold.py`` as its safety net) physically possible, and it was
# a decision about RECOVERABILITY, not evidence. payment and refund were then
# opened on the same principle: a charge and its reversal, verified as one round
# trip so nothing could be stranded paid.
#
# THE 2026-07-26 RUN, in full, because these two carried the thinnest evidence in
# the repository and the run is now the whole of the case for them. A free probe
# went first: a fake card and a non-existent PNR were sent to both routes, and
# neither answered with a 404 or an HTML error shell — both answered with proper
# business envelopes (``/atc/getListAtc14087.do`` with
# ``msgCd=WRT300005``/"조회자료가 없습니다.", the payment route with
# ``strResult=FAIL``/``msgCd=WRT100170``). That established the routes EXIST on
# our app version without spending anything. A real round trip followed: 수서 ->
# 동탄 (0551 -> 0552, the shortest SRT hop), 2026-08-09, train 315, one adult,
# 7,500 KRW — paid, then refunded, then confirmed gone.
#
# WHAT THE RUN DID NOT SETTLE. The origin is unchanged and still worth knowing:
# ``Ata09036``, ``Atc02063`` and ``Atc14087`` are all 0-hit across the 21,673
# files of our v2.0.41 offline bundle (which has no ``Atc02*`` family at all),
# our own app charges through the Ard02017/18 WebView pages plus a TransKey
# keypad and FIDO rather than this plaintext route, the payment shape comes from
# ONE implementation counted twice (srtgo vendored ryanking13/SRT wholesale) and
# the refund shape from one with no upstream at all. One live success does not
# make any of that statically corroborated, and the run covered exactly one
# single-journey, one-adult, general-seat ticket paid with one personal card in
# one lump sum. Multi-leg, group, standby, corporate cards and instalments were
# not exercised.
#
# A payment additionally transmits a PAN in the clear. That is why
# ``post_mutation_form`` keeps a separate card-kind gate (exactly one of
# ``fake_card_only`` / ``real_card_acknowledged``) behind this one, and why
# :data:`CARD_SECRET_FIELDS` is enforced on the BODY rather than on the route:
# opening this gate makes the body-shaped guard matter MORE, not less.
#
# A FIFTH CONSENT CATEGORY NOW EXISTS AND IS DELIBERATELY NOT IN THIS SET.
# "coupon" (할인쿠폰 등록, COUPON_REGISTRATION_PATH) was added on 2026-07-26 with
# a builder, a parser and a client method, and none of that admits it here:
# membership is granted on the strength of a response from app.srail.or.kr, and
# no coupon registration has ever been sent from this library. So
# SrtClient.register_discount_coupon can build and preview the exact request and
# cannot transmit it -- post_mutation_form and _send_mutation_request both
# refuse the category outright, exactly as they refused all four of the above
# before their own live runs.
#
# That is the whole point of keeping consent and live-enablement as two separate
# questions: adding the category was a MODELLING decision (a coupon redemption
# is not a booking and is not a payment, so it needed its own opt-in), while
# adding it HERE would be an evidence decision of the same weight as opening
# payment was. ``test_mutation_live_paths`` carries a canary that pins this set
# to exactly these four and so fails loudly on any addition or removal --
# including on "coupon".
#
# Kept as pure data in this module (no imports) so http.py can enforce it
# without creating an import cycle.
SRT_LIVE_MUTATION_CATEGORIES: frozenset[str] = frozenset(
    {"reserve", "cancel", "payment", "refund"}
)

# The consent category each mutation route belongs to. The mutation send path
# cross-checks the caller-supplied category against the route so a consent for
# one category (e.g. "reserve") can never be used to POST a different category's
# route (e.g. the refund route).
SRT_MUTATION_ROUTE_CATEGORIES = {
    "/arc/selectListArc05013_n.do": "reserve",
    "/ard/selectListArd02045_n.do": "cancel",
    "/ata/selectListAta09036_n.do": "payment",
    "/atc/selectListAtc02063_n.do": "refund",
    COUPON_REGISTRATION_PATH: "coupon",
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


def _assert_exact_form_contract(
    request: httpx.Request,
    *,
    context: str,
    fields: frozenset[str],
    fixed_values: dict[str, str],
    value_patterns: dict[str, str],
) -> None:
    """Require a POST read's body to be EXACTLY one registered form contract.

    Shared by the seat page and the seat grid, which are the same kind of route:
    a POST read whose body is a fixed set of journey identifiers. Extracted
    rather than copied so that a second such route cannot be registered with a
    quietly weaker check than the first.
    """
    if b"?" in request.url.raw_path:
        raise SrtProtocolError(f"SRT {context} request must not use URL query parameters")
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise SrtProtocolError(f"SRT {context} request must use URL-encoded form data")
    try:
        body = request.content.decode("ascii")
        items = parse_qsl(body, keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        raise SrtProtocolError(f"SRT {context} form encoding is invalid") from None
    counts = Counter(name for name, _value in items)
    if set(counts) != fields or any(count != 1 for count in counts.values()):
        raise SrtProtocolError(f"SRT {context} form keys do not match the registered contract")
    values = dict(items)
    if any(values.get(name) != value for name, value in fixed_values.items()):
        raise SrtProtocolError(
            f"SRT {context} fixed form values do not match the registered contract"
        )
    if any(
        re.fullmatch(pattern, values.get(name, "")) is None
        for name, pattern in value_patterns.items()
    ):
        raise SrtProtocolError(f"SRT {context} dynamic form values are malformed")


def _assert_seat_page_request(request: httpx.Request) -> None:
    _assert_exact_form_contract(
        request,
        context="seat page",
        fields=SEAT_PAGE_FIELDS,
        fixed_values=SEAT_PAGE_FIXED_VALUES,
        value_patterns=SEAT_PAGE_VALUE_PATTERNS,
    )


def _assert_seat_grid_request(request: httpx.Request) -> None:
    _assert_exact_form_contract(
        request,
        context="seat grid",
        fields=SEAT_GRID_FIELDS,
        fixed_values=SEAT_GRID_FIXED_VALUES,
        value_patterns=SEAT_GRID_VALUE_PATTERNS,
    )


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


# The card-secret field names, as they appear on the payment wire. A request
# carrying any of these is a card charge no matter what route or category it
# claims to be.
#
# WHY THIS EXISTS AS A SEPARATE CHECK. Both request guards validate the ROUTE
# and, with two exceptions, not the BODY — which is correct for reads whose
# bodies are ordinary query parameters, but it left one gap that no
# route/category rule could close: a caller can hand-assemble a payment body and
# post it to a DIFFERENT, permitted route. ``post_form`` would send it to any
# allowlisted read path, and ``post_mutation_form`` would send it to the
# live-enabled reserve route under a perfectly valid ``category="reserve"``
# consent. Neither is a category or route violation, so neither was refused.
#
# The invariant this restores is worth more than the hole it closes, because it
# is stated on the DATA rather than on the route: a PAN, a card PIN, a card
# expiry or a cardholder birthdate may travel only as a ``payment``.
#
# THIS CHECK MATTERS MORE SINCE 2026-07-26, NOT LESS. While ``payment`` was
# outside :data:`SRT_LIVE_MUTATION_CATEGORIES` the consequence was absolute and
# the guard was, in practice, a second lock on a door that was already welded
# shut. Now that payment is live-enabled it is the ONLY thing standing between a
# hand-assembled card form and the wire on every route that is not the payment
# route: a card body aimed at a read path, at the reserve or cancel route under
# a perfectly valid consent for that category, or at ``_send_mutation_request``
# directly, is refused here and nowhere else. The check did not degrade when the
# gate opened; it became load-bearing.
CARD_SECRET_FIELDS = frozenset(
    {
        "stlCrCrdNo1",  # PAN
        "vanPwd1",  # first two digits of the card PIN
        "crdVlidTrm1",  # expiry YYMM
        "athnVal1",  # birthdate YYMMDD / 사업자등록번호
    }
)


def _carried_card_secret_fields(request: httpx.Request) -> set[str]:
    """The card-secret field names appearing in a request's body or query.

    Matched as raw substrings rather than by parsing, so a body this library
    would not otherwise decode (a different encoding, a nested payload) cannot
    smuggle one past. These names are distinctive enough that a substring match
    has no realistic false positive.
    """
    haystack = request.url.raw_path + b"\n" + request.content
    return {
        name for name in CARD_SECRET_FIELDS if name.encode("ascii") in haystack
    }


def assert_no_card_secrets(request: httpx.Request) -> None:
    """Refuse any request carrying card secrets. See :data:`CARD_SECRET_FIELDS`."""
    carried = _carried_card_secret_fields(request)
    if carried:
        raise SrtProtocolError(
            "SRT request carries card-secret fields ("
            + ", ".join(sorted(carried))
            + ") on a route that is not the card payment; a PAN, card PIN, "
            "expiry or cardholder birthdate may travel only as a payment "
            "mutation, on the payment route, under a payment consent"
        )


def _assert_empty_body_request(request: httpx.Request) -> None:
    """Require a POST read whose contract is "no body" to actually carry none.

    The read-only guard otherwise validates the ROUTE and not the BODY, which is
    fine for reads whose bodies are ordinary query parameters. It is not fine
    for :data:`REFUND_TICKET_INFO_PATH`: that route is allowlisted, sits in the
    middle of the refund flow, and its neighbours in a caller's mind are a card
    payment and a refund form. Without this check ``post_form`` would transmit
    whatever mapping it was handed to an allowlisted path — a PAN, a card PIN or
    a ticket return password included — with no gate anywhere refusing it,
    because none of the mutation gates apply to a read route.

    So the emptiness the docstrings claim is enforced here rather than trusted.
    """
    if request.content:
        raise SrtProtocolError(
            "SRT refund ticket info request must carry no body; the PNR travels "
            "in the Referer and this route must never be used to transmit form "
            "data"
        )
    if b"?" in request.url.raw_path:
        raise SrtProtocolError(
            "SRT refund ticket info request must not use URL query parameters"
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
    # No read carries card secrets, on any route. See CARD_SECRET_FIELDS for why
    # this is checked on the data rather than on the route.
    assert_no_card_secrets(request)
    if route == ReadOnlyRoute("POST", "app", SEAT_PAGE_PATH):
        _assert_seat_page_request(request)
        return
    if route == ReadOnlyRoute("POST", "app", SEAT_GRID_PATH):
        _assert_seat_grid_request(request)
        return
    if route == ReadOnlyRoute("POST", "app", REFUND_TICKET_INFO_PATH):
        _assert_empty_body_request(request)
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
