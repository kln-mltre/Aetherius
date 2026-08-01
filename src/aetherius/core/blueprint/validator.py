"""Semantic validation: verifies that every step action is supported by its effective Act.

Since Jalon 2-D a step may override the Blueprint act (``step.act``, multi-Act composition);
nested flow steps inherit the enclosing step's effective act. Recurses into the nested step
lists of the flow actions (``if``/``repeat``/``for_each``) so an unsupported action buried in a
branch is rejected before the run starts, with a readable path. Self-healing chains
(``options.fallback`` / ``step.fallback``) are checked here too.
"""

from __future__ import annotations

from typing import Callable

from pydantic import ValidationError

from ..actions.base import ACT_CAPABILITIES
from ..actions.base import FLOW_NESTED_FIELDS as FLOW_NESTED_FIELDS  # re-export (public surface)
from ..actions.registry import plugin_actions
from ..errors import BlueprintValidationError
from .models import Blueprint, StepModel

# Map back from Capability value to the first Act that introduces it.
_CAPABILITY_ORIGIN: dict[str, str] = {
    "navigate": "continuum",
    "back": "continuum",
    "forward": "continuum",
    "reload": "continuum",
    "click": "continuum",
    "fill": "continuum",
    "type": "continuum",
    "press": "continuum",
    "select": "continuum",
    "hover": "continuum",
    "scroll": "continuum",
    "upload": "continuum",
    "drag": "continuum",
    "screenshot": "continuum",
    "evaluate": "continuum",
    "wait_for": "continuum",
    "read": "oracle",
}

# Acts allowed in a self-healing escalation chain: escalation is a browser-Act concept, and
# Continuum is the floor it escalates *from* (see docs/composition.md).
FALLBACK_ACTS: frozenset[str] = frozenset({"oracle", "phantom"})


def validate_for_act(blueprint: Blueprint) -> None:
    """Raise BlueprintValidationError if any step uses an action unsupported by its effective act.

    This is a semantic check complementing the JSON Schema structural validation.
    """
    # A goal-only Blueprint (no steps) is the Phantom contract: the agent decides its own steps.
    # Any other Act declaring a goal without steps is an authoring mistake — steps are its surface.
    if not blueprint.steps and blueprint.act != "phantom":
        raise BlueprintValidationError(
            f"A goal-only Blueprint (no 'steps') requires act='phantom', got act={blueprint.act!r}."
        )

    # Plugin actions are act-agnostic by design (docs/plugins.md): registered = accepted on every
    # Act. They must be loaded before validation — the engine, the CLI and the daemon all call
    # load_plugins() at startup.
    plugins = plugin_actions()
    cache: dict[str, set[str]] = {}

    def supported_values(act: str) -> set[str]:
        if act not in cache:
            cache[act] = {cap.value for cap in ACT_CAPABILITIES.get(act, frozenset())} | plugins
        return cache[act]

    _validate_chain(blueprint.options.fallback, "options.fallback")
    for index, step in enumerate(blueprint.steps):
        _validate_step(step, blueprint.act, supported_values, f"steps[{index}]")


def _validate_step(
    step: StepModel,
    inherited_act: str,
    supported_values: Callable[[str], set[str]],
    path: str,
) -> None:
    act = step.act or inherited_act
    if step.action not in supported_values(act):
        origin = _CAPABILITY_ORIGIN.get(step.action)
        hint = (
            f" (requires act={origin!r} or higher — set it on the blueprint or on this step)"
            if origin
            else ""
        )
        raise BlueprintValidationError(
            f"Step {step.id!r}: action {step.action!r} is not supported "
            f"by act={act!r}{hint} (at {path})."
        )

    if step.fallback is not None:
        _validate_chain(step.fallback, f"{path}.fallback")

    for field_name in FLOW_NESTED_FIELDS.get(step.action, ()):
        raw = step.extra_fields.get(field_name)
        if raw is None:
            continue
        if not isinstance(raw, list):
            raise BlueprintValidationError(
                f"Step {step.id!r}: {field_name!r} must be a list of steps "
                f"(at {path}.{field_name})."
            )
        for index, item in enumerate(raw):
            child_path = f"{path}.{field_name}[{index}]"
            try:
                child = StepModel.model_validate(item)
            except ValidationError as exc:
                raise BlueprintValidationError(f"Invalid step at {child_path}: {exc}") from exc
            # Nested steps inherit the enclosing step's effective act.
            _validate_step(child, act, supported_values, child_path)


def _validate_chain(chain: list[str], path: str) -> None:
    for entry in chain:
        if entry not in FALLBACK_ACTS:
            raise BlueprintValidationError(
                f"Invalid fallback act {entry!r} (at {path}): a self-healing chain "
                f"may only name {sorted(FALLBACK_ACTS)}."
            )
