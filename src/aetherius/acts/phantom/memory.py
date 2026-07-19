"""Phantom's working and task memory across loop iterations.

Holds the goal, the running history of (action, observation) pairs, any extracted facts, and the
final result the planner reported via ``finish``. The planner reads a compact ``transcript`` of
this each turn so it reasons with context rather than statelessly. Kept deliberately small: one
screenshot per turn already carries the visual state, so the transcript only needs the thread of
what was done and what came back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Observations (especially `read` results) can be large; cap each line so a long run's transcript
# stays within a sane token budget for the planning call.
_MAX_OBS_CHARS = 500


@dataclass
class AgentMemory:
    """Mutable memory threaded through the perceive->reason->act loop."""

    goal: str
    history: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    result: Any = None

    def record(self, action: dict[str, Any], observation: Any) -> None:
        """Append an (action, observation) pair to the history."""
        self.history.append({"action": action, "observation": observation})

    def transcript(self) -> str:
        """Render the history as a compact numbered log for the planner's next call."""
        return "\n".join(
            f"{i}. {_action_summary(entry['action'])}{_observation_summary(entry['observation'])}"
            for i, entry in enumerate(self.history, 1)
        )


def _action_summary(action: dict[str, Any]) -> str:
    name = str(action.get("action", "?"))
    target = action.get("target")
    if isinstance(target, dict) and target.get("vision"):
        detail = repr(target["vision"])
    else:
        detail = next(
            (repr(action[k]) for k in ("url", "vision", "key", "reason") if action.get(k)), ""
        )
    text = action.get("text")
    if text:
        detail = f"{detail} text={text!r}".strip()
    return f"{name} {detail}".strip()


def _observation_summary(observation: Any) -> str:
    if observation is None:
        return ""
    if isinstance(observation, dict):
        if not observation:
            return " -> ok"
        if set(observation) == {"error"}:
            return f" -> FAILED: {_truncate(str(observation['error']))}"
        return f" -> {_truncate(json.dumps(observation, ensure_ascii=False, default=str))}"
    return f" -> {_truncate(str(observation))}"


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_OBS_CHARS else text[:_MAX_OBS_CHARS] + "…"
