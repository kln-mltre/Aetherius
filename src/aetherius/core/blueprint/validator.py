"""Semantic validation: verifies that every step action is supported by the Blueprint's Act."""

from __future__ import annotations

from ..actions.base import ACT_CAPABILITIES
from ..errors import BlueprintValidationError
from .models import Blueprint

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
}


def validate_for_act(blueprint: Blueprint) -> None:
    """Raise BlueprintValidationError if any step uses an action unsupported by blueprint.act.

    This is a semantic check complementing the JSON Schema structural validation.
    """
    supported = ACT_CAPABILITIES.get(blueprint.act, frozenset())
    supported_values = {cap.value for cap in supported}

    for step in blueprint.steps:
        if step.action not in supported_values:
            origin = _CAPABILITY_ORIGIN.get(step.action)
            hint = f" (requires act={origin!r} or higher)" if origin else ""
            raise BlueprintValidationError(
                f"Step {step.id!r}: action {step.action!r} is not supported "
                f"by act={blueprint.act!r}{hint}."
            )
