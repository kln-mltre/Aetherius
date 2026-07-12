"""StateRepository: inter-run key/value state, scoped per schedule or Blueprint.

This is what lets a Blueprint react across runs: remember the last observed value and only alert on a
transition (out-of-stock -> in-stock), instead of firing on every check. Values are stored as opaque
strings; callers serialize as they see fit.
"""

from __future__ import annotations

import sqlite3

_UPSERT = (
    "INSERT INTO state (scope, key, value) VALUES (?, ?, ?) "
    "ON CONFLICT(scope, key) DO UPDATE SET value = excluded.value"
)


class StateRepository:
    """Durable key/value state keyed by (scope, key). Backs alert de-duplication."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, scope: str, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM state WHERE scope = ? AND key = ?", (scope, key)
        ).fetchone()
        return row["value"] if row is not None else None

    def set(self, scope: str, key: str, value: str) -> None:
        self._conn.execute(_UPSERT, (scope, key, value))

    def compare_and_set(self, scope: str, key: str, value: str) -> bool:
        """Store *value* and return True iff it differs from the previously stored one.

        The transition signal the scheduler and the ``notify`` layer use to alert once per change
        rather than on every run. The read and the write share one ``BEGIN IMMEDIATE`` transaction so
        two concurrent callers cannot both observe the old value and race the transition.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT value FROM state WHERE scope = ? AND key = ?", (scope, key)
            ).fetchone()
            changed = row is None or row["value"] != value
            self._conn.execute(_UPSERT, (scope, key, value))
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        return changed
