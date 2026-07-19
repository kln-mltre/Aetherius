"""DriverManager: per-run Act driver lifecycle for multi-Act composition (Jalon 2-D).

Generalises the engine's historical single ``driver = make(act)`` bind: drivers are instantiated
and set up on demand (at the first step that needs them) and torn down together at the end of the
run. The browser Acts (II/III/IV) form one inheritance chain (PhantomDriver > OracleDriver >
ContinuumDriver) designed so a higher driver runs a lower Act's steps identically — the manager
therefore *subsumes* them into a single instance of the highest browser Act the run can reach,
which is what guarantees the central invariant of composition: one browser, one stealth session,
shared by every browser step. Vector (no browser state) keeps its own driver.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..blueprint.models import Blueprint, StepModel
from ..blueprint.validator import FLOW_NESTED_FIELDS
from ..errors import ActionError

if TYPE_CHECKING:
    from .context import RunContext


IMPLEMENTED_ACTS: frozenset[str] = frozenset({"vector", "continuum", "oracle", "phantom"})

# Escalation order of the Acts; self-healing may only walk it upward (core/runtime/healing.py).
ACT_ORDER: dict[str, int] = {"vector": 0, "continuum": 1, "oracle": 2, "phantom": 3}

BROWSER_ACTS: frozenset[str] = frozenset({"continuum", "oracle", "phantom"})


def _make_driver(act: str) -> Any:
    # Drivers are imported lazily so `import aetherius` never pulls in an Act's heavy
    # dependencies (Playwright, Anthropic, ...). Each driver defers its own extra to runtime.
    if act == "vector":
        from ...acts.vector.driver import VectorDriver

        return VectorDriver()
    if act == "continuum":
        from ...acts.continuum.driver import ContinuumDriver

        return ContinuumDriver()
    if act == "oracle":
        from ...acts.oracle.driver import OracleDriver

        return OracleDriver()
    if act == "phantom":
        from ...acts.phantom.driver import PhantomDriver

        return PhantomDriver()
    raise ActionError(f"Act {act!r} is not implemented yet. Available: {sorted(IMPLEMENTED_ACTS)}.")


def collect_effective_acts(blueprint: Blueprint) -> frozenset[str]:
    """Every act a run may touch: the Blueprint act, per-step overrides (inherited through flow
    branches) and the self-healing chains a failing browser step could escalate along.

    Computed statically before the run starts so the manager can pick the single browser driver
    able to serve them all. The tree was already validated (validate_for_act walks the same shape).
    """
    acts: set[str] = {blueprint.act}
    default_chain = blueprint.options.fallback

    def visit(step: StepModel, inherited: str) -> None:
        act = step.act or inherited
        acts.add(act)
        nested_fields = FLOW_NESTED_FIELDS.get(step.action)
        if nested_fields is not None:
            for field in nested_fields:
                raw = step.extra_fields.get(field)
                if isinstance(raw, list):
                    for item in raw:
                        visit(StepModel.model_validate(item), act)
            return
        # A failing leaf may escalate along its chain — upward and between browser Acts only.
        if act in BROWSER_ACTS:
            chain = step.fallback if step.fallback is not None else default_chain
            for entry in chain:
                if ACT_ORDER.get(entry, -1) > ACT_ORDER[act]:
                    acts.add(entry)

    for step in blueprint.steps:
        visit(step, blueprint.act)
    return frozenset(acts)


class DriverManager:
    """Lazy per-run driver registry (see module docstring).

    Satisfies the executor's ``DriverResolver`` protocol (core/runtime/steps.py).
    """

    def __init__(self, blueprint: Blueprint) -> None:
        browser = [act for act in collect_effective_acts(blueprint) if act in BROWSER_ACTS]
        # The one browser driver able to serve every browser act this run can reach.
        self._browser_act: str | None = max(browser, key=ACT_ORDER.__getitem__, default=None)
        self._drivers: dict[str, Any] = {}

    def resolve_driver(self, act: str, ctx: "RunContext") -> Any:
        """Return the live driver for *act*, instantiating and setting it up on first use."""
        key = self._browser_act if act in BROWSER_ACTS and self._browser_act else act
        driver = self._drivers.get(key)
        if driver is None:
            driver = _make_driver(key)
            driver.setup(ctx)
            self._drivers[key] = driver
        return driver

    def teardown_all(self, ctx: "RunContext") -> None:
        """Tear down every live driver, newest first; the first error propagates after all ran."""
        first: Exception | None = None
        for driver in reversed(list(self._drivers.values())):
            try:
                driver.teardown(ctx)
            except Exception as exc:  # one failing teardown must not skip the others
                first = first or exc
        self._drivers.clear()
        if first is not None:
            raise first
