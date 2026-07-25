from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from .config import SrtConfig
from .consent import MutationConsent, MutationPreview, require_mutation_consent
from .errors import (
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
    SrtReservationHold,
    SrtSession,
    TimetablePage,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)
from .netfunnel import build_act10_url, parse_netfunnel_response
from .parsers import (
    parse_fare_page,
    parse_html_page,
    parse_mutual_verification_response,
    parse_notice_list_response,
    parse_reservation_hold_response,
    parse_search_has_following_page,
    parse_search_page_state,
    parse_seat_selection_page,
    parse_timetable_page,
    parse_train_search_response,
    parse_unpaid_cancel_response,
)
from .payloads import (
    date_selector_payload,
    fare_payload,
    group_search_ajax_payload,
    passenger_selector_payload,
    personal_reservation_payload,
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
    ) -> None:
        self.config = config or SrtConfig()
        self.http = SrtHttpClient(self.config, transport=transport)
        self.session = SrtSessionClient(self.http)
        self._clock = clock or time.time

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

    def _get_act10_key(self, referer: str) -> str:
        url = build_act10_url(
            self.config.netfunnel_url,
            timestamp_ms=int(self._clock() * 1000),
        )
        body = self.http.get_text_url(url, referer=referer)
        return parse_netfunnel_response(body, action="act_10").key

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
        path, payload = self._prepare_search(query, group=group)
        return self._post_search_page(path, payload)

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
            response = self.http.post_mutation_form(
                route,
                form,
                consent=consent,
                category="reserve",
                # The app reserves from the search-result page (ara1001l.js:1541
                # -1560), which is the referer every other post-search read here
                # sends. INFERRED from the app flow, not captured from the wire.
                referer=f"{self.config.base_url}/ara/selectListAra10007_n.do",
            )
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
