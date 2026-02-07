"""Regression tests for virtual_pos_printer spawn-position handling."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from Scripts.virtual_pos_printer import VirtualPosPrinter
import Scripts.virtual_pos_printer as virtual_pos_printer_module


def test_parse_spawn_position_accepts_list_tuple_and_dict() -> None:
    assert VirtualPosPrinter.parse_spawn_position([1434, 57]) == (1434, 57)
    assert VirtualPosPrinter.parse_spawn_position((10, 20)) == (10, 20)
    assert VirtualPosPrinter.parse_spawn_position({"x": 7, "y": 9}) == (7, 9)


def test_parse_spawn_position_rejects_invalid_values() -> None:
    assert VirtualPosPrinter.parse_spawn_position(None) == (100, 100)
    assert VirtualPosPrinter.parse_spawn_position("1434,57") == (100, 100)
    assert VirtualPosPrinter.parse_spawn_position([1]) == (100, 100)
    assert VirtualPosPrinter.parse_spawn_position(["x", "y"]) == (100, 100)

def test_refresh_runtime_settings_updates_spawn_position(tmp_path: Path, monkeypatch) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({"spawn_position": [321, 654]}), encoding="utf-8")

    monkeypatch.setattr(virtual_pos_printer_module, "SETTINGS_FILE", str(settings_file))
    fake_app = SimpleNamespace(
        settings={},
        spawn_position=(100, 100),
        parse_spawn_position=VirtualPosPrinter.parse_spawn_position,
    )

    VirtualPosPrinter.refresh_runtime_settings(fake_app)

    assert fake_app.spawn_position == (321, 654)
    assert fake_app.settings["spawn_position"] == [321, 654]
