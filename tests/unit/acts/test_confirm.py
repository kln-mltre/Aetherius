"""End-to-end tests for the confirm action through the Vector driver (acts/_shared.py).

Confirm is an Act-agnostic shared handler like notify; the Vector driver dispatches it identically to
every browser Act (asserted structurally by tests/unit/acts/test_action_dispatch.py). Here we drive
the real handler: the rendezvous parks the worker, a surface thread resolves it, and the on_timeout
policy fires when no one answers. No browser, no daemon.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from aetherius.acts.vector.driver import VectorDriver
from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import StepTimeoutError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.approvals import ApprovalRegistry, Decision
from aetherius.core.runtime.context import RunContext

pytestmark = pytest.mark.unit


class ListSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


def _render(value: Any) -> Any:
    return value


def _ctx(registry: ApprovalRegistry | None) -> RunContext:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t",
            "act": "vector",
            "steps": [{"action": "set", "value": "x"}],
        }
    )
    return RunContext(run_id="run", blueprint=bp, inputs={}, secrets={}, approvals=registry)


def _bus() -> tuple[EventBus, ListSink]:
    bus = EventBus()
    sink = ListSink()
    bus.register(sink)
    return bus, sink


def _confirm(
    step_fields: dict[str, Any], registry: ApprovalRegistry | None
) -> tuple[dict[str, Any], ListSink]:
    driver = VectorDriver()
    bus, sink = _bus()
    step = StepModel.model_validate({"id": "approve", "action": "confirm", **step_fields})
    outputs = driver._confirm(step, _ctx(registry), bus, _render)
    return outputs, sink


def test_confirm_parks_then_resumes_on_approval() -> None:
    registry = ApprovalRegistry()

    def surface() -> None:
        for _ in range(100):
            request = registry.pending("run")
            if request is not None:
                registry.resolve("run", request.token, Decision(True, decided_by="test"))
                return
            time.sleep(0.01)

    threading.Thread(target=surface, daemon=True).start()
    outputs, sink = _confirm({"message": "proceed?", "timeout_ms": 5000}, registry)

    assert outputs["approved"] is True
    assert outputs["decision"] == "approved"
    assert outputs["decided_by"] == "test"
    types = [e.type for e in sink.events]
    assert EventType.INPUT_REQUESTED in types
    assert EventType.INPUT_PROVIDED in types


def test_confirm_rejection_is_carried_through() -> None:
    registry = ApprovalRegistry()

    def surface() -> None:
        for _ in range(100):
            request = registry.pending("run")
            if request is not None:
                registry.resolve("run", request.token, Decision(False, decided_by="test"))
                return
            time.sleep(0.01)

    threading.Thread(target=surface, daemon=True).start()
    outputs, _ = _confirm({"message": "proceed?", "timeout_ms": 5000}, registry)
    assert outputs["approved"] is False
    assert outputs["decision"] == "rejected"


def test_on_timeout_reject_is_the_default() -> None:
    outputs, sink = _confirm({"message": "proceed?", "timeout_ms": 30}, ApprovalRegistry())
    assert outputs["approved"] is False
    assert outputs["decided_by"] == "timeout"
    # The request was raised and resolved (by the timeout) on the event stream.
    assert [e.type for e in sink.events].count(EventType.INPUT_PROVIDED) == 1


def test_on_timeout_approve() -> None:
    outputs, _ = _confirm(
        {"message": "proceed?", "timeout_ms": 30, "on_timeout": "approve"}, ApprovalRegistry()
    )
    assert outputs["approved"] is True


def test_on_timeout_fail_raises_with_code() -> None:
    with pytest.raises(StepTimeoutError) as exc:
        _confirm(
            {"message": "proceed?", "timeout_ms": 30, "on_timeout": "fail:NO_DECISION"},
            ApprovalRegistry(),
        )
    assert exc.value.code == "NO_DECISION"


def test_unattended_run_applies_on_timeout_immediately() -> None:
    # No gateway: a bare library run never parks; it applies on_timeout at once (deny-by-default).
    start = time.monotonic()
    outputs, sink = _confirm({"message": "proceed?", "timeout_ms": 60000}, None)
    assert time.monotonic() - start < 1.0
    assert outputs["approved"] is False
    # Unattended: no surface, so no input events are emitted.
    assert sink.events == []
