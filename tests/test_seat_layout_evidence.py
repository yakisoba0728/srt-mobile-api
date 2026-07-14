from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from srt_mobile_api.models import (
    SeatSelectionPage,
    TrainSearchQuery,
    TrainSearchResult,
    TrainSummary,
)


SCRIPT_PATH = Path("scripts/capture_seat_layout_evidence.py")
PAGE_KEYS = {
    "marker_present",
    "external_handoff_candidate",
    "embedded_inventory_candidate",
    "script_present",
    "form_present",
    "tag_names",
    "attribute_names",
    "input_names",
    "structural_class_tokens",
    "element_count",
    "candidate_element_count",
}
REPORT_KEYS = {"schema_version", "status", "calls", "page", "sufficiency"}


def _load_module():
    spec = importlib.util.spec_from_file_location("capture_seat_layout_evidence", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = _load_module()


def _complete_train(train_no: str = "00303") -> TrainSummary:
    return TrainSummary(
        train_no=train_no,
        train_group_code="300",
        run_date="20260714",
        departure_date="20260714",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
    )


def _query() -> TrainSearchQuery:
    return TrainSearchQuery(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20260714",
        departure_station_name="수서",
        arrival_station_name="부산",
    )


def _synthetic_html() -> str:
    attributes = " ".join(f'ATTR{index}="value-{index}"' for index in range(70))
    tags = "".join(f"<STRUCTURE{index}></STRUCTURE{index}>" for index in range(70))
    inputs = "".join(f'<input name="input_name_{index}">' for index in range(70))
    classes = " ".join(f"class_token_{index}" for index in range(70))
    candidates = '<div class="seat available"></div>' * 10_005
    return (
        f"<html {attributes}><body>"
        "<h1>좌석선택</h1>"
        "visible-secret-seat-123456"
        '<form action="https://example.invalid/private">'
        '<input name="scarNo" value="secret-seat-123456">'
        '<input name="seatNo" value="4111-1111-1111-1111">'
        '<input name="private123456" value="ignored">'
        '<input name="member@example.invalid" value="ignored">'
        '<input name="https://example.invalid/private" value="ignored">'
        "</form>"
        '<a href="https://example.invalid/private?srtJob=seatmap">seat map</a>'
        '<button data-seat-no="secret-seat-123456" id="private-id"></button>'
        f'<section class="layout {classes} secret-seat-123456"></section>'
        '<script>const token = "very-long-private-token-abcdefghijklmnopqrstuvwxyz";</script>'
        f"{tags}{inputs}{candidates}</body></html>"
    )


def test_collect_page_evidence_is_bounded_deterministic_and_value_free():
    raw = _synthetic_html()

    evidence = module.collect_page_evidence(raw)

    assert set(evidence) == PAGE_KEYS
    assert evidence == module.collect_page_evidence(raw)
    assert evidence["marker_present"] is True
    assert evidence["external_handoff_candidate"] is True
    assert evidence["embedded_inventory_candidate"] is True
    assert evidence["script_present"] is True
    assert evidence["form_present"] is True
    assert evidence["element_count"] == 10_000
    assert evidence["candidate_element_count"] == 10_000
    assert len(evidence["tag_names"]) <= 64
    assert len(evidence["attribute_names"]) <= 64
    assert len(evidence["input_names"]) <= 64
    assert len(evidence["structural_class_tokens"]) <= 64
    assert evidence["tag_names"] == sorted(set(evidence["tag_names"]))
    assert evidence["attribute_names"] == sorted(set(evidence["attribute_names"]))
    assert evidence["input_names"] == sorted(set(evidence["input_names"]))
    assert evidence["structural_class_tokens"] == sorted(
        set(evidence["structural_class_tokens"])
    )
    assert all(
        len(item) <= 64
        for key in (
            "tag_names",
            "attribute_names",
            "input_names",
            "structural_class_tokens",
        )
        for item in evidence[key]
    )
    serialized = json.dumps(evidence)
    for forbidden in (
        "secret-seat-123456",
        "https://example.invalid/private",
        "4111-1111-1111-1111",
        "very-long-private-token-abcdefghijklmnopqrstuvwxyz",
        "visible-secret",
        "private-id",
        "private123456",
        "member@example.invalid",
    ):
        assert forbidden not in serialized


def test_collect_page_evidence_does_not_treat_unrelated_link_as_seat_handoff():
    evidence = module.collect_page_evidence(
        '<main><h1>좌석선택</h1><a href="https://www.korail.com/info">info</a></main>'
    )

    assert evidence["external_handoff_candidate"] is False
    assert "https://www.korail.com/info" not in json.dumps(evidence)


def test_run_bounded_evidence_uses_only_first_complete_srt_row():
    incomplete = TrainSummary("00301", train_group_code="300")
    non_srt = TrainSummary(
        train_no="00101",
        train_group_code="900",
        run_date="20260714",
        departure_date="20260714",
        departure_time="060000",
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_run_order="000001",
        arrival_run_order="000010",
        seat_attr_code="015",
    )
    complete = _complete_train()
    later = _complete_train("00305")
    client = Mock(spec_set=["login", "search_trains", "get_seat_page"])
    client.search_trains.return_value = TrainSearchResult(
        trains=[incomplete, non_srt, complete, later]
    )
    client.get_seat_page.return_value = SeatSelectionPage(
        text="좌석선택",
        raw=(
            '<main><h1>좌석선택</h1><div class="seat"></div>'
            '<button data-seat-no="synthetic"></button></main>'
        ),
    )
    query = _query()

    result = module.run_bounded_evidence(
        client,
        login_id="member-secret",
        password="password-secret",
        query=query,
    )

    assert set(result) == REPORT_KEYS
    assert result["schema_version"] == 1
    assert result["status"] == "success"
    assert result["calls"] == {"login": 1, "search": 1, "seat_page": 1}
    assert result["page"]["embedded_inventory_candidate"] is True
    assert result["sufficiency"] == "stable_embedded_candidate"
    assert client.mock_calls == [
        call.login("member-secret", "password-secret"),
        call.search_trains(query),
        call.get_seat_page(complete),
    ]
    assert hasattr(module, "_first_complete_srt_seat_train")
    assert not hasattr(module, "run_live_smoke")


def test_run_bounded_evidence_skips_seat_page_without_complete_row():
    client = Mock(spec_set=["login", "search_trains", "get_seat_page"])
    client.search_trains.return_value = TrainSearchResult(
        trains=[
            TrainSummary("00301", train_group_code="300"),
            TrainSummary("00101", train_group_code="900"),
        ]
    )
    query = _query()

    result = module.run_bounded_evidence(
        client,
        login_id="member-secret",
        password="password-secret",
        query=query,
    )

    assert result == {
        "schema_version": 1,
        "status": "no_complete_train",
        "calls": {"login": 1, "search": 1, "seat_page": 0},
        "page": None,
        "sufficiency": "unavailable",
    }
    assert client.mock_calls == [
        call.login("member-secret", "password-secret"),
        call.search_trains(query),
    ]


@pytest.mark.parametrize(
    ("failure_operation", "expected_status", "expected_calls"),
    [
        ("login", "login_failed", {"login": 1, "search": 0, "seat_page": 0}),
        ("search_trains", "search_failed", {"login": 1, "search": 1, "seat_page": 0}),
        ("get_seat_page", "seat_page_failed", {"login": 1, "search": 1, "seat_page": 1}),
    ],
)
def test_run_bounded_evidence_reduces_each_failure_to_fixed_status(
    failure_operation,
    expected_status,
    expected_calls,
):
    client = Mock(spec_set=["login", "search_trains", "get_seat_page"])
    client.search_trains.return_value = TrainSearchResult(trains=[_complete_train()])
    client.get_seat_page.return_value = SeatSelectionPage(
        text="좌석선택",
        raw="<h1>좌석선택</h1>",
    )
    getattr(client, failure_operation).side_effect = RuntimeError(
        "exception-secret https://example.invalid/private"
    )

    result = module.run_bounded_evidence(
        client,
        login_id="member-secret",
        password="password-secret",
        query=_query(),
    )

    assert set(result) == REPORT_KEYS
    assert result["status"] == expected_status
    assert result["calls"] == expected_calls
    assert result["page"] is None
    assert result["sufficiency"] == "unavailable"
    serialized = json.dumps(result)
    assert "exception-secret" not in serialized
    assert "example.invalid" not in serialized


def _safe_success_report() -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "success",
        "calls": {"login": 1, "search": 1, "seat_page": 1},
        "page": {
            "marker_present": True,
            "external_handoff_candidate": False,
            "embedded_inventory_candidate": False,
            "script_present": False,
            "form_present": True,
            "tag_names": ["form", "html"],
            "attribute_names": ["class", "name"],
            "input_names": ["seatNo"],
            "structural_class_tokens": ["layout"],
            "element_count": 2,
            "candidate_element_count": 0,
        },
        "sufficiency": "no_inventory_candidate",
    }


def _install_cli_fakes(monkeypatch, result=None):
    config = object()
    query = object()
    client = Mock()
    config_factory = Mock(return_value=config)
    query_factory = Mock(return_value=query)
    client_factory = Mock(return_value=client)
    credentials_reader = Mock(return_value=("member-secret", "password-secret"))
    runner = Mock(return_value=result or _safe_success_report())
    monkeypatch.setattr(module, "SrtConfig", config_factory)
    monkeypatch.setattr(module, "TrainSearchQuery", query_factory)
    monkeypatch.setattr(module, "SrtClient", client_factory)
    monkeypatch.setattr(module, "read_credentials_from_env", credentials_reader)
    monkeypatch.setattr(module, "run_bounded_evidence", runner)
    monkeypatch.setenv("SRT_MOBILE_API_LIVE", "1")
    monkeypatch.setenv("SRT_TEST_DATE", "20260714")
    monkeypatch.setenv("SRT_DEVICE_KEY", "device-key")
    monkeypatch.setenv("SRT_DEPARTURE_STATION_CODE", "0551")
    monkeypatch.setenv("SRT_ARRIVAL_STATION_CODE", "0020")
    monkeypatch.setenv("SRT_DEPARTURE_TIME", "070000")
    monkeypatch.setenv("SRT_DEPARTURE_STATION_NAME", "수서")
    monkeypatch.setenv("SRT_ARRIVAL_STATION_NAME", "부산")
    return {
        "config": config,
        "query": query,
        "client": client,
        "config_factory": config_factory,
        "query_factory": query_factory,
        "client_factory": client_factory,
        "credentials_reader": credentials_reader,
        "runner": runner,
    }


def test_report_is_safe_fails_closed_for_secrets_and_sensitive_shapes():
    serialized = json.dumps(_safe_success_report(), sort_keys=True)
    assert module.report_is_safe(
        serialized,
        ("member-secret", "password-secret"),
    )
    assert not module.report_is_safe('{"x":"member-secret"}', ("member-secret",))
    assert not module.report_is_safe('{"x":"4111-1111-1111-1111"}', ())
    for unsafe in (
        '{"x":"https://example.invalid/private"}',
        '{"x":"member@example.invalid"}',
        '{"authorization":"opaque"}',
        '{"cookie":"opaque"}',
        '{"x":"abcdefghijklmnopqrstuvwxyzABCDEF0123456789"}',
    ):
        assert not module.report_is_safe(unsafe, ())


def test_main_writes_sorted_utf8_json_via_atomic_sibling_and_closes_client(
    monkeypatch,
    tmp_path,
):
    fakes = _install_cli_fakes(monkeypatch)
    output = tmp_path / "evidence.json"
    output.write_text("old", encoding="utf-8")
    replacements = []
    real_replace = module.os.replace

    def replace_spy(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.parent == output.parent
        assert source_path != output
        assert source_path.exists()
        replacements.append((source_path, destination_path))
        real_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", replace_spy)

    assert module.main(["--output", str(output), "--force"]) == 0

    expected = json.dumps(
        _safe_success_report(),
        ensure_ascii=False,
        sort_keys=True,
    )
    assert output.read_text(encoding="utf-8") == expected
    assert replacements == [(replacements[0][0], output)]
    assert not replacements[0][0].exists()
    assert list(tmp_path.iterdir()) == [output]
    fakes["credentials_reader"].assert_called_once_with()
    fakes["config_factory"].assert_called_once_with(device_key="device-key")
    fakes["query_factory"].assert_called_once_with(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20260714",
        departure_time="070000",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    fakes["client_factory"].assert_called_once_with(fakes["config"])
    fakes["runner"].assert_called_once_with(
        fakes["client"],
        login_id="member-secret",
        password="password-secret",
        query=fakes["query"],
    )
    fakes["client"].close.assert_called_once_with()


@pytest.mark.parametrize("missing", ["opt_in", "date"])
def test_main_rejects_missing_live_configuration_before_client_construction(
    monkeypatch,
    tmp_path,
    missing,
):
    fakes = _install_cli_fakes(monkeypatch)
    if missing == "opt_in":
        monkeypatch.delenv("SRT_MOBILE_API_LIVE", raising=False)
    else:
        monkeypatch.delenv("SRT_TEST_DATE", raising=False)

    assert module.main(["--output", str(tmp_path / "evidence.json")]) == 2

    fakes["client_factory"].assert_not_called()
    fakes["runner"].assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_main_rejects_existing_output_without_force_before_client_construction(
    monkeypatch,
    tmp_path,
):
    fakes = _install_cli_fakes(monkeypatch)
    output = tmp_path / "evidence.json"
    output.write_text("keep", encoding="utf-8")

    assert module.main(["--output", str(output)]) == 2

    assert output.read_text(encoding="utf-8") == "keep"
    fakes["credentials_reader"].assert_not_called()
    fakes["client_factory"].assert_not_called()
    fakes["runner"].assert_not_called()
    assert list(tmp_path.iterdir()) == [output]


def test_main_replaces_unsafe_result_with_fixed_safe_report(monkeypatch, tmp_path):
    unsafe = _safe_success_report()
    unsafe["page"] = dict(unsafe["page"])
    unsafe["page"]["input_names"] = ["member-secret"]
    fakes = _install_cli_fakes(monkeypatch, unsafe)
    output = tmp_path / "evidence.json"

    assert module.main(["--output", str(output)]) == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result == {
        "schema_version": 1,
        "status": "unsafe_report",
        "calls": {"login": 1, "search": 1, "seat_page": 1},
        "page": None,
        "sufficiency": "unavailable",
    }
    assert "member-secret" not in output.read_text(encoding="utf-8")
    fakes["client"].close.assert_called_once_with()


def test_main_closes_client_and_leaves_no_file_when_runner_raises(
    monkeypatch,
    tmp_path,
):
    fakes = _install_cli_fakes(monkeypatch)
    fakes["runner"].side_effect = RuntimeError(
        "exception-secret https://example.invalid/private"
    )
    output = tmp_path / "evidence.json"

    assert module.main(["--output", str(output)]) == 1

    fakes["client"].close.assert_called_once_with()
    assert list(tmp_path.iterdir()) == []


def test_main_deletes_temporary_sibling_when_atomic_replace_fails(
    monkeypatch,
    tmp_path,
):
    fakes = _install_cli_fakes(monkeypatch)
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(
        module.os,
        "replace",
        Mock(side_effect=OSError("exception-secret")),
    )

    assert module.main(["--output", str(output)]) == 1

    fakes["client"].close.assert_called_once_with()
    assert list(tmp_path.iterdir()) == []


def test_script_has_no_direct_networking_or_adjacent_operation_imports():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    live_imports: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
            if node.module == "srt_mobile_api.live":
                live_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called_attributes.add(node.func.attr)
    assert imported_roots.isdisjoint({"httpx", "requests", "socket", "urllib"})
    assert live_imports == {
        "_first_complete_srt_seat_train",
        "read_credentials_from_env",
    }
    assert called_attributes.isdisjoint(
        {
            "get_main",
            "get_booking_page",
            "get_notice_list",
            "get_ticket_list",
            "get_mutual_verification",
            "search_group_trains",
            "get_timetable",
            "get_fare",
        }
    )
