"""Phantom's decision policy: adapt a cognition ``Planner`` to choose the next action.

Wraps ``CognitionProvider.plan`` (Claude tool-use by default) so the loop gets a concrete next
action (a step dict) or ``None`` when the goal is reached. The action vocabulary offered to the
planner is the Act's capability set. Skeleton for Jalon 2-D.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._cognition.provider import Planner
    from .._perception import Perception
    from .memory import AgentMemory


def next_action(
    planner: "Planner",
    goal: str,
    constraints: list[str],
    perception: "Perception",
    memory: "AgentMemory",
) -> dict[str, Any] | None:
    """Ask the planner for the next step toward *goal*, or ``None`` when done. Jalon 2-D."""
    raise NotImplementedError
