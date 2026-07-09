from __future__ import annotations

import httpx

from .config import SrtConfig
from .http import SrtHttpClient
from .models import SrtSession
from .session import SrtSessionClient


class SrtClient:
    def __init__(self, config: SrtConfig | None = None, *, transport: httpx.BaseTransport | None = None) -> None:
        self.config = config or SrtConfig()
        self.http = SrtHttpClient(self.config, transport=transport)
        self.session = SrtSessionClient(self.http)

    def close(self) -> None:
        self.http.close()

    def login(self, login_id: str, password: str, *, login_type: str = "3") -> SrtSession:
        return self.session.login(login_id, password, login_type=login_type)

    def clear_session(self) -> None:
        self.session.clear_session()

    def logout(self) -> None:
        self.clear_session()
