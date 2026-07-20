"""RunContext: mutable per-run state (resolved inputs, injected secrets, step outputs)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from ..blueprint.models import Blueprint
from ..errors import BlueprintValidationError
from .approvals import ApprovalGateway


@dataclass
class RunContext:
    run_id: str
    blueprint: Blueprint
    inputs: dict[str, Any]
    secrets: dict[str, str]
    step_outputs: dict[str, Any] = field(default_factory=dict)
    # Loop variables injected by flow actions (for_each) for the duration of an iteration.
    scope: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Human-in-the-loop decision channel (Jalon 2-E). None means unattended: a ``confirm`` step
    # applies its on_timeout policy at once instead of parking with no surface to answer it.
    approvals: ApprovalGateway | None = None

    def template_ctx(self) -> dict[str, Any]:
        """Build the Jinja2 context dict for rendering step fields and outputs."""
        # Scope is merged last; the executor refuses loop variables that would shadow the
        # reserved names below.
        return {
            "inputs": self.inputs,
            "secrets": self.secrets,
            "vars": self.blueprint.vars,
            "env": dict(os.environ),
            "steps": self.step_outputs,
            **self.scope,
        }


def resolve_inputs(
    blueprint: Blueprint,
    raw: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate and resolve caller-supplied inputs against the Blueprint input specs.

    Raises:
        BlueprintValidationError: a required input is missing.
    """
    raw = dict(raw or {})
    resolved: dict[str, Any] = {}

    for name, spec in blueprint.inputs.items():
        if name in raw:
            resolved[name] = raw[name]
        elif spec.default is not None:
            resolved[name] = spec.default
        elif spec.required:
            raise BlueprintValidationError(
                f"Missing required input '{name}' for Blueprint '{blueprint.name}'."
            )

    # Pass through any extra caller inputs (Blueprint may not declare all runtime vars).
    for name, value in raw.items():
        if name not in resolved:
            resolved[name] = value

    return resolved
