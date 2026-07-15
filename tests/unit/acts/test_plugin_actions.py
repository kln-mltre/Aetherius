"""Plugin action dispatch (Jalon E): drivers fall back to the registry after their built-in match.

Exercises the seam at the driver level for both runnable Acts (with the same fakes as
test_action_dispatch.py) and end to end through a real RunEngine run. An unknown action must keep
failing with the driver's own "unsupported action" error — the fallback never swallows it.
"""

from __future__ import annotations

from typing import Any, Callable
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum.driver import ContinuumDriver
from aetherius.acts.vector.driver import VectorDriver
from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import ActionError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.engine import RunEngine

pytestmark = pytest.mark.unit


def _render(value: Any) -> Any:
    return value


def _ctx(act: str) -> RunContext:
    bp = Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t", "act": act, "steps": [{"action": "set", "value": "x"}]}
    )
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


def _bus() -> EventBus:
    bus = EventBus()
    bus.register(NullSink())
    return bus


def _continuum_driver() -> ContinuumDriver:
    driver = ContinuumDriver()
    driver._session = MagicMock(human=None)
    driver._humanized = frozenset()
    return driver


@pytest.mark.parametrize("make_driver", [VectorDriver, _continuum_driver])
def test_drivers_fall_back_to_the_plugin_registry(
    make_driver: Callable[[], Any], plugin_action: str
) -> None:
    driver = make_driver()
    step = StepModel.model_validate({"action": plugin_action, "value": "per aspera"})
    outputs = driver.run_step(step, _ctx(driver.act), _bus(), _render)
    assert outputs == {"shout": "PER ASPERA"}


@pytest.mark.parametrize("make_driver", [VectorDriver, _continuum_driver])
def test_unknown_actions_still_fail_with_the_driver_error(
    make_driver: Callable[[], Any],
) -> None:
    driver = make_driver()
    step = StepModel.model_validate({"action": "does.not.exist"})
    with pytest.raises(ActionError, match="unsupported action"):
        driver.run_step(step, _ctx(driver.act), _bus(), _render)


def test_engine_runs_a_plugin_action_end_to_end(plugin_action: str) -> None:
    blueprint = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "t.plugin",
            "act": "vector",
            "vars": {"motto": "per aspera"},
            "steps": [{"id": "s", "action": plugin_action, "value": "{{ vars.motto }}"}],
            "outputs": {"shout": "{{ steps.s.shout }}"},
        }
    )
    result = RunEngine().run(blueprint)
    assert result.status.value == "success"
    assert result.outputs["shout"] == "PER ASPERA"
