from __future__ import annotations

from typing import Any, Mapping

import httpx

from .config import APP_ORIGIN, NETFUNNEL_ORIGIN, SrtConfig
from .consent import (
    MutationConsent,
    require_card_kind_claim,
    require_mutation_consent,
)
from .errors import (
    SrtAppError,
    SrtAuthError,
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
        return self._client.cookies

    def close(self) -> None:
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
            raise SrtProtocolError("Expected JSON object but response body was not valid JSON") from None
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
            raise SrtTransportError(f"SRT HTTP {response.status_code} for {method.upper()} {request.url.path}")
        return response

    def get_text(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        referer: str | None = None,
    ) -> str:
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
        headers = {}
        if referer:
            headers["Referer"] = referer
        response = self._request("GET", path, params=params, headers=headers)
        return self._parse_json_object(response)

    def get_text_url(self, url: str, *, referer: str | None = None) -> str:
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
        category: str,
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
        #     exactly {"reserve", "cancel"}, so this refuses payment and refund
        #     outright.
        #   * the path is one of the four registered mutation routes, so this
        #     function cannot be repurposed to POST an arbitrary endpoint.
        #   * the path BELONGS to that category. Without this one the first
        #     check is not sufficient: category="reserve" (live-enabled) paired
        #     with the payment route would build and send a POST to
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
                "reserve and cancel may be transmitted (see "
                "safety.SRT_LIVE_MUTATION_CATEGORIES)"
            )
        assert_mutation_route("POST", path)
        assert_mutation_route_category(path, category)
        request = self._client.build_request(
            "POST", path, data=dict(data), headers=headers
        )
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
        category: str,
        referer: str | None = None,
        accept: str = "application/json, text/javascript, */*; q=0.01",
    ) -> dict[str, Any]:
        """The sole send path for a state-changing form.

        This is the only method that can transmit to a mutation route. Gates are
        applied in this order, and a call must clear all of them:

        1. ``require_mutation_consent(consent, category)`` — a
           :class:`~srt_mobile_api.consent.MutationConsent` with the matching
           per-category opt-in must be supplied.
        2. ``consent.dry_run`` must be ``False`` — a dry-run preview must never
           be transmitted.
        3. ``category`` must be a member of
           :data:`~srt_mobile_api.safety.SRT_LIVE_MUTATION_CATEGORIES` — the
           live-enablement block.
        4. a ``payment`` also requires an unambiguous card-kind claim —
           exactly one of ``consent.fake_card_only`` (a non-chargeable test
           card) or ``consent.real_card_acknowledged`` (an acknowledged real
           charge); neither and both are refused
           (:func:`~srt_mobile_api.consent.require_card_kind_claim`).
        5. the client config must use the canonical origins, and
           ``assert_mutation_route`` + ``assert_mutation_route_category``
           restrict the target to
           :data:`~srt_mobile_api.safety.SRT_MUTATION_ROUTES` for exactly that
           category.

        Gate 3 is the decisive one: ``SRT_LIVE_MUTATION_CATEGORIES`` holds
        exactly ``{"reserve", "cancel"}``. So **``payment`` and ``refund`` are
        refused here unconditionally** with
        :class:`~srt_mobile_api.errors.SrtMutationNotAllowedError`, no matter how
        permissive the consent is, while a consented, non-dry-run ``reserve`` or
        ``cancel`` proceeds to the wire. ``_send_mutation_request``, the function
        that actually calls ``send``, independently re-asserts all of gate 3 and
        gate 5 — membership, ``assert_mutation_route`` and
        ``assert_mutation_route_category`` — so both the payment/refund refusal
        and the route/category binding hold at the true send boundary, and an
        enabled category cannot be pointed at another category's route there.
        Meanwhile the read-only path
        (:func:`~srt_mobile_api.safety.assert_read_only_request`) refuses all
        four routes by allowlist, so a mutation can only ever travel this
        method.

        For an enabled category, ``data`` (which includes the reserve payload's
        ``netfunnelKey``) is sent verbatim via the same request mechanics as
        :meth:`post_form`, with no read-only field allowlist applied, returning
        the parsed JSON object response.
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
        # transmit. SRT_LIVE_MUTATION_CATEGORIES holds {"reserve", "cancel"},
        # so this is what refuses payment and refund at the transport layer
        # rather than merely by the absence of a client method.
        if category not in SRT_LIVE_MUTATION_CATEGORIES:
            raise SrtMutationNotAllowedError(
                f"SRT mutation category {category!r} is not live-enabled: only "
                "reserve and cancel may be transmitted, because they are the "
                "two halves of one reversible operation. Enabling payment or "
                "refund requires implementing it (neither has a client method) "
                "AND verifying its wire format live; a payment additionally "
                "transmits a PAN in the clear. Use dry_run=True for a preview "
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
        # This sits BEHIND the live-enablement block above deliberately. Today
        # "payment" never gets this far — gate 3 refuses it first, and the
        # "not live-enabled" refusal is the more informative one to surface, so
        # the ordering is not an oversight. The check is kept current anyway so
        # that opening the switch does not silently arrive with an unguarded
        # PAN.
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
