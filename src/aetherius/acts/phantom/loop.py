"""The perceive->reason->act loop that advances Phantom toward its goal.

One iteration: perceive (``perception.perceive``) -> decide (``planner.next_action``) -> act
(dispatch the chosen leaf step through the inherited Oracle/Continuum ``run_step``) -> remember
(``memory.record``). Bounded by a step budget; the planner ends it with ``finish`` (goal reached)
or ``abort`` (typed ``AgentError``).

Resilience is the point of Act IV: a failed action (a grounder that is not confident, a timeout)
is recorded as an *observation*, not a fatal error — the planner sees it next turn and adapts.
Only the planner aborting, an unusable planner reply, or an exhausted budget stop the run.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from ...core.errors import AetheriusError, AgentError
from ...core.events.models import EventType, RunEvent
from ...core.runtime.result import RunStatus, StepResult
from .memory import AgentMemory, _action_summary
from .perception import perceive
from .planner import next_action

if TYPE_CHECKING:
    from ...core.events.bus import EventBus
    from ...core.runtime.context import RunContext
    from .._cognition.provider import CognitionProvider
    from ..oracle.driver import OracleDriver


def _identity(value: Any) -> Any:
    # The planner emits final values (a typed URL, the exact text to type); rendering them through
    # the template engine would wrongly reinterpret any ``{{ }}`` the model produced.
    return value


def run_loop(
    driver: "OracleDriver",
    provider: "CognitionProvider",
    page: Any,
    ctx: "RunContext",
    bus: "EventBus",
    results: list[StepResult],
    *,
    goal: str,
    constraints: list[str],
    max_steps: int,
) -> dict[str, Any]:
    """Iterate until the goal is met, the planner aborts, or the step budget runs out.

    Returns ``{"result": <finish payload>, "steps_taken": N}``.

    Raises:
        AgentError: the planner aborted, or the budget was exhausted before the goal was reached.
    """
    memory = AgentMemory(goal=goal)
    steps_taken = 0

    while steps_taken < max_steps:
        perception = perceive(page)
        action = next_action(provider, goal, constraints, perception, memory)
        if action is None:  # finish: the planner reported the goal reached
            _emit(bus, ctx, EventType.PROGRESS, None, f"agent: done in {steps_taken} steps", "info")
            return {"result": memory.result, "steps_taken": steps_taken}

        step_id = f"agent[{steps_taken}]"
        _emit(bus, ctx, EventType.PROGRESS, step_id, f"agent: {_action_summary(action)}", "info")
        _dispatch(driver, action, ctx, bus, results, memory, step_id)
        steps_taken += 1

    raise AgentError(f"agent did not reach its goal within the {max_steps}-step budget: {goal!r}")


def _dispatch(
    driver: "OracleDriver",
    action: dict[str, Any],
    ctx: "RunContext",
    bus: "EventBus",
    results: list[StepResult],
    memory: AgentMemory,
    step_id: str,
) -> None:
    """Play one planner action, recording a StepResult and an observation either way."""
    from ...core.blueprint.models import StepModel

    t0 = time.monotonic()
    _emit(bus, ctx, EventType.STEP_STARTED, step_id, None, "debug")
    try:
        step = StepModel.model_validate(action)
        outputs = driver.run_step(step, ctx, bus, _identity)
    except (AetheriusError, ValidationError) as exc:
        # A failed action (grounding not confident, timeout, or a malformed planner reply) is an
        # observation, not the end of the run: record it and let the planner adapt on the next
        # turn (the resilience Act IV exists for). It still consumes one step of the budget, so a
        # planner stuck failing the same action is bounded.
        duration = (time.monotonic() - t0) * 1000
        results.append(
            StepResult(
                step_id=step_id,
                action=str(action.get("action", "?")),
                status=RunStatus.FAILED,
                error=str(exc),
                duration_ms=duration,
            )
        )
        _emit(bus, ctx, EventType.PROGRESS, step_id, f"agent: action failed: {exc}", "warning")
        memory.record(action, {"error": str(exc)})
        return

    duration = (time.monotonic() - t0) * 1000
    results.append(
        StepResult(
            step_id=step_id,
            action=step.action,
            status=RunStatus.SUCCESS,
            outputs=outputs,
            duration_ms=duration,
        )
    )
    _emit(bus, ctx, EventType.STEP_FINISHED, step_id, None, "debug")
    memory.record(action, outputs)


def _emit(
    bus: "EventBus",
    ctx: "RunContext",
    type_: EventType,
    step_id: str | None,
    message: str | None,
    level: str,
) -> None:
    bus.emit(
        RunEvent(
            run_id=ctx.run_id,
            type=type_,
            step_id=step_id,
            message=message,
            level=level,  # type: ignore[arg-type]
        )
    )
