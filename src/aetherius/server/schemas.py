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
    # SKIPPED is a step-level status; a run never reports it. Mapped defensively.
    RunStatus.SKIPPED: "succeeded",
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


class DecisionRequest(BaseModel):
    """Body of ``POST /v1/runs/{run_id}/decisions``: a human's answer to a parked ``confirm``.

    ``token`` is the opaque credential minted for the request (carried on the ``input_requested``
    event); it authorises exactly one run's pending decision. ``value`` supplies an optional value
    for the "provide a value" case.
    """

    token: str
    approved: bool
    value: Any = None


class DecisionAck(BaseModel):
    """Response of ``POST /v1/runs/{run_id}/decisions``: the decision was delivered to the parked run."""

    run_id: str
    accepted: bool


class ScheduleCreate(BaseModel):
    """Body of ``POST /v1/schedules``: which Blueprint to re-run, when, and how to alert.

    ``trigger`` and ``notify`` are the same shapes the scheduler persists (see docs/scheduler.md);
    they are validated semantically by the route before anything is written. ``secrets`` holds
    names only — values are resolved from the daemon's environment at fire time, never stored.
    """

    name: str
    blueprint: str = Field(..., description="Path to the Blueprint file the schedule re-runs.")
    inputs: dict[str, Any] = Field(default_factory=dict)
    secrets: list[str] = Field(default_factory=list)
    trigger: dict[str, Any]
    notify: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    """Body of ``PATCH /v1/schedules/{id}``: partial edit; omitted fields keep their value.

    Setting ``enabled`` to true (resume) or changing ``trigger`` recomputes ``next_run_at`` from
    now, so a paused window is never treated as a misfire to catch up.
    """

    name: str | None = None
    blueprint: str | None = None
    inputs: dict[str, Any] | None = None
    secrets: list[str] | None = None
    trigger: dict[str, Any] | None = None
    notify: dict[str, Any] | None = None
    enabled: bool | None = None


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
