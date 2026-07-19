"""Anti-drift guard: every capability an Act declares is actually dispatched by its driver.

For each (act, capability) of the runnable Acts, the driver must not fall through to its "unsupported
action" branch — unless the capability is listed in PENDING_ACTIONS, or belongs to FLOW_ACTIONS
(interpreted by the step executor before dispatch: a driver implementing one would shadow the
engine, so the inverse is asserted). Driven with fakes (a mock HTTP client, a mock page), so it
runs in the base CI. This is the test that would have caught a capability declared in the table but
never wired into run_step (e.g. vector's ``extract``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from aetherius.acts.continuum.driver import ContinuumDriver
from aetherius.acts.oracle.driver import OracleDriver
from aetherius.acts.phantom.driver import PhantomDriver
from aetherius.acts.vector.driver import VectorDriver
from aetherius.core.actions.base import ACT_CAPABILITIES, FLOW_ACTIONS, PENDING_ACTIONS, Capability
from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import ActionError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.sinks import NullSink
from aetherius.core.runtime.context import RunContext

pytestmark = pytest.mark.unit

_UNSUPPORTED = "unsupported action"


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


def _vector_driver() -> VectorDriver:
    driver = VectorDriver()
    client = MagicMock()
    client.request.return_value = MagicMock(status_code=200, headers={}, content=b"{}")
    driver._client = client
    return driver


def _continuum_driver() -> ContinuumDriver:
    driver = ContinuumDriver()
    session = MagicMock()
    session.human = None
    driver._session = session
    driver._humanized = frozenset()
    return driver


def _oracle_driver() -> OracleDriver:
    driver = OracleDriver()
    session = MagicMock()
    session.human = None
    driver._session = session
    driver._humanized = frozenset()
    driver._provider = MagicMock()
    return driver


def _phantom_driver() -> PhantomDriver:
    # Phantom inherits Oracle's run_step wholesale (scripted-step path); the goal loop is separate.
    driver = PhantomDriver()
    session = MagicMock()
    session.human = None
    driver._session = session
    driver._humanized = frozenset()
    driver._provider = MagicMock()
    return driver


_DRIVER_FACTORIES: dict[str, Any] = {
    "vector": _vector_driver,
    "continuum": _continuum_driver,
    "oracle": _oracle_driver,
    "phantom": _phantom_driver,
}


def _unsupported_reason(driver: Any, action: str, ctx: RunContext) -> str | None:
    """Run a bare step; return the message iff the driver reported the action as unsupported."""
    try:
        driver.run_step(StepModel(action=action), ctx, _bus(), _render)
    except ActionError as exc:
        return str(exc) if _UNSUPPORTED in str(exc) else None
    except Exception:
        return None  # any other typed error still proves the action was dispatched
    return None


@pytest.mark.parametrize("act", ["vector", "continuum", "oracle", "phantom"])
def test_capabilities_dispatch_unless_pending(act: str, monkeypatch, tmp_path: Path) -> None:
    # Keep screenshot's artifact write inside the test's tmp dir, not the real data dir.
    monkeypatch.setattr("aetherius.acts.continuum.driver.run_dir", lambda run_id: tmp_path)

    driver = _DRIVER_FACTORIES[act]()
    ctx = _ctx(act)
    pending = PENDING_ACTIONS.get(act, frozenset())

    for cap in ACT_CAPABILITIES[act]:
        reason = _unsupported_reason(driver, cap.value, ctx)
        if cap in FLOW_ACTIONS:
            assert reason is not None, (
                f"{act}.{cap.value} is engine-interpreted flow; a driver must not dispatch it"
            )
        elif cap in pending:
            assert reason is not None, f"{act}.{cap.value} should be pending but was dispatched"
        else:
            assert reason is None, f"{act}.{cap.value} is declared but not dispatched: {reason}"


def test_pending_sets_match_the_undispatched_actions() -> None:
    # Sanity: every entry currently in PENDING_ACTIONS is a genuine capability of that Act,
    # and flow actions are never pending (the step executor runs them for every Act).
    for act, pending in PENDING_ACTIONS.items():
        assert all(isinstance(cap, Capability) for cap in pending)
        assert pending <= ACT_CAPABILITIES[act]
        assert not pending & FLOW_ACTIONS, f"{act}: flow actions must not be pending"
