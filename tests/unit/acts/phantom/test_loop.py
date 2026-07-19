"""Tests for acts/phantom/loop.py — the bounded perceive->reason->act loop.

Driven with a scripted planner and a fake driver (no browser, no network, no extra): what is
asserted is that planned actions are dispatched in order, memorized, recorded as StepResults and
events, that ``finish`` stops with the result, that the budget caps a runaway planner, and that a
failed action is an observation the loop survives.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.acts._perception import Perception
from aetherius.acts.phantom import loop as loop_module
from aetherius.acts.phantom.loop import run_loop
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import ActionError, AgentError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.result import RunStatus, StepResult

pytestmark = pytest.mark.unit

_PERCEPTION = Perception(screenshot=b"png", viewport=(1280, 720), url="https://example.com")


@pytest.fixture(autouse=True)
def _stub_perceive(monkeypatch: pytest.MonkeyPatch) -> None:
    # The loop's only page contact is perceive(); stub it so no browser is needed.
    monkeypatch.setattr(loop_module, "perceive", lambda page: _PERCEPTION)


class _ScriptedPlanner:
    """Replays a list of planner replies (dicts), one per plan() call."""

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self._replies = list(replies)
        self.calls = 0

    def plan(
        self, goal: str, constraints: list[str], perception: Perception, memory: Any
    ) -> dict[str, Any] | None:
        self.calls += 1
        # A planner that runs out of scripted replies keeps clicking (used by the budget test).
        return (
            self._replies.pop(0)
            if self._replies
            else {"action": "click", "target": {"vision": "x"}}
        )


class _FakeDriver:
    """Records dispatched actions; raises on any action name in *fail_on*."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.dispatched: list[str] = []
        self._fail_on = fail_on or set()

    def run_step(self, step: Any, ctx: Any, bus: Any, renderer: Any) -> dict[str, Any]:
        self.dispatched.append(step.action)
        if step.action in self._fail_on:
            raise ActionError(f"cannot do {step.action}")
        return {"did": step.action}


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


def _ctx() -> RunContext:
    bp = Blueprint.model_validate({"aetherius": "1.0", "name": "t", "act": "phantom", "goal": "g"})
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


def _run(planner: _ScriptedPlanner, driver: _FakeDriver, *, max_steps: int = 10):
    sink = _RecordingSink()
    bus = EventBus()
    bus.register(sink)
    results: list[StepResult] = []
    outcome = run_loop(
        driver,
        planner,
        object(),
        _ctx(),
        bus,
        results,
        goal="g",
        constraints=[],
        max_steps=max_steps,
    )
    return outcome, results, sink.events


def test_dispatches_actions_in_order_then_finishes() -> None:
    planner = _ScriptedPlanner(
        [
            {"action": "click", "target": {"vision": "a link"}},
            {"action": "read", "vision": "the title"},
            {"action": "finish", "result": {"title": "Hello"}},
        ]
    )
    driver = _FakeDriver()

    outcome, results, events = _run(planner, driver)

    assert driver.dispatched == ["click", "read"]
    assert outcome == {"result": {"title": "Hello"}, "steps_taken": 2}
    assert [r.step_id for r in results] == ["agent[0]", "agent[1]"]
    assert all(r.status is RunStatus.SUCCESS for r in results)
    assert any(e.type is EventType.STEP_STARTED for e in events)
    assert any(e.type is EventType.STEP_FINISHED for e in events)


def test_finish_on_first_call_takes_no_steps() -> None:
    planner = _ScriptedPlanner([{"action": "finish", "result": "already done"}])

    outcome, results, _ = _run(planner, _FakeDriver())

    assert outcome == {"result": "already done", "steps_taken": 0}
    assert results == []


def test_budget_caps_a_runaway_planner() -> None:
    # Never finishes: the scripted planner falls through to endless clicks.
    planner = _ScriptedPlanner([])
    driver = _FakeDriver()

    with pytest.raises(AgentError, match="3-step budget"):
        _run(planner, driver, max_steps=3)

    assert len(driver.dispatched) == 3


def test_failed_action_is_an_observation_and_the_loop_continues() -> None:
    planner = _ScriptedPlanner(
        [
            {"action": "click", "target": {"vision": "a ghost"}},  # fails
            {"action": "finish", "result": "recovered"},
        ]
    )
    driver = _FakeDriver(fail_on={"click"})

    outcome, results, events = _run(planner, driver)

    assert outcome == {"result": "recovered", "steps_taken": 1}
    assert len(results) == 1
    assert results[0].status is RunStatus.FAILED
    assert any(e.level == "warning" and "action failed" in (e.message or "") for e in events)


def test_malformed_planner_action_is_recovered() -> None:
    # An action dict the StepModel cannot validate (action is not a string) must not crash the loop.
    planner = _ScriptedPlanner(
        [{"action": None}, {"action": "finish", "result": "ok"}]  # type: ignore[list-item]
    )
    driver = _FakeDriver()

    outcome, results, _ = _run(planner, driver)

    assert outcome["result"] == "ok"
    assert results[0].status is RunStatus.FAILED
    assert driver.dispatched == []  # the bad action never reached the driver
