"""Fixtures for the Schedules screens: an isolated store seeded with a schedule on the selftest
Blueprint, and a harness app that pushes the screen under test."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from aetherius.store import ScheduleRecord, Store

_NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    instance = Store(tmp_path / "aetherius.db")
    yield instance
    instance.close()


def make_schedule(
    examples_dir: Path, schedule_id: str = "sch-1", **overrides: Any
) -> ScheduleRecord:
    """A valid schedule pointing at the runnable selftest Blueprint; override any field."""
    base: dict[str, Any] = {
        "id": schedule_id,
        "name": "selftest-watch",
        "blueprint": str(examples_dir / "vector" / "daemon-selftest.blueprint.json"),
        "inputs": {"subject": "console"},
        "trigger": {"kind": "interval", "seconds": 3600},
        "created_at": _NOW,
        "next_run_at": _NOW + timedelta(hours=1),
    }
    base.update(overrides)
    return ScheduleRecord(**base)
