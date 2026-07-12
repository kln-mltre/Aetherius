"""Tests for store/engine.py — connection lifecycle, migrations, durability, and the singleton."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from aetherius.config import settings as settings_mod
from aetherius.store import Store
from aetherius.store import engine as engine_mod

from .conftest import make_run, make_schedule

pytestmark = pytest.mark.unit


def _user_version(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_creates_the_file_and_missing_parent_dirs(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "aetherius.db"
    store = Store(db_path)
    try:
        assert db_path.exists()
    finally:
        store.close()


def test_schema_is_migrated_to_the_latest_version(tmp_path: Path) -> None:
    db_path = tmp_path / "aetherius.db"
    Store(db_path).close()
    assert _user_version(db_path) == 1


def test_reopening_the_same_file_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "aetherius.db"
    first = Store(db_path)
    first.schedules.create(make_schedule())
    first.runs.record(make_run())
    first.state.set("sch-1", "stock", "in-stock")
    first.close()

    second = Store(db_path)
    try:
        assert second.schedules.get("sch-1") is not None
        assert second.runs.get("run-1") is not None
        assert second.state.get("sch-1", "stock") == "in-stock"
        # Reopening an already-migrated database must not re-run or fail its migration.
        assert _user_version(db_path) == 1
    finally:
        second.close()


@pytest.fixture
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Point both singletons at a temp data dir and reset their caches around the test.
    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()


def test_get_store_is_a_singleton_rooted_at_settings(
    _isolated_data_dir: None, tmp_path: Path
) -> None:
    store = engine_mod.get_store()
    assert engine_mod.get_store() is store
    assert (tmp_path / "aetherius.db").exists()
    store.close()
