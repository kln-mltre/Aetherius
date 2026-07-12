"""ScheduleRepository: durable CRUD over schedules, plus the due-query the scheduler polls."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .models import ScheduleRecord

_COLUMNS = (
    "id",
    "name",
    "blueprint",
    "inputs",
    "secrets",
    "trigger",
    "notify",
    "enabled",
    "created_at",
    "next_run_at",
    "last_run_at",
)
_COLUMN_SQL = ", ".join(_COLUMNS)
_PLACEHOLDERS = ", ".join("?" * len(_COLUMNS))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _to_params(record: ScheduleRecord) -> tuple[object, ...]:
    """Flatten a record into positional params matching ``_COLUMNS``; dicts/lists as JSON text."""
    return (
        record.id,
        record.name,
        record.blueprint,
        json.dumps(record.inputs),
        json.dumps(record.secrets),
        json.dumps(record.trigger),
        json.dumps(record.notify),
        int(record.enabled),
        record.created_at.isoformat(),
        _iso(record.next_run_at),
        _iso(record.last_run_at),
    )


def _row_to_schedule(row: sqlite3.Row) -> ScheduleRecord:
    """Rebuild a record from a row; pydantic parses the ISO datetimes and coerces ``enabled``."""
    return ScheduleRecord(
        id=row["id"],
        name=row["name"],
        blueprint=row["blueprint"],
        inputs=json.loads(row["inputs"]),
        secrets=json.loads(row["secrets"]),
        trigger=json.loads(row["trigger"]),
        notify=json.loads(row["notify"]),
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        next_run_at=row["next_run_at"],
        last_run_at=row["last_run_at"],
    )


class ScheduleRepository:
    """Persists schedules and answers "which schedules are due to fire now?"."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, record: ScheduleRecord) -> str:
        """Insert a schedule and return its id."""
        self._conn.execute(
            f"INSERT INTO schedules ({_COLUMN_SQL}) VALUES ({_PLACEHOLDERS})",
            _to_params(record),
        )
        return record.id

    def get(self, schedule_id: str) -> ScheduleRecord | None:
        row = self._conn.execute(
            f"SELECT {_COLUMN_SQL} FROM schedules WHERE id = ?", (schedule_id,)
        ).fetchone()
        return _row_to_schedule(row) if row is not None else None

    def all(self) -> list[ScheduleRecord]:
        rows = self._conn.execute(
            f"SELECT {_COLUMN_SQL} FROM schedules ORDER BY created_at"
        ).fetchall()
        return [_row_to_schedule(row) for row in rows]

    def update(self, record: ScheduleRecord) -> None:
        self._conn.execute(
            "UPDATE schedules SET name = ?, blueprint = ?, inputs = ?, secrets = ?, "
            "trigger = ?, notify = ?, enabled = ?, created_at = ?, next_run_at = ?, "
            "last_run_at = ? WHERE id = ?",
            (*_to_params(record)[1:], record.id),
        )

    def delete(self, schedule_id: str) -> None:
        self._conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))

    def due(self, now: datetime) -> list[ScheduleRecord]:
        """Return the enabled schedules whose ``next_run_at`` is at or before *now*."""
        rows = self._conn.execute(
            f"SELECT {_COLUMN_SQL} FROM schedules "
            "WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ? "
            "ORDER BY next_run_at",
            (now.isoformat(),),
        ).fetchall()
        return [_row_to_schedule(row) for row in rows]

    def mark_fired(self, schedule_id: str, next_run_at: datetime | None) -> None:
        """Record that a schedule just fired and stamp its next fire time (None once exhausted)."""
        self._conn.execute(
            "UPDATE schedules SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), _iso(next_run_at), schedule_id),
        )
