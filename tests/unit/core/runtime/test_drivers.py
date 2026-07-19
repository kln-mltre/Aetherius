"""Tests for core/runtime/drivers.py: act pre-scan, lazy setup, browser subsumption, teardown.

Driven by fake drivers injected through the module factory, so no Act extra is needed. A few
cases go through RunEngine end to end to prove the invariant the spec names: a mixed run keeps a
single browser driver instance.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.runtime import drivers as drivers_module
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.drivers import DriverManager, collect_effective_acts
from aetherius.core.runtime.engine import RunEngine
from aetherius.core.runtime.result import RunStatus

pytestmark = pytest.mark.unit


class FakeDriver:
    def __init__(self, act: str) -> None:
        self.act = act
        self.setup_calls = 0
        self.teardown_calls = 0
        self.steps: list[str] = []

    def setup(self, ctx: Any) -> None:
        self.setup_calls += 1

    def teardown(self, ctx: Any) -> None:
        self.teardown_calls += 1

    def run_step(self, step: Any, ctx: Any, bus: Any, renderer: Any) -> dict[str, Any]:
        self.steps.append(step.action)
        return {}


class Factory:
    """Replaces drivers._make_driver, counting instantiations per act."""

    def __init__(self) -> None:
        self.made: list[str] = []
        self.drivers: dict[str, FakeDriver] = {}

    def __call__(self, act: str) -> FakeDriver:
        self.made.append(act)
        driver = FakeDriver(act)
        self.drivers[act] = driver
        return driver


@pytest.fixture()
def factory(monkeypatch: pytest.MonkeyPatch) -> Factory:
    fake = Factory()
    monkeypatch.setattr(drivers_module, "_make_driver", fake)
    return fake


def _bp(act: str = "continuum", **overrides: Any) -> Blueprint:
    data: dict[str, Any] = {
        "aetherius": "1.0",
        "name": "t.drivers",
        "act": act,
        "steps": [{"action": "emit"}],
    }
    data.update(overrides)
    return Blueprint.model_validate(data)


def _ctx(bp: Blueprint) -> RunContext:
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


# ── collect_effective_acts ───────────────────────────────────────────────────


def test_mono_act_blueprint_collects_only_its_act() -> None:
    assert collect_effective_acts(_bp("vector")) == {"vector"}


def test_per_step_overrides_are_collected() -> None:
    bp = _bp(
        "continuum",
        steps=[
            {"action": "navigate", "url": "x"},
            {"action": "read", "act": "oracle", "vision": "y"},
            {"action": "http.request", "act": "vector", "url": "z"},
        ],
    )
    assert collect_effective_acts(bp) == {"continuum", "oracle", "vector"}


def test_flow_branches_inherit_and_override() -> None:
    bp = _bp(
        "continuum",
        steps=[
            {
                "action": "if",
                "act": "oracle",
                "condition": "x",
                "then": [{"action": "read", "vision": "y"}],
                "else": [{"action": "click", "act": "phantom", "selector": "#a"}],
            }
        ],
    )
    assert collect_effective_acts(bp) == {"continuum", "oracle", "phantom"}


def test_fallback_chains_count_toward_the_scan() -> None:
    bp = _bp(
        "continuum",
        options={"fallback": ["oracle"]},
        steps=[{"action": "click", "selector": "#a", "describe": "the button"}],
    )
    assert collect_effective_acts(bp) == {"continuum", "oracle"}


def test_fallback_on_a_vector_step_is_inert() -> None:
    bp = _bp(
        "vector",
        options={"fallback": ["oracle"]},
        steps=[{"action": "http.request", "url": "x"}],
    )
    assert collect_effective_acts(bp) == {"vector"}


def test_step_fallback_overrides_the_global_chain() -> None:
    bp = _bp(
        "continuum",
        options={"fallback": ["phantom"]},
        steps=[{"action": "click", "selector": "#a", "fallback": []}],
    )
    assert collect_effective_acts(bp) == {"continuum"}


# ── DriverManager ────────────────────────────────────────────────────────────


def test_lazy_setup_at_first_resolution(factory: Factory) -> None:
    bp = _bp("vector")
    manager = DriverManager(bp)
    assert factory.made == []
    driver = manager.resolve_driver("vector", _ctx(bp))
    assert factory.made == ["vector"]
    assert driver.setup_calls == 1
    # Resolving again reuses the live driver, without a second setup.
    assert manager.resolve_driver("vector", _ctx(bp)) is driver
    assert driver.setup_calls == 1


def test_browser_acts_subsume_into_one_instance(factory: Factory) -> None:
    bp = _bp(
        "continuum",
        steps=[
            {"action": "navigate", "url": "x"},
            {"action": "read", "act": "oracle", "vision": "y"},
        ],
    )
    manager = DriverManager(bp)
    ctx = _ctx(bp)
    continuum = manager.resolve_driver("continuum", ctx)
    oracle = manager.resolve_driver("oracle", ctx)
    # One instance, of the highest browser act the run can reach.
    assert continuum is oracle
    assert factory.made == ["oracle"]


def test_vector_keeps_its_own_driver(factory: Factory) -> None:
    bp = _bp(
        "continuum",
        steps=[
            {"action": "navigate", "url": "x"},
            {"action": "http.request", "act": "vector", "url": "z"},
        ],
    )
    manager = DriverManager(bp)
    ctx = _ctx(bp)
    browser = manager.resolve_driver("continuum", ctx)
    vector = manager.resolve_driver("vector", ctx)
    assert browser is not vector
    assert sorted(factory.made) == ["continuum", "vector"]


def test_teardown_all_reaches_every_driver_and_reports_the_first_error(
    factory: Factory,
) -> None:
    bp = _bp(
        "continuum",
        steps=[
            {"action": "navigate", "url": "x"},
            {"action": "http.request", "act": "vector", "url": "z"},
        ],
    )
    manager = DriverManager(bp)
    ctx = _ctx(bp)
    browser = manager.resolve_driver("continuum", ctx)
    vector = manager.resolve_driver("vector", ctx)

    boom = RuntimeError("teardown boom")

    def failing_teardown(_ctx: Any) -> None:
        browser.teardown_calls += 1
        raise boom

    browser.teardown = failing_teardown  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="teardown boom"):
        manager.teardown_all(ctx)
    assert browser.teardown_calls == 1
    assert vector.teardown_calls == 1


# ── Through RunEngine ────────────────────────────────────────────────────────


def test_mixed_run_instantiates_a_single_browser_driver(factory: Factory) -> None:
    bp = _bp(
        "continuum",
        steps=[
            {"action": "navigate", "url": "https://x"},
            {"id": "sem", "action": "read", "act": "oracle", "vision": "y"},
        ],
    )
    result = RunEngine().run(bp)
    assert result.status == RunStatus.SUCCESS
    assert factory.made == ["oracle"]
    assert factory.drivers["oracle"].steps == ["navigate", "read"]
    assert factory.drivers["oracle"].teardown_calls == 1


def test_mono_act_run_binds_exactly_the_blueprint_act(factory: Factory) -> None:
    result = RunEngine().run(_bp("vector"))
    assert result.status == RunStatus.SUCCESS
    assert factory.made == ["vector"]
