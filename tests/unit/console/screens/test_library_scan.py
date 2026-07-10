"""Tests for console/screens/library_scan.py — pure discovery/validation, no Textual involved."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.console.screens.library_scan import (
    BlueprintEntry,
    EntryStatus,
    discover_blueprint_dirs,
    entry_status,
    scan_blueprints,
)

pytestmark = pytest.mark.unit

_VALID_VECTOR = {
    "aetherius": "1.0",
    "name": "test.valid",
    "act": "vector",
    "steps": [{"id": "s", "action": "set", "value": "x"}],
}


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_discover_blueprint_dirs_finds_cwd_blueprints_dir(tmp_path: Path) -> None:
    (tmp_path / "blueprints").mkdir()

    dirs = discover_blueprint_dirs(tmp_path)

    assert tmp_path / "blueprints" in dirs


def test_discover_blueprint_dirs_skips_missing_cwd_dir(tmp_path: Path) -> None:
    dirs = discover_blueprint_dirs(tmp_path)

    assert (tmp_path / "blueprints") not in dirs


def test_scan_blueprints_valid_entry(tmp_path: Path) -> None:
    _write(tmp_path / "ok.blueprint.json", _VALID_VECTOR)

    entries = scan_blueprints([tmp_path])

    assert len(entries) == 1
    entry = entries[0]
    assert entry.error is None
    assert entry.act == "vector"
    assert entry.blueprint is not None
    assert entry.blueprint.name == "test.valid"


def test_scan_blueprints_load_error_is_captured(tmp_path: Path) -> None:
    (tmp_path / "broken.blueprint.json").write_text("{not json", encoding="utf-8")

    entries = scan_blueprints([tmp_path])

    assert len(entries) == 1
    assert entries[0].error is not None
    assert entries[0].blueprint is None


def test_scan_blueprints_schema_error_is_captured(tmp_path: Path) -> None:
    bad = dict(_VALID_VECTOR)
    del bad["act"]  # required by the schema
    _write(tmp_path / "no-act.blueprint.json", bad)

    entries = scan_blueprints([tmp_path])

    assert len(entries) == 1
    assert entries[0].error is not None


def _entry(act: str | None, error: str | None) -> BlueprintEntry:
    return BlueprintEntry(path=Path("x.blueprint.json"), blueprint=None, act=act, error=error)


def test_entry_status_ready_for_implemented_act() -> None:
    # vector and continuum have drivers today.
    assert entry_status(_entry("vector", None)) is EntryStatus.READY
    assert entry_status(_entry("continuum", None)) is EntryStatus.READY


def test_entry_status_pending_for_unimplemented_act() -> None:
    assert entry_status(_entry("oracle", None)) is EntryStatus.ACT_PENDING


def test_entry_status_invalid_when_error_present() -> None:
    assert entry_status(_entry("vector", "boom")) is EntryStatus.INVALID
    assert entry_status(_entry(None, None)) is EntryStatus.INVALID


def test_scan_blueprints_capability_validation_error_is_captured(tmp_path: Path) -> None:
    bad = {
        "aetherius": "1.0",
        "name": "test.bad-act",
        "act": "vector",
        "steps": [{"id": "s", "action": "click", "selector": "#x"}],  # continuum-only action
    }
    _write(tmp_path / "bad-act.blueprint.json", bad)

    entries = scan_blueprints([tmp_path])

    assert len(entries) == 1
    assert entries[0].error is not None
    assert "click" in entries[0].error
