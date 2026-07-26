from __future__ import annotations

import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from .config import SrtConfig
from .consent import (
    MutationConsent,
    MutationPreview,
    require_card_kind_claim,
    require_mutation_consent,
)
from .errors import (
    SrtApiError,
    SrtAuthError,
    SrtNetFunnelError,
    SrtProtocolError,
    SrtSessionExpiredError,
)
from .http import SrtHttpClient
from .models import (
    DiscountCouponList,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    NoticeListResult,
    PassengerCounts,
    SearchPageState,
    SeatDesignation,
    SeatGrid,
    SeatSelectionPage,
    SeatType,
    SrtCancelResult,
    SrtPaymentCard,
    SrtPaymentResult,
    SrtRefundResult,
    SrtRefundTicketInfo,
    SrtReservationHold,
    SrtReservationListResult,
    SrtReservationSummary,
    SrtSession,
    TimetablePage,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
    TransferItinerary,
    TransferSearchResult,
)
from .netfunnel import (
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
from .parsers import (
    parse_card_payment_response,
    parse_discount_coupon_page,
    parse_fare_page,
    parse_html_page,
    parse_mutual_verification_response,
    parse_notice_list_response,
    parse_refund_response,
    parse_refund_ticket_info_response,
    parse_reservation_hold_response,
    parse_reservation_list_response,
    parse_search_has_following_page,
    parse_search_page_state,
    parse_seat_grid_response,
    parse_seat_selection_page,
    pair_transfer_itineraries,
    parse_timetable_page,
    parse_train_search_response,
    parse_unpaid_cancel_response,
)
from .payloads import (
    card_payment_payload,
    date_selector_payload,
    fare_payload,
    group_search_ajax_payload,
    passenger_selector_payload,
    personal_reservation_payload,
    refund_payload,
    reservation_list_payload,
    search_ajax_payload,
    search_continuation_payload,
    search_page_payload,
    seat_grid_payload,
    seat_page_payload,
    seat_option_selector_payload,
    station_map_selector_payload,
    station_selector_payload,
    timetable_payload,
    train_group_selector_payload,
    transfer_reservation_payload,
    unpaid_reservation_cancel_payload,
)
from .safety import COUPON_LIST_PATH
from .session import SrtSessionClient


# The PNR shape accepted into the refund step-1 Referer. ASCII only and bounded;
# see SrtClient.get_refund_ticket_info for why str.isalnum() was not enough.
_REFUND_PNR_RE = re.compile(r"[A-Za-z0-9-]{1,32}")


class SrtClient:
    def __init__(
        self,
        config: SrtConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config or SrtConfig()
        self.http = SrtHttpClient(self.config, transport=transport)
        self.session = SrtSessionClient(self.http)
        self._clock = clock or time.time
        self._sleep = sleep or time.sleep
        # act_10 keys acquired but not yet released with setComplete (5004).
        # A list rather than a single slot because a NetFunnel retry mid-flow
        # can acquire a second key before the first is released, and the point
        # of tracking them is that NONE is left holding a place in line.
        self._netfunnel_slots: list[str] = []

    def close(self) -> None:
        self.http.close()

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        return self.session.login(login_id, password, login_type=login_type)

    def clear_session(self) -> None:
        self.session.clear_session()

    def logout(self) -> None:
        self.clear_session()

    @contextmanager
    def _session_guard(self) -> Iterator[None]:
        try:
            yield
        except SrtSessionExpiredError:
            self.clear_session()
            raise

    def get_main(self) -> HtmlPage:
        with self._session_guard():
            raw = self.http.get_text("/main/main.do", params={"deviceId": self.config.device_key})
            return parse_html_page(raw, context="main page")

    def get_booking_page(self) -> HtmlPage:
        with self._session_guard():
            raw = self.http.get_text("/ara/ara0101v.do")
            return parse_html_page(raw, context="booking page")

    def _get_notice_list_result(self) -> NoticeListResult:
        with self._session_guard():
            return parse_notice_list_response(
                self.http.post_form(
                    "/main/noticeList.do",
                    {"pageId": "MB0101000000"},
                    accept="application/json, text/javascript, */*; q=0.01",
                )
            )

    def get_notice_list(self) -> dict[str, Any]:
        """Return the legacy raw notice mapping without changing its shape."""
        return self._get_notice_list_result().raw

    def get_typed_notice_list(self) -> NoticeListResult:
        """Return the same notice read as frozen typed rows."""
        return self._get_notice_list_result()

    def get_ticket_list(self, page_no: int = 0) -> HtmlPage:
        with self._session_guard():
            raw = self.http.get_text("/atc/selectListAtc14017_n.do", params={"pageNo": str(page_no)})
            return parse_html_page(raw, context="ticket list", require_authenticated=True)

    def get_discount_coupons(self) -> DiscountCouponList:
        """Read the account's 할인쿠폰 (discount coupons).

        ``GET /apa/selectListApa03020_n.do``, no parameters — the app reaches it
        from its own MY SRT menu as
        ``pageMove('/apa/selectListApa03020_n.do')``, and ``pageMove`` is
        ``window.location = url``.

        **The route is 0-hit in the v2.0.41 offline bundle**, which contains no
        ``/apa/`` route at all. It was found by reading a page this client
        already fetches: the MY SRT menu is server-rendered into every
        authenticated page, so ``/ara/ara0101v.do`` names it. That is the same
        technique that opened the seat grid, applied to a menu instead of a
        form.

        **Live-verified 2026-07-26 for an account holding no coupons**: 77,056
        bytes, ``ul.coupList`` present and empty, "보유한 쿠폰이 없습니다." A
        populated list has not been read here; see
        :class:`~srt_mobile_api.models.DiscountCoupon` for exactly what its
        field names rest on.

        **This is a read, and only a read.** The page it returns is also the
        coupon REGISTRATION form, and registering a coupon is a mutation that
        this library does not implement: the registration posts
        ``{dscp_no, dscp_pwd}`` to a different route
        (``/arb/selectListArb02A01_n.do``) which is in neither allowlist, and it
        would belong to no member of
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`. Only ``GET``
        is registered for this path, so a coupon number and its password cannot
        travel here under a read either.
        """
        with self._session_guard():
            return parse_discount_coupon_page(
                self.http.get_text(
                    COUPON_LIST_PATH,
                    referer=f"{self.config.base_url}/ara/ara0101v.do",
                )
            )

    def get_reservations(self, page_no: int = 0) -> SrtReservationListResult:
        """Read the account's 예약/발권 목록 as structured rows.

        This is the only read that ENUMERATES reservations. Without it the sole
        way back to a hold whose PNR was lost is to type the PNR into
        ``scripts/recover_hold.py`` — which requires already knowing it. That is
        why the parser is written to surrender a PNR under almost any shape
        surprise (see
        :func:`~srt_mobile_api.parsers.parse_reservation_list_response`) and why
        ``scripts/recover_hold.py --list`` calls this.

        ``get_ticket_list`` is NOT the same read. It GETs the neighbouring
        ``/atc/selectListAtc14017_n.do`` page and returns HTML; this POSTs
        ``/atc/selectListAtc14016_n.do`` and returns rows. The app reaches the
        16 path too (``SRForegroundDialogActivity.java:31``), just as a WebView
        page rather than as an XHR.

        **Live-verified on 2026-07-26 for an account with no reservations**: the
        server answered ``resultMap[0].strResult="SUCC"`` / ``IRZ000005`` /
        "조회할 자료가 없습니다." with ``trainListMap: []`` and
        ``payListMap: []``, and this returned an empty
        :class:`~srt_mobile_api.models.SrtReservationListResult`. The populated
        shape is UNVERIFIED here and its row field names come from srtgo
        (``srt.py:1069-1082``), not from our bundle.

        ``page_no`` goes on the wire as ``pageNo``; the result's
        ``total_page_count`` (``totPageCnt``) says how many pages exist.
        """
        with self._session_guard():
            return parse_reservation_list_response(
                self.http.post_form(
                    "/atc/selectListAtc14016_n.do",
                    reservation_list_payload(page_no),
                    accept="application/json, text/javascript, */*; q=0.01",
                    referer=f"{self.config.base_url}/main/main.do",
                )
            )

    def _get_selector_page(
        self,
        path: str,
        payload: dict[str, str],
        *,
        context: str,
    ) -> HtmlPage:
        raw = self.http.post_html_form(
            path,
            payload,
            referer=f"{self.config.base_url}/ara/ara0101v.do",
        )
        return parse_html_page(raw, context=context, require_authenticated=True)

    def get_station_selector(
        self,
        departure_name: str,
        arrival_name: str,
        departure_code: str,
        arrival_code: str,
    ) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0501P/view.do",
                station_selector_payload(departure_name, arrival_name, departure_code, arrival_code),
                context="station selector",
            )

    def get_station_map_selector(self) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0502P/view.do",
                station_map_selector_payload(),
                context="station map selector",
            )

    def get_date_selector(self, date: str) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0401P/view.do",
                date_selector_payload(date),
                context="date selector",
            )

    def get_passenger_selector(self, passengers: PassengerCounts) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0901P/view.do",
                passenger_selector_payload(passengers),
                context="passenger selector",
            )

    def get_seat_option_selector(
        self,
        *,
        request_seat_attr_code: str = "015",
        location_seat_attr_code: str = "000",
        seat_name: str = "일반/기본",
    ) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0701P/view.do",
                seat_option_selector_payload(
                    request_seat_attr_code,
                    location_seat_attr_code,
                    seat_name,
                ),
                context="seat option selector",
            )

    def get_train_group_selector(
        self,
        train_group_code: str = "109",
        train_group_name: str = "전체",
    ) -> HtmlPage:
        with self._session_guard():
            return self._get_selector_page(
                "/common/ARA/ARA0201V/view.do",
                train_group_selector_payload(train_group_code, train_group_name),
                context="train group selector",
            )

    def get_mutual_verification(self) -> MutualVerificationResult:
        with self._session_guard():
            data = self.http.post_form(
                "/ara/selectListAra10130_n.do",
                {},
                accept="application/json, text/javascript, */*; q=0.01",
                referer=(
                    f"{self.config.base_url}"
                    "/ara/selectListAra10007_n.do"
                ),
            )
            return parse_mutual_verification_response(data)

    def _netfunnel_get(self, url: str, referer: str) -> str:
        return self.http.get_text_url(url, referer=referer)

    def _get_act10_key(self, referer: str) -> str:
        """Acquire an ``act_10`` queue key, WAITING if the queue engages.

        Sends ``getTidChkEnter`` (5101) once. A pass (200, or a 300 bypass that
        carries no key) returns immediately, which is what happens at normal
        load and is the only outcome this repository has ever observed live.

        A 201/202 means we are actually in line, and the app's answer to that is
        to poll ``chkEnter`` (5002) until admitted
        (``_showResultChkEnter`` arms ``setTimeout(chkEnterCont, ttl * 1000)``).
        Before this, we simply failed there and the search died of a queue that
        was working as designed.

        The loop is BOUNDED, unlike the app's. The app polls forever behind a
        wait popup a human can close; a library has no such escape hatch, so
        both a poll count (:data:`~srt_mobile_api.netfunnel.QUEUE_POLL_LIMIT`)
        and a wall-clock budget
        (:data:`~srt_mobile_api.netfunnel.QUEUE_WAIT_LIMIT_SECONDS`) cap it, and
        whichever is reached first raises :class:`SrtNetFunnelError` rather than
        waiting on. Each wait is the server's own ``ttl``, clamped to the app's
        1..5s (``TS_MAX_TTL``), so this cannot become a tight retry loop — which
        matters, because tight retries against a queue are exactly the traffic
        shape that earns an IP block.

        Every acquired key is recorded so it can be released with ``setComplete``
        once the guarded request is done; see :meth:`_release_netfunnel_slots`.

        **Live status: the polling path is OFFLINE-TESTED ONLY.** At normal load
        the SRT queue does not engage, so no run of this code has seen a 201,
        and load was deliberately not synthesised to force one.
        """
        body = self._netfunnel_get(
            build_act10_url(
                self.config.netfunnel_url,
                timestamp_ms=int(self._clock() * 1000),
            ),
            referer,
        )
        token = parse_queue_response(body, action="act_10")
        key = token.key
        deadline = self._clock() + QUEUE_WAIT_LIMIT_SECONDS
        polls = 0
        while is_queued(token):
            if polls >= QUEUE_POLL_LIMIT or self._clock() >= deadline:
                raise SrtNetFunnelError(
                    token.code,
                    "NetFunnel queue did not admit us within the bounded wait",
                )
            wait = queue_wait_seconds(token)
            self._sleep(wait)
            polls += 1
            # The key to poll with is the one the queue last echoed
            # (chkEnterCont(retval.getValue("key"))); a 201 that omits it leaves
            # the previously held key in place rather than aborting.
            key = token.key or key
            if not key:
                raise SrtNetFunnelError(
                    token.code,
                    "NetFunnel queued us without ever issuing a key to poll with",
                )
            body = self._netfunnel_get(
                build_chk_enter_url(
                    self.config.netfunnel_url,
                    key=key,
                    timestamp_ms=int(self._clock() * 1000),
                    ttl=wait,
                ),
                referer,
            )
            token = parse_queue_response(body, action="act_10")
            key = token.key or key
        if key:
            self._netfunnel_slots.append(key)
        return key

    def _release_netfunnel_slots(self, referer: str) -> None:
        """Send ``setComplete`` (5004) for every key we still hold. Best effort.

        Without this our place in line is held until it times out, and at peak
        load that is queue pollution we caused. ``TS_AUTO_COMPLETE = true`` in
        the bundle's own config, so the app releases automatically too.

        Deliberately swallows everything. A release is housekeeping that happens
        AFTER the caller's real request has already succeeded or failed on its
        own terms; letting a failed release replace that outcome would mean a
        successful search reported as an error because we could not tidy up. It
        is also unbounded-retry-free by construction: each key is popped before
        it is sent, so a failure drops the key rather than queueing another
        attempt.
        """
        while self._netfunnel_slots:
            key = self._netfunnel_slots.pop()
            try:
                body = self._netfunnel_get(
                    build_set_complete_url(
                        self.config.netfunnel_url,
                        key=key,
                        timestamp_ms=int(self._clock() * 1000),
                    ),
                    referer,
                )
                parse_set_complete_response(body, action="act_10")
            except (SrtApiError, ValueError):
                continue

    def _hydrate_search(
        self,
        query: TrainSearchQuery,
        key: str,
        *,
        transfer: bool = False,
    ) -> SearchPageState:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        html = self.http.get_text(
            "/ara/selectListAra10007_n.do",
            params=search_page_payload(query, key, transfer=transfer),
            referer=referer,
        )
        return parse_search_page_state(html)

    def _prepare_search(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> tuple[str, dict[str, str]]:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        key = self._get_act10_key(referer)
        state = self._hydrate_search(query, key, transfer=transfer)
        # The URL is chosen by grpDv ALONE (ara1001l.js:174-181). 직통 and 환승
        # share it -- the connection type travels in chtnDvCd, not in the path.
        path = "/ara/selectListAra10082_n.do" if group else "/ara/selectListAra10007_n.do"
        payload = (
            group_search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
            if group
            else search_ajax_payload(
                query, key, hydrated_fields=state.hidden_fields, transfer=transfer
            )
        )
        return path, payload

    def _post_search_page(
        self,
        path: str,
        payload: dict[str, str],
    ) -> TrainSearchResult:
        data = self.http.post_form(
            path,
            payload,
            accept="application/json, text/javascript, */*; q=0.01",
            referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
        )
        return parse_train_search_response(data, request_context=payload)

    def _search_once(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> TrainSearchResult:
        # The slot is released once the guarded request is over, whichever way
        # it went -- a search that raised held a place in line just as much as
        # one that succeeded. This is the app's TS_AUTO_COMPLETE behaviour.
        try:
            path, payload = self._prepare_search(query, group=group, transfer=transfer)
            return self._post_search_page(path, payload)
        finally:
            self._release_netfunnel_slots(
                f"{self.config.base_url}/ara/ara0101v.do"
            )

    def _search_with_retry(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        transfer: bool = False,
    ) -> TrainSearchResult:
        for attempt in range(2):
            try:
                return self._search_once(query, group=group, transfer=transfer)
            except SrtNetFunnelError as exc:
                if exc.code != "NET000001" or attempt == 1:
                    raise
        raise AssertionError("unreachable NetFunnel retry state")

    def search_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        with self._session_guard():
            return self._search_with_retry(query, group=False)

    def search_group_trains(self, query: TrainSearchQuery) -> TrainSearchResult:
        with self._session_guard():
            return self._search_with_retry(query, group=True)

    def search_transfer_trains(self, query: TrainSearchQuery) -> TransferSearchResult:
        """Search 환승 (transfer) itineraries — trains that need a connection.

        A SIBLING METHOD rather than a ``transfer=True`` flag on
        :meth:`search_trains`, and the reason is not the request. The request is
        nearly the same: the endpoint is unchanged
        (``/ara/selectListAra10007_n.do``, chosen by ``grpDv`` alone at
        ``ara1001l.js:174-181``) and the only body delta is ``chtnDvCd`` ``"1"``
        -> ``"2"``, derived by the app from ``jrnyTpCd`` at ``ara1001l.js:98``
        and sent at ``:159``. The hydration GET additionally carries
        ``jrnyTpCd="14"``/``jrnyCnt="2"``, the app's 환승 toggle
        (``ara0101v.js:302-303``).

        The reason is the RESULT. A row from here is **half an itinerary**, and
        nothing about the row says so: it is an ordinary
        :class:`~srt_mobile_api.models.TrainSummary` that
        :meth:`reserve` would accept and book on its own, leaving the traveller
        holding a ticket to the 환승역 and no further. Making that a keyword on
        the method everyone already calls would put the dangerous rows and the
        safe ones behind the same name and the same type. A separate name is the
        signal, and :class:`~srt_mobile_api.models.TransferItinerary` plus
        :meth:`reserve_transfer` is the enforcement — see there.

        **The response shape is LIVE-CONFIRMED (2026-07-26)**, and it is ONE ROW
        PER LEG. The bundle could not have said so — ``fn_postSearch``
        (``ara1001l.js:384-460``) renders one single-leg ``<tr>`` per row with no
        transfer branch, ``fn_moveRsv`` (``:1453-1468``) writes only slot 1, and
        the 환승 list itself is server-rendered (the stylesheet keeps its taller
        two-row card with a layover band, ``custom.css:4412``, ``:4431``). A
        read-only probe of 동대구(0015) -> 광주송정(0036) settled it: 10 ordinary
        ``dsOutput1`` rows, every one carrying ``chtnDvCd="2"``, with the legs of
        one itinerary sharing a ``trnOrdrNo``::

            trnOrdrNo=1   trn 382  동대구->오송        085200->095100
            trnOrdrNo=1   trn 411  오송->광주송정      100600->110500
            trnOrdrNo=2   trn 14   동대구->천안아산    085800->100900
            trnOrdrNo=2   trn 475  천안아산->광주송정  102500->125000

        The ``...2`` columns DO exist on every row and are empty strings
        (``trnNo2: ""``, ``dptRsStnCd2: ""``, ``jrnySqno: ""``) — because the
        second leg is a separate ROW, not a set of columns. ``fllwPgExt2`` was
        ``null``.

        So this returns a
        :class:`~srt_mobile_api.models.TransferSearchResult`: the paired
        ``itineraries``, the ``unpaired`` groups that did not fit with a reason
        each, and ``search`` — the untouched
        :class:`~srt_mobile_api.models.TrainSearchResult` — because the grouping
        is OUR inference and a caller has to be able to get behind it. See
        :func:`~srt_mobile_api.parsers.pair_transfer_itineraries` for the rule
        and for why a group that does not fit is set aside rather than dropped
        or forced.

        Each itinerary is ready for :meth:`reserve_transfer` as it stands: the
        pairing runs :class:`~srt_mobile_api.models.TransferItinerary`'s own
        validation, so anything you get back connects and runs forwards.

        ``iter_train_search_pages`` is still deliberately NOT extended to
        transfer. ``dsOutput0`` carries a second cursor ``fllwPgExt2``, and the
        live transfer probe returned it ``null`` just as every direct search
        does — so what it is FOR remains unobserved, and nothing in the bundle
        reads it. Paging a two-cursor list on a guess would walk the wrong leg.

        The rows still go through the SAME row parser as a direct search, so a
        differently shaped row (a missing ``trnNo``) raises
        :class:`~srt_mobile_api.errors.SrtProtocolError` rather than being
        coerced. So does a response whose rows exist but pair into nothing —
        that would mean this grouping rule is wrong for the response in hand,
        and an empty list would be the one genuinely silent failure available.
        Both carry ``raw``.

        Read-only and consent-free like the other searches. Note that the
        REQUEST is what remains partly unverified for transfer: see
        :meth:`reserve_transfer`. And note the natural way to reach this method
        — a direct search of a pair SRT does not serve answers ``WRD000061``,
        which this library raises as
        :class:`~srt_mobile_api.errors.SrtNoDirectTrainError`.
        """
        with self._session_guard():
            return pair_transfer_itineraries(
                self._search_with_retry(query, group=False, transfer=True)
            )

    def _prepare_first_search_page(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
    ) -> tuple[TrainSearchResult, str, dict[str, str]]:
        for attempt in range(2):
            path, payload = self._prepare_search(query, group=group)
            try:
                return self._post_search_page(path, payload), path, payload
            except SrtNetFunnelError as exc:
                if exc.code != "NET000001" or attempt == 1:
                    raise
        raise AssertionError("unreachable NetFunnel retry state")

    def _iter_train_search_pages(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        max_pages: int,
    ) -> Iterator[TrainSearchResult]:
        # The whole walk is ONE guarded interaction, so the slot is released
        # when the walk ends -- normally, by exception, or by a caller
        # abandoning the generator (GeneratorExit runs this finally too). It is
        # deliberately not released after the first page: continuation pages
        # reuse the same key, and completing it mid-walk would be the app
        # calling setComplete while still on the guarded screen.
        try:
            yield from self._paginate_train_search(
                query, group=group, max_pages=max_pages
            )
        finally:
            self._release_netfunnel_slots(
                f"{self.config.base_url}/ara/ara0101v.do"
            )

    def _paginate_train_search(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
        max_pages: int,
    ) -> Iterator[TrainSearchResult]:
        with self._session_guard():
            page, path, payload = self._prepare_first_search_page(query, group=group)
            prior_cursor = payload["dptTm"]
            seen_cursors = {prior_cursor}
            yielded_pages = 0

            while True:
                has_following_page = parse_search_has_following_page(page.raw)
                page_is_empty = not page.trains
                last_departure_time = (
                    None if page_is_empty else page.trains[-1].departure_time
                )
                yield page
                yielded_pages += 1
                if (
                    yielded_pages >= max_pages
                    or not has_following_page
                    or page_is_empty
                ):
                    return

                try:
                    continuation_payload = search_continuation_payload(
                        payload,
                        last_departure_time,
                    )
                except ValueError as exc:
                    raise SrtProtocolError(
                        "SRT paginated search last_departure_time must be six ASCII digits"
                    ) from exc
                cursor = continuation_payload["dptTm"]
                if cursor in seen_cursors:
                    raise SrtProtocolError(
                        "SRT paginated search produced a repeated cursor"
                    )
                if cursor <= prior_cursor:
                    raise SrtProtocolError(
                        "SRT paginated search cursor did not make forward progress"
                    )

                try:
                    next_page = self._post_search_page(path, continuation_payload)
                except SrtNetFunnelError as exc:
                    if exc.code != "NET000001":
                        raise
                    refreshed_path, refreshed_payload = self._prepare_search(
                        query,
                        group=group,
                    )
                    continuation_payload = search_continuation_payload(
                        refreshed_payload,
                        last_departure_time,
                    )
                    next_page = self._post_search_page(
                        refreshed_path,
                        continuation_payload,
                    )
                    path = refreshed_path

                seen_cursors.add(cursor)
                prior_cursor = cursor
                payload = continuation_payload
                page = next_page

    def iter_train_search_pages(
        self,
        query: TrainSearchQuery,
        *,
        group: bool = False,
        max_pages: int = 10,
    ) -> Iterator[TrainSearchResult]:
        if type(max_pages) is not int or max_pages <= 0:
            raise ValueError("max_pages must be a positive non-boolean integer")
        return self._iter_train_search_pages(
            query,
            group=group,
            max_pages=max_pages,
        )

    def get_seat_page(
        self,
        train: TrainSummary,
        cabin_class: str = "1",
        seat_count: str | None = None,
        *,
        passengers: PassengerCounts | None = None,
        seat_attr_code: str = "015",
    ) -> SeatSelectionPage:
        """Read the seat-selection page for one complete server-returned SRT row.

        ``choiceSeatCount`` is the PARTY SIZE, not a constant: the app sends
        ``choiceSeatCount: lfn_getRsv("totPrnb")`` (``ara1001l.js:1511``), and
        ``totPrnb`` is the passenger total the booking screen collected
        (``ara0101v.js:794``/``:809``, ``getPsgTotCnt()``). So pass
        ``passengers`` and the count is derived from it. ``seat_count`` remains
        available as an explicit override for a caller who wants a specific
        count without constructing a
        :class:`~srt_mobile_api.models.PassengerCounts`; it wins when both are
        given. With neither, the count falls back to ``"1"`` — the same single
        traveller ``PassengerCounts()`` itself defaults to.
        """
        if seat_count is None:
            seat_count = str((passengers or PassengerCounts()).total)
        with self._session_guard():
            raw = self.http.post_html_form(
                "/arc/selectListArc02012_n.do",
                seat_page_payload(
                    train, cabin_class, seat_count, seat_attr_code=seat_attr_code
                ),
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )
            return parse_seat_selection_page(raw)

    def get_seat_grid(
        self,
        train: TrainSummary,
        car_number: str,
        cabin_class: str = "1",
        seat_count: str | None = None,
        *,
        passengers: PassengerCounts | None = None,
        seat_attr_code: str = "015",
    ) -> SeatGrid:
        """Read one 호차's 좌석배치도 — the second half of the seat-selection read.

        :meth:`get_seat_page` answers "which cars have seats"; this answers
        "which seats, and are they pickable". Together they are what the app
        does when a passenger opens 좌석선택 and taps a 호차: the page's inline
        script sets ``scarNo``, serialises ``#trnScarSeatFrm`` and POSTs it to
        ``/arc/selectListArc02011_n.do`` as HTML.

        **LIVE-CONFIRMED 2026-07-26.** 수서 -> 동탄 (0551 -> 0552), 20260812,
        train 315: the request below returned 25,930 bytes containing 74 seat
        cells. Both this route and ``trnScarSeatFrm`` are 0-hit in the v2.0.41
        offline bundle — they exist only in what the server renders — which is
        why this was believed for months to need a traffic capture. It did not;
        the pages are served to our own authenticated session.

        ``car_number`` is a value from :attr:`SeatSelectionPage.cars`
        (``SeatCarOption.car_number``), not a guess: asking for a car the train
        does not have is a wasted request at best.

        Pass the same ``passengers`` the search and :meth:`get_seat_page` used —
        ``choiceSeatCount`` is the party size on this form too — and the same
        ``cabin_class``. ``seat_count`` remains the explicit override, with
        ``"1"`` as the fallback, exactly as on :meth:`get_seat_page`.

        **The train number is zero-padded to five characters** and that is the
        entire difference between a seat grid and a 147-byte alert shell; see
        :data:`~srt_mobile_api.payloads.SEAT_TRAIN_NUMBER_LENGTH`. The shell's
        text mentions seats being auto-assigned 20 minutes before departure,
        which reads like a timing rule and is not one.

        A refusal (``"0#<message>"``) raises
        :class:`~srt_mobile_api.errors.SrtSeatUnavailableError`, not a protocol
        error — see :func:`~srt_mobile_api.parsers.parse_seat_grid_response`.
        """
        if seat_count is None:
            seat_count = str((passengers or PassengerCounts()).total)
        with self._session_guard():
            raw = self.http.post_html_form(
                "/arc/selectListArc02011_n.do",
                seat_grid_payload(
                    train,
                    car_number,
                    cabin_class,
                    seat_count,
                    seat_attr_code=seat_attr_code,
                ),
                # The seat page is where this form lives, so it is the page the
                # app would be on. The 2026-07-26 capture established that the
                # server does not care -- the grid came back with and without a
                # Referer -- so this is the app's flow rather than a requirement.
                referer=f"{self.config.base_url}/arc/selectListArc02012_n.do",
            )
            return parse_seat_grid_response(raw, car_number=car_number)

    def get_timetable(self, train: TrainSummary) -> TimetablePage:
        with self._session_guard():
            raw = self.http.post_form(
                "/ara/selectListAra12009_n.do",
                timetable_payload(train),
                accept="text/html, */*; q=0.01",
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )["html"]
            return parse_timetable_page(raw)

    def get_fare(
        self,
        train: TrainSummary,
        passengers: PassengerCounts | None = None,
    ) -> FarePage:
        with self._session_guard():
            raw = self.http.post_form(
                "/ara/selectListAra13010_n.do",
                fare_payload(train, passengers or PassengerCounts()),
                accept="text/html, */*; q=0.01",
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )["html"]
            return parse_fare_page(raw)

    def _submit_reservation(
        self,
        route: str,
        build_form: Callable[[str], dict[str, str]],
        *,
        consent: MutationConsent,
        netfunnel_key: str | None,
    ) -> MutationPreview | SrtReservationHold:
        """The one reservation send path, shared by :meth:`reserve` and :meth:`reserve_transfer`.

        Extracted rather than copied because every safety property of a
        reservation lives here — the consent gate, the session requirement, the
        no-I/O dry run, the single NetFunnel acquisition, the guaranteed slot
        release, the never-retry rule, and the PNR-salvaging parse. A second
        body deserves a second builder, not a second copy of that list; the app
        itself keeps one ``#rsvForm`` for every reservation shape.
        ``build_form`` is called with the NetFunnel key exactly once, and only
        after the key exists, so no form is ever built twice or sent twice.

        ``route`` stays a parameter even though both callers now pass the same
        URL: it keeps each public method's target visible where that method is
        defined, which is the pairing
        :data:`~srt_mobile_api.safety.SRT_MUTATION_ROUTE_CATEGORIES` re-checks at
        the send boundary.
        """
        require_mutation_consent(consent, "reserve")
        if self.session.current is None:
            raise SrtAuthError("SRT reservation requires an authenticated session")
        if consent.dry_run:
            # Built inside the dry-run branch with the caller's key (or none):
            # a preview must not acquire anything, so it performs no I/O at all.
            return MutationPreview(
                category="reserve",
                method="POST",
                route=route,
                payload=build_form(netfunnel_key or ""),
            )
        # The booking page is the referer search uses for its own act_10
        # acquisition (_prepare_search), and reserve gates on the same key, so
        # the same referer is used rather than inventing a second one.
        booking_referer = f"{self.config.base_url}/ara/ara0101v.do"
        with self._session_guard():
            key = (
                netfunnel_key
                if netfunnel_key
                else self._get_act10_key(booking_referer)
            )
            form = build_form(key)
            try:
                response = self.http.post_mutation_form(
                    route,
                    form,
                    consent=consent,
                    category="reserve",
                    # The app reserves from the search-result page
                    # (ara1001l.js:1541-1560), which is the referer every other
                    # post-search read here sends. INFERRED from the app flow,
                    # not captured from the wire.
                    referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
                )
            finally:
                # Release the queue slot once the reserve is over. Best effort
                # and exception-swallowing by construction (see
                # _release_netfunnel_slots), which matters most HERE: a hold may
                # already exist on the server by this point, and a failed
                # housekeeping call must never be what the caller sees instead
                # of the PNR. A caller-supplied netfunnel_key was not acquired
                # by us and so is not in _netfunnel_slots to release -- whoever
                # obtained it owns completing it.
                self._release_netfunnel_slots(booking_referer)
            # From here a hold may EXIST on the server. parse_reservation_hold_
            # response is the designed guard: it salvages a minimal hold from a
            # PNR-bearing response rather than letting a strict-validation
            # failure orphan it, and refuses to manufacture one when the server
            # declared a failure.
            return parse_reservation_hold_response(response)

    def reserve(
        self,
        train: TrainSummary,
        *,
        consent: MutationConsent,
        passengers: PassengerCounts | None = None,
        seat_type: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
        netfunnel_key: str | None = None,
        standby: bool = False,
        round_trip: bool = False,
        designated_seats: SeatDesignation | None = None,
    ) -> MutationPreview | SrtReservationHold:
        """Create a personal (개인예약) SRT reservation hold under explicit consent.

        Gated by ``require_mutation_consent(consent, "reserve")``: a default
        :class:`~srt_mobile_api.consent.MutationConsent` (``allow_reserve=False``)
        or ``None`` is denied with
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` before
        anything is built. Requires an authenticated session.

        With the default ``dry_run=True`` it validates ``train``/``passengers``
        and returns a :class:`~srt_mobile_api.consent.MutationPreview` of the
        exact form that WOULD be POSTed (mirroring srtgo ``_reserve``),
        performing NO network I/O — the NetFunnel key is left as the
        caller-supplied ``netfunnel_key`` (or empty) and is redacted in the
        preview.

        With ``dry_run=False`` it **transmits**, and a success creates a real
        unpaid hold on a real account. It acquires a NetFunnel key, POSTs
        ``/arc/selectListArc05013_n.do`` through
        :meth:`~srt_mobile_api.http.SrtHttpClient.post_mutation_form` with
        ``category="reserve"``, and returns the parsed
        :class:`~srt_mobile_api.models.SrtReservationHold`, whose ``pnr_no``
        feeds :meth:`cancel`. **The caller owns that hold** and is responsible
        for cancelling or paying it.

        The NetFunnel gate is the SAME ``act_10`` key flow as train search
        (srtgo ``srt.py:987``; NOT ``act_19``), so this reuses
        :meth:`_get_act10_key` rather than introducing a second acquisition
        path. A caller-supplied ``netfunnel_key`` is honoured verbatim and
        suppresses the acquisition, which is what lets an operator reuse a key
        already obtained for the search that chose ``train``.

        **Live-verified once, on 2026-07-25.** One operator-run round trip
        (``scripts/verify_reserve_cancel_roundtrip.py``) reserved and then
        cancelled a real hold against the real server: this method returned
        ``strResult='SUCC'`` with ``msgCd='IRR000018'`` and a PNR, so the
        ``act_10`` key flow above and the referer below were both accepted. That
        run also confirmed :meth:`cancel` (``msgCd='IRG000000'``), so a hold
        created here can in fact be released.

        What that single run does NOT cover: one adult, one journey, general
        seat, one train. Multi-passenger, multi-leg and standby (``jobId=1102``)
        reservations were not exercised. A live call still creates a real unpaid
        hold on a real account, so keep the PNR —
        ``scripts/recover_hold.py`` releases one from the PNR string alone.

        Losing a PNR is the worst outcome this method can produce, so it is
        designed against: ``parse_reservation_hold_response`` salvages a minimal
        but cancelable hold when strict parsing trips over an unrelated
        malformed field, and a failed reserve is never retried — a retry could
        double-book — so at most one hold can exist per call.

        **standby** (``jobId=1102``, 예약대기) puts the party on the waitlist for
        a train whose general cabin is full but whose search row offers 예약대기.
        Bundle-evidenced (``ara0101v.js:90`` names the job type,
        ``ara1001l.js:1445-1448`` chooses it), NOT live-verified. It is opt-in
        rather than derived from the row on purpose: deriving would silently
        change what an existing caller's ``reserve(train)`` sends the first time
        they pass a full train, and a waitlist entry is not the thing they asked
        for. ``ValueError`` if the row says the train is not 예약대기 — see
        :func:`~srt_mobile_api.payloads._refuse_ineligible_standby`, including
        why a row with no such column is accepted rather than refused. srtgo
        additionally POSTs ``/ata/selectListAta01135_n.do`` afterwards to set
        SMS/seat-change options (srt.py:1014-1051); that route is 0-hit in our
        v2.0.41 bundle and has no equivalent in it, so it is NOT implemented and
        a standby entry made here simply carries the server's defaults.

        **round_trip** (``rtnDv=1``, 왕복) is deliberately NOT a second network
        call. SRT models a round trip as 오는열차: the app reserves the outbound
        leg, then re-searches with the stations swapped and the return date, then
        reserves the return leg as a SECOND POST to this same endpoint
        (``ara1001l.js:1580-1596``). So the sequence is two ``reserve`` calls,
        both with ``round_trip=True``:

        1. ``reserve(outbound, round_trip=True, consent=…)`` → hold A
        2. search the return leg — ``TrainSearchQuery.for_return_leg`` builds the
           swapped query for you — then
           ``reserve(inbound, round_trip=True, consent=…)`` → hold B

        Keeping it two calls preserves the property this method is built around:
        one call can create at most one hold, so a failure can strand at most
        one. The caller owns BOTH PNRs and must cancel both. ``jrnyCnt`` stays
        ``"1"`` on each — see
        :func:`~srt_mobile_api.payloads.personal_reservation_payload` for why
        ``jrnyCnt="2"`` means 환승 and not 왕복. Whether the server links the two
        holds (the app carries the outbound result forward in ``go_baseDsXml`` /
        ``go_seatDsXml``, ``ara0101v.js:143-144``, which is not reproducible from
        a search row) is UNVERIFIED; treat them as two independent holds until a
        live run says otherwise.

        **designated_seats** (좌석지정, ``jobId=1103``) reserves NAMED seats
        instead of letting the server assign them. Build it from a grid this
        library read:

        1. ``page = get_seat_page(train, passengers=party)`` → the cars,
        2. ``grid = get_seat_grid(train, page.cars[0].car_number,
           passengers=party)`` → the seats, **live-confirmed 2026-07-26**,
        3. ``grid.choose("1B", "2C")`` → a
           :class:`~srt_mobile_api.models.SeatDesignation`,
        4. ``reserve(train, passengers=party, designated_seats=…, consent=…)``.

        The count must equal the party size and every seat must have been marked
        selectable; both are refused before anything is built, and the second is
        unrepresentable by the time it gets here because
        :class:`~srt_mobile_api.models.SeatDesignation` will not hold an ``N``
        seat.

        **What this rests on, in three tiers, because they are not the same.**

        * *Live-confirmed (2026-07-26)*: the seat grid read that produces the
          seats, including the five-character zero-padding that gates it.
        * *Bundle-evidenced*: the form's seat fields and their values —
          ``seatNo1_1..N`` from the PRINTED labels, ``scarGridcnt1``,
          ``scarGridcnt2="0"``, ``scarNo1``, ``scarNo2=""``
          (``ara0101v.js:866-882``) — and ``jobId=1103`` itself
          (``ara1001l.js:1435-1436``).
        * *INFERRED, and the one thing an operator must settle*: that this body
          goes to ``/arc/selectListArc05013_n.do`` at all. The app's seat
          callback ends in ``fn_submit()``, whose definition is in the
          server-rendered booking page and not in the bundle; the endpoint here
          comes from the commented-out ``//Sr.ara1001l.fn_callReserv();`` on the
          next line, that being the function which POSTs the personal
          reservation. **Fetch ``/ara/ara0101v.do`` and read its inline
          ``fn_submit`` before trusting this**, the same technique that opened
          the seat grid — a WebView shell hides its logic from the APK, not from
          an authenticated HTTP client. If ``fn_submit`` targets something else,
          this method is aiming a valid body at the wrong URL.

        Nothing was added to
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` or to
        :data:`~srt_mobile_api.safety.SRT_MUTATION_ROUTES`: a designated
        reservation is the same operation on the same route under the same
        ``reserve`` consent. It does not compose with ``standby`` (a different
        ``jobId``) or ``round_trip`` (the 왕복 seat callback writes no seat
        fields at all, so its body is unevidenced), and both combinations raise
        ``ValueError`` before anything is built. It is not offered on
        :meth:`reserve_transfer` at all — 좌석지정 blanks the transfer's slot 2.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            lambda key: personal_reservation_payload(
                train,
                passengers or PassengerCounts(),
                seat_type=seat_type,
                netfunnel_key=key,
                window_seat=window_seat,
                standby=standby,
                round_trip=round_trip,
                designated_seats=designated_seats,
            ),
            consent=consent,
            netfunnel_key=netfunnel_key,
        )

    def reserve_transfer(
        self,
        itinerary: TransferItinerary,
        *,
        consent: MutationConsent,
        passengers: PassengerCounts | None = None,
        seat_type: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
        netfunnel_key: str | None = None,
    ) -> MutationPreview | SrtReservationHold:
        """Create a 환승 (transfer) reservation hold: BOTH legs, in ONE request.

        This is the shape SRT reserves as a multi-leg body, and the only one.
        The 환승 toggle sets ``jrnyTpCd="14"`` (환승편도) together with
        ``jrnyCnt="2"`` (``ara0101v.js:302-303``), and ``jrnyCnt="2"`` is written
        nowhere else in the v2.0.41 bundle. Compare :meth:`reserve` with
        ``round_trip=True``, which is the opposite: 왕복 is TWO reservations of
        one journey each, and ``jrnyCnt`` stays ``"1"`` for both.

        **The same endpoint and the same consent category as :meth:`reserve`.**
        ``/arc/selectListArc05013_n.do``, ``category="reserve"``. Nothing was
        added to :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` and
        no new mutation route was registered — a transfer is a personal
        reservation with a second journey slot, not a new kind of mutation. The
        app switches the reservation endpoint on ``grpDv`` alone
        (``ara1001l.js:1542-1547``), and 환승 never touches ``grpDv``, so the
        transfer body goes where a personal one does.

        Everything :meth:`reserve` guarantees is inherited unchanged, because
        this goes through the same ``_submit_reservation``: consent-gated,
        session-required, ``dry_run=True`` by default with NO network I/O, one
        NetFunnel acquisition, guaranteed slot release, never retried, and the
        PNR-salvaging parse. One call can still create at most ONE hold — which
        is the whole point of putting both legs in it.

        **Why the parameter is a :class:`~srt_mobile_api.models.TransferItinerary`
        and not two trains.** Two positional ``TrainSummary`` arguments would
        make it possible to pass the same row twice, to pass legs that do not
        meet, or to pass them in the wrong order, and every one of those failures
        is silent — it produces a plausible form and a real hold. The itinerary
        type validates the join at construction (the first leg must arrive where
        the second departs, and not after it departs), so a malformed pair cannot
        reach this method. The app says the rule in its own words, in a message
        string it ships and never uses because the screen that would raise it is
        server-rendered (``messages.js:217``, ``rsv023``):

            선택하신 열차는 선행 및 후행 열차를 모두 선택하셔야 예약이 가능합니다.

        **What does NOT compose, and why** — the full reasoning is in
        :func:`~srt_mobile_api.payloads.transfer_reservation_payload`, in
        summary: no ``round_trip`` (환승+왕복 is refused by the app in both
        directions, ``ara0101v.js:296-299`` and ``:331-334``), no ``standby``
        (``jobId=1102`` comes from ONE row's image and a transfer has two, so the
        app has no rule to copy), no group (단체환승 is a real SRT product but
        this library does not book 단체 at all — see
        docs/IMPLEMENTATION_PROGRESS.md, "단체 (group) booking: removed"), no
        seat selection (좌석지정 blanks the slot-2 car and seat,
        ``ara0101v.js:875-879``).
        ``passengers``, ``seat_type`` and ``window_seat`` DO apply — once, to
        both legs, because the app's seat-option callback writes slot 1 and slot
        2 from the same values (``ara0101v.js:769-778``) and passengers are
        indexed by type rather than by leg.

        **NOT LIVE-VERIFIED — read this before sending one.** No transfer search
        or reservation has ever been sent from this library. Two specific things
        an operator should expect to have to settle:

        1. Five slot-2 key NAMES (``stlbTrnClsfCd2``, ``dptStnConsOrdr2``,
           ``arvStnConsOrdr2``, ``dptStnRunOrdr2``, ``arvStnRunOrdr2``) are
           inferred from slot 1's names; the server-rendered ``#rsvForm`` is not
           in the bundle. See
           :data:`~srt_mobile_api.payloads.TRANSFER_SLOT2_FIELD_EVIDENCE` for the
           per-key tier.
        2. ``reserveType`` is sent as ``"11"``, the same value :meth:`reserve`
           sends. It is srtgo-only (0 hits in our bundle, ``srt.py:990-991``) and
           it is NOT known whether it tracks ``jrnyTpCd`` — if it does, a
           transfer would want ``"14"``. It is left at ``"11"`` rather than
           guessed; if the server rejects the body, that is the first field to
           try.

        **Cancelling one takes a different argument.** :meth:`cancel` defaults to
        ``jrnyCnt="1"``; a transfer hold has two journeys, so release it with
        ``cancel(hold, journey_count="2", consent=…)``. ``cancel`` was not changed
        — it already takes ``journey_count`` — but its default is wrong for this
        shape, and getting it wrong is how a hold survives a cancel that looked
        like it worked. Keep the PNR either way;
        ``scripts/recover_hold.py`` releases one from the PNR string alone.
        """
        return self._submit_reservation(
            "/arc/selectListArc05013_n.do",
            lambda key: transfer_reservation_payload(
                itinerary,
                passengers or PassengerCounts(),
                seat_type=seat_type,
                netfunnel_key=key,
                window_seat=window_seat,
            ),
            consent=consent,
            netfunnel_key=netfunnel_key,
        )

    def cancel(
        self,
        reservation: SrtReservationHold | str,
        *,
        consent: MutationConsent,
        journey_count: str | None = None,
    ) -> MutationPreview | SrtCancelResult:
        """Cancel a created-but-unpaid SRT reservation (예약취소) under consent.

        **Live-verified on 2026-07-25.** ``/ard/selectListArd02045_n.do`` with
        the body ``pnrNo`` / ``jrnyCnt="1"`` / ``rsvChgTno="0"`` released a real
        unpaid hold against the real server, answering ``strResult='SUCC'``,
        ``msgCd='IRG000000'``, ``msgTxt='정상처리되었습니다'``; the ticket list
        re-read afterwards showed no trace of the reservation
        (``scripts/verify_reserve_cancel_roundtrip.py``, run once).

        Where the shape came from is unchanged and still worth knowing: it was
        taken from srtgo's live runs, and the route has zero hits across all
        21,673 files of our v2.0.41 offline decompile. Nothing static
        corroborates it — the 2026-07-25 run is a *live-server* confirmation, and
        it covered exactly one single-journey, one-adult hold. ``jrnyCnt="1"`` is
        therefore confirmed only for the single-journey case.

        ``reservation`` is an :class:`~srt_mobile_api.models.SrtReservationHold`
        or a bare PNR string — a caller recovering from a partial failure may
        have only the PNR, and that path has to work or the reservation cannot
        be released. Requires an authenticated session and is gated by
        ``require_mutation_consent(consent, "cancel")``, so a default
        :class:`~srt_mobile_api.consent.MutationConsent` (``allow_cancel=False``)
        or ``None`` is denied before the form is built.

        ``journey_count`` overrides the form's ``jrnyCnt``, which otherwise
        defaults to ``"1"`` (see
        :func:`~srt_mobile_api.payloads.unpaid_reservation_cancel_payload` for
        why it is defaulted and not derived). It is reachable from here rather
        than only from the builder so that, if live capture ever shows a
        multi-leg PNR needing ``jrnyCnt="2"``, a caller can express it through
        this method instead of hand-rolling the payload and calling
        ``post_mutation_form`` directly — the hand-rolled path is exactly the
        one that orphans holds. It is normalized numerically and never refused,
        so passing a badly formatted value cannot make a hold uncancellable;
        ``None`` (the default) leaves the behaviour identical.

        With the default ``dry_run=True`` it returns a
        :class:`~srt_mobile_api.consent.MutationPreview` of the exact form that
        WOULD be POSTed (with the PNR redacted) and performs NO network I/O.
        With ``dry_run=False`` it goes through
        :meth:`~srt_mobile_api.http.SrtHttpClient.post_mutation_form` with
        ``category="cancel"`` and returns the parsed
        :class:`~srt_mobile_api.models.SrtCancelResult`. That send path is open:
        ``safety.SRT_LIVE_MUTATION_CATEGORIES`` holds ``{"reserve", "cancel",
        "payment", "refund"}``, and reserve/cancel were enabled together so a
        hold can always be released. A category outside it is refused with
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError`, which sends
        nothing.
        """
        require_mutation_consent(consent, "cancel")
        if self.session.current is None:
            raise SrtAuthError("SRT cancellation requires an authenticated session")
        route = "/ard/selectListArd02045_n.do"
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit. The builder never refuses over a journey
        # count formatting problem — see unpaid_reservation_cancel_payload.
        form = unpaid_reservation_cancel_payload(
            reservation, journey_count=journey_count
        )
        if consent.dry_run:
            return MutationPreview(
                category="cancel",
                method="POST",
                route=route,
                payload=form,
            )
        with self._session_guard():
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="cancel",
            )
            return parse_unpaid_cancel_response(response)

    def pay_with_card(
        self,
        reservation: SrtReservationSummary,
        card: SrtPaymentCard,
        *,
        consent: MutationConsent,
        passenger_count: str | None = None,
        settlement_date: str | None = None,
    ) -> MutationPreview | SrtPaymentResult:
        """Charge a card (카드결제) against an unpaid PNR under consent.

        **Live-verified on 2026-07-26.** ``/ata/selectListAta09036_n.do`` with
        this 31-field body charged a real card for a real hold against the real
        server, answering ``strResult='SUCC'``, ``msgCd='IRT000000'``: 수서 →
        동탄 (0551 → 0552), 2026-08-09, train 315, one adult, 7,500 KRW, paid and
        then refunded in the same run. A free probe went first — a fake card and
        a non-existent PNR — and the route answered a proper business envelope
        (``strResult='FAIL'``, ``msgCd='WRT100170'``) rather than a 404 or an
        HTML error shell, which is what established the route exists on our app
        version without spending anything.

        ``payment`` is therefore a member of
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`, and a
        ``dry_run=False`` call **moves real money**. The default is still
        ``dry_run=True``.

        **PROVENANCE — the origin is unchanged, and still the thinnest here.**
        The route, the body and the response envelope came from the reference
        implementations' live runs and nothing else, and the 2026-07-26 run is
        live-server evidence rather than static corroboration:

        * ``/ata/selectListAta09036_n.do`` has ZERO hits across all 21,673 files
          of our v2.0.41 offline decompile, as does every ``Ata09*`` route.
        * Our own app does not use this path. It serialises ``#rsvForm`` to
          ``/ard/selectListArd02017_n.do`` (personal) or ``Ard02018`` (group)
          and charges through the TransKey secure keypad and RaonSecure FIDO —
          not through plain HTTP form fields. The server honours this plaintext
          route anyway; that is now a fact rather than a hope.
        * The two reference libraries are ONE source. srtgo's payment code is a
          character-for-character vendored copy of ryanking13/SRT's, so their
          agreement corroborates nothing.

        And the run covered exactly one case: a single-journey, one-adult,
        general-seat ticket, one personal card, one lump sum. Group, multi-leg,
        corporate cards and instalments were not exercised. ``IRT000000`` is the
        same confirmation code korail returns for its own card approval, which
        is one more instance of the shared-platform pattern this project has
        recorded elsewhere.

        ``reservation`` is a row from :meth:`get_reservations` — the read that
        can name an unpaid PNR. Note that read's own limits: only its EMPTY
        response is live-verified, so the row field names this form draws on
        (``rcvdAmt``, ``tkSpecNum``, ``dptTm``, ``arvTm``) are srtgo-attested
        too. ``settlement_date`` (``stlDmnDt``) defaults to today; both it and
        ``passenger_count`` exist so a caller with ground truth can override,
        and so a test can pin an exact body.

        The AMOUNT is taken only from ``reservation.received_amount``
        (``rcvdAmt``, the collectable 수납금액) and has no override — see
        :func:`~srt_mobile_api.payloads.card_payment_payload` for why, and for
        the korail bug that makes it worth stating.

        Requires an authenticated session with a membership number, and is
        gated by ``require_mutation_consent(consent, "payment")`` before
        anything is built. With the default ``dry_run=True`` it returns a
        :class:`~srt_mobile_api.consent.MutationPreview` whose payload is
        redacted — the PAN, PIN, expiry, birthdate, membership number and PNR
        all become ``[REDACTED]`` — and performs NO network I/O. With
        ``dry_run=False`` the consent must additionally state which kind of card
        it is (:func:`~srt_mobile_api.consent.require_card_kind_claim`: exactly
        one of ``fake_card_only`` or ``real_card_acknowledged``; neither and
        both are refused). That claim is checked here and again at the send
        gate, and it is now the last thing between a real PAN and the wire.
        """
        require_mutation_consent(consent, "payment")
        session = self.session.current
        if session is None:
            raise SrtAuthError("SRT card payment requires an authenticated session")
        membership_number = session.membership_number
        if not membership_number:
            raise SrtAuthError(
                "SRT card payment requires the account's membership number "
                "(userMap.MB_CRD_NO); the session carried none, which is how "
                "the app itself spells 'not logged in'"
            )
        route = "/ata/selectListAta09036_n.do"
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit, matching cancel. stlDmnDt is resolved here
        # rather than in the builder so payloads.py keeps no clock.
        form = card_payment_payload(
            reservation,
            card,
            membership_number=membership_number,
            # `is None`, not `or`: an explicitly supplied but unusable value
            # must be REFUSED by the builder, not silently replaced with today.
            # Everywhere else on this path an unusable input raises rather than
            # being substituted (see payloads._payment_amount), and a payment
            # settled under a date the caller did not choose is the same class
            # of quiet wrongness.
            settlement_date=(
                time.strftime("%Y%m%d") if settlement_date is None else settlement_date
            ),
            passenger_count=passenger_count,
        )
        if consent.dry_run:
            return MutationPreview(
                category="payment",
                method="POST",
                route=route,
                payload=form,
            )
        # Only on the transmit path: a dry run sends nothing, so requiring the
        # card-kind claim to PREVIEW would buy no safety and would just make
        # previewing harder. post_mutation_form re-checks this itself.
        require_card_kind_claim(consent)
        with self._session_guard():
            # The single send path, so the gate ordering and the refusals stay
            # the transport layer's decision and cannot drift out of sync with
            # it. Since 2026-07-26 this reaches the wire.
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="payment",
            )
            return parse_card_payment_response(response)

    def get_refund_ticket_info(self, pnr_no: str) -> SrtRefundTicketInfo:
        """Read an issued ticket's refund identity — step 1 of 2 of a 환불.

        POSTs ``/atc/getListAtc14087.do`` with **no body**, gated by a
        ``Referer`` of ``<base_url>/common/ATC/ATC0201L/view.do?pnrNo=<PNR>``,
        and returns the ``outDataSets.dsOutput1[0]`` payload as an
        :class:`~srt_mobile_api.models.SrtRefundTicketInfo`. Feed that to
        :meth:`refund`.

        This travels the READ path, not the mutation gate: it is classified as a
        read and registered in
        :data:`~srt_mobile_api.safety.READ_ONLY_ROUTES`. That classification is
        an inference, not a proof — see the comment on the route there for what
        supports it and what does not — and the route is 0-hit in our v2.0.41
        bundle and attested by exactly one reference implementation. The route
        itself is live-verified (2026-07-26): a probe with a non-existent PNR got
        a proper business envelope back (``msgCd='WRT300005'``, "조회자료가
        없습니다."), and the round trip that followed read a real ticket's
        identity from it. Nothing in the refund path calls it for you —
        :meth:`refund` takes the identity you already hold.

        ``pnr_no`` is restricted to alphanumerics and hyphens. It is
        interpolated into a URL, so anything else could smuggle extra query
        parameters into the ``Referer`` this endpoint gates on.

        One deviation from the reference implementation, deliberate: it sets the
        ``Referer`` as a PERSISTENT session header and never removes it, so
        every later request on that session keeps carrying a PNR. Here it is
        passed per-request, like every other referer in this client.
        """
        if not isinstance(pnr_no, str) or not pnr_no.strip():
            raise ValueError("refund ticket info requires a non-empty PNR")
        pnr = pnr_no.strip()
        # ASCII-only and length-bounded, via an explicit character class rather
        # than str.isalnum(). isalnum() is UNICODE-aware, so "한글PNR", Arabic-Indic
        # digits and fullwidth letters all satisfied it and then died inside
        # httpx as a bare UnicodeEncodeError — an exception outside this
        # library's taxonomy entirely, raised while building the request. The
        # unbounded form also let a 5,000-character PNR become a 5,058-byte
        # Referer. Same ASCII-class style as safety.NETFUNNEL_KEY_RE.
        if _REFUND_PNR_RE.fullmatch(pnr) is None:
            raise ValueError(
                "refund ticket info PNR must be 1-32 ASCII alphanumerics or "
                "hyphens; it is interpolated into the Referer URL this endpoint "
                "gates on"
            )
        with self._session_guard():
            return parse_refund_ticket_info_response(
                self.http.post_form(
                    "/atc/getListAtc14087.do",
                    # No body. The reference implementation POSTs bare, and the
                    # Referer is what identifies the ticket.
                    None,
                    accept="application/json, text/javascript, */*; q=0.01",
                    referer=(
                        f"{self.config.base_url}"
                        f"/common/ATC/ATC0201L/view.do?pnrNo={pnr}"
                    ),
                )
            )

    def refund(
        self,
        ticket_info: SrtRefundTicketInfo,
        *,
        consent: MutationConsent,
    ) -> MutationPreview | SrtRefundResult:
        """Refund an issued ticket (환불) — step 2 of 2, under consent.

        **Live-verified on 2026-07-26.** ``/atc/selectListAtc02063_n.do`` with
        this seven-field body returned a real, paid ticket against the real
        server, answering ``strResult='SUCC'``, ``msgCd='IRT200277'``: the 수서 →
        동탄 (0551 → 0552) ticket bought minutes earlier in the same run, after
        which the account was verified empty of both reservations and tickets
        from a separate session. ``refund`` is therefore a member of
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` and a
        ``dry_run=False`` call **really returns the ticket**; the default is
        still ``dry_run=True``.

        ``ticket_info`` comes from :meth:`get_refund_ticket_info`. **The two
        steps are deliberately NOT fused into one method**, and that is still
        true now that both can transmit. Step 2's body is nothing but the
        identity step 1 returned (sale date, window, sequence, return password,
        purchaser), so this method takes an already-fetched
        :class:`~srt_mobile_api.models.SrtRefundTicketInfo` and never fetches
        one itself: a refund that is refused — by consent, by session, by
        anything — sends nothing at all rather than leaving a live step-1 read
        behind, and a caller cannot fabricate a step-2 form for a ticket the
        server never described. It also means a dry run needs no network. Do not
        "simplify" this by having :meth:`refund` fetch its own info.

        **PROVENANCE — the origin is unchanged, and thinner than the payment's.**
        The card payment at least has one implementation copied into two
        libraries. This route exists in exactly ONE: ryanking13/SRT has no refund
        at all, and srtgo added both steps from scratch four days after vendoring
        its SRT support. There is no upstream to have agreed with it,
        ``Atc02063`` is 0-hit across all 21,673 files of our v2.0.41 offline
        decompile, and the bundle has no ``Atc02*`` family whatsoever. The
        2026-07-26 run is live-server evidence, not static corroboration, and it
        covered exactly one single-journey, one-adult ticket.

        **The disputed field names are now settled in srtgo's favour.**
        ``tkRetPwd`` (against our own app's ``retPwd``) and ``psgNm`` (against
        ``buyPsNm``) were single-sourced and doubted here, because this project
        had already been burned once by exactly that — srtgo's ``txtPrnNo`` for
        korail's ``txtPnrNo``, which really was a typo. These two are not: the
        live run sent ``tkRetPwd``/``psgNm``/``pnr_no`` and the server accepted
        them. The app-side ``retPwd``/``buyPsNm`` spellings come from a local
        ``"ticketListOffline"`` cache handler, which was never evidence about
        this request, and that is now demonstrated rather than argued. See
        :func:`~srt_mobile_api.payloads.refund_payload`.

        Gated by ``require_mutation_consent(consent, "refund")``. With the
        default ``dry_run=True`` it returns a
        :class:`~srt_mobile_api.consent.MutationPreview` — the return password,
        the purchaser name and the PNR redacted, the sale identifiers legible —
        and performs NO network I/O.
        """
        require_mutation_consent(consent, "refund")
        if self.session.current is None:
            raise SrtAuthError("SRT refund requires an authenticated session")
        route = "/atc/selectListAtc02063_n.do"
        # Built before the dry-run branch so a preview validates exactly what a
        # live send would transmit, matching cancel and pay_with_card.
        form = refund_payload(ticket_info)
        if consent.dry_run:
            return MutationPreview(
                category="refund",
                method="POST",
                route=route,
                payload=form,
            )
        with self._session_guard():
            # The single send path, so gate ordering and refusals stay the
            # transport layer's decision. Since 2026-07-26 this reaches the wire.
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="refund",
            )
            return parse_refund_response(response)
