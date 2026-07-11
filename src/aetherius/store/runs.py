"""RunRepository: durable run history, queryable by Blueprint or schedule."""

from __future__ import annotations

import sqlite3

from .models import RunRecord

_PENDING = "Jalon 1.5-A (store): run history not implemented yet."


class RunRepository:
    """Appends run outcomes and reads them back for history and observability."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, record: RunRecord) -> None:
        """Persist a finished (or failed) run outcome."""
        raise NotImplementedError(_PENDING)

    def recent(
        self,
        *,
        blueprint: str | None = None,
        schedule_id: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        """Return recent runs, newest first, optionally filtered by Blueprint or schedule."""
        raise NotImplementedError(_PENDING)

    def get(self, run_id: str) -> RunRecord | None:
        raise NotImplementedError(_PENDING)
