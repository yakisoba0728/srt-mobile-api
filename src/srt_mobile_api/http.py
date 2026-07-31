"""HTTP 전송 계층 —— 요청이 실제로 나가는 유일한 지점.

:class:`SrtHttpClient` 는 ``httpx.Client`` 를 감싸면서 안전 규칙을 요청마다
적용합니다.

* 읽기(:meth:`~SrtHttpClient.get_text`, :meth:`~SrtHttpClient.get_json`,
  :meth:`~SrtHttpClient.post_form`, :meth:`~SrtHttpClient.post_html_form`)는
  :func:`~srt_mobile_api.safety.assert_read_only_request` 를 지납니다.
* 쓰기는 :meth:`~SrtHttpClient.post_mutation_form` 하나뿐이고, 동의·경로·
  카드비밀 검사를 통과해야 합니다.

``httpx`` 예외는 :class:`~srt_mobile_api.errors.SrtTransportError` 로 감싸고,
리다이렉트 목적지가 로그인이면
:class:`~srt_mobile_api.errors.SrtSessionExpiredError` 입니다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .config import APP_ORIGIN, NETFUNNEL_ORIGIN, SrtConfig
from .consent import (
    MutationCategory,
    MutationConsent,
    require_card_kind_claim,
    require_mutation_consent,
)
from .errors import (
    SrtAppError,
    SrtIpBlockedError,
    SrtMutationNotAllowedError,
    SrtProtocolError,
    SrtSessionExpiredError,
    SrtTransportError,
)
from .parsers import is_unauthenticated_page
from .safety import (
    SRT_LIVE_MUTATION_CATEGORIES,
    assert_mutation_route,
    assert_mutation_route_category,
    assert_no_card_secrets,
    assert_read_only_request,
)


LOGIN_PAGE_PATH = "/login/login.do"
LOGIN_API_PATH = "/apb/selectListApb01080_n.do"


def _is_login_redirect(request_url: httpx.URL, location: str) -> bool:
    """Location 헤더가 로그인 페이지를 가리키는지 판정."""
    if not location:
        return False
    try:
        target = request_url.join(location)
        port = target.port
    except (TypeError, ValueError):
        return False
    return (
        target.scheme == "https"
        and target.host == "app.srail.or.kr"
        and port in {None, 443}
        and not target.userinfo
        and target.path == LOGIN_PAGE_PATH
    )


def _check_redirect_and_status(
    request: httpx.Request, response: httpx.Response
) -> None:
    """리다이렉트·오류 상태를 공통 처리. 로그인 리다이렉트 → 세션 만료."""
    if response.is_redirect:
        location = response.headers.get("location", "")
        if _is_login_redirect(request.url, location):
            raise SrtSessionExpiredError("SRT session redirected to login")
        raise SrtTransportError(
            f"SRT HTTP {response.status_code} redirect for"
            f" {request.method} {request.url.path}"
        )
    if response.is_error:
        raise SrtTransportError(
            f"SRT HTTP {response.status_code} for"
            f" {request.method} {request.url.path}"
        )


class SrtHttpClient:
    """쿠키와 안전 검사를 함께 들고 다니는 HTTP 클라이언트.

    ``transport`` 는 테스트에서 가짜 응답을 물리기 위한 자리입니다.
    """

    def __init__(self, config: SrtConfig, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout,
            headers={"User-Agent": config.user_agent},
            transport=transport,
        )

    @property
    def cookies(self) -> httpx.Cookies:
        """쿠키 저장소. 로그인 세션(``JSESSIONID``)이 여기 있습니다."""
        return self._client.cookies

    def close(self) -> None:
        """연결 풀을 닫습니다."""
        self._client.close()

    @staticmethod
    def _is_json_content_type(content_type: str) -> bool:
        return "json" in content_type.lower()

    @staticmethod
    def _expects_json(accept: str) -> bool:
        return "json" in accept.lower()

    @staticmethod
    def _is_authenticated_login_form(response: httpx.Response) -> bool:
        """응답이 로그인 요구 페이지인지. 로그인 경로 자체는 제외."""
        # is_unauthenticated_page 는 두 모양을 감지: 로그인 폼 + 로그인 안내 스크립트.
        # 로그인 경로 자체(login.do, login API)는 정상적으로 로그인 페이지이므로 제외.
        return response.request.url.path not in {
            LOGIN_PAGE_PATH,
            LOGIN_API_PATH,
        } and is_unauthenticated_page(response.text, base_url=APP_ORIGIN)

    def _parse_json_object(self, response: httpx.Response) -> dict[str, Any]:
        """응답을 JSON 객체로 파싱. 실패 시 만료·IP차단·프로토콜 오류 분류."""
        try:
            payload = response.json()
        except ValueError:
            if self._is_authenticated_login_form(response):
                raise SrtSessionExpiredError(
                    "SRT authenticated request returned the login form",
                    raw=response.text,
                ) from None
            # IP 차단: 로그인 경로에서 non-JSON "Your IP Address Blocked" 응답.
            # SrtIpBlockedError ⊂ SrtAuthError 이므로 기존 except SrtAuthError 호환.
            if (
                response.request.url.path == LOGIN_API_PATH
                and "Your IP Address Blocked" in response.text
            ):
                raise SrtIpBlockedError(response.text.strip()) from None
            raise SrtProtocolError(
                "Expected JSON object but response body was not valid JSON"
            ) from None
        if not isinstance(payload, dict):
            raise SrtProtocolError("Expected JSON object but received a non-object JSON payload")
        return payload

    def _parse_text(self, response: httpx.Response) -> str:
        """응답을 텍스트로 반환. JSON content-type 이면 만료 검사 건너뜀."""
        content_type = response.headers.get("content-type", "")
        if self._is_json_content_type(content_type):
            try:
                response.json()
            except ValueError:
                pass
            else:
                return response.text
        if self._is_authenticated_login_form(response):
            raise SrtSessionExpiredError(
                "SRT authenticated request returned the login form",
                raw=response.text,
            )
        return response.text

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """읽기 전용 요청을 보내고 리다이렉트·오류를 처리."""
        request = self._client.build_request(method, url, params=params, data=data, headers=headers)
        assert_read_only_request(request, self.config)
        try:
            response = self._client.send(request)
        except httpx.HTTPError:
            raise SrtTransportError(
                f"SRT transport failed for {method.upper()} {request.url.path}"
            ) from None
        _check_redirect_and_status(request, response)
        return response

    # ── 읽기 메서드 ──

    def get_text(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        """읽기 GET → 문자열. 로그인 안내 페이지면 SrtSessionExpiredError."""
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self._request("GET", path, params=params, headers=headers)
        return self._parse_text(response)

    def get_json(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> dict[str, Any]:
        """읽기 GET → JSON 객체. 비-JSON 이면 SrtProtocolError."""
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self._request("GET", path, params=params, headers=headers)
        return self._parse_json_object(response)

    def get_text_url(self, url: str, *, referer: str | None = None) -> str:
        """절대 URL 로 읽기 GET —— NetFunnel 대기열 호스트용."""
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self._request("GET", url, headers=headers)
        return self._parse_text(response)

    def post_form(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        *,
        accept: str = "*/*",
        referer: str | None = None,
    ) -> dict[str, Any]:
        """읽기 POST(ajax 폼). accept/content-type 이 JSON 이면 JSON 객체,
        아니면 ``{"html": ...}`` 로 감싸 반환."""
        response = self._post_form_response(path, data, accept=accept, referer=referer)
        content_type = response.headers.get("content-type", "")
        if self._expects_json(accept) or self._is_json_content_type(content_type):
            return self._parse_json_object(response)
        return {"html": self._parse_text(response)}

    def _post_form_response(
        self,
        path: str,
        data: Mapping[str, Any] | None,
        *,
        accept: str,
        referer: str | None,
    ) -> httpx.Response:
        """ajax 헤더를 붙여 POST 를 보내는 공통 부분."""
        headers = {
            "Accept": accept,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.config.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        return self._request("POST", path, data=dict(data or {}), headers=headers)

    def post_html_form(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        """HTML 조각을 돌려주는 읽기 POST —— 선택기 화면용.

        JSON 이 돌아오면 오류: ``ErrorCode`` 비정상이면 SrtAppError, 그 외 SrtProtocolError.
        """
        response = self._post_form_response(
            path, data, accept="text/html, */*; q=0.01", referer=referer,
        )
        content_type = response.headers.get("content-type", "")
        if not self._is_json_content_type(content_type):
            return self._parse_text(response)
        try:
            payload = response.json()
        except ValueError:
            if self._is_authenticated_login_form(response):
                raise SrtSessionExpiredError(
                    "SRT authenticated request returned the login form",
                    raw=response.text,
                ) from None
            raise SrtProtocolError(
                "Expected selector HTML but received invalid JSON framing",
                raw=response.text,
            ) from None
        if not isinstance(payload, dict):
            raise SrtProtocolError(
                "Expected selector HTML but received non-object JSON framing",
                raw=payload,
            )
        error_code = payload.get("ErrorCode")
        if isinstance(error_code, str) and error_code not in {"", "0"}:
            message = payload.get("ErrorMsg")
            raise SrtAppError(
                error_code,
                message if isinstance(message, str) else str(message or ""),
                raw=payload,
            )
        raise SrtProtocolError(
            "Expected selector HTML but received JSON framing",
            raw=payload,
        )

    # ── 쓰기 메서드 ──

    def _send_mutation_request(
        self,
        path: str,
        *,
        category: MutationCategory,
        data: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        """mutation 요청의 실제 전송. 세 중첩 검사로 방어:
        1) category 가 live-enabled, 2) path 가 mutation route, 3) path/category 바인딩.
        """
        if category not in SRT_LIVE_MUTATION_CATEGORIES:
            raise SrtMutationNotAllowedError(
                f"SRT mutation category {category!r} is not live-enabled; only "
                "reserve, cancel, payment and refund may be transmitted (see "
                "safety.SRT_LIVE_MUTATION_CATEGORIES)"
            )
        assert_mutation_route("POST", path)
        assert_mutation_route_category(path, category)
        request = self._client.build_request("POST", path, data=dict(data), headers=headers)
        # payment 가 아닌 요청에 카드 필드가 있으면 거부 (route/category 로는 못 막는 경우).
        if category != "payment":
            assert_no_card_secrets(request)
        try:
            response = self._client.send(request)
        except httpx.HTTPError:
            raise SrtTransportError(
                f"SRT transport failed for POST {request.url.path}"
            ) from None
        _check_redirect_and_status(request, response)
        return response

    def post_mutation_form(
        self,
        path: str,
        data: Mapping[str, Any],
        *,
        consent: MutationConsent,
        category: MutationCategory,
        referer: str | None = None,
        accept: str = "application/json, text/javascript, */*; q=0.01",
    ) -> dict[str, Any]:
        """상태를 바꾸는 폼이 나가는 **유일한** 경로.

        관문:
        1. ``consent`` 에 해당 category 동의가 켜져 있어야 함.
        2. ``consent.dry_run`` 이 ``False`` 여야 함.
        3. ``category`` 가 SRT_LIVE_MUTATION_CATEGORIES 에 있어야 함.
        4. ``payment`` 면 fake_card_only / real_card_acknowledged 중 정확히 하나.
        5. 정규 출처 + path/category 바인딩.
        """
        require_mutation_consent(consent, category)
        if consent.dry_run:
            raise SrtMutationNotAllowedError(
                "post_mutation_form requires consent.dry_run=False; a dry-run "
                "preview must never be transmitted"
            )
        if category not in SRT_LIVE_MUTATION_CATEGORIES:
            raise SrtMutationNotAllowedError(
                f"SRT mutation category {category!r} is not live-enabled: only "
                "reserve, cancel, payment and refund may be transmitted, and "
                "each is in that set because a live run answered it (reserve "
                "and cancel 2026-07-25, payment and refund 2026-07-26). Adding "
                "a category requires verifying its wire format against the live "
                "server first. Use dry_run=True for a preview "
                "(see safety.SRT_LIVE_MUTATION_CATEGORIES)"
            )
        if category == "payment":
            require_card_kind_claim(consent)
        if (
            self.config.base_url != APP_ORIGIN
            or self.config.netfunnel_url != NETFUNNEL_ORIGIN
        ):
            raise SrtProtocolError(
                "SRT request configuration does not use canonical origins"
            )
        assert_mutation_route("POST", path)
        assert_mutation_route_category(path, category)
        if not isinstance(data, Mapping):
            raise SrtProtocolError("SRT mutation form data must be a mapping")
        headers = {
            "Accept": accept,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.config.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        response = self._send_mutation_request(
            path, category=category, data=data, headers=headers
        )
        return self._parse_json_object(response)
