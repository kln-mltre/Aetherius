"""Cognition providers: the model-backed reasoning shared by Oracle (III) and Phantom (IV).

Three segregated roles behind one interface, so a Blueprint picks ``claude`` (default) or a local
model without any Act knowing which:

- ``Grounder``  — locate a UI element from a natural-language description (Oracle targeting, Phantom).
- ``Extractor`` — read data off the screen described in natural language (semantic extraction).
- ``Planner``   — choose the next action toward a goal (Phantom's decision policy).

Heavy SDKs (``anthropic``, ``onnxruntime``) are imported lazily by the concrete providers
(``claude.py`` / ``local.py``), never here: ``import aetherius`` stays light. Skeleton for Jalon 2-A.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ...core.runtime.selector import Box
    from .._perception import Perception


@dataclass(frozen=True)
class GroundResult:
    """A located element: its box in the viewport and the provider's confidence (0..1)."""

    box: "Box"
    confidence: float


class Grounder(Protocol):
    """Locate a UI element on screen from a natural-language description."""

    def locate(self, perception: "Perception", description: str) -> GroundResult: ...


class Extractor(Protocol):
    """Read data off the screen, described in natural language, optionally shaped by a schema."""

    def read(
        self, perception: "Perception", description: str, *, schema: dict[str, Any] | None = None
    ) -> Any: ...


class Planner(Protocol):
    """Choose the next action toward a goal, or ``None`` when the goal is reached."""

    def plan(
        self,
        goal: str,
        constraints: list[str],
        perception: "Perception",
        memory: Any,
    ) -> dict[str, Any] | None: ...


class CognitionProvider(Grounder, Extractor, Planner, Protocol):
    """A provider filling all three roles (e.g. Claude). Local providers may implement a subset."""

    name: str
