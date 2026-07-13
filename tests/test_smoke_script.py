import ast
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock


SCRIPT_PATH = Path("scripts/srt_app_api_smoke.py")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("srt_app_api_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_script_contains_no_endpoint_or_direct_networking_code():
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots.isdisjoint({"aiohttp", "http", "httpx", "requests", "socket", "urllib"})
    assert ".do" not in source
    for forbidden in (
        "act_19",
        "/arc/selectListArc02012_n.do",
        "/arc/selectListArc05013_n.do",
        "/arc/selectListArc06014_n.do",
        "/arc/selectListArc10013_n.do",
        "/ard/",
        "/ata/",
        "--keep-raw",
    ):
        assert forbidden not in source


def test_legacy_script_delegates_only_to_safe_live_helper(monkeypatch, capsys):
    module = _load_smoke_module()
    config = object()
    query = object()
    client = Mock()
    result = {"loggedIn": True, "personalTrainCount": 1, "fareItemCount": 1}
    config_factory = Mock(return_value=config)
    query_factory = Mock(return_value=query)
    client_factory = Mock(return_value=client)
    credentials_reader = Mock(return_value=("member", "password"))
    live_smoke = Mock(return_value=result)
    monkeypatch.setattr(module, "SrtConfig", config_factory)
    monkeypatch.setattr(module, "TrainSearchQuery", query_factory)
    monkeypatch.setattr(module, "SrtClient", client_factory)
    monkeypatch.setattr(module, "read_credentials_from_env", credentials_reader)
    monkeypatch.setattr(module, "run_live_smoke", live_smoke)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT_PATH),
            "--date",
            "20260710",
            "--depart-code",
            "0551",
            "--depart-name",
            "수서",
            "--arrive-code",
            "0020",
            "--arrive-name",
            "부산",
            "--device-key",
            "device-key",
        ],
    )

    assert module.main() == 0

    credentials_reader.assert_called_once_with()
    config_factory.assert_called_once_with(device_key="device-key")
    query_factory.assert_called_once_with(
        departure_station_code="0551",
        arrival_station_code="0020",
        departure_date="20260710",
        departure_station_name="수서",
        arrival_station_name="부산",
    )
    client_factory.assert_called_once_with(config)
    live_smoke.assert_called_once_with(
        client,
        login_id="member",
        password="password",
        query=query,
    )
    client.close.assert_called_once_with()
    assert json.loads(capsys.readouterr().out) == result
