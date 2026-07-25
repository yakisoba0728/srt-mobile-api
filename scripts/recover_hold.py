#!/usr/bin/env python3
"""Cancel one SRT reservation hold, given nothing but its PNR.

This is the operator's safety net. If a reserve->cancel round trip (or any
other flow) leaves an unpaid hold stranded on a real account, this script
releases it from the PNR string alone -- no hold object, no search result, no
state carried over from the run that created it. That standalone property is
the whole point: the situation this exists for is precisely the one where the
process that made the hold is gone.

    SRT_LOGIN_ID=... SRT_LOGIN_PASSWORD=... python3 scripts/recover_hold.py <PNR>

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


def cancel_hold(client: SrtClient, pnr: str) -> SrtCancelResult:
    """Cancel ``pnr`` on an already-authenticated ``client``."""
    result = client.cancel(pnr, consent=build_cancel_consent())
    # cancel() returns a MutationPreview for a dry-run consent. build_cancel_
    # consent sets dry_run=False, so this cannot normally happen -- but if a
    # future edit broke that, a preview would look like success while releasing
    # nothing. Fail loudly instead.
    if not isinstance(result, SrtCancelResult):
        raise RuntimeError(
            "cancel returned a preview, not a result: the hold was NOT released"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cancel one unpaid SRT reservation hold by PNR",
    )
    parser.add_argument("pnr", help="the PNR of the hold to cancel")
    parser.add_argument(
        "--device-key",
        default=None,
        help="override SRT_DEVICE_KEY",
    )
    args = parser.parse_args(argv)

    pnr = args.pnr.strip()
    if not pnr:
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
    print(f"Recovering hold PNR={pnr}")
    try:
        client.login(login_id, password)
        masked = (
            "*" * len(login_id)
            if len(login_id) <= 2
            else f"{login_id[0]}{'*' * (len(login_id) - 2)}{login_id[-1]}"
        )
        print(f"Logged in as {masked}")
        result = cancel_hold(client, pnr)
    except Exception as exc:  # noqa: BLE001 - the PNR must survive ANY failure
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
