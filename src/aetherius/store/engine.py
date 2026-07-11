"""Store: the SQLite connection facade and its per-concern repositories.

One :class:`Store` (one connection) lives per process, resolved from
``AetheriusSettings.db_path``. Opening the connection in WAL mode and running the schema migrations
is the first task of Jalon A; until then, accessing a repository raises a clear "jalon en attente"
error rather than pretending to persist anything.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from .runs import RunRepository
from .schedules import ScheduleRepository
from .state import StateRepository

_PENDING = "Jalon 1.5-A (store): SQLite persistence not implemented yet."


class Store:
    """Facade over the SQLite-backed repositories (schedules, runs, inter-run state)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        # Opening the connection (WAL mode) and running migrations lands with Jalon A.
        self._conn: sqlite3.Connection | None = None

    @property
    def schedules(self) -> ScheduleRepository:
        raise NotImplementedError(_PENDING)

    @property
    def runs(self) -> RunRepository:
        raise NotImplementedError(_PENDING)

    @property
    def state(self) -> StateRepository:
        raise NotImplementedError(_PENDING)

    def close(self) -> None:
        """Close the underlying connection, if one was opened."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


@lru_cache(maxsize=1)
def get_store() -> Store:
    """Return the process-wide store singleton, rooted at ``settings.db_path``."""
    from ..config.settings import get_settings

    return Store(get_settings().db_path)
