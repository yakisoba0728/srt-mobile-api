from __future__ import annotations

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
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    NoticeListResult,
    PassengerCounts,
    SearchPageState,
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
    parse_seat_selection_page,
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
    seat_page_payload,
    seat_option_selector_payload,
    station_map_selector_payload,
    station_selector_payload,
    timetable_payload,
    train_group_selector_payload,
    unpaid_reservation_cancel_payload,
)
from .session import SrtSessionClient


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

    def _hydrate_search(self, query: TrainSearchQuery, key: str) -> SearchPageState:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        html = self.http.get_text(
            "/ara/selectListAra10007_n.do",
            params=search_page_payload(query, key),
            referer=referer,
        )
        return parse_search_page_state(html)

    def _prepare_search(
        self,
        query: TrainSearchQuery,
        *,
        group: bool,
    ) -> tuple[str, dict[str, str]]:
        referer = f"{self.config.base_url}/ara/ara0101v.do"
        key = self._get_act10_key(referer)
        state = self._hydrate_search(query, key)
        path = "/ara/selectListAra10082_n.do" if group else "/ara/selectListAra10007_n.do"
        payload = (
            group_search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
            if group
            else search_ajax_payload(query, key, hydrated_fields=state.hidden_fields)
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

    def _search_once(self, query: TrainSearchQuery, *, group: bool) -> TrainSearchResult:
        # The slot is released once the guarded request is over, whichever way
        # it went -- a search that raised held a place in line just as much as
        # one that succeeded. This is the app's TS_AUTO_COMPLETE behaviour.
        try:
            path, payload = self._prepare_search(query, group=group)
            return self._post_search_page(path, payload)
        finally:
            self._release_netfunnel_slots(
                f"{self.config.base_url}/ara/ara0101v.do"
            )

    def _search_with_retry(self, query: TrainSearchQuery, *, group: bool) -> TrainSearchResult:
        for attempt in range(2):
            try:
                return self._search_once(query, group=group)
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

    def reserve(
        self,
        train: TrainSummary,
        *,
        consent: MutationConsent,
        passengers: PassengerCounts | None = None,
        seat_type: SeatType = SeatType.GENERAL_FIRST,
        window_seat: bool | None = None,
        netfunnel_key: str | None = None,
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
        seat, one train. Multi-passenger, multi-leg, standby (``jobId=1102``)
        and group reservations were not exercised. A live call still creates a
        real unpaid hold on a real account, so keep the PNR —
        ``scripts/recover_hold.py`` releases one from the PNR string alone.

        Losing a PNR is the worst outcome this method can produce, so it is
        designed against: ``parse_reservation_hold_response`` salvages a minimal
        but cancelable hold when strict parsing trips over an unrelated
        malformed field, and a failed reserve is never retried — a retry could
        double-book — so at most one hold can exist per call.
        """
        require_mutation_consent(consent, "reserve")
        if self.session.current is None:
            raise SrtAuthError("SRT reservation requires an authenticated session")
        route = "/arc/selectListArc05013_n.do"
        passengers = passengers or PassengerCounts()
        if consent.dry_run:
            # Built inside the dry-run branch with the caller's key (or none):
            # a preview must not acquire anything, so it performs no I/O at all.
            return MutationPreview(
                category="reserve",
                method="POST",
                route=route,
                payload=personal_reservation_payload(
                    train,
                    passengers,
                    seat_type=seat_type,
                    netfunnel_key=netfunnel_key or "",
                    window_seat=window_seat,
                ),
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
            form = personal_reservation_payload(
                train,
                passengers,
                seat_type=seat_type,
                netfunnel_key=key,
                window_seat=window_seat,
            )
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
        ``safety.SRT_LIVE_MUTATION_CATEGORIES`` holds ``{"reserve", "cancel"}``,
        the pair enabled together so a hold can always be released. A category
        outside it is refused with
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
        """Build a card payment (카드결제) for an unpaid PNR — preview only, today.

        **THIS METHOD CANNOT TRANSMIT.** ``payment`` is not a member of
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`, which holds
        exactly ``{"reserve", "cancel"}``. With ``dry_run=False`` the call is
        refused by :meth:`~srt_mobile_api.http.SrtHttpClient.post_mutation_form`
        with :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` and
        nothing reaches the network, no matter how permissive the consent is —
        including one that acknowledges a real card. Implementing this method
        did not open that gate; doing so is a separate decision, and a test
        pins the refusal.

        **PROVENANCE — the weakest in this library.** The route, the 32-field
        body and the response envelope come from the reference implementations'
        live runs and nothing else:

        * ``/ata/selectListAta09036_n.do`` has ZERO hits across all 21,673 files
          of our v2.0.41 offline decompile, as does every ``Ata09*`` route.
        * Our own app does not use this path. It serialises ``#rsvForm`` to
          ``/ard/selectListArd02017_n.do`` (personal) or ``Ard02018`` (group)
          and charges through the TransKey secure keypad and RaonSecure FIDO —
          not through plain HTTP form fields.
        * The two reference libraries are ONE source. srtgo's payment code is a
          character-for-character vendored copy of ryanking13/SRT's, so their
          agreement corroborates nothing.

        So this endpoint may be a legacy path the server still honours, or it
        may be dead for our app version. Nobody has tested it, and this library
        cannot.

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
        one of ``fake_card_only`` or ``real_card_acknowledged``) before the send
        path refuses it anyway.
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
            settlement_date=settlement_date or time.strftime("%Y%m%d"),
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
            # Refused here, every time, by the live-enablement gate. Kept as a
            # real call rather than a raise so the refusal is the transport
            # layer's single decision and cannot drift out of sync with it.
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

        **THIS ONE CAN ACTUALLY TRANSMIT**, unlike :meth:`refund`, because it is
        classified as a read and registered in
        :data:`~srt_mobile_api.safety.READ_ONLY_ROUTES`. That classification is
        an inference, not a proof — see the comment on the route there for what
        supports it and what does not — and the route is 0-hit in our v2.0.41
        bundle and attested by exactly one reference implementation. Calling
        this is a deliberate act against an unverified endpoint; nothing in the
        refund path calls it for you.

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
        if not all(character.isalnum() or character == "-" for character in pnr):
            raise ValueError(
                "refund ticket info PNR must be alphanumeric (hyphens allowed); "
                "it is interpolated into the Referer URL this endpoint gates on"
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
        """Refund an issued ticket (환불) — step 2 of 2. **Cannot transmit.**

        ``refund`` is not a member of
        :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`, which holds
        exactly ``{"reserve", "cancel"}``. A ``dry_run=False`` call is refused by
        :meth:`~srt_mobile_api.http.SrtHttpClient.post_mutation_form` with
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` and nothing
        reaches the network, however permissive the consent is. Implementing
        this did not open that gate.

        ``ticket_info`` comes from :meth:`get_refund_ticket_info`. **The two
        steps are deliberately NOT fused into one method.** A combined call
        would perform step 1 — a real network request — and only then discover
        that step 2 is refused, so every attempt to refund would leave a live
        request behind for an operation that can never complete. Keeping them
        apart means a refused refund sends nothing at all, which is what the
        tests assert.

        It also means a dry run needs no network: the preview is built purely
        from the ``ticket_info`` the caller already holds.

        **PROVENANCE — thinner than the payment's.** The card payment at least
        has one implementation copied into two libraries. This route exists in
        exactly ONE: ryanking13/SRT has no refund at all, and srtgo added both
        steps from scratch four days after vendoring its SRT support. There is
        no upstream to have agreed with it, ``Atc02063`` is 0-hit across all
        21,673 files of our v2.0.41 offline decompile, and the bundle has no
        ``Atc02*`` family whatsoever.

        **Two of the seven field names are disputed** — ``tkRetPwd`` against our
        own app's ``retPwd``, and ``psgNm`` against ``buyPsNm``. We send srtgo's
        spelling because it is the only one attested by a live run of this
        endpoint, and this project has already been burned once by trusting a
        single-source field name (srtgo's ``txtPrnNo`` for korail's
        ``txtPnrNo``). See
        :func:`~srt_mobile_api.payloads.refund_payload` for the full argument
        and the alternatives to try first if it is ever rejected.

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
            # Refused here, every time, by the live-enablement gate. Kept as a
            # real call rather than a raise so the refusal stays the transport
            # layer's single decision.
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="refund",
            )
            return parse_refund_response(response)
