"""Phantom driver (Act IV): autonomous, goal-driven browser automation.

Runs a Blueprint that declares a ``goal``/``constraints`` instead of ``steps``. Reuses the shared
browser + stealth + perception substrate and drives a perceive->reason->act loop (``loop.py``) whose
policy is a cognition ``Planner`` (Claude by default). Not yet wired into ``RunEngine._make_driver``
— implemented in Jalon 2-D (docs/phase-2/2-d-phantom.md). This is the interface skeleton.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .._shared import SharedActionsMixin

if TYPE_CHECKING:
    from ...core.blueprint.models import StepModel
    from ...core.events.bus import EventBus
    from ...core.runtime.context import RunContext


class PhantomDriver(SharedActionsMixin):
    act = "phantom"

    def setup(self, ctx: "RunContext") -> None:
        raise NotImplementedError("Jalon 2-D (docs/phase-2/2-d-phantom.md).")

    def teardown(self, ctx: "RunContext") -> None:
        raise NotImplementedError("Jalon 2-D (docs/phase-2/2-d-phantom.md).")

    def run_goal(self, ctx: "RunContext", bus: "EventBus") -> dict[str, Any]:
        """Drive the perceive->reason->act loop toward ``blueprint.goal``.

        A goal-only Blueprint has no ``steps``; the engine invokes this seam instead of the step
        pipeline. Engine integration + the loop land in Jalon 2-D.
        """
        raise NotImplementedError("Jalon 2-D (docs/phase-2/2-d-phantom.md).")

    def run_step(
        self,
        step: "StepModel",
        ctx: "RunContext",
        bus: "EventBus",
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        # Retained for the scripted-with-fallback case (Jalon 2-E): a Phantom step reached via a
        # per-step ``act`` override or a self-healing escalation.
        raise NotImplementedError("Jalon 2-D (docs/phase-2/2-d-phantom.md).")
