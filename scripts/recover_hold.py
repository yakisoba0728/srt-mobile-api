#!/usr/bin/env python3
"""Cancel one SRT reservation hold, given nothing but its PNR.

This is the operator's safety net. If a reserve->cancel round trip (or any
other flow) leaves an unpaid hold stranded on a real account, this script
releases it from the PNR string alone -- no hold object, no search result, no
state carried over from the run that created it. That standalone property is
the whole point: the situation this exists for is precisely the one where the
process that made the hold is gone.

    SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py <PNR>

And when the PNR itself is what was lost, ``--list`` enumerates the account's
reservations instead of cancelling anything:

    SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py --list

``--list`` is a pure READ (``SrtClient.get_reservations`` ->
``POST /atc/selectListAtc14016_n.do``, on the read-only allowlist) and
constructs no consent at all, so it cannot cancel, reserve, pay or refund. It
exists because until it did, the recovery path had a hole in exactly the shape
of its own worst case: the tool for a lost hold required you to already know
the hold's identity. Run it, read the PNR, then run the cancel form above.

Exit code 0 means the server reported the hold cancelled. ANY other outcome
exits non-zero and reprints the PNR, because an operator who loses the PNR has
no way back to the reservation.

The password is read from the environment and never printed. The PNR IS
printed -- it is the one identifier the operator cannot afford to lose, and
this script is run by the account holder against their own reservation.

Importing this module performs no I/O and sends nothing; all work happens in
main() under ``if __name__ == "__main__"``.
"""

from __future__ import annotations

import argparse
import sys

from srt_mobile_api import (
    MutationConsent,
    SrtCancelResult,
    SrtClient,
    SrtConfig,
    SrtReservationListResult,
)
from srt_mobile_api.live import read_credentials_from_env


def build_cancel_consent() -> MutationConsent:
    """The explicit consent this script runs under, spelled out field by field.

    Constructed here rather than inline so the grant is auditable in one place:
    cancel ONLY, and non-dry-run (a dry run would print a preview and release
    nothing, which for a recovery tool is a silent no-op and worse than an
    error). Every other category stays denied, so this script cannot reserve,
    pay or refund even if something downstream asked it to.
    """
    return MutationConsent(
        allow_reserve=False,
        allow_payment=False,
        allow_cancel=True,
        allow_refund=False,
        dry_run=False,
        fake_card_only=True,
    )


def _print_banner(lines: list[str]) -> None:
    width = max(len(line) for line in lines) + 4
    print("=" * width)
    for line in lines:
        print(f"  {line}")
    print("=" * width)


def cancel_hold(
    client: SrtClient, pnr: str, journey_count: str = "1"
) -> SrtCancelResult:
    """Cancel ``pnr`` on an already-authenticated ``client``.

    ``journey_count`` is the hold's ``jrnyCnt``. It is "1" for an ordinary
    reservation and "2" for a 환승 one, and this script is the last-resort path
    that only has a PNR to work from -- so the value cannot be derived here and
    has to be stated. Getting it wrong is how a hold survives a cancel that
    looked like it worked.
    """
    result = client.cancel(
        pnr, consent=build_cancel_consent(), journey_count=journey_count
    )
    # cancel() returns a MutationPreview for a dry-run consent. build_cancel_
    # consent sets dry_run=False, so this cannot normally happen -- but if a
    # future edit broke that, a preview would look like success while releasing
    # nothing. Fail loudly instead.
    if not isinstance(result, SrtCancelResult):
        raise RuntimeError(
            "cancel returned a preview, not a result: the hold was NOT released"
        )
    return result


def list_holds(client: SrtClient) -> SrtReservationListResult:
    """Read the account's reservations on an already-authenticated ``client``.

    Deliberately a bare read with NO consent object anywhere near it: listing
    must never be able to change state, not even by a later refactor that
    reaches for the consent this module already builds for the cancel path.
    """
    return client.get_reservations()


def _print_holds(result: SrtReservationListResult) -> None:
    """Print every PNR the server returned, or say plainly that there are none.

    The PNRs ARE printed, for the same reason the cancel path prints one: this
    is the account holder looking at their own reservations, and a masked PNR is
    useless to the person who needs to type it into the cancel command.
    """
    if not result.reservations:
        print("No reservations on this account.")
        return
    print(f"{len(result.reservations)} reservation(s):")
    for item in result.reservations:
        detail = " ".join(
            part
            for part in (
                f"train={item.train_no}" if item.train_no else "",
                f"dep={item.departure_date}/{item.departure_time}"
                if item.departure_date or item.departure_time
                else "",
                f"payBy={item.payment_limit_date}{item.payment_limit_time or ''}"
                if item.payment_limit_date
                else "",
            )
            if part
        )
        print(f"  PNR: {item.pnr_no}" + (f"  ({detail})" if detail else ""))
    print("")
    print("Cancel one with:")
    print(f"  python3 scripts/recover_hold.py {result.reservations[0].pnr_no}")


def _mask_login_id(login_id: str) -> str:
    if len(login_id) <= 2:
        return "*" * len(login_id)
    return f"{login_id[0]}{'*' * (len(login_id) - 2)}{login_id[-1]}"


def _run_list(client: SrtClient, login_id: str, password: str) -> int:
    """The ``--list`` mode: log in, read, print, exit. Cancels nothing."""
    try:
        client.login(login_id, password)
        print(f"Logged in as {_mask_login_id(login_id)}")
        result = list_holds(client)
    except Exception as exc:  # 넓게 잡는다: 운영자에게 트레이스백을 던지지 않고 보고한다
        print(f"ERROR: could not list reservations: {type(exc).__name__}: {exc}")
        return 1
    finally:
        client.close()
    _print_holds(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cancel one unpaid SRT reservation hold by PNR",
    )
    parser.add_argument(
        "pnr",
        nargs="?",
        default=None,
        help="the PNR of the hold to cancel",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_holds",
        help=(
            "list the account's reservations and their PNRs, then exit; "
            "cancels nothing"
        ),
    )
    parser.add_argument(
        "--journey-count",
        default="1",
        help=(
            "the hold's jrnyCnt: 1 for an ordinary reservation (default), "
            "2 for a 환승 hold created by reserve_transfer. A transfer hold "
            "cancelled with 1 may not actually be released"
        ),
    )
    parser.add_argument(
        "--device-key",
        default=None,
        help="override SRT_DEVICE_KEY",
    )
    args = parser.parse_args(argv)

    # Exactly one mode. Accepting both would make "which one wins?" a question
    # an operator has to guess at while a real hold is outstanding.
    if args.list_holds and args.pnr is not None:
        print("ERROR: --list takes no PNR", file=sys.stderr)
        return 2
    if not args.list_holds and args.pnr is None:
        print("ERROR: a PNR is required (or use --list)", file=sys.stderr)
        return 2

    pnr = "" if args.pnr is None else args.pnr.strip()
    if not args.list_holds and not pnr:
        print("ERROR: PNR is empty", file=sys.stderr)
        return 2

    try:
        login_id, password = read_credentials_from_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    config = (
        SrtConfig(device_key=args.device_key)
        if args.device_key is not None
        else SrtConfig()
    )
    client = SrtClient(config)
    if args.list_holds:
        return _run_list(client, login_id, password)
    print(f"Recovering hold PNR={pnr}")
    try:
        client.login(login_id, password)
        masked = (
            "*" * len(login_id)
            if len(login_id) <= 2
            else f"{login_id[0]}{'*' * (len(login_id) - 2)}{login_id[-1]}"
        )
        print(f"Logged in as {masked}")
        result = cancel_hold(client, pnr, args.journey_count)
    except Exception as exc:  # 넓게 잡는다: 어떤 실패에도 PNR 은 살아남아야 한다
        _print_banner(
            [
                "CANCEL FAILED -- THE HOLD MAY STILL EXIST",
                f"PNR: {pnr}",
                f"{type(exc).__name__}: {exc}",
                "Retry this command, or cancel it in the SRT app.",
            ]
        )
        return 1
    finally:
        client.close()

    # Raw confirmation codes, printed whichever way it went: they are the
    # evidence of what the server actually said.
    print(f"strResult={result.status!r} msgCd={result.message_code!r}")
    if not result.succeeded:
        _print_banner(
            [
                "SERVER REFUSED THE CANCEL -- THE HOLD STILL EXISTS",
                f"PNR: {pnr}",
                f"strResult={result.status} msgCd={result.message_code}",
                "Retry this command, or cancel it in the SRT app.",
            ]
        )
        return 1

    _print_banner([f"HOLD CANCELLED -- PNR {pnr} is released"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
