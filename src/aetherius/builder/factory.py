"""Assemble a valid Blueprint from structured choices, validating against the schema as it is built.

The headless heart of the Blueprint Studio, reusable by the Console, the daemon and the SDKs. A
:class:`BlueprintDraft` is the mutable editing state: raw data (dicts/lists), legitimately partial
while a user is still filling it in. :func:`validate_draft` reports issues without raising (the live
preview calls it on every change); :func:`build_blueprint` / :func:`save_blueprint` finalise it and
raise typed errors. ``assemble_blueprint`` and ``slugify_name`` live here — the recorder, a producer
of steps, re-exports them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..core.actions.registry import get_spec
from ..core.actions.spec import ParamKind
from ..core.blueprint.loader import load_blueprint, validate_blueprint_data
from ..core.blueprint.models import Blueprint
from ..core.blueprint.validator import validate_for_act
from ..core.errors import BuilderError
from .validation import ValidationIssue, validate_draft

__all__ = [
    "slugify_name",
    "assemble_blueprint",
    "StepDraft",
    "BlueprintDraft",
    "ValidationIssue",
    "validate_draft",
    "build_blueprint",
    "save_blueprint",
]


def slugify_name(name: str) -> str:
    """Filesystem-safe stem derived from a Blueprint name (keeps dots, e.g. quotes.login)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
    return slug or "blueprint"


def assemble_blueprint(
    name: str,
    steps: list[dict[str, Any]],
    secrets: list[str],
    *,
    act: str = "continuum",
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    description: str | None = None,
    vars: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    vision: dict[str, Any] | None = None,
    goal: str | None = None,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a minimal, ordered Blueprint dict for *act* (schema key order, empties omitted)."""
    blueprint: dict[str, Any] = {"aetherius": "1.0", "name": name}
    if description:
        blueprint["description"] = description
    blueprint["act"] = act
    if inputs:
        blueprint["inputs"] = inputs
    if secrets:
        blueprint["secrets"] = secrets
    if vars:
        blueprint["vars"] = vars
    if options:
        blueprint["options"] = options
    if vision:
        blueprint["vision"] = vision
    if goal:
        blueprint["goal"] = goal
    if constraints:
        blueprint["constraints"] = constraints
    # A goal-only Blueprint (Phantom) legitimately has no steps; otherwise steps are always present.
    if steps or not goal:
        blueprint["steps"] = steps
    if outputs:
        blueprint["outputs"] = outputs
    return blueprint


# Empty value used to pre-seed a required parameter, per kind, so a freshly added step shows what it
# still needs (and validate_draft flags it until filled). Empty object/array stay valid JSON.
def _empty_value(kind: ParamKind) -> Any:
    if kind == "boolean":
        return False
    if kind == "object":
        return {}
    if kind == "array":
        return []
    return ""


@dataclass
class StepDraft:
    """One editable step: an action, an optional id, and its raw parameters."""

    action: str
    id: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    def to_data(self) -> dict[str, Any]:
        """Serialise to the step dict shape (id first when set, then action, then params)."""
        data: dict[str, Any] = {}
        if self.id:
            data["id"] = self.id
        data["action"] = self.action
        data.update(self.params)
        return data

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "StepDraft":
        params = {k: v for k, v in data.items() if k not in ("id", "action")}
        return cls(action=str(data.get("action", "")), id=data.get("id"), params=params)


@dataclass
class BlueprintDraft:
    """Mutable editing state of a Blueprint. Lossless: carries every envelope field so an existing
    file round-trips unchanged through ``from_data``/``to_data`` (e.g. refining recorder output)."""

    name: str = ""
    act: str = "vector"
    description: str | None = None
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    secrets: list[str] = field(default_factory=list)
    vars: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    steps: list[StepDraft] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    vision: dict[str, Any] | None = None
    goal: str | None = None
    constraints: list[str] = field(default_factory=list)

    def add_step(self, action: str, *, index: int | None = None) -> StepDraft:
        """Append (or insert at *index*) a step, pre-seeding its required parameters."""
        params: dict[str, Any] = {}
        try:
            spec = get_spec(action)
        except Exception:
            spec = None
        if spec is not None:
            for param in spec.required_params():
                params[param.name] = _empty_value(param.kind)
        step = StepDraft(action=action, params=params)
        if index is None:
            self.steps.append(step)
        else:
            self.steps.insert(max(0, min(index, len(self.steps))), step)
        return step

    def remove_step(self, index: int) -> None:
        if 0 <= index < len(self.steps):
            del self.steps[index]

    def move_step(self, index: int, delta: int) -> None:
        """Move the step at *index* by *delta* positions, clamped to the list bounds."""
        if not (0 <= index < len(self.steps)):
            return
        target = max(0, min(index + delta, len(self.steps) - 1))
        if target != index:
            self.steps.insert(target, self.steps.pop(index))

    def to_data(self) -> dict[str, Any]:
        """Assemble the ordered Blueprint dict this draft represents (empties omitted)."""
        return assemble_blueprint(
            self.name,
            [step.to_data() for step in self.steps],
            list(self.secrets),
            act=self.act,
            inputs=dict(self.inputs) or None,
            outputs=dict(self.outputs) or None,
            description=self.description,
            vars=dict(self.vars) or None,
            options=dict(self.options) or None,
            vision=self.vision,
            goal=self.goal,
            constraints=list(self.constraints) or None,
        )

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "BlueprintDraft":
        """Build a draft from a Blueprint dict (as loaded from a file), preserving every field."""
        return cls(
            name=str(data.get("name", "")),
            act=str(data.get("act", "vector")),
            description=data.get("description"),
            inputs={k: dict(v) for k, v in (data.get("inputs") or {}).items()},
            secrets=list(data.get("secrets") or []),
            vars=dict(data.get("vars") or {}),
            options=dict(data.get("options") or {}),
            steps=[StepDraft.from_data(s) for s in (data.get("steps") or [])],
            outputs=dict(data.get("outputs") or {}),
            vision=data.get("vision"),
            goal=data.get("goal"),
            constraints=list(data.get("constraints") or []),
        )


def build_blueprint(draft: BlueprintDraft) -> Blueprint:
    """Finalise *draft* into a validated Blueprint model, raising typed errors on any problem."""
    blueprint = validate_blueprint_data(draft.to_data(), source="<studio>")
    validate_for_act(blueprint)
    return blueprint


def save_blueprint(
    draft: BlueprintDraft,
    *,
    path: Path | str | None = None,
    out_dir: Path | str | None = None,
) -> Path:
    """Validate and write *draft* to disk, returning the file path.

    With *path* (edit mode) the file is overwritten in place. Otherwise the file is created under
    *out_dir* (or ``./blueprints``) as ``{slug}.blueprint.json``; a name collision with a different
    existing file raises :class:`BuilderError` rather than clobbering it. Validation runs before any
    write, and the written file is re-read through the canonical loader as a final guarantee.
    """
    build_blueprint(draft)  # raise before touching disk

    if path is not None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = Path(out_dir) if out_dir is not None else Path.cwd() / "blueprints"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{slugify_name(draft.name)}.blueprint.json"
        if target.exists():
            raise BuilderError(
                f"A Blueprint already exists at {target}. Rename this one, or open that file to edit."
            )

    target.write_text(
        json.dumps(draft.to_data(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    validate_for_act(load_blueprint(target))
    return target
