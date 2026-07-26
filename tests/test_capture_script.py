"""Offline tests for ``scripts/capture_live_read_surface.py``.

The script drives the live READ surface and writes every raw response to disk,
so the properties worth pinning are the ones that decide whether running it can
hurt anyone: that importing it sends nothing, that it cannot fire without both
explicit opt-ins, that raw captures cannot land in the repository, that it
reaches no mutation route, and that everything it prints is redacted.

Everything here is offline. Nothing in this file touches the network.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = ROOT / "scripts/capture_live_read_surface.py"
SECRET_PASSWORD = "SYNTHETIC-PASSWORD-DO-NOT-PRINT"
SECRET_LOGIN_ID = "synthetic-member-id"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because the module defines dataclasses, which
    # resolve their annotations through sys.modules.
    sys.modules[path.stem] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(path.stem, None)
    return module


@pytest.fixture(name="capture")
def capture_module():
    return _load(CAPTURE_PATH)


def test_importing_the_capture_script_sends_nothing(capture):
    assert capture.CAPTURE_ENV == "SRT_LIVE_READ_CAPTURE"
    assert capture.DEFAULT_PACE_SECONDS >= 1.0


def test_capture_script_reaches_no_mutation_route_and_builds_no_consent():
    """A read capture must be incapable of changing anything.

    Checked in the source rather than at runtime so it holds for every path,
    including ones no test drives.
    """
    source = CAPTURE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "/arc/selectListArc05013_n.do",
        # The 단체 reservation endpoint is a second reserve URL, so the read
        # capture has to be unable to reach it too -- listing only arc05013
        # would have let a group reservation through this guard.
        "/arc/selectListArc06014_n.do",
        "/ard/selectListArd02045_n.do",
        "/ata/selectListAta09036_n.do",
        "/atc/selectListAtc02063_n.do",
        "MutationConsent",
        "allow_reserve",
        "allow_payment",
        "allow_cancel",
        "allow_refund",
        "post_mutation_form",
        ".reserve(",
        ".reserve_group(",
        ".cancel(",
    ):
        assert forbidden not in source, forbidden


def test_capture_script_calls_only_public_read_methods():
    """Every SrtClient attribute it touches is a read (or the session helpers)."""
    tree = ast.parse(CAPTURE_PATH.read_text(encoding="utf-8"))
    touched = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "client"
    }
    assert touched <= {
        "login",
        "clear_session",
        "close",
        "http",
        "get_main",
        "get_booking_page",
        "get_notice_list",
        "get_typed_notice_list",
        "get_ticket_list",
        "get_reservations",
        "get_station_selector",
        "get_station_map_selector",
        "get_date_selector",
        "get_passenger_selector",
        "get_seat_option_selector",
        "get_train_group_selector",
        "get_mutual_verification",
        "search_trains",
        "search_group_trains",
        "iter_train_search_pages",
        "get_seat_page",
        "get_timetable",
        "get_fare",
    }, touched


@pytest.mark.parametrize(
    ("live", "capture_flag"),
    [(None, "1"), ("1", None), (None, None), ("0", "1"), ("1", "0")],
)
def test_both_opt_ins_are_required(capture, monkeypatch, live, capture_flag, capsys):
    for name, value in (
        ("SRT_MOBILE_API_LIVE", live),
        ("SRT_LIVE_READ_CAPTURE", capture_flag),
    ):
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)

    assert capture.main([]) == 2


def test_capture_directory_must_be_outside_the_repository(capture, monkeypatch):
    """Raw captures carry the account's own data; the repo is where they must not go."""
    monkeypatch.setenv(capture.CAPTURE_DIR_ENV, str(ROOT / "tests" / "fixtures"))
    with pytest.raises(RuntimeError, match="OUTSIDE"):
        capture.resolve_capture_dir(ROOT)

    monkeypatch.setenv(capture.CAPTURE_DIR_ENV, str(ROOT))
    with pytest.raises(RuntimeError, match="OUTSIDE"):
        capture.resolve_capture_dir(ROOT)


def test_capture_directory_has_no_default(capture, monkeypatch):
    monkeypatch.delenv(capture.CAPTURE_DIR_ENV, raising=False)
    with pytest.raises(RuntimeError, match=capture.CAPTURE_DIR_ENV):
        capture.resolve_capture_dir(ROOT)


def test_capture_directory_outside_the_repository_is_accepted(
    capture, monkeypatch, tmp_path
):
    monkeypatch.setenv(capture.CAPTURE_DIR_ENV, str(tmp_path / "out"))
    assert capture.resolve_capture_dir(ROOT) == (tmp_path / "out").resolve()


@pytest.mark.parametrize("value", ["0", "0.1", "-5", "", "not-a-number"])
def test_pacing_never_drops_below_the_rate_limit_floor(capture, monkeypatch, value):
    """The pace knob is the rate-limit guard, not a speed dial."""
    monkeypatch.setenv(capture.PACE_ENV, value)
    assert capture.resolve_pace_seconds() >= 1.0


def test_pacing_honours_a_slower_setting(capture, monkeypatch):
    monkeypatch.setenv(capture.PACE_ENV, "9")
    assert capture.resolve_pace_seconds() == 9.0


def test_step_selection_always_keeps_login(capture, monkeypatch):
    monkeypatch.setenv(capture.STEPS_ENV, "get_fare, get_timetable")
    assert capture.resolve_selected_steps() == frozenset(
        {"login", "get_fare", "get_timetable"}
    )

    monkeypatch.setenv(capture.STEPS_ENV, "   ")
    assert capture.resolve_selected_steps() is None

    monkeypatch.delenv(capture.STEPS_ENV, raising=False)
    assert capture.resolve_selected_steps() is None


def test_printed_output_is_redacted(capture, capsys):
    capture.say(f"hmpgPwdCphd={SECRET_PASSWORD} netfunnelKey=SYNTHETIC-KEY")
    out = capsys.readouterr().out
    assert SECRET_PASSWORD not in out
    assert "SYNTHETIC-KEY" not in out
    assert "[REDACTED]" in out


def test_login_id_is_masked_but_still_identifies_the_account(capture):
    masked = capture.mask_login_id(SECRET_LOGIN_ID)
    assert SECRET_LOGIN_ID not in masked
    assert masked.startswith(SECRET_LOGIN_ID[0])
    assert masked.endswith(SECRET_LOGIN_ID[-1])
    assert capture.mask_login_id("ab") == "**"
    assert capture.mask_login_id("") == ""


def test_the_password_is_never_printed_anywhere_in_the_script():
    """No print/say call references the password VALUE.

    Checked against the identifier, not the word: the script legitimately prints
    the reassurance "(password never printed)", and a substring test would
    forbid saying so.
    """
    tree = ast.parse(CAPTURE_PATH.read_text(encoding="utf-8"))
    printed = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"print", "say"}
    ]
    assert printed
    for node in printed:
        names = {
            inner.id for inner in ast.walk(node) if isinstance(inner, ast.Name)
        }
        assert "password" not in names


def test_a_failing_step_is_recorded_and_the_walk_continues(capture):
    """A step that raises is a finding, not the end of the pass."""

    class _Recorder:
        step = ""
        exchanges: list[object] = []

        def record(self, request, response):  # pragma: no cover - unused here
            raise AssertionError("no I/O in this test")

    run = capture.ReadSurfaceCapture(object(), _Recorder(), pace=0.0)

    def boom():
        raise RuntimeError("synthetic failure")

    assert run.run_step("first", boom) is None
    assert run.run_step("second", lambda: "value", describe=lambda v: v) == "value"

    summary = run.summary()
    assert [item["name"] for item in summary["steps"]] == ["first", "second"]
    assert summary["steps"][0]["ok"] is False
    assert "synthetic failure" in summary["steps"][0]["detail"]
    assert summary["steps"][1]["ok"] is True
    assert summary["reached"] == 1
    assert summary["unreached"] == 1


def test_deselected_steps_are_skipped_without_running_them(capture):
    class _Recorder:
        step = ""
        exchanges: list[object] = []

    run = capture.ReadSurfaceCapture(
        object(), _Recorder(), pace=0.0, selected=frozenset({"wanted"})
    )
    calls: list[str] = []

    run.run_step("skipped", lambda: calls.append("skipped"))
    run.run_step("wanted", lambda: calls.append("wanted"))

    assert calls == ["wanted"]
    assert [item["name"] for item in run.summary()["steps"]] == ["wanted"]
