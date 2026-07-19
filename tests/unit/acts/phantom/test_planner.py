"""Tests for acts/phantom/planner.py — adapting a Planner reply into the loop's next move."""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.acts._perception import Perception
from aetherius.acts.phantom.memory import AgentMemory
from aetherius.acts.phantom.planner import next_action
from aetherius.core.errors import AgentError

pytestmark = pytest.mark.unit

_PERCEPTION = Perception(screenshot=b"png", viewport=(1280, 720))


class _FixedPlanner:
    """A Planner returning one scripted reply, recording the call."""

    def __init__(self, reply: dict[str, Any] | None) -> None:
        self._reply = reply
        self.calls: list[tuple[str, list[str]]] = []

    def plan(
        self, goal: str, constraints: list[str], perception: Perception, memory: Any
    ) -> dict[str, Any] | None:
        self.calls.append((goal, constraints))
        return self._reply


def test_leaf_action_passes_through() -> None:
    planner = _FixedPlanner({"action": "click", "target": {"vision": "the button"}})
    memory = AgentMemory(goal="g")

    action = next_action(planner, "g", ["stay put"], _PERCEPTION, memory)

    assert action == {"action": "click", "target": {"vision": "the button"}}
    assert planner.calls == [("g", ["stay put"])]


def test_finish_stores_result_and_returns_none() -> None:
    planner = _FixedPlanner({"action": "finish", "result": {"quote": "hi"}})
    memory = AgentMemory(goal="g")

    assert next_action(planner, "g", [], _PERCEPTION, memory) is None
    assert memory.result == {"quote": "hi"}


def test_abort_raises_agent_error_with_reason() -> None:
    planner = _FixedPlanner({"action": "abort", "reason": "captcha wall"})

    with pytest.raises(AgentError, match="captcha wall"):
        next_action(planner, "g", [], _PERCEPTION, AgentMemory(goal="g"))


def test_none_reply_is_treated_as_done() -> None:
    planner = _FixedPlanner(None)
    assert next_action(planner, "g", [], _PERCEPTION, AgentMemory(goal="g")) is None
