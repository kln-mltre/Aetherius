"""Claude-backed cognition provider (default): grounding, semantic extraction and planning.

Fills the three roles of ``provider.py`` via the Anthropic API (vision + tool-use). ``anthropic``
(extra ``[cognition]``) is imported lazily inside the methods, never at module load, so
``import aetherius`` stays light. Skeleton for Jalon 2-A; the API calls land in 2-A (grounding /
extraction) and 2-D (planning).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._perception import Perception
    from .provider import GroundResult


class ClaudeProvider:
    """Default cognition provider. One instance per run; ``model`` comes from ``vision.model``."""

    name = "claude"

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def locate(self, perception: "Perception", description: str) -> "GroundResult":
        raise NotImplementedError("Claude grounding lands in Jalon 2-A/2-B.")

    def read(
        self, perception: "Perception", description: str, *, schema: dict[str, Any] | None = None
    ) -> Any:
        raise NotImplementedError("Semantic extraction lands in Jalon 2-B.")

    def plan(
        self,
        goal: str,
        constraints: list[str],
        perception: "Perception",
        memory: Any,
    ) -> dict[str, Any] | None:
        raise NotImplementedError("Claude planner lands in Jalon 2-D.")
