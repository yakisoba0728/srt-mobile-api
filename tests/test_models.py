from dataclasses import is_dataclass

import srt_mobile_api
from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import SrtApiError, SrtAuthError, SrtProtocolError
from srt_mobile_api.models import (
    HtmlPage,
    PassengerCounts,
    SrtSession,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)


def test_public_exports_are_available():
    assert srt_mobile_api.SrtConfig is SrtConfig
    assert issubclass(SrtAuthError, SrtApiError)
    assert issubclass(SrtProtocolError, SrtApiError)


def test_core_models_are_dataclasses():
    assert is_dataclass(SrtConfig)
    assert is_dataclass(SrtSession)
    assert is_dataclass(PassengerCounts)
    assert is_dataclass(TrainSearchQuery)
    assert is_dataclass(TrainSummary)
    assert is_dataclass(TrainSearchResult)
    assert is_dataclass(HtmlPage)


def test_config_defaults_match_design():
    config = SrtConfig()
    assert config.base_url == "https://app.srail.or.kr"
    assert config.netfunnel_url == "https://nf.letskorail.com:443"
    assert "SRT-APP-Android V.2.0.41" in config.user_agent
    assert config.device_key == "0123456789ABCDEF"
    assert config.live_env_var == "SRT_MOBILE_API_LIVE"


def test_html_page_has_text_and_raw_fields():
    page = HtmlPage(text="parsed", raw="<html></html>")
    assert page.text == "parsed"
    assert page.raw == "<html></html>"
