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
    SrtMutationNotAllowedError,
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
        seat_count: str = "1",
        *,
        seat_attr_code: str = "015",
    ) -> SeatSelectionPage:
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
    ) -> MutationPreview:
        """Preview a personal (개인예약) SRT reservation under explicit consent.

        Gated by ``require_mutation_consent(consent, "reserve")``: a default
        :class:`~srt_mobile_api.consent.MutationConsent` (``allow_reserve=False``)
        or ``None`` is denied with
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` before
        anything is built. Requires an authenticated session. With the default
        ``dry_run=True`` it validates ``train``/``passengers`` and returns a
        :class:`~srt_mobile_api.consent.MutationPreview` of the exact form that
        WOULD be POSTed (mirroring srtgo ``_reserve``), performing NO network I/O
        — the NetFunnel key is left as the caller-supplied ``netfunnel_key`` (or
        empty) and is redacted in the preview.

        This method is **preview-only**: ``dry_run=False`` is refused. A
        :meth:`cancel` method now exists, but it cannot transmit either while
        ``SRT_LIVE_MUTATION_CATEGORIES`` is empty, and its wire shape is
        srtgo-attested and unconfirmed against our app version — so a live
        reserve would still create a hold this library could not release, and
        the live NetFunnel/referer wiring remains unverified. Live sending is
        deferred until a reserve->cancel round trip is verified against the real
        server. Of the tiered mutation routes only reserve and cancel have a
        client method; payment/refund remain classification-only pending live
        capture. The reserve-response parser (``parse_reservation_hold_response``,
        → ``SrtReservationHold``) is exported for the future live path and feeds
        :meth:`cancel`.
        """
        require_mutation_consent(consent, "reserve")
        if self.session.current is None:
            raise SrtAuthError("SRT reservation requires an authenticated session")
        if not consent.dry_run:
            # Live SRT reserve is deliberately not enabled yet. A cancel method
            # exists now, but no mutation category is live-enabled, so cancel
            # cannot transmit either: a created hold would still be
            # unreleasable by this library. Its shape is also srtgo-attested
            # only, and the live NetFunnel-key/referer wiring is unverified
            # against the server. Enabling live sending before a verified
            # reserve->cancel round trip could strand a real hold. dry_run
            # previews the exact form without sending.
            raise SrtMutationNotAllowedError(
                "live SRT reserve is not enabled: no mutation category can be "
                "transmitted yet, so a created hold could not be released even "
                "though a cancel method exists, and the NetFunnel/referer "
                "wiring is unverified; use dry_run=True for a preview"
            )
        passengers = passengers or PassengerCounts()
        form = personal_reservation_payload(
            train,
            passengers,
            seat_type=seat_type,
            netfunnel_key=netfunnel_key or "",
            window_seat=window_seat,
        )
        return MutationPreview(
            category="reserve",
            method="POST",
            route="/arc/selectListArc05013_n.do",
            payload=form,
        )

    def cancel(
        self,
        reservation: SrtReservationHold | str,
        *,
        consent: MutationConsent,
        journey_count: str | None = None,
    ) -> MutationPreview | SrtCancelResult:
        """Cancel a created-but-unpaid SRT reservation (예약취소) under consent.

        **The wire shape is UNVERIFIED for our app version.**
        ``/ard/selectListArd02045_n.do`` and its ``pnrNo``/``jrnyCnt``/
        ``rsvChgTno`` body are attested only by srtgo's live runs; the route has
        zero hits across all 21,673 files of our v2.0.41 offline decompile, so
        nothing here has been confirmed against the app we analysed, let alone
        against the live server.

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
        :class:`~srt_mobile_api.models.SrtCancelResult`. **That send path
        currently always refuses**: ``safety.SRT_LIVE_MUTATION_CATEGORIES`` is
        empty, so no cancel can be transmitted until a category is added there
        following a live verification. A refusal raises
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` and sends
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
