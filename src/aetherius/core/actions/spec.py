"""Declarative field specs for actions: the typed metadata the builder projects into forms.

The action *registry* dispatches by name; this module describes each action's parameters (name,
kind, whether required, a one-line help, an example placeholder) so a UI can generate a form and a
validator can flag a missing required field before the step ever runs. The specs are the single
source the builder catalogue is a projection of — they carry no behaviour, only shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Object/array params are edited as JSON (their shape is left open by the schema on purpose);
# scalar kinds map to a flat form field.
ParamKind = Literal["string", "number", "integer", "boolean", "object", "array"]


@dataclass(frozen=True)
class ParamSpec:
    """One parameter of an action: how a form renders it and how a validator checks it."""

    name: str
    kind: ParamKind
    required: bool = False
    help: str = ""
    default: Any = None
    # Example value shown to guide the user; a JSON snippet for object/array params.
    placeholder: str = ""


@dataclass(frozen=True)
class ActionSpec:
    """An action's name, a one-line summary, and its ordered parameters."""

    name: str
    summary: str
    params: tuple[ParamSpec, ...] = field(default_factory=tuple)

    def required_params(self) -> tuple[ParamSpec, ...]:
        """The subset of parameters a Blueprint step must provide for this action."""
        return tuple(p for p in self.params if p.required)
