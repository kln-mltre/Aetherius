"""Tests for store/schedules.py — CRUD, the due-query, and mark_fired."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aetherius.store import Store

from .conftest import make_schedule

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_create_then_get_round_trips_all_fields(store: Store) -> None:
    record = make_schedule(
        inputs={"group": "TP-A1"},
        secrets=["CAS_PASSWORD"],
        trigger={"kind": "interval", "seconds": 900},
        notify={"channel": "ntfy", "on_change": True},
        next_run_at=_NOW,
    )
    store.schedules.create(record)

    loaded = store.schedules.get("sch-1")
    assert loaded == record


def test_get_unknown_returns_none(store: Store) -> None:
    assert store.schedules.get("missing") is None


def test_all_lists_every_schedule(store: Store) -> None:
    store.schedules.create(make_schedule("a"))
    store.schedules.create(make_schedule("b"))
    assert {s.id for s in store.schedules.all()} == {"a", "b"}


def test_update_persists_changes(store: Store) -> None:
    store.schedules.create(make_schedule())
    updated = make_schedule(
        name="renamed", enabled=False, trigger={"kind": "cron", "expr": "* * * * *"}
    )
    store.schedules.update(updated)

    loaded = store.schedules.get("sch-1")
    assert loaded is not None
    assert loaded.name == "renamed"
    assert loaded.enabled is False
    assert loaded.trigger == {"kind": "cron", "expr": "* * * * *"}


def test_delete_removes_the_schedule(store: Store) -> None:
    store.schedules.create(make_schedule())
    store.schedules.delete("sch-1")
    assert store.schedules.get("sch-1") is None


def test_due_returns_only_past_enabled_schedules(store: Store) -> None:
    store.schedules.create(make_schedule("past", next_run_at=_NOW - timedelta(minutes=1)))
    store.schedules.create(make_schedule("exactly-now", next_run_at=_NOW))
    store.schedules.create(make_schedule("future", next_run_at=_NOW + timedelta(minutes=1)))
    store.schedules.create(make_schedule("no-next", next_run_at=None))
    store.schedules.create(
        make_schedule("disabled", enabled=False, next_run_at=_NOW - timedelta(hours=1))
    )

    due_ids = [s.id for s in store.schedules.due(_NOW)]
    assert due_ids == ["past", "exactly-now"]


def test_mark_fired_stamps_next_and_last_run(store: Store) -> None:
    store.schedules.create(make_schedule(next_run_at=_NOW - timedelta(minutes=1)))
    next_run = _NOW + timedelta(minutes=15)
    store.schedules.mark_fired("sch-1", next_run)

    loaded = store.schedules.get("sch-1")
    assert loaded is not None
    assert loaded.next_run_at == next_run
    assert loaded.last_run_at is not None
    # No longer due: its next fire is in the future.
    assert store.schedules.due(_NOW) == []


def test_mark_fired_with_none_exhausts_the_schedule(store: Store) -> None:
    store.schedules.create(make_schedule(next_run_at=_NOW - timedelta(minutes=1)))
    store.schedules.mark_fired("sch-1", None)

    loaded = store.schedules.get("sch-1")
    assert loaded is not None
    assert loaded.next_run_at is None
    assert store.schedules.due(_NOW) == []
