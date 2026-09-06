"""Tests for core/runtime/steps.py: when guards, flow actions, recursion, error reporting.

Driven by a fake driver that records every dispatched (action, rendered params) pair and can
fail on demand, so the executor is exercised without any Act extra. A few cases go through
RunEngine end to end to prove the run-level status semantics.
"""

from __future__ import annotations

from typing import Any, Callable

import pytest

from aetherius.core.actions.base import FLOW_ACTIONS
from aetherius.core.blueprint.models import Blueprint, StepModel
from aetherius.core.errors import ActionError, AetheriusError, StepTimeoutError, TemplateError
from aetherius.core.events.bus import EventBus
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.context import RunContext
from aetherius.core.runtime.result import RunStatus, StepResult
from aetherius.core.runtime.steps import StepFailed, is_truthy, run_steps

pytestmark = pytest.mark.unit


class ListSink:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def on_event(self, event: RunEvent) -> None:
        self.events.append(event)


class FakeDriver:
    """Records every dispatched step; fails when a step carries ``boom: true``."""

    act = "vector"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def setup(self, ctx: RunContext) -> None:
        pass

    def teardown(self, ctx: RunContext) -> None:
        pass

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        params = {k: renderer(v) for k, v in step.extra_fields.items()}
        if params.get("boom"):
            raise ActionError("boom")
        self.calls.append((step.action, params))
        return {"value": params.get("value")}


def _steps(*raw: dict[str, Any]) -> list[StepModel]:
    return [StepModel.model_validate(item) for item in raw]


def _ctx(**inputs: Any) -> RunContext:
    bp = Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t", "act": "vector", "steps": [{"action": "set"}]}
    )
    return RunContext(run_id="r", blueprint=bp, inputs=dict(inputs), secrets={})


def _run(
    *raw: dict[str, Any], inputs: dict[str, Any] | None = None
) -> tuple[list[StepResult], ListSink, FakeDriver, RunContext]:
    ctx = _ctx(**(inputs or {}))
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    driver = FakeDriver()
    results: list[StepResult] = []
    run_steps(_steps(*raw), ctx, bus, driver, results)
    return results, sink, driver, ctx


def _events(sink: ListSink, type_: EventType) -> list[RunEvent]:
    return [e for e in sink.events if e.type == type_]


# ── Truthiness ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["true", "1", "yes", " True ", "YES", True, 1])
def test_is_truthy_accepts_the_assert_rule(value: Any) -> None:
    assert is_truthy(value)


@pytest.mark.parametrize("value", ["false", "0", "no", "", None, False, 0, "maybe"])
def test_is_truthy_rejects_everything_else(value: Any) -> None:
    assert not is_truthy(value)


# ── when guard ────────────────────────────────────────────────────────────────


def test_when_true_executes_the_step() -> None:
    results, sink, driver, ctx = _run({"id": "a", "action": "set", "when": "true", "value": "x"})
    assert [r.status for r in results] == [RunStatus.SUCCESS]
    assert driver.calls == [("set", {"value": "x"})]
    assert ctx.step_outputs["a"] == {"value": "x"}


def test_when_false_skips_with_result_event_and_no_outputs() -> None:
    results, sink, driver, ctx = _run({"id": "a", "action": "set", "when": "false", "value": "x"})
    assert [r.status for r in results] == [RunStatus.SKIPPED]
    assert results[0].step_id == "a"
    assert driver.calls == []
    assert "a" not in ctx.step_outputs

    skipped = _events(sink, EventType.STEP_SKIPPED)
    assert len(skipped) == 1
    assert skipped[0].step_id == "a"
    assert skipped[0].data == {"when": "false"}
    # A skipped step emits neither started nor finished.
    assert not _events(sink, EventType.STEP_STARTED)
    assert not _events(sink, EventType.STEP_FINISHED)


def test_when_references_a_previous_step_output() -> None:
    results, _, driver, _ = _run(
        {"id": "check", "action": "set", "value": True},
        {"id": "alert", "action": "emit", "when": "{{ steps.check.value }}"},
        {"id": "never", "action": "emit", "when": "{{ not steps.check.value }}"},
    )
    assert [r.status for r in results] == [
        RunStatus.SUCCESS,
        RunStatus.SUCCESS,
        RunStatus.SKIPPED,
    ]
    assert [action for action, _ in driver.calls] == ["set", "emit"]


def test_referencing_a_skipped_step_raises_template_error() -> None:
    with pytest.raises(StepFailed):
        _run(
            {"id": "a", "action": "set", "when": "false", "value": "x"},
            {"id": "b", "action": "set", "value": "{{ steps.a.value }}"},
        )


def test_when_render_error_fails_the_step() -> None:
    ctx = _ctx()
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    results: list[StepResult] = []
    with pytest.raises(StepFailed):
        run_steps(
            _steps({"id": "a", "action": "set", "when": "{{ nope.nope }}"}),
            ctx,
            bus,
            FakeDriver(),
            results,
        )
    assert [r.status for r in results] == [RunStatus.FAILED]
    assert len(_events(sink, EventType.ERROR)) == 1


def test_when_guards_a_flow_step_as_a_whole() -> None:
    results, sink, driver, _ = _run(
        {
            "id": "block",
            "action": "if",
            "when": "false",
            "condition": "true",
            "then": [{"action": "set", "value": "x"}],
        }
    )
    assert [r.status for r in results] == [RunStatus.SKIPPED]
    assert driver.calls == []


def test_when_true_as_json_boolean_is_rejected_at_parse() -> None:
    with pytest.raises(Exception):
        StepModel.model_validate({"action": "set", "when": True})


# ── if / then / else ──────────────────────────────────────────────────────────


def test_if_runs_then_branch() -> None:
    results, _, driver, ctx = _run(
        {
            "id": "gate",
            "action": "if",
            "condition": "true",
            "then": [{"id": "inner", "action": "set", "value": "t"}],
            "else": [{"id": "other", "action": "set", "value": "e"}],
        }
    )
    assert driver.calls == [("set", {"value": "t"})]
    assert ctx.step_outputs["gate"] == {"branch": "then"}
    assert ctx.step_outputs["inner"] == {"value": "t"}
    # Nested results precede their container (completion order).
    assert [(r.step_id, r.status) for r in results] == [
        ("gate.inner", RunStatus.SUCCESS),
        ("gate", RunStatus.SUCCESS),
    ]


def test_if_runs_else_branch() -> None:
    _, _, driver, ctx = _run(
        {
            "id": "gate",
            "action": "if",
            "condition": "false",
            "then": [{"action": "set", "value": "t"}],
            "else": [{"action": "set", "value": "e"}],
        }
    )
    assert driver.calls == [("set", {"value": "e"})]
    assert ctx.step_outputs["gate"] == {"branch": "else"}


def test_if_without_else_is_a_successful_noop() -> None:
    results, _, driver, ctx = _run(
        {
            "id": "gate",
            "action": "if",
            "condition": "false",
            "then": [{"action": "set", "value": "t"}],
        }
    )
    assert driver.calls == []
    assert [r.status for r in results] == [RunStatus.SUCCESS]
    assert ctx.step_outputs["gate"] == {"branch": None}


def test_if_requires_condition() -> None:
    with pytest.raises(StepFailed, match="condition"):
        _run({"id": "gate", "action": "if", "then": [{"action": "set"}]})


# ── repeat ────────────────────────────────────────────────────────────────────


def test_repeat_runs_nested_steps_n_times() -> None:
    results, _, driver, ctx = _run(
        {
            "id": "loop",
            "action": "repeat",
            "times": 3,
            "steps": [{"id": "tick", "action": "emit"}],
        }
    )
    assert [action for action, _ in driver.calls] == ["emit"] * 3
    assert ctx.step_outputs["loop"] == {"iterations": 3}
    assert [r.step_id for r in results] == ["loop[0].tick", "loop[1].tick", "loop[2].tick", "loop"]


def test_repeat_times_can_be_templated() -> None:
    _, _, driver, _ = _run(
        {
            "id": "loop",
            "action": "repeat",
            "times": "{{ inputs.n }}",
            "steps": [{"action": "emit"}],
        },
        inputs={"n": 2},
    )
    assert len(driver.calls) == 2


def test_repeat_zero_times_is_a_successful_noop() -> None:
    results, _, driver, _ = _run(
        {"id": "loop", "action": "repeat", "times": 0, "steps": [{"action": "emit"}]}
    )
    assert driver.calls == []
    assert [r.status for r in results] == [RunStatus.SUCCESS]


@pytest.mark.parametrize("times", ["abc", -1, None, 1.5, True])
def test_repeat_rejects_invalid_times(times: Any) -> None:
    with pytest.raises(StepFailed, match="times"):
        _run({"id": "loop", "action": "repeat", "times": times, "steps": [{"action": "emit"}]})


def test_repeat_requires_times() -> None:
    with pytest.raises(StepFailed, match="times"):
        _run({"id": "loop", "action": "repeat", "steps": [{"action": "emit"}]})


# ── for_each ──────────────────────────────────────────────────────────────────


def test_for_each_exposes_the_loop_variable() -> None:
    _, _, driver, ctx = _run(
        {
            "id": "loop",
            "action": "for_each",
            "items": "{{ inputs.names }}",
            "as": "name",
            "steps": [{"id": "say", "action": "emit", "value": "{{ name }}"}],
        },
        inputs={"names": ["a", "b"]},
    )
    assert [params["value"] for _, params in driver.calls] == ["a", "b"]
    assert ctx.step_outputs["loop"] == {"iterations": 2}
    # The loop variable does not leak out of the loop.
    assert "name" not in ctx.scope


def test_for_each_defaults_the_loop_variable_to_item() -> None:
    _, _, driver, _ = _run(
        {
            "id": "loop",
            "action": "for_each",
            "items": "{{ inputs.names }}",
            "steps": [{"action": "emit", "value": "{{ item }}"}],
        },
        inputs={"names": ["x"]},
    )
    assert driver.calls == [("emit", {"value": "x"})]


def test_for_each_restores_a_shadowed_variable() -> None:
    ctx = _ctx(names=["a"])
    ctx.scope["name"] = "outer"
    bus = EventBus()
    bus.register(ListSink())
    results: list[StepResult] = []
    run_steps(
        _steps(
            {
                "id": "loop",
                "action": "for_each",
                "items": "{{ inputs.names }}",
                "as": "name",
                "steps": [{"action": "emit", "value": "{{ name }}"}],
            }
        ),
        ctx,
        bus,
        FakeDriver(),
        results,
    )
    assert ctx.scope["name"] == "outer"


def test_for_each_over_an_empty_list_is_a_successful_noop() -> None:
    results, _, driver, ctx = _run(
        {
            "id": "loop",
            "action": "for_each",
            "items": "{{ inputs.names }}",
            "steps": [{"action": "emit"}],
        },
        inputs={"names": []},
    )
    assert driver.calls == []
    assert [r.status for r in results] == [RunStatus.SUCCESS]
    assert ctx.step_outputs["loop"] == {"iterations": 0}


@pytest.mark.parametrize("items", ["abc", 3, {"a": 1}, None])
def test_for_each_rejects_non_list_items(items: Any) -> None:
    with pytest.raises(StepFailed, match="items"):
        _run(
            {
                "id": "loop",
                "action": "for_each",
                "items": "{{ inputs.it }}",
                "steps": [{"action": "emit"}],
            },
            inputs={"it": items},
        )


def test_for_each_requires_items() -> None:
    with pytest.raises(StepFailed, match="items"):
        _run({"id": "loop", "action": "for_each", "steps": [{"action": "emit"}]})


@pytest.mark.parametrize("var", ["steps", "inputs", "not an identifier"])
def test_for_each_rejects_reserved_or_invalid_loop_variables(var: str) -> None:
    with pytest.raises(StepFailed):
        _run(
            {
                "id": "loop",
                "action": "for_each",
                "items": "{{ inputs.names }}",
                "as": var,
                "steps": [{"action": "emit"}],
            },
            inputs={"names": ["a"]},
        )


def test_for_each_iterations_overwrite_flat_output_keys() -> None:
    _, _, _, ctx = _run(
        {
            "id": "loop",
            "action": "for_each",
            "items": "{{ inputs.names }}",
            "as": "n",
            "steps": [{"id": "keep", "action": "set", "value": "{{ n }}"}],
        },
        inputs={"names": ["a", "b"]},
    )
    # Flat namespace: the last iteration wins after the loop.
    assert ctx.step_outputs["keep"] == {"value": "b"}


# ── Nesting, errors, structure ────────────────────────────────────────────────


def test_nested_flow_actions_compose() -> None:
    _, _, driver, ctx = _run(
        {
            "id": "outer",
            "action": "repeat",
            "times": 2,
            "steps": [
                {
                    "id": "gate",
                    "action": "if",
                    "condition": "true",
                    "then": [
                        {
                            "id": "inner",
                            "action": "for_each",
                            "items": "{{ inputs.names }}",
                            "as": "n",
                            "steps": [{"id": "say", "action": "emit", "value": "{{ n }}"}],
                        }
                    ],
                }
            ],
        },
        inputs={"names": ["a", "b"]},
    )
    assert [params["value"] for _, params in driver.calls] == ["a", "b", "a", "b"]
    assert ctx.step_outputs["outer"] == {"iterations": 2}


def test_anonymous_nested_steps_do_not_collide_with_root_keys() -> None:
    _, _, _, ctx = _run(
        {"action": "set", "value": "root"},
        {
            "id": "gate",
            "action": "if",
            "condition": "true",
            "then": [{"action": "set", "value": "nested"}],
        },
    )
    assert ctx.step_outputs["_step_0"] == {"value": "root"}
    assert ctx.step_outputs["gate._step_0"] == {"value": "nested"}


def test_error_in_a_branch_reports_once_and_aborts() -> None:
    ctx = _ctx()
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    driver = FakeDriver()
    results: list[StepResult] = []
    with pytest.raises(StepFailed, match="boom"):
        run_steps(
            _steps(
                {
                    "id": "loop",
                    "action": "repeat",
                    "times": 2,
                    "steps": [{"id": "bad", "action": "set", "boom": True}],
                },
                {"id": "after", "action": "emit"},
            ),
            ctx,
            bus,
            driver,
            results,
        )
    # Exactly one ERROR event, for the innermost failing step.
    errors = _events(sink, EventType.ERROR)
    assert len(errors) == 1
    assert errors[0].step_id == "loop[0].bad"
    # The child and its container are both recorded as failed; nothing runs after.
    assert [(r.step_id, r.status) for r in results] == [
        ("loop[0].bad", RunStatus.FAILED),
        ("loop", RunStatus.FAILED),
    ]
    assert driver.calls == []


def test_a_named_failure_carries_its_code_into_the_result() -> None:
    # `on_timeout: "fail:LOGIN_FAILED"` exists so a caller can tell "wrong password" from "the page
    # changed". The code was set on the exception and read by nobody, so it never left the engine.
    class NamingDriver(FakeDriver):
        def run_step(
            self, step: StepModel, ctx: RunContext, bus: EventBus, renderer: Callable[[Any], Any]
        ) -> dict[str, Any]:
            raise StepTimeoutError("wait_for timed out", code="LOGIN_FAILED")

    ctx = _ctx()
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    results: list[StepResult] = []
    with pytest.raises(StepFailed, match="LOGIN_FAILED"):
        run_steps(_steps({"id": "wait", "action": "wait_for"}), ctx, bus, NamingDriver(), results)

    assert results[0].error == "LOGIN_FAILED: wait_for timed out"
    assert _events(sink, EventType.ERROR)[0].message == "LOGIN_FAILED: wait_for timed out"


def test_an_unnamed_failure_keeps_its_message_untouched() -> None:
    ctx = _ctx()
    bus = EventBus()
    bus.register(ListSink())
    results: list[StepResult] = []
    with pytest.raises(StepFailed):
        run_steps(
            _steps({"id": "bad", "action": "set", "boom": True}), ctx, bus, FakeDriver(), results
        )
    assert results[0].error == "boom"


def test_flow_actions_never_reach_the_driver() -> None:
    class ExplodingDriver(FakeDriver):
        def run_step(
            self, step: StepModel, ctx: RunContext, bus: EventBus, renderer: Callable[[Any], Any]
        ) -> dict[str, Any]:
            raise AssertionError(f"driver saw {step.action!r}")

    for cap in FLOW_ACTIONS:
        ctx = _ctx()
        bus = EventBus()
        bus.register(ListSink())
        results: list[StepResult] = []
        step = {
            "if": {"action": "if", "condition": "false"},
            "repeat": {"action": "repeat", "times": 0, "steps": []},
            "for_each": {"action": "for_each", "items": "{{ [] }}", "steps": []},
            "optional": {"action": "optional", "steps": []},
        }[cap.value]
        run_steps(_steps(step), ctx, bus, ExplodingDriver(), results)
        assert results[-1].status == RunStatus.SUCCESS


def test_linear_blueprints_keep_their_historical_shape() -> None:
    results, sink, driver, ctx = _run(
        {"id": "a", "action": "set", "value": "1"},
        {"action": "emit"},
    )
    assert [(r.step_id, r.status) for r in results] == [
        ("a", RunStatus.SUCCESS),
        (None, RunStatus.SUCCESS),
    ]
    assert set(ctx.step_outputs) == {"a", "_step_1"}
    started = _events(sink, EventType.STEP_STARTED)
    assert [e.step_id for e in started] == ["a", None]


# ── Per-step act routing (Jalon 2-D) ──────────────────────────────────────────


class RoutingResolver:
    """Serves one FakeDriver per act and records every resolution."""

    def __init__(self, *acts: str) -> None:
        self.drivers = {act: FakeDriver() for act in acts}
        self.asked: list[str] = []

    def resolve_driver(self, act: str, ctx: RunContext) -> FakeDriver:
        self.asked.append(act)
        return self.drivers[act]


def _run_routed(
    resolver: RoutingResolver, *raw: dict[str, Any], act: str = "continuum"
) -> tuple[list[StepResult], RunContext]:
    bp = Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t", "act": act, "steps": [{"action": "set"}]}
    )
    ctx = RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})
    bus = EventBus()
    bus.register(ListSink())
    results: list[StepResult] = []
    run_steps(_steps(*raw), ctx, bus, resolver, results)
    return results, ctx


def test_steps_route_to_their_effective_act() -> None:
    resolver = RoutingResolver("continuum", "oracle")
    _run_routed(
        resolver,
        {"action": "navigate", "url": "x"},
        {"action": "read", "act": "oracle", "vision": "y"},
        {"action": "click", "selector": "#a"},
    )
    assert resolver.asked == ["continuum", "oracle", "continuum"]
    assert resolver.drivers["continuum"].calls == [
        ("navigate", {"url": "x"}),
        ("click", {"selector": "#a"}),
    ]
    assert [a for a, _ in resolver.drivers["oracle"].calls] == ["read"]


def test_flow_children_inherit_the_enclosing_step_act() -> None:
    resolver = RoutingResolver("continuum", "oracle")
    _run_routed(
        resolver,
        {
            "action": "if",
            "act": "oracle",
            "condition": "true",
            "then": [
                {"action": "read", "vision": "y"},
                {"action": "click", "act": "continuum", "selector": "#a"},
            ],
        },
    )
    assert resolver.asked == ["oracle", "continuum"]


# ── Self-healing through the executor (Jalon 2-D) ────────────────────────────


def _healing_run(
    *raw: dict[str, Any], fallback: list[str] | None = None
) -> tuple[list[StepResult], ListSink, RoutingResolver, RunContext]:
    data: dict[str, Any] = {
        "aetherius": "1.0",
        "name": "t",
        "act": "continuum",
        "steps": [{"action": "set"}],
    }
    if fallback is not None:
        data["options"] = {"fallback": fallback}
    bp = Blueprint.model_validate(data)
    ctx = RunContext(run_id="r", blueprint=bp, inputs={}, secrets={})
    sink = ListSink()
    bus = EventBus()
    bus.register(sink)
    resolver = RoutingResolver("continuum", "oracle")
    results: list[StepResult] = []
    run_steps(_steps(*raw), ctx, bus, resolver, results)
    return results, sink, resolver, ctx


def test_a_failed_step_healed_by_oracle_is_recorded_success() -> None:
    results, sink, resolver, ctx = _healing_run(
        {"id": "n", "action": "click", "selector": "#gone", "boom": True, "describe": "the link"},
        {"id": "after", "action": "emit"},
        fallback=["oracle"],
    )
    assert [(r.step_id, r.status) for r in results] == [
        ("n", RunStatus.SUCCESS),
        ("after", RunStatus.SUCCESS),
    ]
    assert results[0].healed_by == "oracle"
    assert results[1].healed_by is None
    # The replay went to the oracle driver as a vision step; the outputs are the replay's.
    action, params = resolver.drivers["oracle"].calls[0]
    assert action == "click"
    assert params["target"] == {"vision": "the link"}
    assert ctx.step_outputs["n"] == {"value": None}
    # No ERROR event: the step never failed from the run's point of view.
    assert _events(sink, EventType.ERROR) == []


def test_without_fallback_the_failure_propagates_as_before() -> None:
    with pytest.raises(StepFailed, match="boom"):
        _healing_run(
            {"id": "n", "action": "click", "selector": "#gone", "boom": True, "describe": "d"},
        )


def test_healing_the_next_step_goes_back_to_the_declared_act() -> None:
    # Escalation is per-step, never sticky: the step after a healed one runs on its own act.
    results, _, resolver, _ = _healing_run(
        {"id": "n", "action": "click", "selector": "#gone", "boom": True, "describe": "the link"},
        {"id": "after", "action": "click", "selector": "#ok"},
        fallback=["oracle"],
    )
    assert results[1].healed_by is None
    assert resolver.drivers["continuum"].calls[-1] == ("click", {"selector": "#ok"})


# ── Through RunEngine ─────────────────────────────────────────────────────────


def _engine_run(monkeypatch: pytest.MonkeyPatch, steps: list[dict[str, Any]]) -> Any:
    from aetherius.core.runtime import drivers as drivers_mod
    from aetherius.core.runtime import engine as engine_mod

    driver = FakeDriver()
    monkeypatch.setattr(drivers_mod, "_make_driver", lambda act: driver)
    bp = Blueprint.model_validate(
        {"aetherius": "1.0", "name": "t.flow", "act": "vector", "steps": steps}
    )
    return engine_mod.RunEngine().run(bp)


def test_run_with_skipped_steps_is_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _engine_run(
        monkeypatch,
        [
            {"id": "a", "action": "set", "value": "x"},
            {"id": "b", "action": "emit", "when": "false"},
        ],
    )
    assert result.status == RunStatus.SUCCESS
    assert [r.status for r in result.step_results] == [RunStatus.SUCCESS, RunStatus.SKIPPED]


def test_run_with_a_failing_branch_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _engine_run(
        monkeypatch,
        [
            {
                "id": "gate",
                "action": "if",
                "condition": "true",
                "then": [{"id": "bad", "action": "set", "boom": True}],
            }
        ],
    )
    assert result.status == RunStatus.FAILED
    assert result.error == "boom"
    assert [(r.step_id, r.status) for r in result.step_results] == [
        ("gate.bad", RunStatus.FAILED),
        ("gate", RunStatus.FAILED),
    ]


def test_step_failed_is_an_aetherius_error() -> None:
    # The engine's error handling relies on this relationship.
    assert issubclass(StepFailed, AetheriusError)
    assert issubclass(TemplateError, AetheriusError)
