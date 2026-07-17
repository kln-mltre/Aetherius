"""Unified target model: express an action's target independently of the Act that resolves it.

A step aims at either a DOM *selector* (css/xpath/text — resolved by Continuum, Act II) or a
natural-language *vision* description (resolved by an Oracle/Phantom ``Grounder`` into on-screen
coordinates). ``Target`` is the single shape both Acts share, so the same action (``click``,
``type``, ``wait_for``) reads identically regardless of who resolves it — the seam the multi-Act
composition (Jalon 2-E) and Oracle (2-B) build on.

Skeleton for Phase 2 (Jalon 2-A): the parsing/validation of a step's target lands there; the data
shapes below are the contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

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

        Implemented in Jalon 2-A (docs/phase-2/2-a-cognition.md).
        """
        raise NotImplementedError
