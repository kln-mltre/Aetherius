"""Self-healing: replay a failed step's intent on a higher Act before the failure propagates.

A Blueprint opts in with an escalation chain (``options.fallback``, overridable per step with
``step.fallback``) and, for selector-targeted steps, a ``describe`` — the natural-language intent
the higher Act consumes when the selector fails. No ``describe`` means no escalation: inferring
intent from a broken selector would be guesswork, and healing must stay predictable
(docs/composition.md).

Escalation is per-step and never sticky: the healed step's successor runs back on its declared
act (the fast, cheap path), and the warning events double as the signal that the Blueprint
deserves a fix. Two escalation shapes exist:

- ``oracle`` — replay the same step through vision grounding (``target: {vision: describe}``);
  ``fill`` becomes a vision ``type`` (Oracle deliberately has no vision fill).
- ``phantom`` — hand the intent to a tightly budgeted perceive->reason->act micro-loop, able to
  clear obstacles (a popup, a scroll) that a single vision replay cannot. Limited to the intents
  the planner vocabulary can express (no hover/upload).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Mapping

from ..blueprint.models import StepModel
from ..errors import ActionError
from ..events.models import EventType, RunEvent
from .drivers import ACT_ORDER, BROWSER_ACTS
from .result import StepResult

if TYPE_CHECKING:
    from ..events.bus import EventBus
    from .context import RunContext
    from .steps import DriverResolver

# Actions self-healing knows how to replay by vision; every other action fails as before.
_VISION_REPLAY: frozenset[str] = frozenset({"click", "hover", "type", "fill", "upload", "wait_for"})

# Intents the Phantom planner vocabulary can express (acts/_cognition/planning.py): it has no
# hover/upload tool, so those step intents stop their escalation at Oracle.
_MICRO_GOAL_ACTIONS: frozenset[str] = frozenset({"click", "type", "fill", "wait_for"})

# Parameters forwarded verbatim to the escalated vision step, per action. Everything else
# (selector, selector_type, describe, fallback) is intent already consumed by the escalation.
_FORWARDED_PARAMS: dict[str, tuple[str, ...]] = {
    "click": ("min_confidence", "scan"),
    "hover": ("min_confidence", "scan"),
    "type": ("text", "value", "min_confidence", "scan"),
    "fill": ("min_confidence", "scan"),
    "upload": ("file", "files", "min_confidence", "scan"),
    "wait_for": ("timeout_ms", "on_timeout", "min_confidence"),
}

# The micro-goal budget: enough for "close the popup, scroll, then click" and far below a full
# Phantom run (options.agent.max_steps) — healing rescues one step, it does not take over the run.
_MICRO_GOAL_MAX_STEPS = 6


def attempt_healing(
    step: StepModel,
    act: str,
    error: Exception,
    *,
    ctx: "RunContext",
    bus: "EventBus",
    drivers: "DriverResolver",
    results: list[StepResult],
    renderer: Callable[[Any], Any],
    step_id: str | None,
) -> tuple[dict[str, Any], str] | None:
    """Try each configured higher Act against the failed *step*, in chain order.

    Returns ``(outputs, healed_by)`` on the first success; ``None`` when no escalation applies or
    every entry failed — the caller then propagates *error* unchanged (the attempts are already
    told through events).
    """
    if act not in BROWSER_ACTS:
        return None  # healing is a browser concept; a vector step fails as before
    chain = step.fallback if step.fallback is not None else ctx.blueprint.options.fallback
    entries = [entry for entry in chain if ACT_ORDER.get(entry, -1) > ACT_ORDER[act]]
    if not entries:
        return None

    if step.action not in _VISION_REPLAY:
        _emit(
            bus,
            ctx,
            step_id,
            f"self-healing does not cover action {step.action!r}; propagating the failure",
        )
        return None
    description = _description(step)
    if description is None:
        _emit(
            bus,
            ctx,
            step_id,
            "self-healing skipped: the step carries no 'describe' (nor a vision target) "
            "to replay its intent from",
        )
        return None

    for target_act in entries:
        if target_act == "phantom" and step.action not in _MICRO_GOAL_ACTIONS:
            _emit(
                bus,
                ctx,
                step_id,
                f"self-healing: skipping 'phantom' — the planner cannot express {step.action!r}",
            )
            continue
        _emit(
            bus,
            ctx,
            step_id,
            f"self-healing: {step.action} failed on {act!r}, replaying on {target_act!r} "
            f"as {description!r}",
            data={"from_act": act, "to_act": target_act, "error": str(error)},
        )
        try:
            if target_act == "oracle":
                outputs = _replay_by_vision(step, description, ctx, bus, drivers, renderer)
            else:
                outputs = _replay_by_micro_goal(
                    step, description, ctx, bus, drivers, results, renderer, step_id
                )
        except Exception as exc:  # an escalation failure is contained: the chain continues,
            # and when it runs out the caller propagates the original error.
            _emit(
                bus,
                ctx,
                step_id,
                f"self-healing: {target_act!r} escalation failed too: {exc}",
                data={"to_act": target_act, "error": str(exc)},
            )
            continue
        _emit(
            bus,
            ctx,
            step_id,
            f"self-healing: step healed by {target_act!r}",
            level="info",
            data={"healed_by": target_act},
        )
        return outputs, target_act
    return None


def _description(step: StepModel) -> str | None:
    """The step's replayable intent, raw (rendered downstream, like any step field)."""
    if step.describe:
        return step.describe
    target = step.extra_fields.get("target")
    if isinstance(target, Mapping) and target.get("vision"):
        return str(target["vision"])
    return None


def _replay_by_vision(
    step: StepModel,
    description: str,
    ctx: "RunContext",
    bus: "EventBus",
    drivers: "DriverResolver",
    renderer: Callable[[Any], Any],
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "action": "type" if step.action == "fill" else step.action,
        "target": {"vision": description},
    }
    if step.id:
        data["id"] = step.id
    params = step.extra_fields
    for key in _FORWARDED_PARAMS[step.action]:
        if key in params:
            data[key] = params[key]
    if step.action == "fill":
        data["text"] = params.get("value", "")
    replay = StepModel.model_validate(data)
    return drivers.resolve_driver("oracle", ctx).run_step(replay, ctx, bus, renderer)


def _replay_by_micro_goal(
    step: StepModel,
    description: str,
    ctx: "RunContext",
    bus: "EventBus",
    drivers: "DriverResolver",
    results: list[StepResult],
    renderer: Callable[[Any], Any],
    step_id: str | None,
) -> dict[str, Any]:
    driver = drivers.resolve_driver("phantom", ctx)
    run_micro_goal = getattr(driver, "run_micro_goal", None)
    if run_micro_goal is None:
        raise ActionError(
            f"phantom escalation unavailable: {type(driver).__name__} cannot run goals."
        )
    run_micro_goal(
        ctx,
        bus,
        results,
        goal=_micro_goal(step, str(renderer(description)), renderer),
        constraints=[
            "Perform exactly this one step, nothing more.",
            "Stay on the current page unless the step itself requires navigating.",
        ],
        max_steps=_MICRO_GOAL_MAX_STEPS,
        id_prefix=f"{step_id or step.action}.heal",
    )
    # Interactive intents have no outputs (like their Oracle/Continuum forms); the micro-loop's
    # own StepResults carry the trace.
    return {}


def _micro_goal(step: StepModel, description: str, renderer: Callable[[Any], Any]) -> str:
    """One sentence of intent for the planner. Rendered values on purpose: the agent needs the
    real text to act (a templated secret in a healed type/fill does reach the planner — a
    documented trade-off of the phantom escalation)."""
    params = step.extra_fields
    if step.action in ("type", "fill"):
        text = str(renderer(params.get("text", params.get("value", ""))))
        return f"Type {text!r} into {description}."
    if step.action == "wait_for":
        return f"Confirm that {description} is visible on the current screen, then finish."
    return f"Click {description}."


def _emit(
    bus: "EventBus",
    ctx: "RunContext",
    step_id: str | None,
    message: str,
    *,
    level: Literal["info", "warning"] = "warning",
    data: dict[str, Any] | None = None,
) -> None:
    bus.emit(
        RunEvent(
            run_id=ctx.run_id,
            type=EventType.PROGRESS,
            step_id=step_id,
            message=message,
            level=level,
            data=data or {},
        )
    )
