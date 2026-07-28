"""HTTP 전송 계층 —— 요청이 실제로 나가는 유일한 지점.

:class:`SrtHttpClient` 는 ``httpx.Client`` 를 감싸면서 이 라이브러리의 안전
규칙을 요청 하나하나에 적용한다. 읽기와 쓰기가 서로 다른 문으로 나간다:

* 읽기(:meth:`~SrtHttpClient.get_text`, :meth:`~SrtHttpClient.get_json`,
  :meth:`~SrtHttpClient.post_form`, :meth:`~SrtHttpClient.post_html_form`)는
  :func:`~srt_mobile_api.safety.assert_read_only_request` 를 지난다. 등록된
  읽기 경로가 아니면 나가지 못한다.
* 쓰기는 :meth:`~SrtHttpClient.post_mutation_form` 하나뿐이고, 동의·경로·
  카드비밀 검사를 통과해야 한다.

전송 실패는 :class:`~srt_mobile_api.errors.SrtTransportError` 로 바뀐다.
``httpx`` 예외가 밖으로 새지 않는다. 리다이렉트는 따라가지 않는다 —— 목적지가
로그인 페이지면 :class:`~srt_mobile_api.errors.SrtSessionExpiredError`, 아니면
역시 전송 오류다. 세션이 끊긴 뒤 서버가 HTTP 200 에 로그인 안내 페이지를 실어
보내는 경우도 응답 본문을 보고 같은 예외로 바꾼다.
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


class SrtHttpClient:
    """쿠키와 안전 검사를 함께 들고 다니는 HTTP 클라이언트.

    ``config`` 의 ``base_url``·``timeout``·``user_agent`` 로 ``httpx.Client`` 를
    만든다. ``transport`` 는 테스트에서 가짜 응답을 물리기 위한 자리이고,
    실제 사용에서는 넘기지 않는다.

    로그인 세션은 :attr:`cookies` 에 산다. 다 쓰면 :meth:`close` 를 부른다 ——
    :class:`~srt_mobile_api.client.SrtClient` 를 ``with`` 로 쓰면 대신 해 준다.
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
        """이 클라이언트의 쿠키 저장소. 로그인 세션(``JSESSIONID``)이 여기 있다."""
        return self._client.cookies

    def close(self) -> None:
        """연결 풀을 닫는다. 이후의 요청은 실패한다."""
        self._client.close()

    @staticmethod
    def _is_json_content_type(content_type: str) -> bool:
        return "json" in content_type.lower()

    @staticmethod
    def _expects_json(accept: str) -> bool:
        return "json" in accept.lower()

    @staticmethod
    def _is_authenticated_login_form(response: httpx.Response) -> bool:
        # is_unauthenticated_page, not is_login_form: the live server answers an
        # expired authenticated read with the login-REDIRECT page (HTTP 200, no
        # login form on it at all), which is_login_form cannot see. The two login
        # paths stay excluded — the login page legitimately IS a login page.
        return response.request.url.path not in {
            LOGIN_PAGE_PATH,
            LOGIN_API_PATH,
        } and is_unauthenticated_page(response.text, base_url=APP_ORIGIN)

    def _parse_json_object(self, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            if self._is_authenticated_login_form(response):
                raise SrtSessionExpiredError(
                    "SRT authenticated request returned the login form",
                    raw=response.text,
                ) from None
            # An IP block on the login endpoint returns a non-JSON plain-text body (e.g.
            # "Your IP Address Blocked ..."). srtgo surfaces this as a login failure
            # (srt.py:719-720: if "Your IP Address Blocked" in r.text -> SRTLoginError).
            # Classify it as an auth error -- not a generic protocol error -- so callers
            # catching SrtAuthError from login() see it, with the block reason preserved.
            #
            # SrtIpBlockedError refines that: it SUBCLASSES SrtAuthError, so every
            # existing `except SrtAuthError` around login() is unaffected, while a
            # caller that wants to tell "this network is banned" (waiting or changing
            # egress is the only fix) from "these credentials are wrong" (re-prompt the
            # user) no longer has to substring-match an English infrastructure message.
            # This is the one place in the taxonomy that classifies on text, because the
            # response is not an app response at all: no msgCd, no JSON, no envelope.
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
        request = self._client.build_request(method, url, params=params, data=data, headers=headers)
        assert_read_only_request(request, self.config)
        try:
            response = self._client.send(request)
        except httpx.HTTPError:
            raise SrtTransportError(
                f"SRT transport failed for {method.upper()} {request.url.path}"
            ) from None
        if response.is_redirect:
            location = response.headers.get("location", "")
            if _is_login_redirect(request.url, location):
                raise SrtSessionExpiredError("SRT session redirected to login")
            raise SrtTransportError(
                f"SRT HTTP {response.status_code} redirect for {method.upper()} {request.url.path}"
            )
        if response.is_error:
            raise SrtTransportError(
                f"SRT HTTP {response.status_code} for {method.upper()} {request.url.path}"
            )
        return response

    def get_text(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        """읽기 GET 을 보내고 응답 본문을 문자열 그대로 돌려준다.

        본문이 로그인 안내 페이지면
        :class:`~srt_mobile_api.errors.SrtSessionExpiredError` 다. 단, 서버가
        JSON content-type 으로 유효한 JSON 을 보냈으면 그 검사를 건너뛰고 원문을
        그대로 준다.
        """
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
        """읽기 GET 을 보내고 JSON 객체로 해석한다.

        본문이 JSON 이 아니면 :class:`~srt_mobile_api.errors.SrtProtocolError`,
        로그인 안내 페이지면 :class:`~srt_mobile_api.errors.SrtSessionExpiredError`
        다. 최상위가 객체가 아닌 JSON(배열 등)도 프로토콜 오류로 거른다.
        """
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self._request("GET", path, params=params, headers=headers)
        return self._parse_json_object(response)

    def get_text_url(self, url: str, *, referer: str | None = None) -> str:
        """절대 URL 로 읽기 GET 을 보낸다 —— NetFunnel 대기열 호스트용이다.

        :meth:`get_text` 와 같은 처리를 하되 경로가 아니라 URL 을 받는다. 허용
        출처는 여전히 :func:`~srt_mobile_api.safety.assert_read_only_request` 가
        정한 두 곳뿐이다.
        """
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
        """읽기 POST(ajax 폼)를 보낸다. 상태를 바꾸는 요청은 여기로 못 나간다.

        앱의 ajax 헤더(``X-Requested-With``, ``Origin``, 폼 content-type)를 붙여
        보내고, ``accept`` 또는 응답 content-type 이 JSON 이면 JSON 객체를,
        아니면 본문을 ``{"html": ...}`` 로 감싸 돌려준다.

        경로는 :func:`~srt_mobile_api.safety.assert_read_only_request` 의 허용
        목록에 있어야 한다. 예약·취소·결제·환불 경로는 그 목록에 없으므로 이
        메서드로는 보낼 수 없고 :meth:`post_mutation_form` 만이 보낼 수 있다.
        """
        response = self._post_form_response(
            path,
            data,
            accept=accept,
            referer=referer,
        )
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
        headers = {
            "Accept": accept,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.config.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        return self._request("POST", path, data=dict(data or {}), headers=headers)

    def _send_mutation_request(
        self,
        path: str,
        *,
        category: MutationCategory,
        data: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> httpx.Response:
        # Mirrors _request's transport/redirect/error handling, but WITHOUT
        # assert_read_only_request (which would reject a mutation route). The
        # consent and dry-run gating happens in post_mutation_form before we
        # reach here.
        #
        # Defense in depth: this is the function that actually calls
        # self._client.send, i.e. the true send boundary, so it re-asserts the
        # WHOLE route invariant itself rather than trusting its caller — not
        # just the category half. Three checks, and all three must hold:
        #
        #   * the category is live-enabled. SRT_LIVE_MUTATION_CATEGORIES holds
        #     the four live-verified categories, so this refuses anything else
        #     outright.
        #   * the path is one of the four registered mutation routes, so this
        #     function cannot be repurposed to POST an arbitrary endpoint.
        #   * the path BELONGS to that category. Without this one the first
        #     check is not sufficient: category="reserve" paired with the
        #     payment route would build and send a POST to
        #     /ata/selectListAta09036_n.do, carrying whatever `data` held —
        #     which for a payment is a PAN in the clear. The route/category
        #     binding used to live only in post_mutation_form, so a direct call
        #     here bypassed it entirely.
        #
        # No future refactor of post_mutation_form can therefore widen either
        # the categories or the routes that reach the wire.
        if category not in SRT_LIVE_MUTATION_CATEGORIES:
            raise SrtMutationNotAllowedError(
                f"SRT mutation category {category!r} is not live-enabled; only "
                "reserve, cancel, payment and refund may be transmitted (see "
                "safety.SRT_LIVE_MUTATION_CATEGORIES)"
            )
        assert_mutation_route("POST", path)
        assert_mutation_route_category(path, category)
        request = self._client.build_request(
            "POST", path, data=dict(data), headers=headers
        )
        # Stated on the DATA, not on the route, and therefore catching the one
        # case no route/category rule could: a hand-assembled payment body
        # posted to the live-enabled RESERVE route under a valid
        # category="reserve" consent. That is neither a category violation nor a
        # route violation, so nothing above refuses it. See
        # safety.CARD_SECRET_FIELDS.
        if category != "payment":
            assert_no_card_secrets(request)
        try:
            response = self._client.send(request)
        except httpx.HTTPError:
            raise SrtTransportError(
                f"SRT transport failed for POST {request.url.path}"
            ) from None
        if response.is_redirect:
            location = response.headers.get("location", "")
            if _is_login_redirect(request.url, location):
                raise SrtSessionExpiredError("SRT session redirected to login")
            raise SrtTransportError(
                f"SRT HTTP {response.status_code} redirect for POST {request.url.path}"
            )
        if response.is_error:
            raise SrtTransportError(
                f"SRT HTTP {response.status_code} for POST {request.url.path}"
            )
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

        통과해야 할 관문은 다섯이고 순서대로 적용된다. 하나라도 걸리면
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError` 또는
        :class:`~srt_mobile_api.errors.SrtProtocolError` 다.

        1. ``category`` 에 해당하는 개별 동의가 켜진
           :class:`~srt_mobile_api.consent.MutationConsent` 여야 한다.
        2. ``consent.dry_run`` 이 ``False`` 여야 한다. 미리보기는 전송되지
           않는다.
        3. ``category`` 가 :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES`
           —— ``reserve``·``cancel``·``payment``·``refund`` —— 에 있어야 한다.
           동의가 아무리 넓어도 이 넷 밖은 전송되지 않는다.
        4. ``payment`` 는 카드 종류를 명확히 밝혀야 한다. ``fake_card_only``
           (청구되지 않는 시험카드)와 ``real_card_acknowledged``(실제 청구를
           인지) 중 **정확히 하나**여야 하고, 둘 다이거나 둘 다 아니면 거부다
           (:func:`~srt_mobile_api.consent.require_card_kind_claim`).
        5. 설정이 정규 출처여야 하고, 경로는
           :data:`~srt_mobile_api.safety.SRT_MUTATION_ROUTES` 중 **그
           category 에 묶인** 것이어야 한다.

        3번과 5번은 실제로 ``send`` 를 부르는 ``_send_mutation_request`` 가 한 번
        더 검사한다. 카테고리를 다른 카테고리의 경로로 겨눌 수 없고, ``payment``
        가 아닌 요청의 본문에 카드 필드가 들어 있으면
        :func:`~srt_mobile_api.safety.assert_no_card_secrets` 가 막는다 ——
        정당한 ``reserve`` 동의에 손으로 만든 결제 본문을 태우는 경우가 그것이다.

        반대편 문인 :func:`~srt_mobile_api.safety.assert_read_only_request` 는 이
        네 경로를 허용 목록에서 빼 놓았다. 그래서 상태 변경은 이 메서드로만
        나간다.

        관문을 다 지나면 ``data`` 는 손대지 않고 그대로 나간다 —— 읽기 쪽처럼
        필드를 걸러 내지 않는다. 반환은 파싱된 JSON 객체다.
        """
        require_mutation_consent(consent, category)
        if consent.dry_run:
            raise SrtMutationNotAllowedError(
                "post_mutation_form requires consent.dry_run=False; a dry-run "
                "preview must never be transmitted"
            )
        # Live-enablement block. Placed after the consent and dry-run gates (so
        # those keep their meaning and their error messages) but before every
        # check below, because from here on a call would otherwise actually
        # transmit. SRT_LIVE_MUTATION_CATEGORIES holds the four categories whose
        # wire format a live run has answered, so this is what refuses anything
        # else at the transport layer rather than merely by the absence of a
        # client method.
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
        # Defense-in-depth at the transmit boundary: a payment carries the PAN
        # in the clear, so the send gate itself refuses to transmit one unless
        # the consent states, unambiguously, WHICH kind of card it is — exactly
        # one of fake_card_only (a test card) or real_card_acknowledged (a real
        # charge). See consent.require_card_kind_claim, which SrtClient.
        # pay_with_card also calls before it reaches this method, so the claim
        # is enforced at the public entry point AND again here at the layer that
        # actually sends.
        #
        # This sits BEHIND the live-enablement block above deliberately: a
        # category that may not be transmitted at all should say so first. Since
        # 2026-07-26 "payment" clears gate 3, so this is now the gate that
        # actually decides whether a PAN goes out — exactly what it was kept
        # current for while the switch was shut.
        if category == "payment":
            require_card_kind_claim(consent)
        # Canonical-origin safety, matching the read-only guard's requirement.
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

    def post_html_form(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
        """HTML 조각을 돌려주는 읽기 POST —— 역·날짜 같은 선택기 화면용이다.

        ``Accept: text/html`` 로 보내고 본문을 그대로 돌려준다.

        **JSON 이 돌아오면 그것은 언제나 오류다.** 이 경로들은 성공하면 HTML 을
        준다. ``ErrorCode`` 가 ``""``/``"0"`` 이 아닌 JSON 은
        :class:`~srt_mobile_api.errors.SrtAppError` 로, 그 밖의 JSON 은
        :class:`~srt_mobile_api.errors.SrtProtocolError` 로 올린다.
        """
        response = self._post_form_response(
            path,
            data,
            accept="text/html, */*; q=0.01",
            referer=referer,
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
