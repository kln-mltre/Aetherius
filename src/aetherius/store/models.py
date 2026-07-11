"""Typed records persisted by the store: ScheduleRecord and RunRecord.

These are the durable rows the scheduler and the run history read and write. The ``trigger`` and
``notify`` policies are kept as opaque dicts here on purpose: the store persists them verbatim and the
scheduler (``aetherius.server.scheduler``) and the notification layer (``aetherius.notify``) are the
only components that interpret their shape, so the store never couples to either.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ScheduleRecord(BaseModel):
    """A persisted schedule: which Blueprint to re-run, when, and how to alert."""

    id: str
    name: str
    # Path to the Blueprint file (or a stored reference) the schedule re-runs.
    blueprint: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    # Secret names only; values are resolved at fire time, never persisted (see config/secrets.py).
    secrets: list[str] = Field(default_factory=list)
    # Interpreted by the scheduler's Trigger (cron/interval/at). Opaque to the store.
    trigger: dict[str, Any] = Field(default_factory=dict)
    # Alert policy (channel, target, on_change/on_failure/always). Opaque to the store.
    notify: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    created_at: datetime
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class RunRecord(BaseModel):
    """A persisted run outcome, whether triggered manually or by a schedule."""

    run_id: str
    blueprint_name: str
    # Mirrors ``core.runtime.result.RunStatus`` values (success/failed/partial).
    status: str
    schedule_id: str | None = None
    error: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime
    finished_at: datetime | None = None
