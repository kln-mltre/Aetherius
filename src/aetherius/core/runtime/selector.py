"""Unified target model: express an action's target independently of the Act that resolves it.

A step aims at either a DOM *selector* (css/xpath/text — resolved by Continuum, Act II) or a
natural-language *vision* description (resolved by an Oracle/Phantom ``Grounder`` into on-screen
coordinates). ``Target`` is the single shape both Acts share, so the same action (``click``,
``type``, ``wait_for``) reads identically regardless of who resolves it — the seam the multi-Act
composition (Jalon 2-E) and Oracle (2-B) build on.

The parsing rules mirror the Blueprint surface: Continuum steps carry a top-level ``selector``
(plus optional ``selector_type``), Oracle steps carry ``target: {vision: ...}`` — and a nested
``target: {selector: ...}`` is accepted so the unified form also works for DOM targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, get_args

from ..errors import ActionError

SelectorType = Literal["css", "xpath", "text"]


@dataclass(frozen=True)
class Box:
    """An axis-aligned rectangle in CSS pixels within the current viewport."""

    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass(frozen=True)
class Target:
    """Where an action points: a DOM selector, or a vision description — never both."""

    selector: str | None = None
    selector_type: SelectorType = "css"
    vision: str | None = None

    @property
    def is_vision(self) -> bool:
        return self.vision is not None

    @classmethod
    def from_step(cls, params: Mapping[str, Any]) -> "Target":
        """Read a step's ``selector``/``selector_type`` or ``target: {vision: ...}`` into a Target.

        Raises :class:`ActionError` when the step is ambiguous (both a selector and a vision
        description) or targets nothing — the caller only asks for a Target when the action
        needs one, so both cases are authoring mistakes worth a clear message.
        """
        raw_target = params.get("target")
        nested: Mapping[str, Any] = raw_target if isinstance(raw_target, Mapping) else {}

        selector = params.get("selector", nested.get("selector"))
        vision = nested.get("vision")
        if selector is not None and vision is not None:
            raise ActionError(
                "Ambiguous target: a step must aim at a selector or a vision description, not both."
            )
        if selector is None and vision is None:
            raise ActionError(
                "Missing target: expected a 'selector' or a 'target: {vision: ...}' on the step."
            )

        selector_type = params.get("selector_type", nested.get("selector_type", "css"))
        if selector_type not in get_args(SelectorType):
            raise ActionError(
                f"Unknown selector_type {selector_type!r}; expected one of {get_args(SelectorType)}."
            )
        return cls(selector=selector, selector_type=selector_type, vision=vision)
