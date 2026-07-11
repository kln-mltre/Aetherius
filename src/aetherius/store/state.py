"""StateRepository: inter-run key/value state, scoped per schedule or Blueprint.

This is what lets a Blueprint react across runs: remember the last observed value and only alert on a
transition (out-of-stock -> in-stock), instead of firing on every check. Values are stored as opaque
strings; callers serialize as they see fit.
"""

from __future__ import annotations

import sqlite3

_PENDING = "Jalon 1.5-A (store): inter-run state not implemented yet."


class StateRepository:
    """Durable key/value state keyed by (scope, key). Backs alert de-duplication."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, scope: str, key: str) -> str | None:
        raise NotImplementedError(_PENDING)

    def set(self, scope: str, key: str, value: str) -> None:
        raise NotImplementedError(_PENDING)

    def compare_and_set(self, scope: str, key: str, value: str) -> bool:
        """Store *value* and return True iff it differs from the previously stored one.

        The transition signal the scheduler and the ``notify`` layer use to alert once per change
        rather than on every run.
        """
        raise NotImplementedError(_PENDING)
