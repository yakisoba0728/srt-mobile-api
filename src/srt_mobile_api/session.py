"""로그인과 세션 정리 —— 쿠키를 얻는 곳.

SRT 는 ``JSESSIONID`` 쿠키로 세션을 유지합니다. 이 모듈은 앱과 같은 순서로
로그인 폼을 POST 하고, 메인·예매 페이지를 GET 해서 쿠키가 인증됐는지 확인합니다.
"""

from __future__ import annotations

import re

from .errors import SrtAuthError
from .http import SrtHttpClient
from .models import SrtSession
from .parsers import parse_html_page


# login.do srchDvCd 판정: srtgo srt.py:691-698 에서 유래.
# 이메일 → "2", 01X 휴대폰 → "3", 그 외(회원번호) → "1".
_EMAIL_LOGIN_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")
_PHONE_LOGIN_RE = re.compile(r"01[0-9]-?\d{3,4}-?\d{4}")


def _detect_login_type(login_id: str) -> str:
    """로그인 식별자 종류를 자동 판별 → srchDvCd 값."""
    if _EMAIL_LOGIN_RE.fullmatch(login_id):
        return "2"
    if _PHONE_LOGIN_RE.fullmatch(login_id):
        return "3"
    return "1"


class SrtSessionClient:
    """로그인 상태를 들고 있는 래퍼.

    :attr:`current` 는 로그인 성공 후 :class:`~srt_mobile_api.models.SrtSession`,
    로그인 전이나 :meth:`clear_session` 후에는 ``None``.
    """

    def __init__(self, http: SrtHttpClient) -> None:
        self.http = http
        self.current: SrtSession | None = None

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        """``POST /apb/selectListApb01080_n.do`` 로 로그인.

        ``login_id`` 종류(``srchDvCd``)는 자동 판별: 이메일 "2", 01X 전화 "3"
        (하이픈 있든 없든, 전송 시 제거), 그 외 회원번호 "1". ``login_type`` 으로
        직접 지정 가능.

        폼의 ``deviceKey`` 는 상수 ``"-"`` (srtgo srt.py:704).
        진짜 ANDROID_ID 인 ``config.device_key`` 는 ``/main/main.do?deviceId=``
        에만 쓰임 (SRWebActivity.java:1581-1583).

        성공: ``userMap.RTNCD == "Y"``. 실패: 최상위 ``MSG`` 또는
        ``userMap.MSG`` → SrtAuthError.

        **어떤 예외로 끝나든 쿠키는 비워집니다.**
        """
        self.clear_session()
        resolved_type = login_type if login_type is not None else _detect_login_type(login_id)
        # 전화번호("3")는 하이픈 없이 전송 (srtgo re.sub('-', '', id)).
        srch_dv_nm = re.sub("-", "", login_id) if resolved_type == "3" else login_id
        try:
            parse_html_page(self.http.get_text("/login/login.do"), context="login page")
            response = self.http.post_form(
                "/apb/selectListApb01080_n.do",
                {
                    "srchDvCd": resolved_type,
                    "srchDvNm": srch_dv_nm,
                    "check": "",
                    "auto": "",
                    "login_referer": "",
                    "hmpgPwdCphd": password,
                    "deviceKey": "-",
                    "page": "",
                    "customerYn": "",
                    "ciUptYn": "",
                    "dupInfoVal": "",
                },
                accept="application/json, text/javascript, */*; q=0.01",
                referer=f"{self.http.config.base_url}/login/login.do",
            )
            user_map = response.get("userMap")
            if not isinstance(user_map, dict) or user_map.get("RTNCD") != "Y":
                # 실패 시 최상위 MSG 우선 (srtgo srt.py:716,718), fallback userMap.MSG.
                message = response.get("MSG")
                if not message and isinstance(user_map, dict):
                    message = user_map.get("MSG")
                raise SrtAuthError(str(message or "SRT login failed"))
            parse_html_page(
                self.http.get_text(
                    "/main/main.do", params={"deviceId": self.http.config.device_key}
                ),
                context="main page",
                require_authenticated=True,
            )
            parse_html_page(
                self.http.get_text("/ara/ara0101v.do"),
                context="booking page",
                require_authenticated=True,
            )
            self.current = SrtSession(login_id=login_id, user_map=user_map)
            return self.current
        except Exception:
            self.clear_session()
            raise

    def clear_session(self) -> None:
        """쿠키를 버리고 :attr:`current` 를 ``None`` 으로 돌립니다.

        서버에 로그아웃을 알리지 않는 로컬 동작입니다.
        """
        self.http.cookies.clear()
        self.current = None
