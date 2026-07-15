"""Incremental Blueprint validation for the live editor.

:func:`validate_draft` never raises: it returns a flat list of :class:`ValidationIssue` (errors and
warnings) that the Studio's preview renders on every change. It layers the same checks the runtime
enforces — JSON Schema structure, the Pydantic model, then the semantic Act/action rules — so what
reads as valid here is what will actually load and run. Finalisation (raising) stays in
``factory.build_blueprint``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ..core.actions.base import ACT_CAPABILITIES, PENDING_ACTIONS, Capability
from ..core.actions.registry import action_specs, plugin_actions
from ..core.blueprint.loader import blueprint_schema
from ..core.blueprint.models import Blueprint
from ..core.runtime.engine import IMPLEMENTED_ACTS

if TYPE_CHECKING:
    from .factory import BlueprintDraft

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    """One problem found in a draft: its severity, a dotted path, and a human message."""

    severity: Severity
    path: str
    message: str


def _format_path(parts: Any) -> str:
    """Render a jsonschema/pydantic location (['steps', 2, 'url']) as 'steps[2].url'."""
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out or "<root>"


def _missing(value: Any) -> bool:
    """True when a required parameter is effectively empty (absent, blank, or empty container)."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (dict, list)):
        return len(value) == 0
    return False


def _semantic_issues(draft: "BlueprintDraft") -> list[ValidationIssue]:
    """Act/action rules the JSON Schema deliberately leaves open (steps are additionalProperties)."""
    issues: list[ValidationIssue] = []
    caps = ACT_CAPABILITIES.get(draft.act)
    specs = action_specs()
    plugins = plugin_actions()
    pending: frozenset[Capability] = PENDING_ACTIONS.get(draft.act, frozenset())

    if draft.act and draft.act not in IMPLEMENTED_ACTS:
        issues.append(ValidationIssue("warning", "act", f"Act {draft.act!r} is not runnable yet."))

    for index, step in enumerate(draft.steps):
        base = f"steps[{index}]"
        action = step.action
        if not action:
            issues.append(ValidationIssue("error", base, "Step is missing an action."))
            continue
        if action not in specs:
            issues.append(ValidationIssue("error", base, f"Unknown action {action!r}."))
            continue
        # Plugin actions are act-agnostic (docs/plugins.md): they bypass the capability table and
        # are never pending, so only their required parameters remain to check.
        if action not in plugins:
            if caps is not None and action not in {c.value for c in caps}:
                issues.append(
                    ValidationIssue(
                        "error", base, f"Action {action!r} is not supported by act {draft.act!r}."
                    )
                )
                continue
            if Capability(action) in pending:
                issues.append(
                    ValidationIssue("warning", base, f"Action {action!r} is not runnable yet.")
                )
                continue
        for param in specs[action].required_params():
            if _missing(step.params.get(param.name)):
                issues.append(
                    ValidationIssue("error", f"{base}.{param.name}", f"'{param.name}' is required.")
                )
    return issues


def validate_draft(draft: "BlueprintDraft") -> list[ValidationIssue]:
    """Return every issue in *draft*, most structural first. Never raises."""
    data = draft.to_data()
    issues: list[ValidationIssue] = []

    validator = Draft202012Validator(blueprint_schema())
    schema_errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    for error in schema_errors:
        issues.append(ValidationIssue("error", _format_path(error.path), error.message))

    # Only run the Pydantic model when the schema is clean, to avoid reporting the same shape twice.
    if not schema_errors:
        try:
            Blueprint.model_validate(data)
        except ValidationError as exc:
            for err in exc.errors():
                issues.append(ValidationIssue("error", _format_path(err["loc"]), err["msg"]))

    issues.extend(_semantic_issues(draft))
    return issues
