"""Tests for store/runs.py — recording outcomes and reading recent history."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aetherius.store import Store

from .conftest import make_run

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_record_then_get_round_trips(store: Store) -> None:
    record = make_run(
        status="partial",
        schedule_id="sch-1",
        error="one step failed",
        outputs={"events": [1, 2, 3]},
        finished_at=_T0 + timedelta(seconds=5),
    )
    store.runs.record(record)
    assert store.runs.get("run-1") == record


def test_get_unknown_returns_none(store: Store) -> None:
    assert store.runs.get("missing") is None


def test_recent_orders_newest_first(store: Store) -> None:
    store.runs.record(make_run("old", started_at=_T0))
    store.runs.record(make_run("mid", started_at=_T0 + timedelta(minutes=1)))
    store.runs.record(make_run("new", started_at=_T0 + timedelta(minutes=2)))

    assert [r.run_id for r in store.runs.recent()] == ["new", "mid", "old"]


def test_recent_respects_limit(store: Store) -> None:
    for index in range(5):
        store.runs.record(make_run(f"run-{index}", started_at=_T0 + timedelta(minutes=index)))
    recent = store.runs.recent(limit=2)
    assert [r.run_id for r in recent] == ["run-4", "run-3"]


def test_recent_filters_by_blueprint(store: Store) -> None:
    store.runs.record(make_run("a", blueprint_name="alpha", started_at=_T0))
    store.runs.record(make_run("b", blueprint_name="beta", started_at=_T0 + timedelta(minutes=1)))
    recent = store.runs.recent(blueprint="alpha")
    assert [r.run_id for r in recent] == ["a"]


def test_recent_filters_by_schedule(store: Store) -> None:
    store.runs.record(make_run("scheduled", schedule_id="sch-1", started_at=_T0))
    store.runs.record(make_run("manual", schedule_id=None, started_at=_T0 + timedelta(minutes=1)))
    recent = store.runs.recent(schedule_id="sch-1")
    assert [r.run_id for r in recent] == ["scheduled"]
