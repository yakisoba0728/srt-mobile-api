from __future__ import annotations

from typing import Any, Mapping

import httpx

from .config import SrtConfig
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
        return response.json()

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
        if "json" in content_type:
            return response.json()
        try:
            return response.json()
        except ValueError:
            return {"html": response.text}
