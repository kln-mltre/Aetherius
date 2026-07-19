"""Semantic validation: verifies that every step action is supported by the Blueprint's Act.

Recurses into the nested step lists of the flow actions (``if``/``repeat``/``for_each``) so an
unsupported action buried in a branch is rejected before the run starts, with a readable path.
"""

from __future__ import annotations

from pydantic import ValidationError

from ..actions.base import ACT_CAPABILITIES
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

# Step fields holding nested step lists, per flow action.
_FLOW_NESTED_FIELDS: dict[str, tuple[str, ...]] = {
    "if": ("then", "else"),
    "repeat": ("steps",),
    "for_each": ("steps",),
}


def validate_for_act(blueprint: Blueprint) -> None:
    """Raise BlueprintValidationError if any step uses an action unsupported by blueprint.act.

    This is a semantic check complementing the JSON Schema structural validation.
    """
    # A goal-only Blueprint (no steps) is the Phantom contract: the agent decides its own steps.
    # Any other Act declaring a goal without steps is an authoring mistake — steps are its surface.
    if not blueprint.steps and blueprint.act != "phantom":
        raise BlueprintValidationError(
            f"A goal-only Blueprint (no 'steps') requires act='phantom', got act={blueprint.act!r}."
        )

    supported = ACT_CAPABILITIES.get(blueprint.act, frozenset())
    # Plugin actions are act-agnostic by design (docs/plugins.md): registered = accepted on every
    # Act. They must be loaded before validation — the engine, the CLI and the daemon all call
    # load_plugins() at startup.
    supported_values = {cap.value for cap in supported} | plugin_actions()

    for index, step in enumerate(blueprint.steps):
        _validate_step(step, blueprint.act, supported_values, f"steps[{index}]")


def _validate_step(step: StepModel, act: str, supported_values: set[str], path: str) -> None:
    if step.action not in supported_values:
        origin = _CAPABILITY_ORIGIN.get(step.action)
        hint = f" (requires act={origin!r} or higher)" if origin else ""
        raise BlueprintValidationError(
            f"Step {step.id!r}: action {step.action!r} is not supported "
            f"by act={act!r}{hint} (at {path})."
        )

    for field_name in _FLOW_NESTED_FIELDS.get(step.action, ()):
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
            _validate_step(child, act, supported_values, child_path)
