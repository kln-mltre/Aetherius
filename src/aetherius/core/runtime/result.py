"""Result and StepResult: structured outputs returned to the caller after a Blueprint run."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    # Step-level only: a step whose `when` guard rendered falsy. A run never reports SKIPPED.
    SKIPPED = "skipped"


class StepResult(BaseModel):
    step_id: str | None
    action: str
    status: RunStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float


class Result(BaseModel):
    run_id: str
    blueprint_name: str
    status: RunStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    step_results: list[StepResult] = Field(default_factory=list)
    error: str | None = None
    started_at: datetime
    finished_at: datetime

    @property
    def duration_ms(self) -> float:
        return (self.finished_at - self.started_at).total_seconds() * 1000
