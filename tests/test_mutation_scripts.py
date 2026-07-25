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
CANCEL_ROUTE = "/ard/selectListArd02045_n.do"
FAKE_PNR = "SYNTHETIC_PNR_REFERENCE"
SECRET_PASSWORD = "SYNTHETIC-PASSWORD-DO-NOT-PRINT"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="recover")
def recover_module():
    return _load(RECOVER_PATH)


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
