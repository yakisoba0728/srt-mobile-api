"""로그인과 세션 정리 —— 쿠키를 얻는 곳.

SRT 는 토큰이 아니라 쿠키(``JSESSIONID``)로 세션을 유지한다. 이 모듈은 앱과
같은 순서로 로그인 폼을 POST 하고, 뒤이어 메인·예매 페이지를 GET 해서 그
쿠키가 실제로 인증된 세션인지 확인한다. 이후의 모든 읽기·쓰기는 같은
:class:`~srt_mobile_api.http.SrtHttpClient` 의 쿠키를 탄다.
"""

from __future__ import annotations

import re

from .errors import SrtAuthError
from .http import SrtHttpClient
from .models import SrtSession
from .parsers import parse_html_page


# login.do's srchDvCd (login-tab) selection is server-rendered and absent from the
# offline bundle, so the ground truth is srtgo (srt.py:691-698): the identifier is
# auto-detected as email → "2", phone → "3", else membership number → "1". A phone
# A Korean mobile number (01X prefix, with or without dashes) resolves to a phone
# login ("3"); the leading "01X" distinguishes it from an all-digit membership number
# ("1"). srtgo used a dash-requiring regex, but real credentials are commonly entered
# without dashes -- a real stored dashless phone id must resolve to a phone and not
# fall through to membership. When the resolved type is "3" the dashes are stripped
# from the transmitted srchDvNm (srt.py:697-698).
_EMAIL_LOGIN_RE = re.compile(r"[^@]+@[^@]+\.[^@]+")
_PHONE_LOGIN_RE = re.compile(r"01[0-9]-?\d{3,4}-?\d{4}")


def _detect_login_type(login_id: str) -> str:
    if _EMAIL_LOGIN_RE.fullmatch(login_id):
        return "2"
    if _PHONE_LOGIN_RE.fullmatch(login_id):
        return "3"
    return "1"


class SrtSessionClient:
    """로그인 상태를 들고 있는 얇은 래퍼.

    :attr:`current` 는 로그인 성공 뒤의
    :class:`~srt_mobile_api.models.SrtSession` 이고, 로그인 전이나
    :meth:`clear_session` 뒤에는 ``None`` 이다. 쿠키 자체는 주입받은
    :class:`~srt_mobile_api.http.SrtHttpClient` 가 보관하며 이 객체는 그것을
    비우는 권한만 갖는다.

    :class:`~srt_mobile_api.client.SrtClient` 가 내부에서 쓰는 부품이다. 직접
    만들 필요는 보통 없다.
    """

    def __init__(self, http: SrtHttpClient) -> None:
        self.http = http
        self.current: SrtSession | None = None

    def login(
        self, login_id: str, password: str, *, login_type: str | None = None
    ) -> SrtSession:
        """로그인해 세션 쿠키를 얻고, 그 쿠키가 인증됐는지까지 확인한다.

        ``POST /apb/selectListApb01080_n.do``. 먼저 기존 세션을 버리고 로그인
        페이지를 한 번 GET 한 뒤 폼을 보낸다. 성공하면
        :class:`~srt_mobile_api.models.SrtSession` 을 돌려주고 :attr:`current`
        에도 남긴다.

        ``login_id`` 의 종류(``srchDvCd``)는 넘기지 않으면 자동으로 정한다 ——
        이메일이면 ``"2"``, 01X 로 시작하는 휴대전화번호면 ``"3"``, 그 밖에는
        모두 회원번호로 보아 ``"1"`` 이다. 휴대전화번호는 하이픈이 있든 없든
        판별되고, 보낼 때 하이픈을 뗀다. 자동 판별이 틀리면 ``login_type`` 으로
        직접 지정한다.

        폼의 ``deviceKey`` 는 기기 식별자가 아니라 상수 ``"-"`` 다. 진짜 기기
        식별자인 :attr:`~srt_mobile_api.config.SrtConfig.device_key` 는 로그인
        직후 GET 하는 ``/main/main.do?deviceId=`` 에만 쓰인다.

        **아이디·비밀번호가 틀린 경우는 언제나**
        :class:`~srt_mobile_api.errors.SrtAuthError` 다 —— 응답 최상위 ``MSG``
        를, 없으면 ``userMap.MSG`` 를 메시지로 싣는다. ``userMap`` 이 통째로
        없어도 프로토콜 오류로 바꾸지 않는다. 성공 판정은
        ``userMap.RTNCD == "Y"`` 뿐이다.

        폼이 통과해도 끝이 아니다. 이어서 ``/main/main.do`` 와
        ``/ara/ara0101v.do`` 를 읽어 로그인 페이지로 튕기지 않는지 본다 —— 여기서
        걸리면 :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 다. 그래서
        이 메서드가 돌아왔다는 것은 예매 페이지까지 인증된 상태라는 뜻이다.

        **어떤 예외로 끝나든 쿠키는 비워진다.** 실패한 로그인이 반쯤 살아 있는
        세션을 남기지 않는다.
        """
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
                    # The login deviceKey is the server-rendered constant "-", not an
                    # ANDROID_ID. Both wire refs agree: srtgo srt.py:704 (data["deviceKey"]
                    # = "-") and ref-srtgo_plus.md:112,120-121. The real ANDROID_ID-shaped
                    # config.device_key belongs only on /main/main.do?deviceId= below
                    # (SRWebActivity.java:1582-1584), not on this login field.
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
            # Spelled as one negated condition rather than via an `authenticated`
            # flag so the success path below is provably reached only with
            # user_map a dict -- the same test, stated where a reader (and a type
            # checker) can see that SrtSession never receives a non-mapping.
            if not isinstance(user_map, dict) or user_map.get("RTNCD") != "Y":
                # On a failed login the app reads the TOP-LEVEL MSG and treats it as an
                # auth failure (srtgo srt.py:716,718 -> raise SRTLoginError(r.json()["MSG"])
                # for both non-existent-member and wrong-password cases; MSG is sibling to
                # userMap, which the failure path never touches). Read top-level MSG first,
                # fall back to userMap.MSG, and always raise SrtAuthError -- never
                # SrtProtocolError -- even when userMap is absent.
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
        """쿠키를 버리고 :attr:`current` 를 ``None`` 으로 돌린다.

        서버에 로그아웃을 알리지는 않는다 —— 쿠키를 버리는 로컬 동작이다.
        로그인 전이든 후든 여러 번 불러도 된다.
        """
        self.http.cookies.clear()
        self.current = None
