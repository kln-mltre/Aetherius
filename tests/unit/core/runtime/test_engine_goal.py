"""Tests for the goal-only engine seam (Phantom, Jalon 2-C).

A Blueprint with no steps but a goal invokes driver.run_goal instead of the step pipeline; a
Blueprint with steps keeps the classic pipeline. Driven with a fake driver (no browser, no model),
so it runs in the base CI.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.runtime import engine as engine_module
from aetherius.core.runtime.engine import RunEngine
from aetherius.core.runtime.result import RunStatus

pytestmark = pytest.mark.unit


class _FakeDriver:
    def __init__(self) -> None:
        self.goal_called = False
        self.steps: list[str] = []

    def setup(self, ctx: Any) -> None:  # noqa: D401
        pass

    def teardown(self, ctx: Any) -> None:
        pass

    def run_goal(self, ctx: Any, bus: Any, results: list[Any]) -> dict[str, Any]:
        self.goal_called = True
        outcome = {"result": {"found": "yes"}, "steps_taken": 2}
        ctx.step_outputs["agent"] = outcome
        return outcome

    def run_step(self, step: Any, ctx: Any, bus: Any, renderer: Any) -> dict[str, Any]:
        self.steps.append(step.action)
        return {"value": "x"}


def _install(monkeypatch: pytest.MonkeyPatch) -> _FakeDriver:
    driver = _FakeDriver()
    monkeypatch.setattr(engine_module, "_make_driver", lambda act: driver)
    return driver


def _goal_bp(outputs: dict[str, Any] | None = None) -> Blueprint:
    data: dict[str, Any] = {
        "aetherius": "1.0",
        "name": "t.goal",
        "act": "phantom",
        "goal": "achieve something",
    }
    if outputs is not None:
        data["outputs"] = outputs
    return Blueprint.model_validate(data)


def test_goal_only_invokes_run_goal_not_the_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _install(monkeypatch)

    result = RunEngine().run(_goal_bp())

    assert driver.goal_called is True
    assert driver.steps == []
    assert result.status is RunStatus.SUCCESS


def test_goal_only_without_outputs_returns_the_agent_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)

    result = RunEngine().run(_goal_bp())

    assert result.outputs == {"result": {"found": "yes"}, "steps_taken": 2}


def test_goal_only_with_declared_outputs_interpolates_steps_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)

    result = RunEngine().run(_goal_bp(outputs={"found": "{{ steps.agent.result.found }}"}))

    assert result.outputs == {"found": "yes"}


def test_blueprint_with_steps_uses_the_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _install(monkeypatch)
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.steps",
            "act": "vector",
            "steps": [{"action": "set", "value": "x"}],
        }
    )

    result = RunEngine().run(bp)

    assert driver.goal_called is False
    assert driver.steps == ["set"]
    assert result.status is RunStatus.SUCCESS
