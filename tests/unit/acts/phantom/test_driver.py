"""Tests for acts/phantom/driver.py — run_goal wiring on top of the inherited Oracle driver.

The loop itself is stubbed (tested in test_loop.py); what is asserted here is that run_goal renders
the goal/constraints through the template engine, reads the step budget from options.agent, and
publishes the outcome under steps.agent.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.phantom import driver as driver_module
from aetherius.acts.phantom.driver import PhantomDriver
from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import ActionError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.result import RunStatus, StepResult

pytestmark = pytest.mark.unit


def _ctx(**blueprint_overrides: Any) -> RunContext:
    data = {
        "aetherius": "1.0",
        "name": "t",
        "act": "phantom",
        "inputs": {"who": {"type": "string", "default": "Ada"}},
        "goal": "find {{ inputs.who }}",
        "constraints": ["stay on {{ inputs.who }}.example"],
        "options": {"agent": {"max_steps": 7}},
    }
    data.update(blueprint_overrides)
    bp = Blueprint.model_validate(data)
    return RunContext(run_id="r", blueprint=bp, inputs={"who": "Ada"}, secrets={})


def _bus() -> EventBus:
    bus = EventBus()
    bus.register(NullSink())
    return bus


def test_run_goal_renders_goal_and_reads_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_run_loop(driver, provider, page, ctx, bus, results, *, goal, constraints, max_steps):
        seen.update(goal=goal, constraints=constraints, max_steps=max_steps)
        return {"result": {"found": True}, "steps_taken": 3}

    monkeypatch.setattr(driver_module, "run_loop", fake_run_loop)

    driver = PhantomDriver()
    session = MagicMock()
    driver._session = session
    driver._provider = MagicMock()
    ctx = _ctx()

    outcome = driver.run_goal(ctx, _bus(), [])

    assert seen["goal"] == "find Ada"  # template rendered
    assert seen["constraints"] == ["stay on Ada.example"]
    assert seen["max_steps"] == 7
    assert outcome == {"result": {"found": True}, "steps_taken": 3}
    assert ctx.step_outputs["agent"] == outcome  # published for outputs interpolation


def test_run_goal_before_setup_raises() -> None:
    driver = PhantomDriver()  # no session/provider
    with pytest.raises(ActionError, match="before setup"):
        driver.run_goal(_ctx(), _bus(), [])


def test_default_budget_is_used_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        driver_module,
        "run_loop",
        lambda *a, goal, constraints, max_steps, **k: seen.update(max_steps=max_steps) or {},
    )
    driver = PhantomDriver()
    driver._session = MagicMock()
    driver._provider = MagicMock()

    driver.run_goal(_ctx(options={}), _bus(), [])

    assert seen["max_steps"] == 40  # AgentOptions default


def test_phantom_driver_is_an_oracle_driver() -> None:
    from aetherius.acts.oracle.driver import OracleDriver

    assert issubclass(PhantomDriver, OracleDriver)


def test_results_list_is_threaded_through(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_loop(driver, provider, page, ctx, bus, results, **k):
        results.append(
            StepResult(
                step_id="agent[0]", action="click", status=RunStatus.SUCCESS, duration_ms=1.0
            )
        )
        return {"result": None, "steps_taken": 1}

    monkeypatch.setattr(driver_module, "run_loop", fake_run_loop)
    driver = PhantomDriver()
    driver._session = MagicMock()
    driver._provider = MagicMock()
    results: list[StepResult] = []

    driver.run_goal(_ctx(), _bus(), results)

    assert [r.step_id for r in results] == ["agent[0]"]
