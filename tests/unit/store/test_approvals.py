"""Unit tests for the approvals audit trail (store/approvals.py) and its migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aetherius.store import Store
from aetherius.store.schema import _MIGRATIONS, apply_migrations

pytestmark = pytest.mark.unit


def test_open_pending_then_resolve(store: Store) -> None:
    store.approvals.open_pending("tok-1", "run-1", "proceed?", step_id="approve")
    row = store.approvals.get("tok-1")
    assert row is not None
    assert row["status"] == "pending"
    assert row["run_id"] == "run-1"
    assert row["step_id"] == "approve"
    assert row["decided_at"] is None

    store.approvals.resolve("tok-1", "approved", decided_by="api")
    row = store.approvals.get("tok-1")
    assert row is not None
    assert row["status"] == "approved"
    assert row["decided_by"] == "api"
    assert row["decided_at"] is not None


def test_get_unknown_token_returns_none(store: Store) -> None:
    assert store.approvals.get("nope") is None


def test_for_run_lists_requests_in_order(store: Store) -> None:
    store.approvals.open_pending("t1", "run-x", "first")
    store.approvals.open_pending("t2", "run-x", "second")
    store.approvals.open_pending("t3", "run-y", "other")
    rows = store.approvals.for_run("run-x")
    assert [r["token"] for r in rows] == ["t1", "t2"]


def test_migration_upgrades_a_v1_database_in_place(tmp_path: Path) -> None:
    # Build a database at schema v1 (pre-2-E), then confirm apply_migrations adds the approvals table
    # without touching the existing data.
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db)
    for statement in _MIGRATIONS[0]:
        conn.execute(statement)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()

    store = Store(db)
    try:
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == len(_MIGRATIONS)
        store.approvals.open_pending("tok", "run", "ok?")
        assert store.approvals.get("tok") is not None
    finally:
        store.close()


def test_apply_migrations_is_idempotent(tmp_path: Path) -> None:
    db = tmp_path / "twice.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    apply_migrations(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    apply_migrations(conn)  # second call is a no-op
    assert conn.execute("PRAGMA user_version").fetchone()[0] == version
    conn.close()
