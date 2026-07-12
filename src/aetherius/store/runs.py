"""RunRepository: durable run history, queryable by Blueprint or schedule."""

from __future__ import annotations

import json
import sqlite3

from .models import RunRecord

_COLUMNS = (
    "run_id",
    "blueprint_name",
    "status",
    "schedule_id",
    "error",
    "outputs",
    "started_at",
    "finished_at",
)
_COLUMN_SQL = ", ".join(_COLUMNS)
_PLACEHOLDERS = ", ".join("?" * len(_COLUMNS))


def _to_params(record: RunRecord) -> tuple[object, ...]:
    return (
        record.run_id,
        record.blueprint_name,
        record.status,
        record.schedule_id,
        record.error,
        json.dumps(record.outputs),
        record.started_at.isoformat(),
        record.finished_at.isoformat() if record.finished_at is not None else None,
    )


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        blueprint_name=row["blueprint_name"],
        status=row["status"],
        schedule_id=row["schedule_id"],
        error=row["error"],
        outputs=json.loads(row["outputs"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


class RunRepository:
    """Appends run outcomes and reads them back for history and observability."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, record: RunRecord) -> None:
        """Persist a finished (or failed) run outcome."""
        self._conn.execute(
            f"INSERT INTO runs ({_COLUMN_SQL}) VALUES ({_PLACEHOLDERS})",
            _to_params(record),
        )

    def recent(
        self,
        *,
        blueprint: str | None = None,
        schedule_id: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        """Return recent runs, newest first, optionally filtered by Blueprint or schedule."""
        clauses: list[str] = []
        params: list[object] = []
        if blueprint is not None:
            clauses.append("blueprint_name = ?")
            params.append(blueprint)
        if schedule_id is not None:
            clauses.append("schedule_id = ?")
            params.append(schedule_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT {_COLUMN_SQL} FROM runs{where} ORDER BY started_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [_row_to_run(row) for row in rows]

    def get(self, run_id: str) -> RunRecord | None:
        row = self._conn.execute(
            f"SELECT {_COLUMN_SQL} FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return _row_to_run(row) if row is not None else None
