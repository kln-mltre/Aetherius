"""Tests for core/runtime/healing.py: chain resolution, step transformation, escalation replay.

Driven by fake drivers behind a fake resolver, so no Act extra (browser, cognition) is needed.
The executor-level integration (a healed step recorded SUCCESS with ``healed_by``) lives in
test_steps.py, next to the rest of the pipeline behaviour.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import ActionError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import RunEvent
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.healing import attempt_healing
from aetherius.core.runtime.result import StepResult

pytestmark = pytest.mark.unit


class OracleFake:
    """Records the replayed step; optionally fails to let the chain continue."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.replays: list[StepModel] = []

    def run_step(self, step: StepModel, ctx: Any, bus: Any, renderer: Any) -> dict[str, Any]:
        self.replays.append(step)
        if self.fail:
            raise ActionError("grounding failed")
        return {"replayed": True}


class PhantomFake(OracleFake):
    """Adds the micro-goal seam the phantom escalation duck-calls."""

    def __init__(self, fail: bool = False) -> None:
        super().__init__(fail)
        self.goals: list[dict[str, Any]] = []

    def run_micro_goal(
        self,
        ctx: Any,
        bus: Any,
        results: Any,
        *,
        goal: str,
        constraints: list[str],
        max_steps: int,
        id_prefix: str,
    ) -> dict[str, Any]:
        self.goals.append(
            {"goal": goal, "constraints": constraints, "max_steps": max_steps, "id": id_prefix}
        )
        if self.fail:
            raise ActionError("budget exhausted")
        return {"result": None, "steps_taken": 2}


class Resolver:
    def __init__(self, **drivers: Any) -> None:
        self.drivers = drivers
        self.asked: list[str] = []

    def resolve_driver(self, act: str, ctx: Any) -> Any:
        self.asked.append(act)
        return self.drivers[act]


def _ctx(fallback: list[str] | None = None) -> RunContext:
    data: dict[str, Any] = {
        "aetherius": "1.0",
        "name": "t.heal",
        "act": "continuum",
        "steps": [{"action": "emit"}],
    }
    if fallback is not None:
        data["options"] = {"fallback": fallback}
    bp = Blueprint.model_validate(data)
    return RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})


class ListSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


def _heal(
    step: dict[str, Any],
    *,
    act: str = "continuum",
    fallback: list[str] | None = None,
    resolver: Resolver | None = None,
) -> tuple[tuple[dict[str, Any], str] | None, Resolver, ListSink, list[StepResult]]:
    ctx = _ctx(fallback)
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    resolver = resolver or Resolver(oracle=OracleFake(), phantom=PhantomFake())
    results: list[StepResult] = []
    outcome = attempt_healing(
        StepModel.model_validate(step),
        act,
        ActionError("selector broke"),
        ctx=ctx,
        bus=bus,
        drivers=resolver,
        results=results,
        renderer=lambda v: v,
        step_id="s",
    )
    return outcome, resolver, sink, results


def _messages(sink: ListSink) -> str:
    return "\n".join(e.message or "" for e in sink.events)


# ── When healing does not apply ──────────────────────────────────────────────


def test_no_chain_means_no_healing() -> None:
    outcome, resolver, _, _ = _heal({"action": "click", "selector": "#x", "describe": "d"})
    assert outcome is None
    assert resolver.asked == []


def test_vector_steps_never_heal() -> None:
    outcome, _, _, _ = _heal(
        {"action": "http.request", "url": "x", "describe": "d"},
        act="vector",
        fallback=["oracle"],
    )
    assert outcome is None


def test_entries_not_above_the_act_are_filtered() -> None:
    outcome, resolver, _, _ = _heal(
        {"action": "click", "target": {"vision": "the button"}},
        act="oracle",
        fallback=["oracle"],
    )
    assert outcome is None
    assert resolver.asked == []


def test_uncoverable_action_is_reported_and_propagated() -> None:
    outcome, _, sink, _ = _heal(
        {"action": "extract", "outputs": {}, "describe": "d"}, fallback=["oracle"]
    )
    assert outcome is None
    assert "does not cover action 'extract'" in _messages(sink)


def test_missing_describe_skips_healing_with_a_clear_event() -> None:
    outcome, _, sink, _ = _heal({"action": "click", "selector": "#x"}, fallback=["oracle"])
    assert outcome is None
    assert "no 'describe'" in _messages(sink)


# ── Oracle escalation (vision replay) ────────────────────────────────────────


def test_click_is_replayed_as_a_vision_step() -> None:
    outcome, resolver, sink, _ = _heal(
        {"id": "n", "action": "click", "selector": "#x", "describe": "the Next link"},
        fallback=["oracle"],
    )
    assert outcome == ({"replayed": True}, "oracle")
    replay = resolver.drivers["oracle"].replays[0]
    assert replay.action == "click"
    assert replay.extra_fields["target"] == {"vision": "the Next link"}
    assert "selector" not in replay.extra_fields
    assert "healed by 'oracle'" in _messages(sink)


def test_fill_becomes_a_vision_type_with_its_value_as_text() -> None:
    outcome, resolver, _, _ = _heal(
        {"action": "fill", "selector": "#q", "value": "hello", "describe": "the search box"},
        fallback=["oracle"],
    )
    assert outcome is not None
    replay = resolver.drivers["oracle"].replays[0]
    assert replay.action == "type"
    assert replay.extra_fields["text"] == "hello"
    assert replay.extra_fields["target"] == {"vision": "the search box"}


def test_wait_for_forwards_its_timeout_parameters() -> None:
    outcome, resolver, _, _ = _heal(
        {
            "action": "wait_for",
            "selector": ".gone",
            "timeout_ms": 1234,
            "on_timeout": "fail:X",
            "describe": "the banner",
        },
        fallback=["oracle"],
    )
    assert outcome is not None
    replay = resolver.drivers["oracle"].replays[0]
    assert replay.extra_fields["timeout_ms"] == 1234
    assert replay.extra_fields["on_timeout"] == "fail:X"


def test_step_fallback_overrides_the_global_chain() -> None:
    outcome, resolver, _, _ = _heal(
        {"action": "click", "selector": "#x", "describe": "d", "fallback": []},
        fallback=["oracle"],
    )
    assert outcome is None
    assert resolver.asked == []


# ── Phantom escalation (micro-goal) ──────────────────────────────────────────


def test_oracle_failure_escalates_to_the_phantom_micro_goal() -> None:
    resolver = Resolver(oracle=OracleFake(fail=True), phantom=PhantomFake())
    outcome, _, sink, _ = _heal(
        {"id": "n", "action": "click", "selector": "#x", "describe": "the Next link"},
        fallback=["oracle", "phantom"],
        resolver=resolver,
    )
    assert outcome == ({}, "phantom")
    goal = resolver.drivers["phantom"].goals[0]
    assert goal["goal"] == "Click the Next link."
    assert goal["max_steps"] == 6
    # The prefix derives from the display id the executor passed, keeping nested paths intact.
    assert goal["id"] == "s.heal"
    assert "'oracle' escalation failed too" in _messages(sink)


def test_type_micro_goal_carries_the_rendered_text() -> None:
    resolver = Resolver(oracle=OracleFake(fail=True), phantom=PhantomFake())
    outcome, _, _, _ = _heal(
        {"action": "type", "selector": "#q", "text": "hi", "describe": "the search box"},
        fallback=["oracle", "phantom"],
        resolver=resolver,
    )
    assert outcome == ({}, "phantom")
    assert resolver.drivers["phantom"].goals[0]["goal"] == "Type 'hi' into the search box."


def test_planner_inexpressible_actions_skip_phantom() -> None:
    resolver = Resolver(oracle=OracleFake(fail=True), phantom=PhantomFake())
    outcome, _, sink, _ = _heal(
        {"action": "hover", "selector": "#x", "describe": "the menu"},
        fallback=["oracle", "phantom"],
        resolver=resolver,
    )
    assert outcome is None
    assert resolver.drivers["phantom"].goals == []
    assert "cannot express 'hover'" in _messages(sink)


def test_a_vision_step_reuses_its_target_as_description() -> None:
    resolver = Resolver(oracle=OracleFake(), phantom=PhantomFake())
    outcome, _, _, _ = _heal(
        {"action": "click", "target": {"vision": "the Post button"}},
        act="oracle",
        fallback=["phantom"],
        resolver=resolver,
    )
    assert outcome == ({}, "phantom")
    assert resolver.drivers["phantom"].goals[0]["goal"] == "Click the Post button."


def test_exhausted_chain_returns_none_after_telling_the_story() -> None:
    resolver = Resolver(oracle=OracleFake(fail=True), phantom=PhantomFake(fail=True))
    outcome, _, sink, _ = _heal(
        {"action": "click", "selector": "#x", "describe": "d"},
        fallback=["oracle", "phantom"],
        resolver=resolver,
    )
    assert outcome is None
    text = _messages(sink)
    assert "'oracle' escalation failed too" in text
    assert "'phantom' escalation failed too" in text
