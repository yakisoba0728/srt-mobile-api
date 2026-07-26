from srt_mobile_api.errors import SrtAppError, SrtAuthError, SrtNetFunnelError, SrtProtocolError
from srt_mobile_api.models import (
    HtmlPage,
    NetFunnelToken,
    SearchPageState,
    SrtSession,
    TrainSearchResult,
)
from srt_mobile_api.redaction import (
    redact_mapping,
    redact_payload,
    redact_text,
    redact_url,
    redact_value,
)
from srt_mobile_api.safety import EXCLUDED_API_DOMAINS


def test_redact_mapping_masks_sensitive_values():
    data = {
        "srchDvNm": "login-id",
        "hmpgPwdCphd": "password",
        "netfunnelKey": "NF",
        "cookie": "abc",
        "set-cookie": "def",
        "pnrNo": "123456789012",
        "mutMrkVrfCd": "server-secret",
        "verification_code": "model-secret",
        "safe": "value",
    }
    redacted = redact_mapping(data)
    assert redacted["srchDvNm"] == "[REDACTED]"
    assert redacted["hmpgPwdCphd"] == "[REDACTED]"
    assert redacted["netfunnelKey"] == "[REDACTED]"
    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["set-cookie"] == "[REDACTED]"
    assert redacted["pnrNo"] == "[REDACTED]"
    assert redacted["mutMrkVrfCd"] == "[REDACTED]"
    assert redacted["verification_code"] == "[REDACTED]"
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
                    "MUTMRKVRFCD": "server-secret",
                    "VERIFICATION_CODE": "model-secret",
                    "url": "https://host/path?netfunnelKey=key-secret&safe=1",
                }
            ]
        }
    )
    assert redacted["outer"][0]["HMPGPWDCphd"] == "[REDACTED]"
    assert redacted["outer"][0]["MUTMRKVRFCD"] == "[REDACTED]"
    assert redacted["outer"][0]["VERIFICATION_CODE"] == "[REDACTED]"
    assert "key-secret" not in redacted["outer"][0]["url"]
    assert "safe=1" in redacted["outer"][0]["url"]


def test_mutual_verification_names_are_redacted_everywhere():
    redacted = redact_mapping(
        {
            "mutMrkVrfCd": "server-secret",
            "VERIFICATION_CODE": "model-secret",
        }
    )
    assert redacted == {
        "mutMrkVrfCd": "[REDACTED]",
        "VERIFICATION_CODE": "[REDACTED]",
    }
    rendered = redact_text(
        'mutMrkVrfCd="server-secret" verification_code=model-secret'
    )
    assert "server-secret" not in rendered
    assert "model-secret" not in rendered


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
    assert "ard-payment-entry" in EXCLUDED_API_DOMAINS
    assert "payment" in EXCLUDED_API_DOMAINS


# --- Payment and refund secrets ----------------------------------------------
#
# Every value below is obviously synthetic. There is no real PAN anywhere in
# this repository, and these fixtures must never acquire one.


def test_redact_payload_masks_every_payment_card_field():
    # The five secrets a card payment puts on the wire, each under the exact
    # field name /ata/selectListAta09036_n.do takes. A MutationPreview stores
    # its payload through redact_payload, so these are what a preview of a
    # payment can hold.
    redacted = redact_payload(
        {
            "stlCrCrdNo1": "0000000000000000",  # PAN
            "vanPwd1": "00",  # first two PIN digits
            "crdVlidTrm1": "0101",  # expiry YYMM
            "athnVal1": "000101",  # birthdate YYMMDD
            "athnDvCd1": "J",  # card type
            "mbCrdNo": "SYNTHETIC-MEMBER",  # membership number
            "pnrNo": "SYNTHETIC-PNR",
            # Not a secret: the amount and the fixed protocol constants stay
            # legible, or a preview says nothing at all.
            "totNewStlAmt": "36900",
            "stlMnsCd1": "02",
        }
    )
    for masked in (
        "stlCrCrdNo1",
        "vanPwd1",
        "crdVlidTrm1",
        "athnVal1",
        "athnDvCd1",
        "mbCrdNo",
        "pnrNo",
    ):
        assert redacted[masked] == "[REDACTED]"
    assert redacted["totNewStlAmt"] == "36900"
    assert redacted["stlMnsCd1"] == "02"


def test_redact_payload_masks_the_refund_return_password_in_every_spelling():
    # The return password is the credential that authorises a refund, and which
    # spelling the live API uses is precisely what is unresolved: srtgo's
    # step-2 request says tkRetPwd, its step-1 response says ogtkRetPwd, and our
    # own app's offline ticket cache (webview/b.java:645) says retPwd. All three
    # are masked, so being wrong about the name cannot leak the value.
    redacted = redact_payload(
        {
            "ogtkRetPwd": "SYNTHETIC-RETURN-PASSWORD",
            "tkRetPwd": "SYNTHETIC-RETURN-PASSWORD",
            "retPwd": "SYNTHETIC-RETURN-PASSWORD",
            "buyPsNm": "SYNTHETIC-BUYER",
            "psgNm": "SYNTHETIC-BUYER",
            "pnr_no": "SYNTHETIC-PNR",
        }
    )
    assert set(redacted.values()) == {"[REDACTED]"}


def test_redact_payload_keeps_refund_sale_identifiers_legible():
    # The counterpart decision, pinned so it stays a decision: the issuance
    # identifiers are NOT credentials once the password above is masked, and a
    # refund preview whose every field is [REDACTED] tells a caller nothing.
    redacted = redact_payload(
        {
            "saleDt": "20990101",
            "saleWctNo": "0000",
            "saleSqno": "0001",
            "cnc_dmn_cont": "승차권 환불로 취소",
        }
    )
    assert redacted["saleDt"] == "20990101"
    assert redacted["saleWctNo"] == "0000"
    assert redacted["saleSqno"] == "0001"
    assert redacted["cnc_dmn_cont"] == "승차권 환불로 취소"


def test_redact_value_masks_the_pnr_under_its_snake_case_attribute_name():
    # redact_value redacts a dataclass by FIELD NAME. `pnr_no` is the attribute
    # on SrtReservationHold / SrtReservationSummary / SrtRefundTicketInfo and
    # the refund step-2 wire field, and it used to be absent from SENSITIVE_KEYS
    # while `pnrNo` and `pnr_number` were present -- so a real PNR passed
    # through untouched.
    assert redact_value({"pnr_no": "SYNTHETIC-PNR"}) == {"pnr_no": "[REDACTED]"}
    assert redact_text("pnr_no=SYNTHETIC-PNR") == "pnr_no=[REDACTED]"
