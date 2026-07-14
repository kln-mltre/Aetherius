"""Fixtures for the scheduler unit tests.

A fresh store on a per-test temporary file (the real ``~/.aetherius`` is never touched), a schedule
factory, and a deterministic timezone: cron math depends on the host's local zone, so tests pin
``TZ=Europe/Paris`` (a zone with DST, matching the documented examples) and restore it afterwards.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import tzlocal

from aetherius.store import ScheduleRecord, Store


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    instance = Store(tmp_path / "aetherius.db")
    yield instance
    instance.close()


@pytest.fixture
def paris_tz() -> Iterator[None]:
    """Pin the process to Europe/Paris for deterministic local-time cron assertions."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Paris"
    time.tzset()
    tzlocal.reload_localzone()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()
    tzlocal.reload_localzone()


def make_schedule(schedule_id: str = "sch-1", **overrides: Any) -> ScheduleRecord:
    """A minimal valid ScheduleRecord with an interval trigger; override any field."""
    base: dict[str, Any] = {
        "id": schedule_id,
        "name": "watch",
        "blueprint": "examples/vector/daemon-selftest.blueprint.json",
        "trigger": {"kind": "interval", "seconds": 60},
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return ScheduleRecord(**base)
