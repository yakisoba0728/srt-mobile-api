from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

import srt_mobile_api
from srt_mobile_api import SrtConfig
from srt_mobile_api.errors import (
    SrtApiError,
    SrtAuthError,
    SrtNetFunnelError,
    SrtProtocolError,
    SrtSessionExpiredError,
)
from srt_mobile_api.models import (
    FareItem,
    FarePage,
    HtmlPage,
    MutualVerificationResult,
    NetFunnelToken,
    PassengerCounts,
    SeatSelectionPage,
    SrtSession,
    TimetablePage,
    TimetableRow,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)
from srt_mobile_api.payloads import TRAIN_GROUP_OPTIONS


def test_public_exports_are_available():
    assert srt_mobile_api.SrtConfig is SrtConfig
    assert issubclass(SrtAuthError, SrtApiError)
    assert issubclass(SrtProtocolError, SrtApiError)


def test_completed_error_hierarchy_is_public():
    assert issubclass(SrtSessionExpiredError, SrtAuthError)
    error = SrtNetFunnelError("NET000001", "refresh required")
    assert error.code == "NET000001"
    assert error.message == "refresh required"
    assert srt_mobile_api.SrtNetFunnelError is SrtNetFunnelError
    assert srt_mobile_api.SrtSessionExpiredError is SrtSessionExpiredError


def test_core_models_are_dataclasses():
    assert is_dataclass(SrtConfig)
    assert is_dataclass(SrtSession)
    assert is_dataclass(PassengerCounts)
    assert is_dataclass(TrainSearchQuery)
    assert is_dataclass(TrainSummary)
    assert is_dataclass(TrainSearchResult)
    assert is_dataclass(HtmlPage)
    assert is_dataclass(TimetableRow)
    assert is_dataclass(TimetablePage)
    assert is_dataclass(FareItem)
    assert is_dataclass(FarePage)
    assert issubclass(TimetablePage, HtmlPage)
    assert issubclass(FarePage, HtmlPage)


def test_structured_page_models_are_exported():
    assert srt_mobile_api.TimetableRow is TimetableRow
    assert srt_mobile_api.TimetablePage is TimetablePage
    assert srt_mobile_api.FareItem is FareItem
    assert srt_mobile_api.FarePage is FarePage


def test_config_defaults_match_design():
    config = SrtConfig()
    assert config.base_url == "https://app.srail.or.kr"
    assert config.netfunnel_url == "https://nf.letskorail.com:443"
    assert "SRT-APP-Android V.2.0.41" in config.user_agent
    assert config.device_key == "0123456789ABCDEF"
    assert config.live_env_var == "SRT_MOBILE_API_LIVE"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("base_url", "app.srail.or.kr"),
        ("base_url", "http://app.srail.or.kr"),
        ("base_url", "https://collector.example"),
        ("base_url", "https://member:secret@app.srail.or.kr"),
        ("base_url", "https://app.srail.or.kr:444"),
        ("base_url", "https://app.srail.or.kr/"),
        ("base_url", "https://app.srail.or.kr/main"),
        ("base_url", "https://app.srail.or.kr?mode=test"),
        ("base_url", "https://app.srail.or.kr#fragment"),
        ("netfunnel_url", "ftp://nf.letskorail.com"),
        ("netfunnel_url", "http://nf.letskorail.com:443"),
        ("netfunnel_url", "https://collector.example:443"),
        ("netfunnel_url", "https://member:secret@nf.letskorail.com:443"),
        ("netfunnel_url", "https://nf.letskorail.com:444"),
        ("netfunnel_url", "https://nf.letskorail.com:bad"),
        ("netfunnel_url", "https://nf.letskorail.com:443/ts.wseq"),
        ("netfunnel_url", "https://nf.letskorail.com:443?mode=test"),
        ("netfunnel_url", "https://nf.letskorail.com:443#fragment"),
    ],
)
def test_config_rejects_noncanonical_origins(field_name, value):
    with pytest.raises(ValueError):
        SrtConfig(**{field_name: value})


def test_config_normalizes_equivalent_default_https_ports():
    config = SrtConfig(
        base_url="https://app.srail.or.kr:443",
        netfunnel_url="https://nf.letskorail.com",
    )
    assert config.base_url == "https://app.srail.or.kr"
    assert config.netfunnel_url == "https://nf.letskorail.com:443"


@pytest.mark.parametrize("kwargs", [{"device_key": ""}, {"timeout": 0}])
def test_config_rejects_invalid_device_or_timeout(kwargs):
    with pytest.raises(ValueError):
        SrtConfig(**kwargs)


def test_passenger_counts_reject_empty_or_negative_totals():
    with pytest.raises(ValueError):
        PassengerCounts(adult=0)
    with pytest.raises(ValueError):
        PassengerCounts(adult=-1)


def test_passenger_counts_has_no_infant_type():
    # B2: SRT has exactly five passenger types (psgTpCd 1..5); there is no infant type
    # (`infantCnt` appears nowhere in the app). `.total` must equal the sum of the five
    # types so totPrnb == sum(psgInfoPerPrnb1..5) holds everywhere.
    with pytest.raises(TypeError):
        PassengerCounts(adult=1, infant=1)  # type: ignore[call-arg]
    counts = PassengerCounts(
        adult=1, child=2, senior=3, disability_1_to_3=4, disability_4_to_6=5
    )
    assert counts.total == 15


@pytest.mark.parametrize(
    "kwargs",
    [
        {"adult": True},
        {"adult": 1, "child": False},
    ],
)
def test_passenger_counts_reject_boolean_values(kwargs):
    with pytest.raises(ValueError, match="non-negative integers"):
        PassengerCounts(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"departure_station_code": "", "arrival_station_code": "0020", "departure_date": "20260710"},
        {"departure_station_code": "0551", "arrival_station_code": "", "departure_date": "20260710"},
        {"departure_station_code": "0551", "arrival_station_code": "0020", "departure_date": "2026-07-10"},
        {
            "departure_station_code": "0551",
            "arrival_station_code": "0020",
            "departure_date": "20260710",
            "departure_time": "60000",
        },
        {
            "departure_station_code": "0551",
            "arrival_station_code": "0020",
            "departure_date": "20260710",
            "train_group_code": "unknown",
        },
    ],
)
def test_search_query_rejects_invalid_contract(kwargs):
    with pytest.raises(ValueError):
        TrainSearchQuery(**kwargs)


def test_search_query_defaults_train_group_to_the_apps_booking_screen_default():
    # The app's booking screen loads on 전체, seeded twice: ara0101v.js:85-86
    # sets $("#btn_trnGpCd").val("109") with text "전체" (its own comment reads
    # "300: SRT, 900: KTX+SRT, 109: 전체"), and :98-99 seeds trnGpCd1="109" /
    # trnGpNm1="전체". All three codes are legitimate on the wire, so this pins a
    # default CHOICE, not a wire fix -- and it is the same "109" that
    # SrtClient.get_train_group_selector and train_group_selector_payload have
    # always defaulted to.
    query = TrainSearchQuery("0551", "0020", "20260710")

    assert query.train_group_code == "109"
    # The paired 역무차종별코드 the app seeds alongside it (ara0101v.js:87,
    # stlbTrnClsfCd1 "05" = 전체).
    assert TRAIN_GROUP_OPTIONS[query.train_group_code] == ("전체", "05")
    # The other two stay constructible: this changes which is default, nothing else.
    for code in ("300", "900"):
        assert (
            TrainSearchQuery(
                "0551", "0020", "20260710", train_group_code=code
            ).train_group_code
            == code
        )


def test_search_query_accepts_optional_station_names():
    query = TrainSearchQuery(
        "0551",
        "0020",
        "20260710",
        departure_station_name="Suseo",
        arrival_station_name="Busan",
    )
    assert query.departure_station_name == "Suseo"
    assert query.arrival_station_name == "Busan"


def test_preexisting_dataclass_field_order_matches_baseline():
    expected_prefixes = {
        SrtConfig: [
            "base_url",
            "netfunnel_url",
            "user_agent",
            "device_key",
            "timeout",
            "live_env_var",
        ],
        SrtSession: ["login_id", "user_map"],
        PassengerCounts: [
            "adult",
            "child",
            "senior",
            "disability_1_to_3",
            "disability_4_to_6",
        ],
        NetFunnelToken: ["action", "key", "raw_type", "code", "params"],
        TrainSearchQuery: [
            "departure_station_code",
            "arrival_station_code",
            "departure_date",
            "departure_time",
            "passengers",
            "train_group_code",
            "seat_attr_code",
        ],
        TrainSummary: [
            "train_no",
            "train_group_code",
            "service_class_code",
            "run_date",
            "departure_date",
            "departure_time",
            "arrival_date",
            "arrival_time",
            "departure_station_code",
            "arrival_station_code",
            "raw",
        ],
        TrainSearchResult: ["trains", "result", "raw"],
        HtmlPage: ["text", "raw"],
    }
    for model, expected in expected_prefixes.items():
        assert [field.name for field in fields(model)][: len(expected)] == expected


def test_train_summary_legacy_positional_raw_argument_remains_compatible():
    raw = {"legacy": "row"}
    train = TrainSummary(
        "303",
        "300",
        "17",
        "20260710",
        "20260710",
        "060000",
        "20260710",
        "083000",
        "0551",
        "0020",
        raw,
    )
    assert train.raw is raw
    assert train.departure_station_name is None
    assert train.arrival_station_name is None


def test_sensitive_and_raw_model_fields_are_hidden_from_repr():
    session = SrtSession("login-secret", {"cookie": "cookie-secret"})
    token = NetFunnelToken("act_10", "key-secret", "5101", "5101", {"key": "key-secret"})
    train = TrainSummary("303", raw={"secret": "train-raw"})
    result = TrainSearchResult([train], raw={"secret": "search-raw"})
    page = HtmlPage(text="parsed", raw="html-raw")
    seat_page = SeatSelectionPage(text="좌석선택", raw="seat-page-secret")
    assert "seat-page-secret" not in repr(seat_page)
    for value, secret in (
        (session, "login-secret"),
        (token, "key-secret"),
        (train, "train-raw"),
        (result, "search-raw"),
        (page, "html-raw"),
    ):
        assert secret not in repr(value)


def test_html_page_has_text_and_raw_fields():
    page = HtmlPage(text="parsed", raw="<html></html>")
    assert page.text == "parsed"
    assert page.raw == "<html></html>"
    TimetablePage,
    TimetableRow,


def test_mutual_verification_model_is_frozen_and_repr_safe():
    value = MutualVerificationResult(
        message_code="IRZ000008",
        status="SUCC",
        message="mutual-secret",
        verification_code="mutual-secret",
        raw={"mutMrkVrfCd": "mutual-secret"},
    )
    assert is_dataclass(value)
    assert value.message == "mutual-secret"
    assert "mutual-secret" not in repr(value)
    with pytest.raises(FrozenInstanceError):
        value.status = "FAIL"
