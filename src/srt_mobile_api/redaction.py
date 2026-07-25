from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEYS = frozenset(
    key.casefold()
    for key in {
        "srchDvNm",
        "hmpgPwdCphd",
        "password",
        "cookie",
        "set-cookie",
        "JSESSIONID",
        "netfunnelKey",
        "key",
        "pnrNo",
        "pnr_number",
        "JRNYLIST_KEY",
        "journey_list_key",
        "tmpJobSqno1",
        "temporary_job_sequence",
        "lumpStlTgtNo",
        "lump_settlement_target_number",
        "seatNo",
        "seat_number",
        "scarNo",
        "car_number",
        "command",
        "commandMap",
        "mutMrkVrfCd",
        "verification_code",
        # Payment card fields (srtgo pay_with_card, srt.py:1184-1216). A mutation
        # preview must never expose card data even though no callable method sends
        # them here. CARD_RE only masks bare PANs; these mask the keyed
        # PAN/password/expiry/auth/installment/input-way variants CARD_RE misses,
        # plus the membership card number carried on the same form.
        "stlCrCrdNo1",
        "vanPwd1",
        "crdVlidTrm1",
        "athnVal1",
        "athnDvCd1",
        "ismtMnthNum1",
        "crdInpWayCd1",
        "mbCrdNo",
        # Reservation identity carried on the reserve/cancel/payment forms
        # (srtgo srt.py:1006/1138/1199). pnrNo is already covered above; these are
        # the settlement-target and change-number identifiers.
        "rsvChgTno",
    }
)
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
SESSION_RE = re.compile(r"(?i)(JSESSIONID=)[^&;\s]+")
URL_USERINFO_RE = re.compile(r"(?i)\b(https?://)[^/@\s]+@")
SENSITIVE_KEY_PATTERN = "|".join(
    sorted((re.escape(key) for key in SENSITIVE_KEYS), key=len, reverse=True)
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    rf"""
    (?<![\w-])
    (?P<key_quote>["']?)
    (?P<key>{SENSITIVE_KEY_PATTERN})
    (?P=key_quote)
    \s*(?:=|:)\s*
    (?P<value>
        "(?:\\.|[^"\\])*"
        |
        '(?:\\.|[^'\\])*'
        |
        [^&;,\s}}\]]+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _redact_assignment(match: re.Match[str]) -> str:
    value = match.group("value")
    replacement = "[REDACTED]"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        replacement = f"{value[0]}[REDACTED]{value[-1]}"
    value_offset = match.start("value") - match.start()
    return f"{match.group(0)[:value_offset]}{replacement}"


def redact_text(value: str) -> str:
    redacted = URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(_redact_assignment, redacted)
    return SESSION_RE.sub(r"\1[REDACTED]", CARD_RE.sub("[REDACTED_CARD]", redacted))


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return redact_text(value)
    if not parsed.scheme or not parsed.netloc:
        return redact_text(value)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"[REDACTED]@{netloc.rsplit('@', 1)[1]}"
    query = [
        (name, "[REDACTED]" if name.casefold() in SENSITIVE_KEYS else redact_text(item))
        for name, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            redact_text(parsed.path),
            urlencode(query),
            redact_text(parsed.fragment),
        )
    )


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and key.casefold() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {name: redact_value(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: redact_value(getattr(value, field.name), key=field.name) for field in fields(value)}
    if isinstance(value, str):
        return redact_url(value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    return {name: redact_value(item, key=str(name)) for name, item in data.items()}


def redact_payload(payload: Mapping[str, str]) -> dict[str, str]:
    """Redact a mutation form/payload mapping for a ``MutationPreview``.

    Every sensitive key (card fields, PII, PNR, NetFunnel key) becomes
    ``[REDACTED]``; every remaining value is card-masked via
    :func:`redact_text` so a raw PAN can never surface in a preview even when it
    appears under an unexpected key. The result is a plain ``dict[str, str]``
    safe to log or display.
    """
    return {
        str(key): "[REDACTED]"
        if str(key).casefold() in SENSITIVE_KEYS
        else redact_text(str(value))
        for key, value in payload.items()
    }
