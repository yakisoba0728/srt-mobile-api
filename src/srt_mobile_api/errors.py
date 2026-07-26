from .redaction import redact_text, redact_url


class SrtApiError(Exception):
    """Base error for SRT client failures."""

    def __init__(self, message: str = "SRT API request failed") -> None:
        super().__init__(redact_url(message))


class SrtTransportError(SrtApiError):
    """HTTP transport failed before an app-level response was parsed."""


class SrtProtocolError(SrtApiError):
    """The server response did not match the documented protocol."""

    def __init__(
        self,
        message: str = "SRT protocol response was invalid",
        *,
        raw: object | None = None,
    ) -> None:
        self.raw = raw
        super().__init__(message)


class SrtAuthError(SrtApiError):
    """Login or session authentication failed."""

    def __init__(self, message: str = "SRT authentication failed") -> None:
        self.message = redact_url(message)
        super().__init__(self.message)


class SrtSessionExpiredError(SrtAuthError):
    """The server returned a login redirect or login form for an authenticated request.

    Also raised for a reserve response that declares ``strResult="FAIL"`` with
    ``msgCd="S111"``. That is the app's OWN rule and the only place in the whole
    v2.0.41 bundle where a ``msgCd`` value is branched on::

        if (resultMap.strResult == "FAIL") {
            var redirectToLogin = null
            if (resultMap.msgCd == "S111") {
                localStorage.setItem('userReservation', param);
                redirectToLogin = "memberShipLogin()";
            }
            srtAlertBoxDivShow("알림", resultMap.msgTxt, null, redirectToLogin);

    (``analysis/raw/base/assets/offline/js/ara/ara1001l.js:1562-1573``.) It is
    deliberately NOT generalised to every endpoint: the branch exists only in the
    reserve handler, and promoting an arbitrary ``S111`` to an auth error
    elsewhere would move it OUT of :class:`SrtAppError`, breaking an existing
    ``except SrtAppError`` for callers of those reads.

    srtgo reaches the same conclusion by matching the message substring
    "로그인 후 사용하십시오" (``srtgo/srtgo.py:729``). Our bundle does not contain
    that exact string — the closest are the app's own client-side prompts
    "로그인 후 사용하십시요" (``messages.js:224``, note 시요/시오) and
    "비회원은 사용할 수 없습니다.<br/>로그인 후 사용하시기 바랍니다."
    (``messages.js:231``) — so we classify on the code the app itself reads.
    """

    def __init__(self, message: str = "SRT session expired", *, raw: object | None = None) -> None:
        self.raw = raw
        super().__init__(message)


class SrtIpBlockedError(SrtAuthError):
    """The edge refused the request outright because the source IP is blocked.

    The login endpoint answers a non-JSON plain-text body containing
    "Your IP Address Blocked"; :class:`SrtHttpClient` surfaces it here so a
    caller can tell "this network is banned" from "these credentials are wrong"
    without reading the body. Both are :class:`SrtAuthError`, so an existing
    ``except SrtAuthError`` around ``login()`` keeps its meaning exactly.

    NOT bundle-attested — this is an infrastructure response, not an app one, and
    the string is 0-hit across the v2.0.41 bundle. It is our own live-facing
    handling, corroborated by srtgo (``srt.py:719-720``).

    Distinct from the queue's own IP block (``kTsIpBlock`` 302, see
    :class:`SrtQueueRejectedError`): that one is NetFunnel refusing entry to the
    waiting room and leaves the app itself reachable.
    """


class SrtAppError(SrtApiError):
    """The server returned an app-level failure response.

    Base of the app-level taxonomy. ``code`` is the server's ``msgCd`` (or the
    wrapper's ``ErrorCode``/``ERROR_CODE``) verbatim, and ``raw`` is the whole
    response, so a caller can always fall back to inspecting the code even for a
    failure this library has no subclass for — and so a code map can be built
    from real traffic. Every subclass below is a REFINEMENT: catching
    ``SrtAppError`` still catches all of them.
    """

    def __init__(self, code: str | None, message: str | None, *, raw: object | None = None) -> None:
        self.code = code
        self.message = redact_url(message or "")
        self.raw = raw
        safe_code = redact_url(str(code or "UNKNOWN"))
        super().__init__(f"{safe_code}: {self.message}".strip())


class SrtNoResultsError(SrtAppError):
    """The request was accepted and simply matched nothing.

    "Retry is pointless; ask a different question." An empty search is NOT an
    empty list on this server: it is a declared failure. Live-captured
    2026-07-26, the deliberate empty-window search answered
    ``strResult=FAIL`` / ``msgCd=WRG000000`` / "조회 결과가 없습니다.", and the
    app alerts on it like any other FAIL (``ara1001l.js:206-210``).

    ``WRT300005`` ("조회자료가 없습니다.") joins it: the same live capture saw it
    in the reservation list's secondary ``rsMap`` envelope. **That envelope is
    not read** — :func:`~srt_mobile_api.parsers.parse_reservation_list_response`
    reads ``resultMap`` and only ``resultMap``, which on that response said
    ``SUCC`` / ``IRZ000005`` with empty arrays and therefore returns an empty
    list rather than raising anything at all. ``WRT300005`` is mapped here for
    the case where some other endpoint puts it in the envelope we DO read.

    The bundle does not distinguish this from any other FAIL — the app shows
    ``msgTxt`` and goes back either way — so the split is ours, made on codes
    this repository has observed live.
    """


class SrtInvalidRequestError(SrtAppError):
    """The server rejected the request we built; the fix is the input.

    "Retry is pointless; fix the payload." Both codes are this repository's own
    live observations, not srtgo's:

    * ``WRP011002`` "승객수 오류" — a passenger-count rejection, seen alongside
      ``strResult=FAIL`` on a reserve
      (``docs/analysis/srt-app-api-library-spec-2026-07-09.md:359``);
    * ``WRR000100`` — the input-validation rejection returned by the bounded
      zero-passenger one-shot of 2026-07-15 (same spec, :391).

    ``WRP011002`` keeps its long-standing independent behaviour: it is treated as
    a failure even when ``strResult`` does not say ``FAIL``, so a server that
    reports the rejection only in ``msgCd`` is still not read as a hold.
    """


class SrtSeatUnavailableError(SrtAppError):
    """The seat-selection page came back as the server's error shell.

    "Retry is pointless for this train; pick another." Live-captured 2026-07-26
    on two trains differing only in availability: the SOLD-OUT one answered
    ``/arc/selectListArc02012_n.do`` with no ``<select id="selectScarNo">``, no
    options and no form — only the page heading and one trailing script::

        srtAlertBoxDivShow("알림", Sr.msgs.error001, null, "historyBack();");

    ``code`` here is the ``messages.js`` KEY of that alert (``"error001"``), NOT
    a ``msgCd``: this response is HTML and carries no ``msgCd`` at all.
    ``messages.js:6`` gives the key its text ("서비스가 접속이 원활하지 않습니다.
    잠시후 다시 시도하여 주시기 바랍니다."), which is the app's generic
    service-busy string, so the shell is strictly "no car is selectable" and
    sold-out is the observed cause rather than a claim the server makes.

    srtgo's non-fatal substring "잔여석없음" is a DIFFERENT signal — a ``msgTxt``
    on a reserve response — and is 0-hit in our bundle. It is not encoded here.
    """


class SrtMutationNotAllowedError(SrtApiError):
    """A state-changing request was attempted without matching consent.

    Raised by ``require_mutation_consent`` when no ``MutationConsent`` is
    supplied, when the supplied object is not a ``MutationConsent``, or when
    the matching per-category ``allow_<category>`` opt-in is False. It fires
    before any request is built or sent, keeping mutations off by default.
    """


class SrtNetFunnelError(SrtApiError):
    """NetFunnel token parsing or acquisition failed.

    ``code`` is whichever code identifies the failure: the queue's own 3-digit
    status for a ``/ts.wseq`` reply (netfunnel.js:84's table), or the app's
    ``msgCd`` when the APP rejects a request for want of a key. Both subclasses
    keep it, so the ``NET000001`` retry gate in
    :class:`~srt_mobile_api.client.SrtClient` is unaffected by the refinement.
    """

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        *,
        raw: object | None = None,
    ) -> None:
        self.code = code
        self.message = redact_url(message or "NetFunnel request failed")
        self.raw = raw
        safe_code = redact_url(str(code or "NETFUNNEL"))
        super().__init__(f"{safe_code}: {self.message}")


class SrtNetFunnelKeyError(SrtNetFunnelError):
    """The app refused the request because its NetFunnel key was missing or stale.

    "A fresh key may work." ``code`` is ``NET000001``, the app-level ``msgCd``
    the search endpoint answers when ``netfunnelKey`` does not satisfy it. This
    is the ONE failure the client already acts on by itself, and the taxonomy
    does not widen that: a search is retried exactly once with a newly acquired
    key (``client.py:_search_with_retry``), and ``reserve`` is never retried,
    because a retried reserve is a duplicate booking.

    srtgo reaches the same rule from the other end, matching the message
    "정상적인 경로로 접근 부탁드립니다" (``srtgo/srtgo.py:721``) and then calling
    ``rail.clear()`` to drop the key. That substring is 0-hit in our bundle, and
    so is ``NET000001`` itself and even the field name ``netfunnelKey`` — the
    bundle's NetFunnel integration is commented out. We keep the code, because a
    code is what our own live traffic and the retained spec record.
    """


class SrtQueueRejectedError(SrtNetFunnelError):
    """The waiting room refused entry outright — not queued, rejected.

    "Retry is pointless right now; this is not a wait." The app has separate
    events for exactly this, distinct from its generic ``onError``, in
    ``_showResultChkEnter`` (``analysis/raw/base/assets/offline/js/common/
    netfunnel.js``)::

        case NetFunnel.kTsBlock:   ... this.fireEvent(null, this, "onBlock",   ...)
        case NetFunnel.kTsIpBlock: ... this.fireEvent(null, this, "onIpBlock", ...)

    with ``kTsBlock=301`` and ``kTsIpBlock=302`` in the code table at
    netfunnel.js:84. A queued reply (``kContinue`` 201/202) is NOT this — that
    one polls, and :func:`~srt_mobile_api.netfunnel.parse_queue_response`
    returns it as a token.

    The IP block here is the QUEUE's, not the edge's; the edge's plain-text ban
    is :class:`SrtIpBlockedError`. The app's own answer to a 302 is to wait
    ``ipblock_wait_time`` and re-acquire up to ``ipblock_wait_count`` times; we
    deliberately do not, for the same reason the queue poll is bounded — a
    library that retries into a block is the traffic shape that earns a longer
    one.
    """


# ---------------------------------------------------------------------------
# msgCd -> exception mapping
#
# CODES, NOT MESSAGE TEXT. The requirement is the app's own: the single place in
# the whole v2.0.41 bundle where a server-supplied string is branched on is
# `resultMap.msgCd == "S111"` (ara1001l.js:1565) -- a CODE. Every other branch is
# `strResult == "FAIL"` (ara1001l.js:206, :234, :1855) or `ErrorCode == -1`
# (ara1001l.js:193, :1840), neither of which discriminates a reason at all. The
# app never substring-matches msgTxt; it only displays it.
#
# So the app itself supplies no reason taxonomy beyond S111, and every entry
# below is a code THIS repository has seen on the wire, mapped to the action a
# caller would take. Anything unmapped stays a plain SrtAppError with its code
# and raw response attached, which is how the map is meant to grow.
#
# WHAT IS DELIBERATELY ABSENT. srtgo classifies four more conditions purely by
# Korean substring (srtgo/srtgo.py:736-744): "잔여석없음",
# "사용자가 많아 접속이 원활하지 않습니다", "예약대기 접수가 마감되었습니다" and
# "예약대기자한도수초과". All four are 0-hit across our bundle, none has a known
# msgCd, and the last two describe 예약대기 (standby), a surface this library
# does not implement. Encoding them would mean adding message matching the app
# does not do, for conditions we cannot verify -- so they are documented as
# srtgo-attested leads instead of guessed at here.
# ---------------------------------------------------------------------------

NO_RESULT_CODES = frozenset({"WRG000000", "WRT300005"})
INVALID_REQUEST_CODES = frozenset({"WRP011002", "WRR000100"})
NETFUNNEL_KEY_REQUIRED_CODE = "NET000001"
SESSION_EXPIRED_CODE = "S111"

_APP_ERROR_BY_CODE: dict[str, type[SrtAppError]] = {
    **{code: SrtNoResultsError for code in NO_RESULT_CODES},
    **{code: SrtInvalidRequestError for code in INVALID_REQUEST_CODES},
}


def classify_app_error(
    code: str | None,
    message: str | None,
    *,
    raw: object | None = None,
) -> SrtAppError:
    """Build the most specific :class:`SrtAppError` the ``msgCd`` justifies.

    Returns rather than raises, so the call site keeps its own ``raise`` and its
    own traceback. An unknown or absent code yields a plain
    :class:`SrtAppError` — the pre-existing behaviour, unchanged — and every
    result carries ``code``/``message``/``raw`` exactly as before.

    ``NET000001`` is not handled here: it is answered by
    :class:`SrtNetFunnelKeyError`, which is not an :class:`SrtAppError`, and it
    is raised at the one call site that has always special-cased it. ``S111`` is
    likewise not handled here — see :class:`SrtSessionExpiredError`.
    """
    subclass = _APP_ERROR_BY_CODE.get(code or "", SrtAppError)
    return subclass(code, message, raw=raw)
