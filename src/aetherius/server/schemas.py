"""Request and response DTOs for the daemon API, aligned with contracts/openapi.yaml.

The daemon speaks its own lifecycle vocabulary (``queued``/``running``/``succeeded``/``failed``),
distinct from the engine's :class:`~aetherius.core.runtime.result.RunStatus`
(``success``/``failed``/``partial``): the former describes a *job* on the daemon, the latter the
*outcome* of a Blueprint. ``to_daemon_status`` bridges the two at the boundary.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..core.events.models import RunEvent
from ..core.runtime.result import RunStatus

DaemonRunStatus = Literal["queued", "running", "succeeded", "failed"]

_STATUS_MAP: dict[RunStatus, DaemonRunStatus] = {
    RunStatus.SUCCESS: "succeeded",
    RunStatus.PARTIAL: "succeeded",
    RunStatus.FAILED: "failed",
}


def to_daemon_status(status: RunStatus) -> DaemonRunStatus:
    """Map an engine run outcome onto the daemon's job status vocabulary."""
    return _STATUS_MAP[status]


class RunRequest(BaseModel):
    """Body of ``POST /v1/runs``: a Blueprint plus its inputs and runtime secrets."""

    blueprint: dict[str, Any] | str = Field(
        ..., description="Inline Blueprint object, or a path resolvable by the daemon."
    )
    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)


class RunHandle(BaseModel):
    """Response of ``POST /v1/runs``: the identifier to poll and stream."""

    run_id: str


class Run(BaseModel):
    """Response of ``GET /v1/runs/{run_id}``: the job's current state."""

    run_id: str
    status: DaemonRunStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ValidationErrorItem(BaseModel):
    path: str
    message: str


class ValidationReport(BaseModel):
    """Response of ``POST /v1/blueprints/validate``: never raises, always reports."""

    valid: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


def event_to_wire(event: RunEvent) -> dict[str, Any]:
    """Serialize a :class:`RunEvent` into a JSON object conforming to events.schema.json.

    The schema forbids unknown/null properties (``additionalProperties: false``), so absent fields
    are dropped rather than emitted as ``null``, and an empty ``data`` payload is omitted entirely.
    """
    wire = event.model_dump(mode="json", exclude_none=True)
    if not wire.get("data"):
        wire.pop("data", None)
    return wire
