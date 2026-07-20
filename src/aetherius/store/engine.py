"""Store: the SQLite connection facade and its per-concern repositories.

One :class:`Store` (one connection) lives per process, resolved from ``AetheriusSettings.db_path``. The
connection opens in WAL mode with a busy timeout so the daemon (asyncio loop plus worker threads) and
the CLI can read and write the same file without stepping on each other, and ``check_same_thread`` is
disabled because runs persist their outcome from a worker thread. Schema migrations run on open.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

from .approvals import ApprovalRepository
from .runs import RunRepository
from .schedules import ScheduleRepository
from .schema import apply_migrations
from .state import StateRepository

# How long a writer waits for a competing lock before raising, in milliseconds. WAL keeps readers
# lock-free, so this only ever matters between concurrent writers (daemon versus CLI).
_BUSY_TIMEOUT_MS = 5000


class Store:
    """Facade over the SQLite-backed repositories (schedules, runs, inter-run state)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._connect(db_path)
        apply_migrations(self._conn)
        self._schedules = ScheduleRepository(self._conn)
        self._runs = RunRepository(self._conn)
        self._state = StateRepository(self._conn)
        self._approvals = ApprovalRepository(self._conn)

    @staticmethod
    def _connect(db_path: Path) -> sqlite3.Connection:
        # isolation_level=None puts transaction control in our hands: no implicit commit before DDL
        # (the Python 3.11 legacy behaviour that would defeat atomic migrations), and explicit
        # BEGIN/COMMIT where a read-modify-write must be one unit (state.compare_and_set).
        conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @property
    def schedules(self) -> ScheduleRepository:
        return self._schedules

    @property
    def runs(self) -> RunRepository:
        return self._runs

    @property
    def state(self) -> StateRepository:
        return self._state

    @property
    def approvals(self) -> ApprovalRepository:
        return self._approvals

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()


@lru_cache(maxsize=1)
def get_store() -> Store:
    """Return the process-wide store singleton, rooted at ``settings.db_path``."""
    from ..config.settings import get_settings

    return Store(get_settings().db_path)
