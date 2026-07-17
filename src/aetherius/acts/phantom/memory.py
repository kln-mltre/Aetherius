"""Phantom's working and task memory across loop iterations.

Holds the goal, the running history of actions and observations, and any extracted facts, so the
planner reasons with context rather than statelessly. Skeleton for Jalon 2-D.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMemory:
    """Mutable memory threaded through the perceive->reason->act loop."""

    goal: str
    history: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)

    def record(self, action: dict[str, Any], observation: Any) -> None:
        """Append an (action, observation) pair to the history. Implemented in Jalon 2-D."""
        raise NotImplementedError
