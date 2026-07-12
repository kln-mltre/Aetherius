"""Fixtures for the store unit tests: a fresh SQLite store on a per-test temporary file.

Every test gets its own ``aetherius.db`` under ``tmp_path``; the real ``~/.aetherius`` is never
touched. The store is built directly (not via ``get_store()``) so no environment override is needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from aetherius.store import RunRecord, ScheduleRecord, Store


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    instance = Store(tmp_path / "aetherius.db")
    yield instance
    instance.close()


def make_schedule(schedule_id: str = "sch-1", **overrides: Any) -> ScheduleRecord:
    """A minimal valid ScheduleRecord; override any field for a specific case."""
    base: dict[str, Any] = {
        "id": schedule_id,
        "name": "watch stock",
        "blueprint": "examples/vector/watch.blueprint.json",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return ScheduleRecord(**base)


def make_run(run_id: str = "run-1", **overrides: Any) -> RunRecord:
    """A minimal valid RunRecord; override any field for a specific case."""
    base: dict[str, Any] = {
        "run_id": run_id,
        "blueprint_name": "watch",
        "status": "success",
        "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return RunRecord(**base)
