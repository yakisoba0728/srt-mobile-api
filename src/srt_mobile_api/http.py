from __future__ import annotations

from typing import Any, Mapping

import httpx

from .config import SrtConfig
from .errors import SrtProtocolError
from .errors import SrtTransportError


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
    def _parse_json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SrtProtocolError("Expected JSON object but response body was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise SrtProtocolError("Expected JSON object but received a non-object JSON payload")
        return payload

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
        try:
            response = self._client.get(path, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return response.text

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
        try:
            response = self._client.get(path, params=params, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return self._parse_json_object(response)

    def get_text_url(self, url: str, *, referer: str | None = None) -> str:
        headers = {}
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        return response.text

    def post_form(
        self,
        path: str,
        data: Mapping[str, Any] | None = None,
        *,
        accept: str = "*/*",
        referer: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Accept": accept,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": self.config.base_url,
            "X-Requested-With": "XMLHttpRequest",
        }
        if referer:
            headers["Referer"] = referer
        try:
            response = self._client.post(path, data=dict(data or {}), headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SrtTransportError(str(exc)) from exc
        content_type = response.headers.get("content-type", "")
        if self._expects_json(accept) or self._is_json_content_type(content_type):
            return self._parse_json_object(response)
        return {"html": response.text}
