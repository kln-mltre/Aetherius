"""Event types emitted during a Blueprint run. Mirrors contracts/events.schema.json.

STEP_SKIPPED replaces the started/finished pair for a step whose ``when`` guard rendered falsy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    PROGRESS = "progress"
    STEP_STARTED = "step_started"
    STEP_FINISHED = "step_finished"
    STEP_SKIPPED = "step_skipped"
    DEBUG = "debug"
    ARTIFACT = "artifact"
    ERROR = "error"
    DONE = "done"
    # Human-in-the-loop (Jalon 2-E): a ``confirm`` step parked the run awaiting a decision, and the
    # decision (or timeout) that resumed it. The run stays ``running`` throughout — no new status.
    INPUT_REQUESTED = "input_requested"
    INPUT_PROVIDED = "input_provided"


class RunEvent(BaseModel):
    run_id: str
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    type: EventType
    step_id: str | None = None
    level: Literal["debug", "info", "warning", "error"] | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
