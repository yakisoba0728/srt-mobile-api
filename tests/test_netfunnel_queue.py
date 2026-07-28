"""The full NetFunnel queue protocol: 5101 acquire, 5002 poll, 5004 release.

Before this, the client sent `getTidChkEnter` (5101) and nothing else. That had
two consequences worth naming, because they are what these tests pin:

  * if the queue actually engaged (201 kContinue) the search simply FAILED. The
    queue working as designed looked like an error.
  * the slot was never released, so our place in line was held until it timed
    out. At peak load that is queue pollution we caused.

Every URL asserted here is the concatenation the bundle's own netfunnel.js
performs -- getTidChkEnterProc, chkEnterProc and TsClient.prototype.setComplete.
Where the three disagree (setComplete carries no sid/aid; ttl sits between
prefix and sid), the test says so, because the tempting assumption is that one
query shape covers all three.

**The 201 polling path is offline-tested only.** At normal load the SRT queue
does not engage, and load was deliberately not synthesised to force it.
"""

import httpx
import pytest

from srt_mobile_api import SrtClient, SrtConfig
from srt_mobile_api.errors import SrtNetFunnelError, SrtProtocolError
from srt_mobile_api.netfunnel import (
    MAX_TTL_SECONDS,
    NETFUNNEL_OPCODES,
    QUEUE_POLL_LIMIT,
    QUEUE_WAIT_LIMIT_SECONDS,
    build_act10_url,
    build_chk_enter_url,
    build_set_complete_url,
    is_queued,
    parse_queue_response,
    parse_set_complete_response,
    queue_wait_seconds,
)
from srt_mobile_api.safety import assert_read_only_request


NF = SrtConfig().netfunnel_url
TS = 1712345678901
KEY = "SYNTHETIC_QUEUE_KEY"


def _result(value: str) -> str:
    return f"NetFunnel.gControl.result='{value}';"


# --------------------------------------------------------------------------
# URL construction, against netfunnel.js's own concatenation
# --------------------------------------------------------------------------


def test_the_three_opcodes_are_the_bundles_own_constants():
    # netfunnel.js:84 -- RTYPE_CHK_ENTER=5002, RTYPE_SET_COMPLETE=5004,
    # RTYPE_GET_TID_CHK_ENTER=5101. RTYPE_ALIVE_NOTICE (5003), RTYPE_INIT (5105)
    # and RTYPE_STOP (5106) exist too and are deliberately not implemented.
    assert NETFUNNEL_OPCODES == {"5002", "5004", "5101"}


def test_get_tid_chk_enter_url_is_unchanged():
    assert build_act10_url(NF, timestamp_ms=TS) == (
        f"{NF}/ts.wseq?opcode=5101&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B"
        f"&sid=service_1&aid=act_10&js=yes&{TS}"
    )


def test_chk_enter_url_puts_ttl_between_prefix_and_sid():
    """chkEnterProc: `...prefix=...;` then `if (ttl>0) &ttl=`, THEN `&sid&aid`.

    Not appended at the end, and not a constant: the ttl is the one the previous
    201 sent back (`NetFunnel.ttl = a` in _showResultChkEnter, the same value
    used to arm the retry timer), so it is the server's own "come back in N
    seconds" echoed to it.
    """
    assert build_chk_enter_url(NF, key=KEY, timestamp_ms=TS, ttl=3) == (
        f"{NF}/ts.wseq?opcode=5002&key={KEY}"
        "&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B"
        f"&ttl=3&sid=service_1&aid=act_10&js=yes&{TS}"
    )


@pytest.mark.parametrize("ttl", [None, 0])
def test_chk_enter_omits_ttl_when_the_app_would_omit_it(ttl):
    # netfunnel.js appends it only `if (NetFunnel.ttl > 0)`.
    assert "ttl" not in build_chk_enter_url(NF, key=KEY, timestamp_ms=TS, ttl=ttl)


def test_set_complete_url_carries_no_sid_and_no_aid():
    """The one builder in netfunnel.js that never appends sid/aid.

    Worth pinning precisely because it contradicts the obvious assumption that
    all four request types share a query shape. The key alone identifies the
    slot being released.
    """
    url = build_set_complete_url(NF, key=KEY, timestamp_ms=TS)

    assert url == (
        f"{NF}/ts.wseq?opcode=5004&key={KEY}"
        "&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B"
        f"&js=yes&{TS}"
    )
    assert "sid=" not in url and "aid=" not in url and "ttl=" not in url


def test_every_builder_sends_js_yes_not_js_true():
    # srtgo and ryanking13/SRT both send js=true. The bundle we ship says yes.
    for url in (
        build_act10_url(NF, timestamp_ms=TS),
        build_chk_enter_url(NF, key=KEY, timestamp_ms=TS),
        build_set_complete_url(NF, key=KEY, timestamp_ms=TS),
    ):
        assert "js=yes" in url and "js=true" not in url


def test_a_keyed_request_without_a_key_is_refused_before_it_is_built():
    for builder in (build_chk_enter_url, build_set_complete_url):
        with pytest.raises(ValueError):
            builder(NF, key="", timestamp_ms=TS)


def test_an_opaque_key_is_percent_encoded():
    url = build_chk_enter_url(NF, key="a b&c=d", timestamp_ms=TS)
    assert "key=a%20b%26c%3Dd" in url


# --------------------------------------------------------------------------
# The safety contract: three registered opcodes, not one loosened one
# --------------------------------------------------------------------------


def _assert_allowed(url: str) -> None:
    assert_read_only_request(httpx.Request("GET", url), SrtConfig())


def _assert_refused(url: str) -> None:
    with pytest.raises(SrtProtocolError):
        assert_read_only_request(httpx.Request("GET", url), SrtConfig())


def test_all_three_builders_pass_their_own_contract():
    _assert_allowed(build_act10_url(NF, timestamp_ms=TS))
    _assert_allowed(build_chk_enter_url(NF, key=KEY, timestamp_ms=TS))
    _assert_allowed(build_chk_enter_url(NF, key=KEY, timestamp_ms=TS, ttl=5))
    _assert_allowed(build_set_complete_url(NF, key=KEY, timestamp_ms=TS))


@pytest.mark.parametrize(
    "query",
    [
        # An unregistered opcode. 5003 aliveNotice and 5105/5106 init/stop are
        # real NetFunnel operations we do not implement; the guard must refuse
        # them rather than accept "any /ts.wseq".
        f"opcode=5003&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5003%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        f"opcode=&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        # chkEnter with no key at all.
        f"opcode=5002&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        # chkEnter with an empty key.
        f"opcode=5002&key=&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        # A key carrying characters a NetFunnel key is not made of.
        f"opcode=5002&key=a%2Fb&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        # ttl outside the app's own 1..5 (TS_MAX_TTL) range.
        f"opcode=5002&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&ttl=0&sid=service_1&aid=act_10&js=yes&{TS}",
        f"opcode=5002&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&ttl=6&sid=service_1&aid=act_10&js=yes&{TS}",
        # ttl on an opcode that never carries one.
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&ttl=3&js=yes&{TS}",
        # setComplete must NOT carry sid/aid: the app does not send them, and
        # accepting them would mean the contract had been loosened rather than
        # registered.
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&sid=service_1&aid=act_10&js=yes&{TS}",
        # chkEnter/getTid MUST carry them.
        f"opcode=5002&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&js=yes&{TS}",
        # The prefix must echo this request's own opcode.
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5101%3B&js=yes&{TS}",
        # js=true is what the other libraries send; the app says yes.
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&js=true&{TS}",
        # A different action id.
        f"opcode=5002&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5002%3B&sid=service_1&aid=act_19&js=yes&{TS}",
        # No timestamp, two timestamps, an extra field, a duplicated field.
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&js=yes",
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&js=yes&{TS}&{TS}",
        f"opcode=5004&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&js=yes&extra=1&{TS}",
        f"opcode=5004&key={KEY}&key={KEY}&nfid=0&prefix=NetFunnel.gRtype%3D5004%3B&js=yes&{TS}",
    ],
)
def test_the_contract_is_three_registered_shapes_and_nothing_else(query):
    _assert_refused(f"{NF}/ts.wseq?{query}")


# --------------------------------------------------------------------------
# Status semantics: what each code means depends on which request it answers
# --------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["201", "202"])
def test_a_queued_reply_is_a_wait_not_a_failure(code):
    token = parse_queue_response(
        _result(f"5002:{code}:key={KEY}&ttl=3&nwait=42"), action="act_10"
    )
    assert is_queued(token) is True
    assert token.key == KEY
    assert queue_wait_seconds(token) == 3


def test_a_pass_is_not_queued():
    token = parse_queue_response(_result(f"5101:200:key={KEY}"), action="act_10")
    assert is_queued(token) is False


def test_a_queued_reply_need_not_re_echo_the_key():
    # The caller already holds one; refusing a wait over a missing echo would
    # abort a search that was merely queued.
    token = parse_queue_response(_result("5002:201:ttl=2&nwait=9"), action="act_10")
    assert is_queued(token) and token.key == ""


@pytest.mark.parametrize(
    ("raw_ttl", "expected"),
    [
        ("ttl=3", 3),
        ("ttl=5", MAX_TTL_SECONDS),
        # Capped exactly as _showResultChkEnter caps it at mConfig.max_ttl
        # (TS_MAX_TTL = 5), so a hostile ttl cannot stall us for minutes.
        ("ttl=900", MAX_TTL_SECONDS),
        # Floored at 1: the app disarms its timer entirely when ttl is 0
        # (`if (a > 0)`), which a polling loop cannot do without spinning.
        ("ttl=0", 1),
        ("nwait=1", 1),
        ("ttl=abc", 1),
    ],
)
def test_the_wait_is_clamped_the_way_the_app_clamps_it(raw_ttl, expected):
    token = parse_queue_response(_result(f"5002:201:{raw_ttl}"), action="act_10")
    assert queue_wait_seconds(token) == expected


@pytest.mark.parametrize("code", ["301", "302", "502", "500", "900"])
def test_chk_enter_still_fails_on_every_error_code(code):
    # These all fall to _showResultChkEnter's switch default -> onError. 502
    # (kTsErrorAComplete) included: "already complete" is only meaningful as an
    # answer to setComplete.
    with pytest.raises(SrtNetFunnelError):
        parse_queue_response(_result(f"5002:{code}:key={KEY}"), action="act_10")


def test_set_complete_accepts_200_and_502():
    assert parse_set_complete_response(
        _result("5004:200:utime=1"), action="act_10"
    ).code == "200"
    # 502 kTsErrorAComplete. This one is an INFERENCE and is labelled as such in
    # netfunnel.py: the app's _showResultSetComplete routes it to onError, but
    # the question this answers is "is my slot released?", and "already
    # complete" means yes.
    assert parse_set_complete_response(
        _result("5004:502:msg=already"), action="act_10"
    ).code == "502"


@pytest.mark.parametrize("code", ["201", "300", "301", "505"])
def test_set_complete_refuses_everything_else(code):
    with pytest.raises(SrtNetFunnelError):
        parse_set_complete_response(_result(f"5004:{code}:x=1"), action="act_10")


def test_set_complete_does_not_demand_a_key_back():
    # Its reply carries utime, not a key, and there is nothing left to identify.
    assert parse_set_complete_response(
        _result("5004:200:utime=1"), action="act_10"
    ).key == ""


# --------------------------------------------------------------------------
# The client loop
# --------------------------------------------------------------------------


class _Queue:
    """A NetFunnel that queues us `waits` times, then admits us."""

    def __init__(self, waits: int, *, ttl: int = 2, admit_key: str = KEY):
        self.waits = waits
        self.ttl = ttl
        self.admit_key = admit_key
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host != "nf.letskorail.com":
            raise AssertionError(f"unexpected {request.url}")
        opcode = request.url.params["opcode"]
        if opcode == "5004":
            return httpx.Response(200, text=_result("5004:200:utime=1"))
        if self.waits > 0:
            self.waits -= 1
            return httpx.Response(
                200,
                text=_result(
                    f"{opcode}:201:key={self.admit_key}&ttl={self.ttl}&nwait=7"
                ),
            )
        return httpx.Response(200, text=_result(f"{opcode}:200:key={self.admit_key}"))

    @property
    def opcodes(self) -> list[str]:
        return [request.url.params["opcode"] for request in self.requests]


def _queue_client(queue, *, clock=None, sleeps=None):
    return SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(queue),
        clock=clock or (lambda: 1712345678.901),
        sleep=(sleeps.append if sleeps is not None else (lambda _seconds: None)),
    )


def test_an_engaged_queue_is_polled_with_chk_enter_until_admitted():
    queue = _Queue(waits=3, ttl=2)
    sleeps: list[float] = []
    client = _queue_client(queue, sleeps=sleeps)

    key = client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    assert key == KEY
    # One acquisition then three polls: the app's chkEnterCont loop.
    assert queue.opcodes == ["5101", "5002", "5002", "5002"]
    assert sleeps == [2, 2, 2]
    # The server's own ttl goes back out on each poll, as NetFunnel.ttl does.
    for request in queue.requests[1:]:
        assert request.url.params["ttl"] == "2"
        assert request.url.params["key"] == KEY


def test_a_queue_that_never_admits_us_ends_at_the_poll_cap():
    queue = _Queue(waits=10_000, ttl=1)
    sleeps: list[float] = []
    client = _queue_client(queue, sleeps=sleeps)

    with pytest.raises(SrtNetFunnelError, match="bounded wait"):
        client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    # Bounded, and bounded by the POLL cap here because the clock is frozen.
    assert len(sleeps) == QUEUE_POLL_LIMIT
    assert queue.opcodes.count("5002") == QUEUE_POLL_LIMIT


def test_a_slow_queue_ends_at_the_wall_clock_cap_even_below_the_poll_cap():
    queue = _Queue(waits=10_000, ttl=5)
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    client = SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(queue),
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(SrtNetFunnelError, match="bounded wait"):
        client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    polls = queue.opcodes.count("5002")
    assert polls < QUEUE_POLL_LIMIT
    assert now[0] >= QUEUE_WAIT_LIMIT_SECONDS


def test_a_queue_that_never_issues_a_key_does_not_poll_forever_on_nothing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_result("5101:201:ttl=1&nwait=1"))

    client = _queue_client(handler)

    with pytest.raises(SrtNetFunnelError, match="key to poll with"):
        client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")


def test_a_bypass_holds_no_slot_and_so_releases_nothing():
    # kTsBypass (300) carries no key: there is no place in line, so there is
    # nothing to complete either.
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=_result("5101:300:nwait=0"))

    client = _queue_client(handler)
    assert client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do") == ""

    client._release_netfunnel_slots("https://app.srail.or.kr/ara/ara0101v.do")
    assert [request.url.params["opcode"] for request in requests] == ["5101"]


def test_releasing_sends_one_set_complete_per_held_key_and_holds_nothing_after():
    queue = _Queue(waits=0)
    client = _queue_client(queue)

    client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")
    client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")
    client._release_netfunnel_slots("https://app.srail.or.kr/ara/ara0101v.do")

    assert queue.opcodes == ["5101", "5101", "5004", "5004"]
    assert client._netfunnel_slots == []
    # A second release is a no-op, not a second round of requests.
    client._release_netfunnel_slots("https://app.srail.or.kr/ara/ara0101v.do")
    assert queue.opcodes.count("5004") == 2


@pytest.mark.parametrize(
    "reply",
    [
        _result("5004:505:msg=nope"),  # the server refused
        "not a NetFunnel token at all",  # or answered nonsense
    ],
)
def test_a_failed_release_is_swallowed_and_still_drops_the_key(reply):
    """Housekeeping must never replace the caller's real outcome.

    The release happens AFTER the guarded request has already succeeded or
    failed on its own terms. Raising here would turn a successful search into an
    error because we could not tidy up -- and, worse for a reserve, would hide
    the PNR of a hold that now exists.
    """
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params["opcode"] == "5004":
            return httpx.Response(200, text=reply)
        return httpx.Response(200, text=_result(f"5101:200:key={KEY}"))

    client = _queue_client(handler)
    client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    client._release_netfunnel_slots("https://app.srail.or.kr/ara/ara0101v.do")

    # No exception, one attempt only (the key is popped before it is sent, so a
    # failure drops it instead of queueing another try), and nothing retained.
    assert [request.url.params["opcode"] for request in calls] == ["5101", "5004"]
    assert client._netfunnel_slots == []


def test_a_transport_failure_during_release_is_also_swallowed():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["opcode"] == "5004":
            raise httpx.ConnectError("network gone")
        return httpx.Response(200, text=_result(f"5101:200:key={KEY}"))

    client = _queue_client(handler)
    client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    client._release_netfunnel_slots("https://app.srail.or.kr/ara/ara0101v.do")

    assert client._netfunnel_slots == []


# --------------------------------------------------------------------------
# What the LIVE queue answered, 2026-07-26. Keys are synthetic; everything
# else is the real reply.
# --------------------------------------------------------------------------

LIVE_KEY = "A9" * 128  # 256 chars, the length and charset of a real act_10 key
LIVE_TAIL = (
    "&nwait=0&nnext=0&tps=0.000000&ttl=0&ip=rnf14.letskorail.com&port=443"
    "&vwr_html=https%3a%2f%2fwww%2ekorail%2ecom%2fnetfunnel-statics%2f"
    "assets%2fvwr-page%2fpage%2f1%2f1%2f1%2findex%2ehtml"
    "&live_message=&chk_enter_cnt=1&vwr_type=&sticky=nf4"
)
LIVE_ACQUIRE = (
    f"NetFunnel.gRtype=4999;NetFunnel.gControl.result='5002:200:key={LIVE_KEY}"
    f"{LIVE_TAIL}'; NetFunnel.gControl._showResult();"
)
LIVE_RELEASE = (
    f"NetFunnel.gRtype=4999;NetFunnel.gControl.result='5004:200:key={LIVE_KEY}"
    f"{LIVE_TAIL}'; NetFunnel.gControl._showResult();"
)


def test_the_live_acquire_reply_comes_back_typed_5002_not_5101():
    """We asked opcode 5101 and the server answered a 5002-typed token.

    That is the app's own retyping (`_showResult` rewrites a
    RTYPE_GET_TID_CHK_ENTER reply to RTYPE_CHK_ENTER before dispatching), and it
    is why success is keyed off the 3-digit code rather than the echoed type.
    """
    token = parse_queue_response(LIVE_ACQUIRE, action="act_10")

    assert token.raw_type == "5002"
    assert token.code == "200"
    assert token.key == LIVE_KEY
    # ttl=0 and nwait=0: the queue did not engage. The 201 polling path has
    # never been exercised against the real server.
    assert token.params["ttl"] == "0" and token.params["nwait"] == "0"
    assert is_queued(token) is False


def test_a_real_length_key_survives_the_safety_contract():
    """The regression the live run caught.

    The key bound here was 128 characters; a real key is 256. Every setComplete
    therefore failed the guard -- and because a failed release is swallowed by
    design, it failed SILENTLY. No fixture could have shown that.
    """
    _assert_allowed(build_set_complete_url(NF, key=LIVE_KEY, timestamp_ms=TS))
    _assert_allowed(build_chk_enter_url(NF, key=LIVE_KEY, timestamp_ms=TS, ttl=2))


def test_the_live_release_reply_is_accepted():
    """LIVE, 2026-07-26: a real setComplete round trip answered 5004:200.

    Sent to nf.letskorail.com even though the acquire reply named a specific
    queue node (ip=rnf14.letskorail.com), which the app WOULD have followed. The
    front door released the slot anyway, which is why this client stays pinned
    to its two canonical origins instead of letting a response choose the next
    request's host.
    """
    token = parse_set_complete_response(LIVE_RELEASE, action="act_10")

    assert token.raw_type == "5004" and token.code == "200"
    assert token.params["ip"] == "rnf14.letskorail.com"


# --------------------------------------------------------------------------
# Acquisition and release must stay symmetric on EVERY exit, including the
# ones that raise. A key recorded only after the poll loop finishes is a slot
# the server keeps holding for a caller who has already given up.
# --------------------------------------------------------------------------


def test_a_key_held_when_the_bounded_wait_expires_is_still_ours_to_release():
    def queue(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_result("5101:201:key=QUEUED-KEY&ttl=1&nwait=9"))

    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    client = SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(queue),
        clock=clock,
        sleep=sleep,
    )

    with pytest.raises(SrtNetFunnelError, match="bounded wait"):
        client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    # The raise happens with a key already issued to us. Before, the append
    # below the loop had not run yet and the slot was simply abandoned.
    assert client._netfunnel_slots == ["QUEUED-KEY"]


def test_the_poll_loop_supersedes_its_key_rather_than_accumulating_slots():
    keys = iter(["FIRST-KEY", "SECOND-KEY", "THIRD-KEY"])
    replies = [
        "5101:201:key=FIRST-KEY&ttl=1&nwait=3",
        "5002:201:key=SECOND-KEY&ttl=1&nwait=2",
        "5002:200:key=THIRD-KEY&ttl=1&nwait=0",
    ]
    sent = iter(replies)

    def queue(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_result(next(sent)))

    now = [0.0]
    client = SrtClient(
        SrtConfig(),
        transport=httpx.MockTransport(queue),
        clock=lambda: now[0],
        sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )

    key = client._get_act10_key("https://app.srail.or.kr/ara/ara0101v.do")

    # One slot, the current one -- not one per poll. Releasing three keys for
    # one place in line would be its own kind of wrong.
    assert key == "THIRD-KEY"
    assert client._netfunnel_slots == ["THIRD-KEY"]
    assert list(keys) == ["FIRST-KEY", "SECOND-KEY", "THIRD-KEY"]
