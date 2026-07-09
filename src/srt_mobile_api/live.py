from __future__ import annotations

import os
from typing import Any

from .client import SrtClient
from .config import SrtConfig


def live_enabled() -> bool:
    return os.environ.get("SRT_MOBILE_API_LIVE") == "1"


def read_credentials_from_env() -> tuple[str, str]:
    login_id = os.environ.get("SRT_LOGIN_ID")
    password = os.environ.get("SRT_LOGIN_PASSWORD")
    if not login_id or not password:
        raise RuntimeError("SRT_LOGIN_ID and SRT_LOGIN_PASSWORD are required for live smoke")
    return login_id, password


def run_live_smoke_from_env() -> dict[str, Any]:
    if not live_enabled():
        raise RuntimeError("Set SRT_MOBILE_API_LIVE=1 to run live smoke")
    login_id, password = read_credentials_from_env()
    client = SrtClient(SrtConfig())
    try:
        session = client.login(login_id, password)
        notice = client.get_notice_list()
        tickets = client.get_ticket_list()
        return {
            "loggedIn": bool(session.user_map),
            "noticeCount": len(notice.get("noticeList") or []),
            "ticketTextPrefix": tickets.text[:80],
        }
    finally:
        client.close()
