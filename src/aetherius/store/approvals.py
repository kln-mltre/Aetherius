"""ApprovalRepository: durable audit trail for human-in-the-loop ``confirm`` requests (Jalon 2-E).

The live rendezvous a parked run blocks on is in-memory (approvals.py) — a parked run cannot outlive
its worker, so there is nothing to resume across a restart. This table exists for *observability*:
which requests were raised, and how each was resolved (approved/rejected/timeout/failed, and by which
surface). Writes are best-effort at the call sites (like run history); a store hiccup never blocks a
decision.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


class ApprovalRepository:
    """Records ``confirm`` requests and their resolutions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def open_pending(
        self, token: str, run_id: str, message: str, *, step_id: str | None = None
    ) -> None:
        """Record a freshly raised request as ``pending``."""
        self._conn.execute(
            "INSERT OR REPLACE INTO approvals "
            "(token, run_id, step_id, message, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (token, run_id, step_id, message, datetime.now(timezone.utc).isoformat()),
        )

    def resolve(self, token: str, status: str, *, decided_by: str | None = None) -> None:
        """Mark a request resolved with a final status (approved/rejected/timeout/failed)."""
        self._conn.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, decided_at = ? WHERE token = ?",
            (status, decided_by, datetime.now(timezone.utc).isoformat(), token),
        )

    def get(self, token: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(
            "SELECT * FROM approvals WHERE token = ?", (token,)
        ).fetchone()
        return row

    def for_run(self, run_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM approvals WHERE run_id = ? ORDER BY created_at", (run_id,)
        ).fetchall()
