from __future__ import annotations

from .errors import SrtAuthError, SrtProtocolError
from .http import SrtHttpClient
from .models import SrtSession


class SrtSessionClient:
    def __init__(self, http: SrtHttpClient) -> None:
        self.http = http
        self.current: SrtSession | None = None

    def login(self, login_id: str, password: str, *, login_type: str = "3") -> SrtSession:
        self.clear_session()
        self.http.get_text("/login/login.do")
        response = self.http.post_form(
            "/apb/selectListApb01080_n.do",
            {
                "srchDvCd": login_type,
                "srchDvNm": login_id,
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
            self.clear_session()
            raise SrtProtocolError("SRT login response missing userMap")
        if user_map.get("RTNCD") != "Y":
            self.clear_session()
            raise SrtAuthError(str(user_map.get("MSG") or "SRT login failed"))
        self.http.get_text("/main/main.do", params={"deviceId": self.http.config.device_key})
        self.http.get_text("/ara/ara0101v.do")
        self.current = SrtSession(login_id=login_id, user_map=user_map)
        return self.current

    def clear_session(self) -> None:
        self.http.cookies.clear()
        self.current = None
