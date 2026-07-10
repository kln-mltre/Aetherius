"""Tests for server/schemas.py — status mapping and the events wire serializer."""

from __future__ import annotations

import pytest

from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.result import RunStatus
from aetherius.server.schemas import event_to_wire, to_daemon_status

pytestmark = pytest.mark.unit


def test_status_mapping_bridges_engine_to_daemon() -> None:
    assert to_daemon_status(RunStatus.SUCCESS) == "succeeded"
    assert to_daemon_status(RunStatus.FAILED) == "failed"
    # Partial is not produced by the engine today but must still map to a terminal daemon status.
    assert to_daemon_status(RunStatus.PARTIAL) == "succeeded"


def test_event_to_wire_drops_null_and_empty_fields() -> None:
    wire = event_to_wire(RunEvent(run_id="r1", type=EventType.STEP_STARTED))

    assert wire["run_id"] == "r1"
    assert wire["type"] == "step_started"
    assert isinstance(wire["ts"], str)
    # Absent optionals must be dropped, not emitted as null (events.schema.json forbids it).
    for absent in ("step_id", "level", "message", "data"):
        assert absent not in wire


def test_event_to_wire_keeps_present_fields() -> None:
    wire = event_to_wire(
        RunEvent(
            run_id="r1",
            type=EventType.DONE,
            level="info",
            message="run finished: success",
            data={"status": "success"},
        )
    )

    assert wire["level"] == "info"
    assert wire["message"] == "run finished: success"
    assert wire["data"] == {"status": "success"}
