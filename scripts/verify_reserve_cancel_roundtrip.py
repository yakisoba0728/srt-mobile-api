#!/usr/bin/env python3
"""Verify one live SRT reserve->cancel round trip against the real server.

**This creates a REAL unpaid reservation on a REAL account and then cancels
it.** It is the run that turns two unverified wire shapes into confirmed ones:
reserve's live NetFunnel/referer wiring, and cancel's entire body -- which is
srtgo-attested only and has zero hits in our v2.0.41 evidence bundle. Until
this script has been run successfully, neither is confirmed.

Because the cancel shape is exactly what is unproven, the cancel that undoes
the hold may itself fail. Everything here is therefore arranged around one
rule: **the PNR must reach the operator no matter what goes wrong.** A stranded
hold whose PNR nobody knows is the worst outcome available, so the PNR is
printed the instant it exists, before anything else is attempted, and again in
an unmissable banner with a ready-to-run recovery command if the cancel does
not succeed.

Two opt-ins are required, both explicit::

    SRT_MOBILE_API_LIVE=1   # the normal live-test flag
    SRT_LIVE_MUTATION=1     # this script only; a mutation is NOT a smoke test

The second exists so this can never fire from an ordinary live smoke run.

Journey parameters come from the same environment variables as
``srt_mobile_api.live.run_live_smoke_from_env`` (``SRT_TEST_DATE``,
``SRT_DEPARTURE_STATION_CODE``, ``SRT_ARRIVAL_STATION_CODE``,
``SRT_DEPARTURE_TIME``, the station names and the passenger counts), read
through that module's own helpers so the two tools cannot drift apart. The
reservation itself is always ONE adult in the cheapest available class,
regardless of the passenger counts used for the search.

Usage::

    SRT_MOBILE_API_LIVE=1 SRT_LIVE_MUTATION=1 \
    SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... SRT_TEST_DATE=YYYYMMDD \
    python3 scripts/verify_reserve_cancel_roundtrip.py

Exit code 0 means the hold was created AND released AND no trace of it remained
in the ticket list. Any other outcome exits non-zero.

Importing this module performs no I/O and sends nothing.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from srt_mobile_api import (
    MutationConsent,
    PassengerCounts,
    SeatType,
    SrtCancelResult,
    SrtClient,
    SrtConfig,
    SrtReservationHold,
)
from srt_mobile_api.live import (
    first_reservable_srt_train,
    live_enabled,
    read_credentials_from_env,
    read_device_key_from_env,
    read_query_from_env,
)


RECOVERY_SCRIPT = "scripts/recover_hold.py"


def mutation_enabled() -> bool:
    """The second, mutation-specific opt-in.

    Deliberately separate from ``SRT_MOBILE_API_LIVE``: that flag means "live
    reads are acceptable", which is not consent to create a reservation.
    """
    return os.environ.get("SRT_LIVE_MUTATION") == "1"


def build_reserve_consent() -> MutationConsent:
    """Reserve-only, non-dry-run consent."""
    return MutationConsent(
        allow_reserve=True,
        allow_payment=False,
        allow_cancel=False,
        allow_refund=False,
        dry_run=False,
        fake_card_only=True,
    )


def build_cancel_consent() -> MutationConsent:
    """Cancel-only, non-dry-run consent.

    Kept separate from the reserve consent rather than granting both at once,
    so neither call can be performed with the other's authority.
    """
    return MutationConsent(
        allow_reserve=False,
        allow_payment=False,
        allow_cancel=True,
        allow_refund=False,
        dry_run=False,
        fake_card_only=True,
    )


def _banner(lines: list[str]) -> None:
    width = max(len(line) for line in lines) + 4
    print("", flush=True)
    print("!" * width, flush=True)
    for line in lines:
        print(f"  {line}", flush=True)
    print("!" * width, flush=True)
    print("", flush=True)


def _confirmation_codes(label: str, raw: Any) -> None:
    """Print the raw strResult/msgCd pair -- the evidence this run exists for."""
    row: dict = {}
    if isinstance(raw, dict):
        result_map = raw.get("resultMap")
        if isinstance(result_map, list) and result_map and isinstance(result_map[0], dict):
            row = result_map[0]
    print(
        f"[{label}] strResult={row.get('strResult')!r} "
        f"msgCd={row.get('msgCd')!r} msgTxt={row.get('msgTxt')!r}",
        flush=True,
    )


def mask_login_id(login_id: str) -> str:
    """Show just enough of the member id to confirm the right account.

    The password is never printed at all; the id is masked rather than hidden
    because an operator needs to see WHICH account a real reservation was made
    on, and a fully hidden id makes that unverifiable.
    """
    if len(login_id) <= 2:
        return "*" * len(login_id)
    return f"{login_id[0]}{'*' * (len(login_id) - 2)}{login_id[-1]}"


def _describe_train(train) -> str:
    return (
        f"train_no={train.train_no} "
        f"{train.departure_station_name or train.departure_station_code}"
        f"->{train.arrival_station_name or train.arrival_station_code} "
        f"dep={train.departure_date} {train.departure_time} "
        f"general={train.general_seat_availability!r} "
        f"special={train.special_seat_availability!r}"
    )


def _stranded(pnr: str, reason: str) -> None:
    _banner(
        [
            "*** RESERVATION HOLD IS STRANDED -- ACTION REQUIRED ***",
            f"PNR: {pnr}",
            f"reason: {reason}",
            "",
            "Cancel it NOW with:",
            f"  SRT_LOGIN_ID=$SRT_LOGIN_ID SRT_LOGIN_PASSWORD='<password>' \\",
            f"    python3 {RECOVERY_SCRIPT} {pnr}",
            "",
            "If that also fails, cancel it in the SRT app immediately.",
        ]
    )


def _cancel(client: SrtClient, pnr: str) -> SrtCancelResult:
    result = client.cancel(pnr, consent=build_cancel_consent())
    if not isinstance(result, SrtCancelResult):
        raise RuntimeError("cancel returned a preview; the hold was NOT released")
    return result


def _remaining_hold_trace(client: SrtClient, pnr: str) -> bool:
    """Whether the PNR still appears in the account's ticket/reservation list."""
    page = client.get_ticket_list()
    return pnr in page.raw


def run_roundtrip(client: SrtClient, *, login_id: str, password: str) -> int:
    query = read_query_from_env()
    client.login(login_id, password)
    print(f"Logged in as {mask_login_id(login_id)}", flush=True)

    print(
        f"Searching {query.departure_station_code}->{query.arrival_station_code} "
        f"on {query.departure_date} from {query.departure_time}",
        flush=True,
    )
    search = client.search_trains(query)
    print(f"Search returned {len(search.trains)} train(s)", flush=True)

    # ONE adult in the cheapest available class, independent of the search's
    # passenger mix: the smallest possible real reservation.
    passengers = PassengerCounts(adult=1)
    train = first_reservable_srt_train(search.trains, passengers)
    if train is None:
        print(
            "REFUSING TO PROCEED: no train in the search result is reservable "
            "(no bookable seat, or the row is missing fields the reserve form "
            "requires). Nothing was sent. Try another date/time.",
            file=sys.stderr,
        )
        return 1
    print(f"Selected {_describe_train(train)}", flush=True)

    print("Reserving 1 adult (general seat preferred)...", flush=True)
    hold = client.reserve(
        train,
        consent=build_reserve_consent(),
        passengers=passengers,
        seat_type=SeatType.GENERAL_FIRST,
    )
    if not isinstance(hold, SrtReservationHold):
        print(
            "reserve returned a preview, not a hold; nothing was created",
            file=sys.stderr,
        )
        return 1

    # THE PNR, FIRST, BEFORE ANYTHING ELSE CAN FAIL.
    pnr = hold.pnr_no
    print("", flush=True)
    print(f"*** RESERVED. PNR={pnr} ***", flush=True)
    print(f"*** Recover with: python3 {RECOVERY_SCRIPT} {pnr} ***", flush=True)
    print("", flush=True)
    _confirmation_codes("reserve", hold.raw)

    cancelled = False
    try:
        print(f"Cancelling PNR={pnr} immediately...", flush=True)
        cancel_result = _cancel(client, pnr)
        _confirmation_codes("cancel", cancel_result.raw)
        print(
            f"[cancel] parsed status={cancel_result.status!r} "
            f"msgCd={cancel_result.message_code!r}",
            flush=True,
        )
        cancelled = cancel_result.succeeded
        if not cancelled:
            _stranded(pnr, f"server refused the cancel ({cancel_result.status})")
            return 1

        print("Verifying the hold is gone from the ticket list...", flush=True)
        if _remaining_hold_trace(client, pnr):
            _banner(
                [
                    "CANCEL REPORTED SUCCESS BUT THE PNR IS STILL LISTED",
                    f"PNR: {pnr}",
                    "Check the SRT app before assuming it is released.",
                ]
            )
            return 1
        print("Verified: no trace of the PNR remains.", flush=True)
        return 0
    finally:
        # Last line of defence, and the reason the whole post-reserve block is
        # wrapped: if the cancel above never SUCCEEDED -- refusal, exception,
        # anything at all -- try once more here, and if that fails too make the
        # PNR impossible to miss. A retry is safe in a way a reserve retry is
        # not: cancelling an already-cancelled hold cannot create anything.
        if not cancelled:
            try:
                retry = _cancel(client, pnr)
                _confirmation_codes("cancel-retry", retry.raw)
                if retry.succeeded:
                    print(f"Cancelled PNR={pnr} on the retry.", flush=True)
                else:
                    _stranded(pnr, f"retry refused ({retry.status})")
            except Exception as exc:  # noqa: BLE001 - the PNR must survive
                _stranded(pnr, f"retry raised {type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    if argv:
        print(f"ERROR: unexpected arguments: {argv}", file=sys.stderr)
        return 2
    if not live_enabled():
        print("Set SRT_MOBILE_API_LIVE=1 to run the live round trip", file=sys.stderr)
        return 2
    if not mutation_enabled():
        print(
            "Set SRT_LIVE_MUTATION=1 to allow this script to CREATE and CANCEL "
            "a real reservation. SRT_MOBILE_API_LIVE alone is not enough: it "
            "means live reads are acceptable, not that a reservation may be "
            "created.",
            file=sys.stderr,
        )
        return 2
    try:
        login_id, password = read_credentials_from_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    client = SrtClient(SrtConfig(device_key=read_device_key_from_env()))
    try:
        return run_roundtrip(client, login_id=login_id, password=password)
    except Exception as exc:  # noqa: BLE001 - report, never traceback-and-lose
        print(f"ROUND TRIP FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
