"""로그·미리보기에서 비밀을 마스킹.

두 방법: :data:`SENSITIVE_KEYS` 로 키 기반 ``[REDACTED]``, 나머지는 패턴
(카드번호 13-19자리, JSESSIONID, URL userinfo).
대상: 자격증명, 카드, 반환비밀번호, 쿠폰, 세션 ID, PNR, NetFunnel 키.
발권 식별자(saleDt/saleWctNo/saleSqno)는 의도적 비마스킹 — 반환비밀번호 없이 무해.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEYS = frozenset(
    key.casefold()
    for key in {
        # 로그인·세션
        "srchDvNm",
        "hmpgPwdCphd",
        "password",
        "cookie",
        "set-cookie",
        "JSESSIONID",
        "netfunnelKey",
        "key",
        # PNR·예약 식별
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
        # 결제 카드 (srtgo pay_with_card, srt.py:1184-1216)
        "stlCrCrdNo1",
        "vanPwd1",
        "crdVlidTrm1",
        "athnVal1",
        "athnDvCd1",
        "ismtMnthNum1",
        "crdInpWayCd1",
        "mbCrdNo",
        # 예약·취소·결제 폼 식별자 (srtgo srt.py:1006/1138/1199)
        "rsvChgTno",
        # PNR snake_case 철자 (wire field + dataclass attr)
        "pnr_no",
        # 환불 비밀번호 — 3가지 철자 모두 마스킹
        "ogtkRetPwd",
        "tkRetPwd",
        "retPwd",
        # 인명
        "buyPsNm",
        "psgNm",
        # SrtPaymentCard dataclass 속성
        "card_number",
        "card_password",
        "card_expire_date",
        "card_validation_number",
        # 할인쿠폰 (bearer credential — 번호+비밀번호로 타인 계정에 등록 가능)
        "dscp_no",
        "dscp_pwd",
        "coupon_number",
        "coupon_password",
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
    """자유 문자열 하나를 마스킹합니다 —— 키를 모르는 자리에 쓰는 마지막 그물.

    URL 의 ``user:pass@`` 부분, ``key=value``/``key: value`` 형태로 박혀 있는
    :data:`SENSITIVE_KEYS` 의 값, 카드번호로 보이는 13~19자리 숫자열, 그리고
    ``JSESSIONID=`` 뒤를 가립니다. 따옴표로 감싼 값은 따옴표를 남깁니다.
    """
    redacted = URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(_redact_assignment, redacted)
    return SESSION_RE.sub(r"\1[REDACTED]", CARD_RE.sub("[REDACTED_CARD]", redacted))


def redact_url(value: str) -> str:
    """URL 을 조각내어 쿼리 파라미터를 이름으로 가립니다.

    :data:`SENSITIVE_KEYS` 에 해당하는 파라미터는 값 전체가 ``[REDACTED]`` 가
    되고 나머지는 :func:`redact_text` 를 지납니다. 스킴이나 호스트가 없어 URL 로
    읽히지 않으면 통째로 :func:`redact_text` 로 넘깁니다.

    돌아온 문자열은 쿼리가 다시 인코딩되어 원문과 글자가 다를 수 있습니다. 표시용
    이고 재요청용이 아닙니다.
    """
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
    """임의의 값을 구조를 유지한 채 재귀적으로 가립니다.

    ``key`` 가 :data:`SENSITIVE_KEYS` 에 있으면 값을 보지 않고 ``[REDACTED]``
    입니다. 그렇지 않으면 매핑·리스트·튜플·dataclass 를 따라 내려가며, dataclass 는
    **필드명을 키로 삼아** 딕셔너리로 펴집니다. 바닥의 문자열은
    :func:`redact_url` 을 지나고, 숫자 같은 나머지 타입은 그대로 둡니다.
    """
    if key is not None and key.casefold() in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {name: redact_value(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: redact_value(getattr(value, field.name), key=field.name)
            for field in fields(value)
        }
    if isinstance(value, str):
        return redact_url(value)
    return value


def redact_mapping(data: Mapping[str, Any]) -> dict[str, Any]:
    """매핑의 각 항목을 그 키 이름으로 :func:`redact_value` 에 넘깁니다.

    값의 타입은 보존됩니다. 전송 폼처럼 값이 전부 문자열이어야 하면
    :func:`redact_payload` 를 씁니다.
    """
    return {name: redact_value(item, key=str(name)) for name, item in data.items()}


def redact_payload(payload: Mapping[str, str]) -> dict[str, str]:
    """전송 폼을 :class:`~srt_mobile_api.consent.MutationPreview` 용으로 가립니다.

    :data:`SENSITIVE_KEYS` 의 키는 값이 ``[REDACTED]`` 가 되고, 남은 값은 전부
    :func:`redact_text` 를 지납니다 —— 예상 못 한 키에 카드번호가 들어 있어도
    미리보기에 원문이 뜨지 않게 하기 위해서입니다. 키와 값 모두 문자열로 변환된
    ``dict[str, str]`` 을 돌려주므로 그대로 로그에 남겨도 됩니다.
    """
    return {
        str(key): "[REDACTED]"
        if str(key).casefold() in SENSITIVE_KEYS
        else redact_text(str(value))
        for key, value in payload.items()
    }
