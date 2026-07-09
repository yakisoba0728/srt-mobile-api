from srt_mobile_api.redaction import redact_mapping, redact_text
from srt_mobile_api.safety import EXCLUDED_API_DOMAINS


def test_redact_mapping_masks_sensitive_values():
    data = {
        "srchDvNm": "login-id",
        "hmpgPwdCphd": "password",
        "netfunnelKey": "NF",
        "pnrNo": "123456789012",
        "safe": "value",
    }
    redacted = redact_mapping(data)
    assert redacted["srchDvNm"] == "[REDACTED]"
    assert redacted["hmpgPwdCphd"] == "[REDACTED]"
    assert redacted["netfunnelKey"] == "[REDACTED]"
    assert redacted["pnrNo"] == "[REDACTED]"
    assert redacted["safe"] == "value"


def test_redact_text_masks_card_like_values():
    assert "411111" not in redact_text("card 4111-1111-1111-1111")


def test_safety_excludes_dangerous_domains_without_stub_apis():
    assert "reservation" in EXCLUDED_API_DOMAINS
    assert "netfunnel-act-19" in EXCLUDED_API_DOMAINS
    assert "ard-payment-entry" in EXCLUDED_API_DOMAINS
    assert "payment" in EXCLUDED_API_DOMAINS
