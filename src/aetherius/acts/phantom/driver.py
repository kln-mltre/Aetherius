"""Phantom driver (Act IV): autonomous, goal-driven browser automation.

Runs a Blueprint that declares a ``goal``/``constraints`` instead of ``steps``. Extends
``OracleDriver`` — so the browser, the stealth layer, the cognition provider resolution and the
vision/selector dispatch are all inherited unchanged — and adds only the perceive->reason->act
loop (``loop.py``) and its memory. The loop's policy is a cognition ``Planner`` (Claude by
default). In multi-Act composition (Jalon 2-D) a scripted step with ``act: "phantom"`` goes
through the inherited ``run_step`` and behaves exactly like Oracle; a self-healing escalation to
phantom instead runs a tightly budgeted micro-goal loop (``run_micro_goal``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.blueprint.template import render_value
from ...core.errors import ActionError
from ..oracle.driver import OracleDriver
from .loop import run_loop

if TYPE_CHECKING:
    from ...core.events.bus import EventBus
    from ...core.runtime.context import RunContext
    from ...core.runtime.result import StepResult


class PhantomDriver(OracleDriver):
    act = "phantom"

    def run_goal(
        self, ctx: "RunContext", bus: "EventBus", results: list["StepResult"]
    ) -> dict[str, Any]:
        """Drive the perceive->reason->act loop toward ``blueprint.goal``.

        A goal-only Blueprint has no ``steps``; the engine invokes this seam instead of the step
        pipeline. Returns the agent outcome (also published under ``steps.agent`` for ``outputs``).
        """
        if self._session is None or self._provider is None:
            raise ActionError("PhantomDriver.run_goal called before setup().")

        def renderer(value: Any) -> Any:
            return render_value(value, ctx.template_ctx())

        goal = str(renderer(ctx.blueprint.goal or ""))
        constraints = [str(renderer(c)) for c in ctx.blueprint.constraints]
        max_steps = ctx.blueprint.options.agent.max_steps

        outcome = run_loop(
            self,
            self._provider,
            self._session.page,
            ctx,
            bus,
            results,
            goal=goal,
            constraints=constraints,
            max_steps=max_steps,
        )
        # Publish under `steps.agent` so a Blueprint's `outputs` can reference `{{ steps.agent.* }}`.
        ctx.step_outputs["agent"] = outcome
        return outcome

    def run_micro_goal(
        self,
        ctx: "RunContext",
        bus: "EventBus",
        results: list["StepResult"],
        *,
        goal: str,
        constraints: list[str],
        max_steps: int,
        id_prefix: str,
    ) -> dict[str, Any]:
        """Drive a bounded agent loop toward a single-step intent (self-healing, Jalon 2-D).

        Unlike ``run_goal`` this never publishes ``steps.agent``: the outcome belongs to the
        healed step, not to the run's output surface.
        """
        if self._session is None or self._provider is None:
            raise ActionError("PhantomDriver.run_micro_goal called before setup().")
        return run_loop(
            self,
            self._provider,
            self._session.page,
            ctx,
            bus,
            results,
            goal=goal,
            constraints=constraints,
            max_steps=max_steps,
            id_prefix=id_prefix,
        )
