"""The perceive->reason->act loop that advances Phantom toward its goal.

One iteration: perceive (``acts/_perception.capture``) -> plan (``Planner.plan``) -> act (dispatch
the chosen action through the shared substrate) -> remember (``memory.py``). Bounded by a step budget
and the Blueprint's ``constraints``. Skeleton for Jalon 2-D.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.events.bus import EventBus
    from ...core.runtime.context import RunContext
    from .._cognition.provider import CognitionProvider


def run_loop(
    provider: "CognitionProvider",
    ctx: "RunContext",
    bus: "EventBus",
    *,
    max_steps: int = 40,
) -> dict[str, Any]:
    """Iterate until the goal is met, a constraint stops it, or the step budget runs out.

    Implemented in Jalon 2-D. *max_steps* is the guardrail against a runaway agent.
    """
    raise NotImplementedError
