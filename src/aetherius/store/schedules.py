"""ScheduleRepository: durable CRUD over schedules, plus the due-query the scheduler polls."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .models import ScheduleRecord

_PENDING = "Jalon 1.5-A (store): schedule persistence not implemented yet."


class ScheduleRepository:
    """Persists schedules and answers "which schedules are due to fire now?"."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, record: ScheduleRecord) -> str:
        """Insert a schedule and return its id."""
        raise NotImplementedError(_PENDING)

    def get(self, schedule_id: str) -> ScheduleRecord | None:
        raise NotImplementedError(_PENDING)

    def all(self) -> list[ScheduleRecord]:
        raise NotImplementedError(_PENDING)

    def update(self, record: ScheduleRecord) -> None:
        raise NotImplementedError(_PENDING)

    def delete(self, schedule_id: str) -> None:
        raise NotImplementedError(_PENDING)

    def due(self, now: datetime) -> list[ScheduleRecord]:
        """Return the enabled schedules whose ``next_run_at`` is at or before *now*."""
        raise NotImplementedError(_PENDING)

    def mark_fired(self, schedule_id: str, next_run_at: datetime | None) -> None:
        """Record that a schedule just fired and stamp its next fire time (None once exhausted)."""
        raise NotImplementedError(_PENDING)
