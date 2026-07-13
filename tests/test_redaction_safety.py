from srt_mobile_api.errors import SrtAppError, SrtAuthError, SrtNetFunnelError, SrtProtocolError
from srt_mobile_api.models import (
    HtmlPage,
    NetFunnelToken,
    SearchPageState,
    SrtSession,
    TrainSearchResult,
)
from srt_mobile_api.redaction import redact_mapping, redact_text, redact_url, redact_value
from srt_mobile_api.safety import EXCLUDED_API_DOMAINS


def test_redact_mapping_masks_sensitive_values():
    data = {
        "srchDvNm": "login-id",
        "hmpgPwdCphd": "password",
        "netfunnelKey": "NF",
        "cookie": "abc",
        "set-cookie": "def",
        "pnrNo": "123456789012",
        "safe": "value",
    }
    redacted = redact_mapping(data)
    assert redacted["srchDvNm"] == "[REDACTED]"
    assert redacted["hmpgPwdCphd"] == "[REDACTED]"
    assert redacted["netfunnelKey"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["set-cookie"] == "[REDACTED]"
    assert redacted["pnrNo"] == "[REDACTED]"
    assert redacted["safe"] == "value"


def test_redact_text_masks_card_like_values():
    assert "411111" not in redact_text("card 4111-1111-1111-1111")


def test_redact_text_masks_form_and_json_quoted_sensitive_assignments():
    cases = (
        ("hmpgPwdCphd=password-secret", "password-secret"),
        ('{"hmpgPwdCphd": "password-secret"}', "password-secret"),
        ("{'netfunnelKey': 'key-secret'}", "key-secret"),
        ('{"pnrNo":"pnr-secret"}', "pnr-secret"),
        ("prefix PASSWORD : password-secret suffix", "password-secret"),
    )
    for value, secret in cases:
        redacted = redact_text(value)
        assert secret not in redacted
        assert "[REDACTED]" in redacted


def test_redact_url_masks_userinfo_and_sensitive_query_values():
    redacted = redact_url(
        "https://member-secret:password-secret@host/path?netfunnelKey=key-secret&safe=1"
    )
    for secret in ("member-secret", "password-secret", "key-secret"):
        assert secret not in redacted
    assert "safe=1" in redacted


def test_recursive_redaction_is_case_insensitive():
    redacted = redact_mapping(
        {
            "outer": [
                {
                    "HMPGPWDCphd": "password-secret",
                    "url": "https://host/path?netfunnelKey=key-secret&safe=1",
                }
            ]
        }
    )
    assert redacted["outer"][0]["HMPGPWDCphd"] == "[REDACTED]"
    assert "key-secret" not in redacted["outer"][0]["url"]
    assert "safe=1" in redacted["outer"][0]["url"]


def test_redaction_handles_urls_sessions_tuples_and_dataclasses():
    value = (
        "JSESSIONID=session-secret",
        NetFunnelToken("act_10", "key-secret", "5101", "5101"),
    )
    redacted = redact_value(value)
    assert isinstance(redacted, tuple)
    assert "session-secret" not in redacted[0]
    assert redacted[1]["key"] == "[REDACTED]"
    assert "key-secret" not in repr(redacted)
    assert redact_url("https://host/path?safe=1") == "https://host/path?safe=1"


def test_secrets_do_not_appear_in_model_or_exception_repr():
    token = NetFunnelToken("act_10", "key-secret", "5101", "5101")
    session = SrtSession("login-secret", {"cookie": "cookie-secret"})
    app_error = SrtAppError("ERR", "card 4111-1111-1111-1111")
    net_error = SrtNetFunnelError("NET000001", "https://host/path?netfunnelKey=key-secret")
    assert "key-secret" not in repr(token)
    assert "login-secret" not in repr(session)
    assert "4111" not in str(app_error)
    assert "key-secret" not in str(net_error)


def test_all_public_exception_messages_are_sanitized():
    auth_error = SrtAuthError('login failed {"hmpgPwdCphd":"password-secret"}')
    protocol_error = SrtProtocolError(
        "bad response https://member-secret:password-secret@host/path?pnrNo=pnr-secret"
    )
    for error, secrets in (
        (auth_error, ("password-secret",)),
        (protocol_error, ("member-secret", "password-secret", "pnr-secret")),
    ):
        rendered = f"{error!s}\n{error!r}"
        for secret in secrets:
            assert secret not in rendered


def test_parsed_content_remains_accessible_but_is_hidden_from_repr():
    page = HtmlPage(text="ticket password-secret", raw="<html>password-secret</html>")
    result = TrainSearchResult(
        trains=[],
        result={"netfunnelKey": "key-secret"},
        raw={"pnrNo": "pnr-secret"},
    )
    state = SearchPageState(
        hidden_fields={"hmpgPwdCphd": "password-secret"},
        raw="<html>password-secret</html>",
    )
    assert page.text == "ticket password-secret"
    assert result.result["netfunnelKey"] == "key-secret"
    assert state.hidden_fields["hmpgPwdCphd"] == "password-secret"
    rendered = f"{page!r}\n{result!r}\n{state!r}"
    for secret in ("password-secret", "key-secret", "pnr-secret"):
        assert secret not in rendered


def test_safety_excludes_dangerous_domains_without_stub_apis():
    assert "reservation" in EXCLUDED_API_DOMAINS
    assert "netfunnel-act-19" in EXCLUDED_API_DOMAINS
    assert "ard-payment-entry" in EXCLUDED_API_DOMAINS
    assert "payment" in EXCLUDED_API_DOMAINS
