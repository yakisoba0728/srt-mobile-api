"""로그·미리보기에 나가는 값에서 비밀을 가린다.

:class:`~srt_mobile_api.consent.MutationPreview` 가 dry_run 요청 본문을 보여 줄
때 이 모듈을 지나고, 예외 메시지도 :func:`redact_url` 을 지난다. 예외의 ``raw``
는 대체로 원문 그대로다 —— 반환비밀번호가 실려 오는 환불 1단계만 예외다
(:func:`~srt_mobile_api.parsers.parse_refund_ticket_info_response`).
가리는 방법은 두 가지다 ——
:data:`SENSITIVE_KEYS` 에 든 **키 이름**으로 값을 통째로 ``[REDACTED]`` 로
바꾸고, 남은 문자열은 카드번호(13~19자리)·``JSESSIONID``·URL 사용자정보 패턴을
찾아 마스킹한다. 키 이름은 대소문자를 구별하지 않는다.

가리는 대상은 자격증명(비밀번호, 카드정보, 승차권 반환비밀번호, 할인쿠폰
번호·비밀번호), 신원(로그인 아이디, 이름), 그리고 세션·예약을 가리키는
식별자(``JSESSIONID``, PNR, NetFunnel 키)다. 서버 필드명과 이 라이브러리의
dataclass 속성명을 **양쪽 다** 넣어 두었다 —— :func:`redact_value` 는 dataclass
를 필드명 기준으로 가리기 때문이다.

발권 식별자(``saleDt``/``saleWctNo``/``saleSqno`` 와 그 ``ogtk*`` 응답 철자)는
일부러 가리지 않는다. 반환비밀번호가 가려진 이상 그것들만으로는 아무것도
승인되지 않고, 이것마저 가리면 환불 미리보기가 전부 ``[REDACTED]`` 가 되어
읽을 수 없다. 취소 폼에서 ``pnrNo`` 는 가리고 ``jrnyCnt`` 는 가리지 않는 것과
같은 기준이다.
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
        # The PNR under its SNAKE_CASE spellings. `pnrNo` and `pnr_number` were
        # already covered; `pnr_no` was not, and it is BOTH the refund step-2
        # wire field (srtgo srt.py:1242) and the attribute name on
        # SrtReservationHold / SrtReservationSummary / SrtRefundTicketInfo. Its
        # absence meant redact_value(hold) -- which redacts a dataclass by FIELD
        # NAME -- passed a real PNR through untouched.
        "pnr_no",
        # Refund secrets. The ticket RETURN PASSWORD is the credential that
        # authorises a refund, under all three spellings we have seen it in:
        # `ogtkRetPwd` (srtgo's step-1 response key), `tkRetPwd` (srtgo's step-2
        # request field) and `retPwd` (our own app's offline ticket cache,
        # webview/b.java:645-646). All three stay masked. The live API's own
        # spelling is settled -- the 2026-07-26 refund sent `tkRetPwd` and the
        # server took it -- but a value this sensitive is masked under every
        # name it has ever appeared under, not only the winning one, so a cached
        # or step-1 copy cannot leak through a name this set forgot.
        "ogtkRetPwd",
        "tkRetPwd",
        "retPwd",
        # Personal names on the refund forms: `buyPsNm` (purchaser, step-1
        # response and our app's cache) and `psgNm` (passenger, srtgo's step-2
        # request). Plain PII.
        "buyPsNm",
        "psgNm",
        # SrtPaymentCard's own attribute names, so redact_value on the dataclass
        # masks by field name rather than relying on CARD_RE to recognise the
        # digits. CARD_RE only matches a 13-19 digit run, which a deliberately
        # short synthetic test PAN, a 2-digit PIN, a YYMM expiry and a YYMMDD
        # birthdate all slip past.
        "card_number",
        "card_password",
        "card_expire_date",
        "card_validation_number",
        # 할인쿠폰: the wire fields the coupon page's own couponReg() serialises
        # (`dscp_no`, `dscp_pwd` -- the live page, 2026-07-26) and the two
        # attribute names SrtCouponRegistrationRequest carries them under.
        #
        # A COUPON NUMBER IS A BEARER CREDENTIAL. Whoever holds the pair can
        # redeem the coupon against their own account, so it is masked on the
        # same footing as a PAN, not on the footing of a PNR. Neither half was
        # covered before: `dscp_pwd` is not the literal key `password`, and
        # `dscp_no` is at most TEN digits (maxlength="10" on the page's own
        # input), which CARD_RE -- a 13-to-19 digit run -- never matches. So a
        # dry-run MutationPreview of a registration would have printed a usable
        # coupon in full. This project has shipped that exact class of gap
        # before; these four entries are what stop it here.
        "dscp_no",
        "dscp_pwd",
        "coupon_number",
        "coupon_password",
    }
)
# DELIBERATELY NOT REDACTED, and this is a decision rather than an oversight:
# the refund's `saleDt` / `saleWctNo` / `saleSqno` (and their `ogtk*` response
# spellings) are ticket-ISSUANCE identifiers, not credentials. With the return
# password above masked they authorise nothing, and leaving them legible is what
# makes a refund MutationPreview readable at all -- every other field on that
# form is either the PNR, the password or a name. The same line is already drawn
# on the cancel form, where `pnrNo` is masked and `jrnyCnt` is not.
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
    """자유 문자열 하나를 마스킹한다 —— 키를 모르는 자리에 쓰는 마지막 그물.

    URL 의 ``user:pass@`` 부분, ``key=value``/``key: value`` 형태로 박혀 있는
    :data:`SENSITIVE_KEYS` 의 값, 카드번호로 보이는 13~19자리 숫자열, 그리고
    ``JSESSIONID=`` 뒤를 가린다. 따옴표로 감싼 값은 따옴표를 남긴다.
    """
    redacted = URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    redacted = SENSITIVE_ASSIGNMENT_RE.sub(_redact_assignment, redacted)
    return SESSION_RE.sub(r"\1[REDACTED]", CARD_RE.sub("[REDACTED_CARD]", redacted))


def redact_url(value: str) -> str:
    """URL 을 조각내어 쿼리 파라미터를 이름으로 가린다.

    :data:`SENSITIVE_KEYS` 에 해당하는 파라미터는 값 전체가 ``[REDACTED]`` 가
    되고 나머지는 :func:`redact_text` 를 지난다. 스킴이나 호스트가 없어 URL 로
    읽히지 않으면 통째로 :func:`redact_text` 로 넘긴다.

    돌아온 문자열은 쿼리가 다시 인코딩되어 원문과 글자가 다를 수 있다. 표시용
    이고 재요청용이 아니다.
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
    """임의의 값을 구조를 유지한 채 재귀적으로 가린다.

    ``key`` 가 :data:`SENSITIVE_KEYS` 에 있으면 값을 보지 않고 ``[REDACTED]``
    다. 그렇지 않으면 매핑·리스트·튜플·dataclass 를 따라 내려가며, dataclass 는
    **필드명을 키로 삼아** 딕셔너리로 펴진다. 바닥의 문자열은
    :func:`redact_url` 을 지나고, 숫자 같은 나머지 타입은 그대로 둔다.
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
    """매핑의 각 항목을 그 키 이름으로 :func:`redact_value` 에 넘긴다.

    값의 타입은 보존된다. 전송 폼처럼 값이 전부 문자열이어야 하면
    :func:`redact_payload` 를 쓴다.
    """
    return {name: redact_value(item, key=str(name)) for name, item in data.items()}


def redact_payload(payload: Mapping[str, str]) -> dict[str, str]:
    """전송 폼을 :class:`~srt_mobile_api.consent.MutationPreview` 용으로 가린다.

    :data:`SENSITIVE_KEYS` 의 키는 값이 ``[REDACTED]`` 가 되고, 남은 값은 전부
    :func:`redact_text` 를 지난다 —— 예상 못 한 키에 카드번호가 들어 있어도
    미리보기에 원문이 뜨지 않게 하기 위해서다. 키와 값 모두 문자열로 변환된
    ``dict[str, str]`` 을 돌려주므로 그대로 로그에 남겨도 된다.
    """
    return {
        str(key): "[REDACTED]"
        if str(key).casefold() in SENSITIVE_KEYS
        else redact_text(str(value))
        for key, value in payload.items()
    }
