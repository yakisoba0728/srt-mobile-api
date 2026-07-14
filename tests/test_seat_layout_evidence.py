from __future__ import annotations

import ast
import hashlib
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
    "element_count",
    "inventory_marker_element_count",
    "structural_names",
    "source_categories",
    "scripts",
    "forms",
    "iframes",
    "embedded_json",
    "external_handoff_candidate",
}
REPORT_KEYS = {"schema_version", "status", "calls", "page", "sufficiency"}
STRUCTURAL_NAME_KEYS = {
    "tag_names",
    "attribute_names",
    "input_names",
    "class_tokens",
    "inventory_names",
}
SCRIPT_KEYS = {
    "count",
    "inline_count",
    "same_origin_count",
    "cross_origin_count",
    "items",
}
SCRIPT_ITEM_KEYS = {
    "kind",
    "type",
    "async",
    "defer",
    "path",
    "length",
    "truncated",
    "sha256",
    "ajax_primitives",
    "http_methods",
    "route_paths",
    "cross_origin_route_count",
    "payload_keys",
    "response_paths",
    "inventory_names",
}
FORM_KEYS = {
    "count",
    "same_origin_count",
    "cross_origin_count",
    "self_count",
    "items",
}
FORM_ITEM_KEYS = {"method", "target", "path", "input_names", "inventory_names"}
IFRAME_KEYS = {
    "count",
    "same_origin_count",
    "cross_origin_count",
    "unresolved_count",
    "same_origin_paths",
}
JSON_KEYS = {"count", "valid_count", "invalid_count", "items"}
JSON_ITEM_KEYS = {
    "root_type",
    "key_types",
    "array_cardinalities",
    "inventory_names",
    "max_depth",
    "truncated",
}


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
    candidates = "".join(
        f'<div class="seatItem{index} available" id="scarSeat{index}"></div>'
        for index in range(10_005)
    )
    return (
        f"<html {attributes}><body>"
        "<h1>좌석선택</h1>"
        "visible-secret-seat-123456"
        '<form method="post" action="/arc/seatForm.do?token=query-secret">'
        '<input name="scarNo" value="secret-seat-123456">'
        '<input name="seatNo" value="4111-1111-1111-1111">'
        '<input name="authorization" value="opaque-token">'
        '<input name="private123456" value="ignored">'
        '<input name="member@example.invalid" value="ignored">'
        '<input name="https://example.invalid/private" value="ignored">'
        "</form>"
        '<form action="https://example.invalid/private?token=cross-secret"></form>'
        '<a href="https://example.invalid/private?srtJob=seatmap">seat map</a>'
        '<button data-seat-no="secret-seat-123456" id="private-id"></button>'
        f'<section class="layout {classes} secret-seat-123456"></section>'
        '<script src="/assets/seat-map.js?token=script-query"></script>'
        '<script src="https://cdn.example.invalid/private.js?token=cross"></script>'
        '<iframe src="/arc/seat-frame.do?token=iframe-query"></iframe>'
        '<iframe src="https://frames.example.invalid/private?token=cross"></iframe>'
        '<script>\n'
        'fetch("/arc/seatInventory.do?token=route-secret", {method: "POST"});\n'
        '$.ajax({url: "https://app.srail.or.kr/arc/seatList.do?secret=query", '
        'type: "POST", data: {scarSeatNo: "A1", token: "opaque-token"}});\n'
        'const seatCars = response.seatCars; const seatRows = response.seatRows;\n'
        'const password = "password-secret"; const email = "member@example.invalid";\n'
        'const card = "4111-1111-1111-1111";\n'
        "</script>"
        '<script type="application/json">'
        '{"cars":[{"carNo":"car-secret-123456","seats":['
        '{"seatNo":"seat-secret-123456","available":true}]}],'
        '"credential":"member-secret","url":"https://example.invalid/private"}'
        "</script>"
        f"{tags}{inputs}{candidates}</body></html>"
    )


def test_collect_page_evidence_is_bounded_deterministic_and_value_free():
    raw = _synthetic_html()

    evidence = module.collect_page_evidence(raw)

    assert set(evidence) == PAGE_KEYS
    assert evidence == module.collect_page_evidence(raw)
    assert evidence["marker_present"] is True
    assert evidence["external_handoff_candidate"] is True
    assert evidence["element_count"] == 10_000
    assert evidence["inventory_marker_element_count"] == 10_000
    assert set(evidence["structural_names"]) == STRUCTURAL_NAME_KEYS
    assert set(evidence["scripts"]) == SCRIPT_KEYS
    assert set(evidence["forms"]) == FORM_KEYS
    assert set(evidence["iframes"]) == IFRAME_KEYS
    assert set(evidence["embedded_json"]) == JSON_KEYS
    assert evidence["source_categories"] == sorted(
        {
            "cross_origin_form_reference",
            "cross_origin_iframe_reference",
            "cross_origin_script_reference",
            "embedded_dom_inventory_candidate",
            "embedded_json_inventory_candidate",
            "external_seat_map_handoff",
            "inline_ajax_inventory_contract",
            "inline_script_inventory_candidate",
            "same_origin_form_reference",
            "same_origin_iframe_reference",
            "same_origin_script_inventory_reference",
            "same_origin_script_reference",
        }
    )
    structural_names = evidence["structural_names"]
    assert all(
        len(item) <= 64
        for key in (
            "tag_names",
            "attribute_names",
            "input_names",
            "class_tokens",
            "inventory_names",
        )
        for item in structural_names[key]
    )
    assert all(
        items == sorted(set(items)) and len(items) <= 64
        for items in structural_names.values()
    )
    assert evidence["scripts"]["count"] == 4
    assert evidence["scripts"]["inline_count"] == 2
    assert evidence["scripts"]["same_origin_count"] == 1
    assert evidence["scripts"]["cross_origin_count"] == 1
    assert all(
        set(item) == SCRIPT_ITEM_KEYS for item in evidence["scripts"]["items"]
    )
    same_origin_script = next(
        item
        for item in evidence["scripts"]["items"]
        if item["kind"] == "same_origin_external"
    )
    assert same_origin_script["path"] == "/assets/seat-map.js"
    ajax_script = next(
        item
        for item in evidence["scripts"]["items"]
        if item["kind"] == "inline" and item["type"] == "classic"
    )
    assert ajax_script["path"] is None
    assert ajax_script["sha256"] is not None
    assert len(ajax_script["sha256"]) == 64
    assert ajax_script["ajax_primitives"] == ["fetch", "jquery_ajax"]
    assert ajax_script["http_methods"] == ["POST"]
    assert ajax_script["route_paths"] == [
        "/arc/seatInventory.do",
        "/arc/seatList.do",
    ]
    assert ajax_script["payload_keys"] == ["scarSeatNo"]
    assert ajax_script["response_paths"] == [
        "response.seatCars",
        "response.seatRows",
    ]
    assert evidence["forms"]["count"] == 2
    assert evidence["forms"]["same_origin_count"] == 1
    assert evidence["forms"]["cross_origin_count"] == 1
    assert set(evidence["forms"]["items"][0]) == FORM_ITEM_KEYS
    assert evidence["forms"]["items"][0]["path"] == "/arc/seatForm.do"
    assert evidence["iframes"]["same_origin_paths"] == ["/arc/seat-frame.do"]
    json_item = evidence["embedded_json"]["items"][0]
    assert set(json_item) == JSON_ITEM_KEYS
    assert json_item["root_type"] == "object"
    assert json_item["inventory_names"] == ["carNo", "cars", "seatNo", "seats"]
    assert json_item["array_cardinalities"] == [
        {"path": "cars", "count": 1, "truncated": False},
        {"path": "cars[].seats", "count": 1, "truncated": False},
    ]
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
        "password-secret",
        "opaque-token",
        "query-secret",
        "script-query",
        "iframe-query",
        "route-secret",
    ):
        assert forbidden not in serialized
    report = module._result(
        "success",
        {"login": 1, "search": 1, "seat_page": 1},
        evidence,
    )
    assert module.report_is_safe(
        json.dumps(report, sort_keys=True),
        ("member-secret", "password-secret", "opaque-token"),
    )


def test_generic_scripts_do_not_imply_an_inventory_source():
    evidence = module.collect_page_evidence(
        '<main><h1>좌석선택</h1>'
        '<script src="/assets/app.js?token=query-secret"></script>'
        '<script>console.log("hello")</script>'
        '<a href="https://www.korail.com/info">info</a></main>'
    )

    assert evidence["external_handoff_candidate"] is False
    assert evidence["source_categories"] == [
        "generic_script",
        "same_origin_script_reference",
    ]
    assert module._result(
        "success",
        {"login": 1, "search": 1, "seat_page": 1},
        evidence,
    )["sufficiency"] == "no_inventory_source"
    assert "https://www.korail.com/info" not in json.dumps(evidence)


def test_inline_literals_and_comments_do_not_become_inventory_evidence():
    evidence = module.collect_page_evidence(
        "<script>"
        'const x = "seat42"; const y = "scar7";'
        '// fetch("/arc/seatInventory.do", {method: "POST", '
        'data: {seatNo: "A1"}}); response.seatCars;\n'
        '/* $.ajax({url: "https://example.invalid/seatmap"}); '
        "new XMLHttpRequest(); result.scarRows; */"
        "</script>"
    )

    item = evidence["scripts"]["items"][0]
    assert item["ajax_primitives"] == []
    assert item["http_methods"] == []
    assert item["route_paths"] == []
    assert item["payload_keys"] == []
    assert item["response_paths"] == []
    assert item["inventory_names"] == []
    assert evidence["external_handoff_candidate"] is False
    assert evidence["source_categories"] == ["generic_script"]
    assert module._result(
        "success",
        {"login": 1, "search": 1, "seat_page": 1},
        evidence,
    )["sufficiency"] == "no_inventory_source"
    serialized = json.dumps(evidence)
    assert "seat42" not in serialized
    assert "scar7" not in serialized


def test_application_json_is_summarized_without_values_and_malformed_json_is_fixed():
    evidence = module.collect_page_evidence(
        '<script type="application/json">'
        '{"cars":[{"seats":[{"seatNo":"A1","available":false},'
        '{"seatNo":"B2","available":true}]}],"token":"opaque-secret"}'
        "</script>"
        '<script type="application/json">{"cars": [}</script>'
    )

    assert evidence["embedded_json"]["count"] == 2
    assert evidence["embedded_json"]["valid_count"] == 1
    assert evidence["embedded_json"]["invalid_count"] == 1
    item = evidence["embedded_json"]["items"][0]
    assert item["root_type"] == "object"
    assert item["key_types"] == [
        "cars:array",
        "cars[].seats:array",
        "cars[].seats[].available:boolean",
        "cars[].seats[].seatNo:string",
    ]
    assert item["array_cardinalities"] == [
        {"path": "cars", "count": 1, "truncated": False},
        {"path": "cars[].seats", "count": 2, "truncated": False},
    ]
    assert "A1" not in json.dumps(evidence)
    assert "B2" not in json.dumps(evidence)
    assert "opaque-secret" not in json.dumps(evidence)


def test_application_json_dynamic_seat_keys_are_treated_as_values():
    evidence = module.collect_page_evidence(
        '<script type="application/json">'
        '{"cars":[{"seats":[{"seatNo":"A1","carNo":"7",'
        '"available":true}]}],"seat42":{"A1":true},"scar7":[]}'
        "</script>"
    )

    item = evidence["embedded_json"]["items"][0]
    assert item["key_types"] == [
        "cars:array",
        "cars[].seats:array",
        "cars[].seats[].available:boolean",
        "cars[].seats[].carNo:string",
        "cars[].seats[].seatNo:string",
    ]
    assert item["inventory_names"] == ["carNo", "cars", "seatNo", "seats"]
    serialized = json.dumps(evidence)
    assert "seat42" not in serialized
    assert "scar7" not in serialized
    assert "A1" not in serialized

    dynamic_only = module.collect_page_evidence(
        '<script type="application/json">'
        '{"seat42":{"A1":true},"scar7":[]}'
        "</script>"
    )
    assert dynamic_only["embedded_json"]["items"][0]["key_types"] == []
    assert dynamic_only["embedded_json"]["items"][0]["inventory_names"] == []
    assert "embedded_json_inventory_candidate" not in dynamic_only[
        "source_categories"
    ]


def test_camel_case_numeric_markers_and_malformed_markup_are_counted_not_emitted():
    evidence = module.collect_page_evidence(
        '<div id="scarSeat1"><span class="seatCell2">x'
        '<button data-scar-seat3="car-7"></button>'
        '<script type="application/json">not-json'
    )

    assert evidence["inventory_marker_element_count"] == 3
    assert "embedded_dom_inventory_candidate" in evidence["source_categories"]
    serialized = json.dumps(evidence)
    assert "scarSeat1" not in serialized
    assert "seatCell2" not in serialized
    assert "car-7" not in serialized
    assert evidence["embedded_json"]["invalid_count"] == 1


def test_dynamic_seat_paths_are_not_retained_but_static_routes_are():
    evidence = module.collect_page_evidence(
        '<script src="/arc/seat/A1.js"></script>'
        '<script src="/assets/seat42.js"></script>'
        '<script src="/assets/app.js?query=secret"></script>'
        '<form action="/arc/car/7.do"></form>'
        '<form action="/arc/normal.do?query=secret"></form>'
        '<iframe src="/arc/seat/A1.do"></iframe>'
        '<iframe src="/arc/seat-frame.do?query=secret"></iframe>'
        "<script>"
        'fetch("/arc/seat/A1"); fetch("/arc/seat/A1.do"); '
        'fetch("/arc/car/7"); fetch("/arc/car/7.js"); '
        'fetch("/arc/seat42.do"); '
        'fetch("/arc/selectListArc02012_n.do?query=secret");'
        "</script>"
    )

    external_paths = [
        item["path"]
        for item in evidence["scripts"]["items"]
        if item["kind"] == "same_origin_external"
    ]
    assert external_paths == ["/assets/app.js"]
    assert [
        item["path"] for item in evidence["forms"]["items"] if item["path"]
    ] == ["/arc/normal.do"]
    assert evidence["iframes"]["same_origin_paths"] == ["/arc/seat-frame.do"]
    inline = next(
        item
        for item in evidence["scripts"]["items"]
        if item["kind"] == "inline"
    )
    assert inline["route_paths"] == ["/arc/selectListArc02012_n.do"]
    serialized = json.dumps(evidence)
    assert "/arc/seat/A1" not in serialized
    assert "/arc/car/7" not in serialized
    assert "/assets/seat42.js" not in serialized
    assert "query=secret" not in serialized


def test_explicit_zero_port_is_cross_origin_for_every_target_kind():
    evidence = module.collect_page_evidence(
        '<script src="https://app.srail.or.kr:0/assets/app.js"></script>'
        '<form action="https://app.srail.or.kr:0/arc/normal.do"></form>'
        '<iframe src="https://app.srail.or.kr:0/arc/frame.do"></iframe>'
    )

    assert evidence["scripts"]["same_origin_count"] == 0
    assert evidence["scripts"]["cross_origin_count"] == 1
    assert evidence["forms"]["same_origin_count"] == 0
    assert evidence["forms"]["cross_origin_count"] == 1
    assert evidence["iframes"]["same_origin_count"] == 0
    assert evidence["iframes"]["cross_origin_count"] == 1
    assert evidence["scripts"]["items"] == []
    assert evidence["forms"]["items"] == []
    assert evidence["iframes"]["same_origin_paths"] == []


def test_script_items_lengths_and_json_cardinalities_are_bounded():
    oversized_script = "x" * (module.MAX_SCRIPT_CHARS + 100)
    scripts = (
        f"<script>{oversized_script}</script>"
        + "".join("<script>void 0</script>" for _ in range(69))
    )
    json_values = ",".join(str(index) for index in range(70))

    evidence = module.collect_page_evidence(
        scripts
        + '<script type="application/json">'
        + f'{{"seats":[{json_values}],"scarRows":[]}}'
        + "</script>"
    )

    assert evidence["scripts"]["count"] == 71
    assert len(evidence["scripts"]["items"]) == 64
    assert evidence["scripts"]["items"][0]["length"] == module.MAX_SCRIPT_CHARS
    assert evidence["scripts"]["items"][0]["truncated"] is True
    assert evidence["scripts"]["items"][0]["sha256"] == hashlib.sha256(
        oversized_script[: module.MAX_SCRIPT_CHARS].encode("utf-8")
    ).hexdigest()
    assert evidence["embedded_json"]["items"][0]["array_cardinalities"] == [
        {"path": "scarRows", "count": 0, "truncated": False},
        {"path": "seats", "count": 64, "truncated": True},
    ]
    assert evidence["embedded_json"]["items"][0]["truncated"] is True


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
    assert result["schema_version"] == 2
    assert result["status"] == "success"
    assert result["calls"] == {"login": 1, "search": 1, "seat_page": 1}
    assert result["page"]["inventory_marker_element_count"] == 2
    assert result["sufficiency"] == "inventory_source_candidate"
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
        "schema_version": 2,
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
        "schema_version": 2,
        "status": "success",
        "calls": {"login": 1, "search": 1, "seat_page": 1},
        "page": {
            "marker_present": True,
            "element_count": 2,
            "inventory_marker_element_count": 0,
            "structural_names": {
                "tag_names": ["html"],
                "attribute_names": [],
                "input_names": [],
                "class_tokens": ["layout"],
                "inventory_names": [],
            },
            "source_categories": [],
            "scripts": {
                "count": 0,
                "inline_count": 0,
                "same_origin_count": 0,
                "cross_origin_count": 0,
                "items": [],
            },
            "forms": {
                "count": 0,
                "same_origin_count": 0,
                "cross_origin_count": 0,
                "self_count": 0,
                "items": [],
            },
            "iframes": {
                "count": 0,
                "same_origin_count": 0,
                "cross_origin_count": 0,
                "unresolved_count": 0,
                "same_origin_paths": [],
            },
            "embedded_json": {
                "count": 0,
                "valid_count": 0,
                "invalid_count": 0,
                "items": [],
            },
            "external_handoff_candidate": False,
        },
        "sufficiency": "no_inventory_source",
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


def test_write_atomic_without_force_publishes_without_replace_and_cleans_temp(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(
        module.os,
        "replace",
        Mock(side_effect=AssertionError("no-force publish must not replace")),
    )

    assert module._write_atomic(output, "new-report", force=False) is True

    assert output.read_text(encoding="utf-8") == "new-report"
    assert list(tmp_path.iterdir()) == [output]


def test_write_atomic_without_force_preserves_destination_created_at_publish(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "evidence.json"
    real_link = module.os.link

    def create_destination_then_link(source, destination):
        output.write_text("concurrent-report", encoding="utf-8")
        real_link(source, destination)

    monkeypatch.setattr(module.os, "link", create_destination_then_link)

    assert module._write_atomic(output, "new-report", force=False) is False

    assert output.read_text(encoding="utf-8") == "concurrent-report"
    assert list(tmp_path.iterdir()) == [output]


def test_write_atomic_without_force_cleans_temp_when_link_errors(
    monkeypatch,
    tmp_path,
):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(
        module.os,
        "link",
        Mock(side_effect=OSError("publication failed")),
    )

    assert module._write_atomic(output, "new-report", force=False) is False

    assert list(tmp_path.iterdir()) == []


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
    unsafe["page"]["structural_names"]["input_names"] = ["member-secret"]
    fakes = _install_cli_fakes(monkeypatch, unsafe)
    output = tmp_path / "evidence.json"

    assert module.main(["--output", str(output)]) == 0

    result = json.loads(output.read_text(encoding="utf-8"))
    assert result == {
        "schema_version": 2,
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


def test_main_deletes_temporary_sibling_when_force_replace_fails(
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

    assert module.main(["--output", str(output), "--force"]) == 1

    fakes["client"].close.assert_called_once_with()
    assert list(tmp_path.iterdir()) == []


def test_script_has_no_direct_networking_or_adjacent_operation_imports():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    imported_modules: set[str] = set()
    live_imports: set[str] = set()
    called_attributes: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
            imported_modules.add(node.module)
            if node.module == "srt_mobile_api.live":
                live_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            called_attributes.add(node.func.attr)
    assert imported_roots.isdisjoint({"httpx", "requests", "socket"})
    assert all(
        not name.startswith("urllib.") or name == "urllib.parse"
        for name in imported_modules
    )
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
