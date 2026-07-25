"""Offline tests for the two operator scripts that can transmit a mutation.

``scripts/recover_hold.py`` cancels a stranded hold from its PNR alone, and
``scripts/verify_reserve_cancel_roundtrip.py`` performs the reserve->cancel
round trip. Both are run by a human against a real account, so the properties
tested here are the ones that decide whether an operator can recover from a
failure: that importing either module sends nothing, that the consent each
constructs grants exactly what it needs and nothing more, and that a PNR is
printed on every path where a hold might exist.

Everything is offline. No test here touches the network: the scripts' clients
are replaced or driven by an ``httpx.MockTransport``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import httpx
import pytest

from srt_mobile_api import (
    MutationConsent,
    SrtCancelResult,
    SrtClient,
    SrtConfig,
    SrtSession,
)


ROOT = Path(__file__).resolve().parents[1]
RECOVER_PATH = ROOT / "scripts/recover_hold.py"
ROUNDTRIP_PATH = ROOT / "scripts/verify_reserve_cancel_roundtrip.py"
CANCEL_ROUTE = "/ard/selectListArd02045_n.do"
FAKE_PNR = "SYNTHETIC_PNR_REFERENCE"
SECRET_PASSWORD = "SYNTHETIC-PASSWORD-DO-NOT-PRINT"
SECRET_LOGIN_ID = "synthetic-member-id"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="recover")
def recover_module():
    return _load(RECOVER_PATH)


@pytest.fixture(name="roundtrip")
def roundtrip_module():
    return _load(ROUNDTRIP_PATH)


# --- import safety ----------------------------------------------------------


def test_recover_hold_is_import_safe(monkeypatch):
    # Importing must not log in, cancel, or read credentials. A recovery tool
    # that acts on import cannot be inspected before it is trusted.
    def _explode(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("import performed I/O")

    monkeypatch.setattr(httpx.Client, "send", _explode)
    module = _load(RECOVER_PATH)
    assert hasattr(module, "main")


def test_recover_hold_guards_its_entrypoint():
    # The work must sit behind __main__, not at module scope.
    tree = ast.parse(RECOVER_PATH.read_text(encoding="utf-8"))
    calls_at_module_scope = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert calls_at_module_scope == []
    assert any(isinstance(node, ast.If) for node in tree.body)


# --- the consent it constructs ---------------------------------------------


def test_recover_hold_consent_grants_cancel_only_and_is_not_a_dry_run(recover):
    consent = recover.build_cancel_consent()

    assert isinstance(consent, MutationConsent)
    assert consent.allow_cancel is True
    # A dry run would preview and release nothing -- a silent no-op is the worst
    # possible behaviour for a recovery tool.
    assert consent.dry_run is False
    # Nothing else is granted, so this script cannot reserve, pay or refund.
    assert consent.allow_reserve is False
    assert consent.allow_payment is False
    assert consent.allow_refund is False


# --- cancel_hold against a mock transport -----------------------------------


def _client(reply: dict, *, status: int = 200) -> tuple[SrtClient, list]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=reply)

    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    client.session.current = SrtSession(login_id="synthetic", user_map={})
    return client, seen


def test_recover_hold_cancels_from_a_bare_pnr(recover):
    client, seen = _client({"resultMap": [{"strResult": "SUCC"}]})

    result = recover.cancel_hold(client, FAKE_PNR)

    assert isinstance(result, SrtCancelResult)
    assert result.succeeded is True
    assert len(seen) == 1
    assert seen[0].url.path == CANCEL_ROUTE
    assert dict(httpx.QueryParams(seen[0].content.decode()))["pnrNo"] == FAKE_PNR


def test_recover_hold_rejects_a_preview_instead_of_reporting_success(recover):
    # If a future edit made the consent a dry run, cancel() would return a
    # preview and the hold would survive. That must be an error, not a success.
    client, _seen = _client({"resultMap": [{"strResult": "SUCC"}]})
    client.cancel = lambda *a, **k: "a preview, not a result"  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="NOT released"):
        recover.cancel_hold(client, FAKE_PNR)


# --- main(): the operator-visible contract ----------------------------------


class _FakeClient:
    """Stands in for SrtClient inside main(), recording what it was asked to do."""

    def __init__(self, cancel_result, *, login_error=None, cancel_error=None):
        self._cancel_result = cancel_result
        self._login_error = login_error
        self._cancel_error = cancel_error
        self.closed = False
        self.logged_in_as: str | None = None

    def login(self, login_id, password, **kwargs):
        if self._login_error is not None:
            raise self._login_error
        self.logged_in_as = login_id
        return SrtSession(login_id=login_id, user_map={})

    def cancel(self, reservation, *, consent, **kwargs):
        if self._cancel_error is not None:
            raise self._cancel_error
        return self._cancel_result

    def close(self):
        self.closed = True


def _run_main(recover, monkeypatch, fake: _FakeClient, argv=None):
    monkeypatch.setenv("SRT_LOGIN_ID", "synthetic-member")
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", SECRET_PASSWORD)
    monkeypatch.setattr(recover, "SrtClient", lambda *a, **k: fake)
    return recover.main(argv if argv is not None else [FAKE_PNR])


def test_recover_hold_main_reports_success_and_exits_zero(
    recover, monkeypatch, capsys
):
    fake = _FakeClient(SrtCancelResult(status="SUCC", message_code="OK-CODE"))

    assert _run_main(recover, monkeypatch, fake) == 0

    out = capsys.readouterr().out
    assert FAKE_PNR in out
    # The raw confirmation codes are the evidence of what the server said.
    assert "SUCC" in out and "OK-CODE" in out
    assert "CANCELLED" in out.upper()
    assert SECRET_PASSWORD not in out
    assert fake.closed is True


def test_recover_hold_main_exits_non_zero_and_reprints_the_pnr_on_refusal(
    recover, monkeypatch, capsys
):
    # The server accepted the request but refused the cancel: the hold still
    # exists, so this is a failure and the PNR must be unmissable.
    fake = _FakeClient(SrtCancelResult(status="FAIL", message_code="NO-CODE"))

    assert _run_main(recover, monkeypatch, fake) == 1

    out = capsys.readouterr().out
    assert FAKE_PNR in out
    assert "STILL EXISTS" in out.upper()
    assert "NO-CODE" in out
    assert SECRET_PASSWORD not in out


def test_recover_hold_main_reprints_the_pnr_when_the_cancel_raises(
    recover, monkeypatch, capsys
):
    # ANY exception -- transport, protocol, anything -- must still surface the
    # PNR. This is the path where an operator would otherwise lose it.
    fake = _FakeClient(None, cancel_error=RuntimeError("synthetic transport failure"))

    assert _run_main(recover, monkeypatch, fake) == 1

    out = capsys.readouterr().out
    assert FAKE_PNR in out
    assert "MAY STILL EXIST" in out.upper()
    assert "synthetic transport failure" in out
    assert SECRET_PASSWORD not in out
    assert fake.closed is True


def test_recover_hold_main_reprints_the_pnr_when_login_fails(
    recover, monkeypatch, capsys
):
    fake = _FakeClient(None, login_error=RuntimeError("synthetic login failure"))

    assert _run_main(recover, monkeypatch, fake) == 1

    out = capsys.readouterr().out
    assert FAKE_PNR in out
    assert SECRET_PASSWORD not in out


def test_recover_hold_main_refuses_an_empty_pnr(recover, monkeypatch, capsys):
    fake = _FakeClient(SrtCancelResult(status="SUCC"))
    assert _run_main(recover, monkeypatch, fake, argv=["   "]) == 2
    # Nothing was attempted, so nothing was logged in either.
    assert fake.logged_in_as is None


def test_recover_hold_main_requires_credentials(recover, monkeypatch, capsys):
    monkeypatch.delenv("SRT_LOGIN_ID", raising=False)
    monkeypatch.delenv("SRT_LOGIN_PASSWORD", raising=False)
    fake = _FakeClient(SrtCancelResult(status="SUCC"))
    monkeypatch.setattr(recover, "SrtClient", lambda *a, **k: fake)

    assert recover.main([FAKE_PNR]) == 2
    assert fake.logged_in_as is None


# ===========================================================================
# verify_reserve_cancel_roundtrip.py
# ===========================================================================


def test_roundtrip_is_import_safe(monkeypatch):
    # Importing a script that can CREATE a real reservation must do nothing.
    def _explode(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("import performed I/O")

    monkeypatch.setattr(httpx.Client, "send", _explode)
    module = _load(ROUNDTRIP_PATH)
    assert hasattr(module, "main")


def test_roundtrip_guards_its_entrypoint():
    tree = ast.parse(ROUNDTRIP_PATH.read_text(encoding="utf-8"))
    calls_at_module_scope = [
        node
        for node in tree.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    ]
    assert calls_at_module_scope == []


# --- the two opt-ins --------------------------------------------------------


def test_roundtrip_refuses_without_the_live_flag(roundtrip, monkeypatch, capsys):
    monkeypatch.delenv("SRT_MOBILE_API_LIVE", raising=False)
    monkeypatch.setenv("SRT_LIVE_MUTATION", "1")

    assert roundtrip.main([]) == 2
    assert "SRT_MOBILE_API_LIVE" in capsys.readouterr().err


def test_roundtrip_refuses_without_the_mutation_opt_in(roundtrip, monkeypatch, capsys):
    # THE point of the second flag: a normal live smoke run sets
    # SRT_MOBILE_API_LIVE, and that must never be enough to create a booking.
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.delenv("SRT_LIVE_MUTATION", raising=False)

    assert roundtrip.main([]) == 2
    assert "SRT_LIVE_MUTATION=1" in capsys.readouterr().err


def test_roundtrip_mutation_flag_requires_exactly_one(roundtrip, monkeypatch):
    monkeypatch.setenv("SRT_LIVE_MUTATION", "true")
    assert roundtrip.mutation_enabled() is False
    monkeypatch.setenv("SRT_LIVE_MUTATION", "1")
    assert roundtrip.mutation_enabled() is True


def test_roundtrip_refuses_arguments(roundtrip, monkeypatch, capsys):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.setenv("SRT_LIVE_MUTATION", "1")
    assert roundtrip.main(["--yolo"]) == 2


# --- consents ---------------------------------------------------------------


def test_roundtrip_consents_are_separate_and_minimal(roundtrip):
    reserve = roundtrip.build_reserve_consent()
    cancel = roundtrip.build_cancel_consent()

    # Neither call carries the other's authority.
    assert (reserve.allow_reserve, reserve.allow_cancel) == (True, False)
    assert (cancel.allow_cancel, cancel.allow_reserve) == (True, False)
    for consent in (reserve, cancel):
        assert consent.dry_run is False
        assert consent.allow_payment is False
        assert consent.allow_refund is False


def test_roundtrip_masks_the_login_id_and_never_the_password(roundtrip):
    masked = roundtrip.mask_login_id(SECRET_LOGIN_ID)
    assert SECRET_LOGIN_ID not in masked
    assert masked.startswith(SECRET_LOGIN_ID[0])
    assert masked.endswith(SECRET_LOGIN_ID[-1])
    assert roundtrip.mask_login_id("ab") == "**"


# --- the flow ---------------------------------------------------------------


def _train(**overrides):
    from srt_mobile_api import TrainSummary

    base = dict(
        train_no="303",
        service_class_code="17",
        train_group_code="300",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20990101",
        departure_time="060000",
        arrival_time="083000",
        departure_station_name="수서",
        arrival_station_name="부산",
        departure_run_order="1",
        arrival_run_order="10",
        departure_consist_order="1",
        arrival_consist_order="2",
        general_seat_availability="예약가능",
        special_seat_availability="매진",
    )
    base.update(overrides)
    return TrainSummary(**base)


class _RoundTripClient:
    """Drives run_roundtrip without any transport at all."""

    def __init__(
        self,
        *,
        trains=None,
        hold=None,
        cancel_results=None,
        cancel_errors=None,
        ticket_body="no trace here",
    ):
        from srt_mobile_api import SrtReservationHold

        self.trains = [_train()] if trains is None else trains
        self.hold = (
            SrtReservationHold(pnr_no=FAKE_PNR, raw={"resultMap": [{"strResult": "SUCC", "msgCd": "R-OK"}]})
            if hold is None
            else hold
        )
        self.cancel_results = list(cancel_results or [])
        self.cancel_errors = list(cancel_errors or [])
        self.ticket_body = ticket_body
        self.cancel_calls: list[str] = []
        self.reserve_calls = 0
        self.closed = False

    def login(self, login_id, password, **kwargs):
        return SrtSession(login_id=login_id, user_map={})

    def search_trains(self, query):
        class _Result:
            pass

        result = _Result()
        result.trains = self.trains
        return result

    def reserve(self, train, *, consent, **kwargs):
        self.reserve_calls += 1
        return self.hold

    def cancel(self, reservation, *, consent, **kwargs):
        self.cancel_calls.append(reservation)
        if self.cancel_errors:
            error = self.cancel_errors.pop(0)
            if error is not None:
                raise error
        if self.cancel_results:
            return self.cancel_results.pop(0)
        return SrtCancelResult(status="SUCC", message_code="C-OK")

    def get_ticket_list(self, page_no: int = 0):
        from srt_mobile_api.models import HtmlPage

        return HtmlPage(text=self.ticket_body, raw=self.ticket_body)

    def close(self):
        self.closed = True


def _run_roundtrip(roundtrip, monkeypatch, client):
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")
    return roundtrip.run_roundtrip(
        client, login_id=SECRET_LOGIN_ID, password=SECRET_PASSWORD
    )


def test_roundtrip_happy_path_reserves_cancels_and_verifies(
    roundtrip, monkeypatch, capsys
):
    client = _RoundTripClient()

    assert _run_roundtrip(roundtrip, monkeypatch, client) == 0

    out = capsys.readouterr().out
    # The PNR is printed the moment it exists.
    assert FAKE_PNR in out
    # Raw confirmation codes for BOTH operations are the evidence of the run.
    assert "R-OK" in out and "C-OK" in out
    assert "strResult" in out
    # Exactly one reserve, exactly one cancel: the finally block must not
    # cancel a second time once the first succeeded.
    assert client.reserve_calls == 1
    assert client.cancel_calls == [FAKE_PNR]
    assert SECRET_PASSWORD not in out
    assert SECRET_LOGIN_ID not in out


def test_roundtrip_refuses_when_no_train_is_reservable(
    roundtrip, monkeypatch, capsys
):
    # Sold out everywhere: nothing may be sent.
    client = _RoundTripClient(
        trains=[
            _train(general_seat_availability="매진", special_seat_availability="매진")
        ]
    )

    assert _run_roundtrip(roundtrip, monkeypatch, client) == 1

    assert client.reserve_calls == 0
    assert client.cancel_calls == []
    assert "REFUSING TO PROCEED" in capsys.readouterr().err


def test_roundtrip_strands_loudly_when_the_cancel_is_refused(
    roundtrip, monkeypatch, capsys
):
    # The worst realistic case: a real hold exists and the server will not
    # release it. The PNR and the exact recovery command must be unmissable.
    client = _RoundTripClient(
        cancel_results=[
            SrtCancelResult(status="FAIL", message_code="C-NO"),
            SrtCancelResult(status="FAIL", message_code="C-NO-AGAIN"),
        ]
    )

    assert _run_roundtrip(roundtrip, monkeypatch, client) == 1

    out = capsys.readouterr().out
    assert "STRANDED" in out.upper()
    assert FAKE_PNR in out
    assert "scripts/recover_hold.py" in out
    assert f"recover_hold.py {FAKE_PNR}" in out
    # The finally block retried before giving up.
    assert client.cancel_calls == [FAKE_PNR, FAKE_PNR]
    assert SECRET_PASSWORD not in out


def test_roundtrip_finally_retries_and_can_still_succeed(
    roundtrip, monkeypatch, capsys
):
    # First cancel raises, the finally-block retry succeeds. The run still
    # fails (the round trip did not complete cleanly) but no hold is left.
    client = _RoundTripClient(
        cancel_errors=[RuntimeError("synthetic cancel failure"), None],
        cancel_results=[SrtCancelResult(status="SUCC", message_code="C-RETRY")],
    )

    assert roundtrip.main is not None
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")
    with pytest.raises(RuntimeError, match="synthetic cancel failure"):
        roundtrip.run_roundtrip(
            client, login_id=SECRET_LOGIN_ID, password=SECRET_PASSWORD
        )

    out = capsys.readouterr().out
    assert FAKE_PNR in out
    assert "C-RETRY" in out or "retry" in out.lower()
    assert client.cancel_calls == [FAKE_PNR, FAKE_PNR]


def test_roundtrip_strands_when_both_the_cancel_and_the_retry_raise(
    roundtrip, monkeypatch, capsys
):
    client = _RoundTripClient(
        cancel_errors=[
            RuntimeError("synthetic first failure"),
            RuntimeError("synthetic retry failure"),
        ]
    )

    monkeypatch.setenv("SRT_TEST_DATE", "20990101")
    with pytest.raises(RuntimeError, match="synthetic first failure"):
        roundtrip.run_roundtrip(
            client, login_id=SECRET_LOGIN_ID, password=SECRET_PASSWORD
        )

    out = capsys.readouterr().out
    assert "STRANDED" in out.upper()
    assert FAKE_PNR in out
    assert f"recover_hold.py {FAKE_PNR}" in out


def test_roundtrip_fails_when_the_pnr_still_appears_after_cancel(
    roundtrip, monkeypatch, capsys
):
    # The server said SUCC but the ticket list still shows it: do not report
    # success on the strength of the envelope alone.
    client = _RoundTripClient(ticket_body=f"...{FAKE_PNR}...")

    assert _run_roundtrip(roundtrip, monkeypatch, client) == 1

    out = capsys.readouterr().out
    assert "STILL LISTED" in out.upper()
    assert FAKE_PNR in out


def test_roundtrip_main_reports_a_failure_without_a_traceback(
    roundtrip, monkeypatch, capsys
):
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.setenv("SRT_LIVE_MUTATION", "1")
    monkeypatch.setenv("SRT_LOGIN_ID", SECRET_LOGIN_ID)
    monkeypatch.setenv("SRT_LOGIN_PASSWORD", SECRET_PASSWORD)
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")

    client = _RoundTripClient()
    monkeypatch.setattr(roundtrip, "SrtClient", lambda *a, **k: client)
    monkeypatch.setattr(
        roundtrip,
        "run_roundtrip",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic boom")),
    )

    assert roundtrip.main([]) == 1
    err = capsys.readouterr().err
    assert "synthetic boom" in err
    assert SECRET_PASSWORD not in err
    assert client.closed is True


# --- end-to-end against a REAL SrtClient (mock transport) -------------------
#
# The tests above drive run_roundtrip with a fake client, which proves the
# script's control flow but not that it integrates with the real client. These
# run the whole script against a genuine SrtClient whose transport is mocked,
# so the actual login/NetFunnel/search/reserve/cancel/ticket-list wiring is
# exercised and the exact bytes the operator's live run would send are
# asserted. Still fully offline: httpx.MockTransport answers everything.


def _roundtrip_transport(
    *, pnr: str, cancel_status: str = "SUCC", load_json_fixture, load_text_fixture
):
    row = {
        "trnNo": "303",
        "trnGpCd": "300",
        "stlbTrnClsfCd": "17",
        "runDt": "20990101",
        "dptDt": "20990101",
        "dptTm": "060000",
        "arvDt": "20990101",
        "arvTm": "083000",
        "dptRsStnCd": "0551",
        "arvRsStnCd": "0020",
        "dptStnRunOrdr": "000001",
        "arvStnRunOrdr": "000010",
        "dptStnConsOrdr": "000001",
        "arvStnConsOrdr": "000002",
        "gnrmRsvPsbStr": "예약가능",
        "sprmRsvPsbStr": "매진",
        "seatAttCd": "015",
    }
    search = load_json_fixture("search_success.json")
    search["outDataSets"]["dsOutput1"] = [row]
    reserve_reply = load_json_fixture("reservation_attempt_success.json")
    reserve_reply["reservListMap"][0]["pnrNo"] = pnr

    sent: dict = {"paths": [], "reserve": None, "cancel": []}
    state = {"cancelled": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        sent["paths"].append(f"{request.method} {path}")
        if path == "/ts.wseq":
            return httpx.Response(200, text=load_text_fixture("netfunnel_act10.js"))
        if path in {"/login/login.do", "/main/main.do", "/ara/ara0101v.do"}:
            return httpx.Response(200, text="<html><body>로그아웃</body></html>")
        if path == "/apb/selectListApb01080_n.do":
            return httpx.Response(200, json=load_json_fixture("login_success.json"))
        if path == "/ara/selectListAra10007_n.do":
            if request.method == "GET":
                return httpx.Response(200, text=load_text_fixture("search_page.html"))
            return httpx.Response(200, json=search)
        if path == "/arc/selectListArc05013_n.do":
            sent["reserve"] = dict(httpx.QueryParams(request.content.decode()))
            return httpx.Response(200, json=reserve_reply)
        if path == "/ard/selectListArd02045_n.do":
            sent["cancel"].append(dict(httpx.QueryParams(request.content.decode())))
            if cancel_status == "SUCC":
                state["cancelled"] = True
            return httpx.Response(
                200,
                json={"resultMap": [{"strResult": cancel_status, "msgCd": "CXL-CODE"}]},
            )
        if path == "/atc/selectListAtc14017_n.do":
            trace = "" if state["cancelled"] else pnr
            return httpx.Response(200, text=f"<html><body>로그아웃 {trace}</body></html>")
        raise AssertionError(f"unexpected {request.method} {path}")

    return handler, sent


def test_roundtrip_end_to_end_against_a_real_client(
    roundtrip, monkeypatch, capsys, load_json_fixture, load_text_fixture
):
    pnr = "SYNTHETIC-E2E-PNR"
    handler, sent = _roundtrip_transport(
        pnr=pnr,
        load_json_fixture=load_json_fixture,
        load_text_fixture=load_text_fixture,
    )
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")
    monkeypatch.setenv("SRT_DEPARTURE_TIME", "060000")

    assert (
        roundtrip.run_roundtrip(
            client, login_id=SECRET_LOGIN_ID, password=SECRET_PASSWORD
        )
        == 0
    )

    # The exact wire the operator's live run will produce.
    assert sent["paths"] == [
        "GET /login/login.do",
        "POST /apb/selectListApb01080_n.do",
        "GET /main/main.do",
        "GET /ara/ara0101v.do",
        "GET /ts.wseq",  # search's act_10
        "GET /ara/selectListAra10007_n.do",
        "POST /ara/selectListAra10007_n.do",
        "GET /ts.wseq",  # reserve's act_10 -- the SAME flow, not act_19
        "POST /arc/selectListArc05013_n.do",
        "POST /ard/selectListArd02045_n.do",
        "GET /atc/selectListAtc14017_n.do",
    ]
    # ABC123 is the key in the netfunnel_act10 fixture: the reserve really did
    # carry a freshly acquired act_10 key.
    assert sent["reserve"]["netfunnelKey"] == "ABC123"
    assert sent["reserve"]["jobId"] == "1101"
    assert sent["reserve"]["totPrnb"] == "1"
    assert sent["reserve"]["psrmClCd1"] == "1"  # general seat was available
    assert sent["cancel"] == [{"pnrNo": pnr, "jrnyCnt": "1", "rsvChgTno": "0"}]

    out = capsys.readouterr().out
    assert pnr in out
    assert "CXL-CODE" in out
    assert SECRET_PASSWORD not in out


def test_roundtrip_end_to_end_strands_loudly_when_the_server_refuses(
    roundtrip, monkeypatch, capsys, load_json_fixture, load_text_fixture
):
    # Same real client, but the server refuses every cancel. A real hold would
    # now exist, so the PNR and the recovery command must be unmissable and the
    # finally-block retry must have been attempted.
    pnr = "SYNTHETIC-E2E-STRANDED"
    handler, sent = _roundtrip_transport(
        pnr=pnr,
        cancel_status="FAIL",
        load_json_fixture=load_json_fixture,
        load_text_fixture=load_text_fixture,
    )
    client = SrtClient(SrtConfig(), transport=httpx.MockTransport(handler))
    monkeypatch.setenv("SRT_TEST_DATE", "20990101")

    assert (
        roundtrip.run_roundtrip(
            client, login_id=SECRET_LOGIN_ID, password=SECRET_PASSWORD
        )
        == 1
    )

    out = capsys.readouterr().out
    assert "STRANDED" in out.upper()
    assert pnr in out
    assert f"recover_hold.py {pnr}" in out
    # Tried once, then once more from the finally block.
    assert len(sent["cancel"]) == 2
    assert SECRET_PASSWORD not in out
