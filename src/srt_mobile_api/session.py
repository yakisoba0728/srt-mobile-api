from __future__ import annotations

import re

from .errors import SrtAuthError, SrtProtocolError
from .http import SrtHttpClient
from .models import SrtSession
from .parsers import parse_html_page


# login.do's srchDvCd (login-tab) selection is server-rendered and absent from the
# offline bundle, so the ground truth is srtgo (srt.py:691-698): the identifier is
# auto-detected as email → "2", phone → "3", else membership number → "1". A phone
# id requires dashes to be distinguished from an all-digit membership number (srtgo
# uses the same dash-requiring regex); when the resolved type is "3" the dashes are
# stripped from the transmitted srchDvNm (srt.py:697-698).
_EMAIL_LOGIN_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")
_PHONE_LOGIN_RE = re.compile(r"\d{3}-\d{3,4}-\d{4}")


def _detect_login_type(login_id: str) -> str:
    if _EMAIL_LOGIN_RE.fullmatch(login_id):
        return "2"
    if _PHONE_LOGIN_RE.fullmatch(login_id):
        return "3"
    return "1"


class SrtSessionClient:
    def __init__(self, http: SrtHttpClient) -> None:
        self.http = http
        self.current: SrtSession | None = None

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        self.clear_session()
        resolved_type = login_type if login_type is not None else _detect_login_type(login_id)
        # srchDvNm carries the raw identifier, except a phone number ("3") is sent
        # without dashes (srtgo re.sub('-', '', id)).
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
                    "deviceKey": self.http.config.device_key,
                    "page": "",
                    "customerYn": "",
                    "ciUptYn": "",
                    "dupInfoVal": "",
                },
                accept="application/json, text/javascript, */*; q=0.01",
                referer=f"{self.http.config.base_url}/login/login.do",
            )
            user_map = response.get("userMap")
            if not isinstance(user_map, dict):
                raise SrtProtocolError("SRT login response missing userMap")
            if user_map.get("RTNCD") != "Y":
                raise SrtAuthError(str(user_map.get("MSG") or "SRT login failed"))
            parse_html_page(
                self.http.get_text("/main/main.do", params={"deviceId": self.http.config.device_key}),
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
        self.http.cookies.clear()
        self.current = None
