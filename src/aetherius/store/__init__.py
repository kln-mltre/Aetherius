"""Durable state store for Aetherius (Phase 1.5, Jalon A).

A single SQLite file under ``~/.aetherius`` backing three concerns that must outlive a process:
scheduled jobs, run history, and inter-run key/value state (used for alert de-duplication). Built on
the stdlib ``sqlite3`` — one portable file, zero extra dependency, safe for the daemon's concurrent
access under WAL. The daemon's in-memory ``RunManager`` graduates its history onto this store.

Status: jalon en attente. The public shape is fixed here; the implementation lands with Jalon A.
See docs/phase-1.5/a-store.md.
"""

from __future__ import annotations

from .engine import Store, get_store
from .models import RunRecord, ScheduleRecord
from .runs import RunRepository
from .schedules import ScheduleRepository
from .state import StateRepository

__all__ = [
    "Store",
    "get_store",
    "ScheduleRecord",
    "RunRecord",
    "ScheduleRepository",
    "RunRepository",
    "StateRepository",
]
