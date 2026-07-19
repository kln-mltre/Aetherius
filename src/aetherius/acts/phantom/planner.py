"""Phantom's decision policy: adapt a cognition ``Planner`` into the loop's next move.

Wraps ``CognitionProvider.plan`` (Claude tool-use by default) and interprets its two terminal
answers so the loop stays a plain "keep going / stop" driver:

- a leaf step dict (``click``/``type``/``read``/...) -> returned as-is, the loop dispatches it;
- ``finish`` -> the goal is reached: the result is stored on the memory and ``None`` is returned;
- ``abort`` -> the goal is impossible or a constraint forbids continuing: a typed ``AgentError``.

The provider stays pluggable: any object implementing ``Planner`` (a local VLM behind the same
interface) drops in without touching this adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.errors import AgentError

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
    """Ask *planner* for the next step toward *goal*, or ``None`` when the goal is reached.

    Raises:
        AgentError: the planner aborted (goal impossible or a constraint forbids continuing).
    """
    action = planner.plan(goal, constraints, perception, memory)
    if action is None:
        return None
    name = action.get("action")
    if name == "finish":
        memory.result = action.get("result")
        return None
    if name == "abort":
        raise AgentError(f"agent aborted: {action.get('reason') or 'no reason given'}")
    return action
