"""Schema definition and forward-only migrations for the SQLite store.

The DDL lives here, apart from the connection facade, so ``engine.py`` stays focused on lifecycle.
Migrations are keyed on ``PRAGMA user_version``: each step bumps it by one, so an existing database
upgrades in place without ever re-running an applied step. Adding a table or column later means
appending a migration, never editing a shipped one.
"""

from __future__ import annotations

import sqlite3

# One tuple of statements per schema version. Index i upgrades user_version i -> i+1, applied inside a
# single transaction (SQLite DDL is transactional) so a failed upgrade rolls back whole.
_MIGRATIONS: tuple[tuple[str, ...], ...] = (
    # v0 -> v1: the three durable concerns (schedules, run history, inter-run state).
    (
        """
        CREATE TABLE schedules (
            id           TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            blueprint    TEXT NOT NULL,
            inputs       TEXT NOT NULL,
            secrets      TEXT NOT NULL,
            trigger      TEXT NOT NULL,
            notify       TEXT NOT NULL,
            enabled      INTEGER NOT NULL,
            created_at   TEXT NOT NULL,
            next_run_at  TEXT,
            last_run_at  TEXT
        )
        """,
        "CREATE INDEX idx_schedules_due ON schedules (enabled, next_run_at)",
        """
        CREATE TABLE runs (
            run_id         TEXT PRIMARY KEY,
            blueprint_name TEXT NOT NULL,
            status         TEXT NOT NULL,
            schedule_id    TEXT,
            error          TEXT,
            outputs        TEXT NOT NULL,
            started_at     TEXT NOT NULL,
            finished_at    TEXT
        )
        """,
        "CREATE INDEX idx_runs_started ON runs (started_at DESC)",
        "CREATE INDEX idx_runs_blueprint ON runs (blueprint_name)",
        "CREATE INDEX idx_runs_schedule ON runs (schedule_id)",
        """
        CREATE TABLE state (
            scope TEXT NOT NULL,
            key   TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (scope, key)
        )
        """,
    ),
    # v1 -> v2: human-in-the-loop approvals (Jalon 2-E). Audit trail of every ``confirm`` request and
    # its resolution; the live rendezvous is in-memory (a parked run cannot outlive its worker), this
    # table is for observability. Keyed by the opaque token so an unknown token is rejected cleanly.
    (
        """
        CREATE TABLE approvals (
            token       TEXT PRIMARY KEY,
            run_id      TEXT NOT NULL,
            step_id     TEXT,
            message     TEXT NOT NULL,
            status      TEXT NOT NULL,
            decided_by  TEXT,
            created_at  TEXT NOT NULL,
            decided_at  TEXT
        )
        """,
        "CREATE INDEX idx_approvals_run ON approvals (run_id)",
    ),
)


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Bring the connection's schema up to the latest version, idempotently.

    Reads ``PRAGMA user_version`` and replays only the migrations not yet applied, each in its own
    transaction so an interrupted upgrade never leaves a half-applied version behind.
    """
    current: int = conn.execute("PRAGMA user_version").fetchone()[0]
    for version in range(current, len(_MIGRATIONS)):
        conn.execute("BEGIN")
        try:
            for statement in _MIGRATIONS[version]:
                conn.execute(statement)
            # PRAGMA takes no bound parameters; the value is an integer we control, not user input.
            conn.execute(f"PRAGMA user_version = {version + 1}")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
