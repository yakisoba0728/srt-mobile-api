from srt_mobile_api.live import live_enabled, read_credentials_from_env


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SRT_MOBILE_API_LIVE", raising=False)
    assert live_enabled() is False


def test_live_enabled_only_with_explicit_flag(monkeypatch):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    assert live_enabled() is True


def test_credentials_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("SRT_LOGIN_ID", "member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", "pw")
    assert read_credentials_from_env() == ("member", "pw")
