"""Tests for the ``optional`` block (Jalon 3-J): a reading whose absence is an acceptable result.

The block is the only thing in the engine that turns a step failure into something other than a
dead run, so what is pinned here is the whole contract: the failing step keeps its FAILED and its
event, the rest of the block is SKIPPED, the block itself is PARTIAL, and the run carries on — to
finish PARTIAL, with its outputs rendered.

Driven through RunEngine rather than the executor alone: the status of a *run* and the rendering of
its outputs are engine-level decisions, and they are half of what this milestone changes.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import TemplateError
from aetherius.core.events.models import EventType, RunEvent
from aetherius.core.runtime.result import RunStatus

from .test_steps import FakeDriver, ListSink

pytestmark = pytest.mark.unit

# A leaf the fake driver always fails on (it raises on ``boom``).
BOOM: dict[str, Any] = {"id": "bad", "action": "set", "boom": True}


def _run(
    monkeypatch: pytest.MonkeyPatch,
    steps: list[dict[str, Any]],
    outputs: dict[str, Any] | None = None,
) -> tuple[Any, ListSink]:
    from aetherius.core.runtime import drivers as drivers_mod
    from aetherius.core.runtime import engine as engine_mod

    monkeypatch.setattr(drivers_mod, "_make_driver", lambda act: FakeDriver())
    sink = ListSink()
    document: dict[str, Any] = {
        "aetherius": "1.0",
        "name": "t.optional",
        "act": "vector",
        "steps": steps,
    }
    if outputs is not None:
        document["outputs"] = outputs
    result = engine_mod.RunEngine().run(Blueprint.model_validate(document), sinks=[sink])
    return result, sink


def _statuses(result: Any) -> list[tuple[str | None, RunStatus]]:
    return [(r.step_id, r.status) for r in result.step_results]


def _events(sink: ListSink, type_: EventType) -> list[RunEvent]:
    return [e for e in sink.events if e.type == type_]


# ── The nominal shape ─────────────────────────────────────────────────────────


def test_a_block_that_fully_succeeds_tints_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = _run(
        monkeypatch,
        [{"id": "blk", "action": "optional", "steps": [{"id": "a", "action": "set", "value": 1}]}],
    )
    assert result.status == RunStatus.SUCCESS
    assert _statuses(result) == [("blk.a", RunStatus.SUCCESS), ("blk", RunStatus.SUCCESS)]


def test_a_block_that_gives_way_skips_the_rest_and_the_run_carries_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, sink = _run(
        monkeypatch,
        [
            {"id": "before", "action": "set", "value": "read"},
            {
                "id": "blk",
                "action": "optional",
                "steps": [
                    {"id": "one", "action": "set", "value": 1},
                    BOOM,
                    {"id": "three", "action": "set", "value": 3},
                    {"id": "four", "action": "set", "value": 4},
                ],
            },
            {"id": "after", "action": "set", "value": "still here"},
        ],
    )

    assert result.status == RunStatus.PARTIAL
    assert _statuses(result) == [
        ("before", RunStatus.SUCCESS),
        ("blk.one", RunStatus.SUCCESS),
        ("blk.bad", RunStatus.FAILED),
        ("blk.three", RunStatus.SKIPPED),
        ("blk.four", RunStatus.SKIPPED),
        ("blk", RunStatus.PARTIAL),
        ("after", RunStatus.SUCCESS),
    ]

    # The failure stays visible: one error event, on the step that carried it, and its message is
    # kept on the step result. Swallowing either would defeat the point of the block.
    errors = _events(sink, EventType.ERROR)
    assert [e.step_id for e in errors] == ["blk.bad"]
    assert result.step_results[2].error == "boom"

    # A partial run is not a failure: the run-level error stays empty and `done` is not an error.
    assert result.error is None
    done = _events(sink, EventType.DONE)[0]
    assert done.data["status"] == "partial" and done.level == "info"


def test_a_hard_failure_after_a_block_still_kills_the_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(
        monkeypatch,
        [
            {"id": "blk", "action": "optional", "steps": [BOOM]},
            {"id": "hard", "action": "set", "boom": True},
        ],
    )
    assert result.status == RunStatus.FAILED
    assert result.error == "boom"


def test_skipped_steps_of_a_block_say_why(monkeypatch: pytest.MonkeyPatch) -> None:
    _, sink = _run(
        monkeypatch,
        [{"action": "optional", "steps": [BOOM, {"id": "next", "action": "set"}]}],
    )
    skipped = _events(sink, EventType.STEP_SKIPPED)
    assert [e.step_id for e in skipped] == ["_step_0.next"]
    # Worded identically in the embedded engine, and distinct from a `when` guard: the two reasons
    # to skip a step must not read the same.
    assert skipped[0].message == "skipped: an earlier step of the optional block failed"


def test_an_anonymous_skipped_step_keeps_its_position(monkeypatch: pytest.MonkeyPatch) -> None:
    # The skipped steps are marked from a slice of the block, so their index must be offset back:
    # an anonymous step skipped in third position is `_step_2`, never `_step_0`.
    result, _ = _run(
        monkeypatch,
        [
            {
                "id": "blk",
                "action": "optional",
                "steps": [{"action": "set"}, BOOM, {"action": "set"}, {"action": "set"}],
            }
        ],
    )
    assert _statuses(result) == [
        ("blk._step_0", RunStatus.SUCCESS),
        ("blk.bad", RunStatus.FAILED),
        ("blk._step_2", RunStatus.SKIPPED),
        ("blk._step_3", RunStatus.SKIPPED),
        ("blk", RunStatus.PARTIAL),
    ]


# ── Outputs: the half of the milestone that lives in the engine ───────────────


def test_a_partial_run_still_renders_its_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = _run(
        monkeypatch,
        [
            {"id": "identity", "action": "set", "value": "read before the block"},
            {"action": "optional", "steps": [BOOM, {"id": "bonus", "action": "set", "value": "x"}]},
        ],
        outputs={
            "identity": "{{ steps.identity.value }}",
            "bonus": "{{ steps.bonus.value | default(none) }}",
        },
    )
    assert result.status == RunStatus.PARTIAL
    # Everything that does not depend on the block survives; what does falls back.
    assert result.outputs == {"identity": "read before the block", "bonus": None}


def test_steps_of_a_block_that_produced_nothing_are_seeded_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Both engines reject the undefined at the point of use, so `steps.bonus.x | default(...)`
    # would raise if `steps.bonus` were missing entirely. Seeding `{}` is what makes the documented
    # writing rule true — and `is defined` holding is the accepted, documented consequence.
    result, _ = _run(
        monkeypatch,
        [{"action": "optional", "steps": [BOOM, {"id": "bonus", "action": "set"}]}],
        outputs={
            "seeded": "{{ steps.bonus is defined }}",
            "failing": "{{ steps.bad is defined }}",
        },
    )
    assert result.outputs == {"seeded": True, "failing": True}


def test_seeding_reaches_a_nested_block(monkeypatch: pytest.MonkeyPatch) -> None:
    # The rule has to hold at any depth inside the block, or it breaks the moment a loop is put in
    # one — which is exactly the shape of the portal walk that opened this milestone.
    result, _ = _run(
        monkeypatch,
        [
            {
                "action": "optional",
                "steps": [
                    {
                        "action": "for_each",
                        "items": "{{ [1, 2] }}",
                        "steps": [{"id": "coord", "action": "set", "boom": True}],
                    }
                ],
            }
        ],
        outputs={"city": "{{ steps.coord.city | default(none) }}"},
    )
    assert result.status == RunStatus.PARTIAL
    assert result.outputs == {"city": None}


def test_seeding_never_overwrites_what_a_step_published(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A loop whose first iteration succeeded keeps its reading when the second gives way.
    result, _ = _run(
        monkeypatch,
        [
            {
                "action": "optional",
                "steps": [
                    {"id": "kept", "action": "set", "value": "first pass"},
                    BOOM,
                ],
            }
        ],
        outputs={"kept": "{{ steps.kept.value | default(none) }}"},
    )
    assert result.outputs == {"kept": "first pass"}


def test_an_output_without_a_default_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    # The writing rule is a rule, not magic: a Blueprint that forgets it must break, and break at
    # the outputs rather than silently render a hole.
    with pytest.raises(TemplateError):
        _run(
            monkeypatch,
            [{"action": "optional", "steps": [BOOM, {"id": "bonus", "action": "set"}]}],
            outputs={"bonus": "{{ steps.bonus.value }}"},
        )


# ── Nesting and guards ────────────────────────────────────────────────────────


def test_tolerance_does_not_climb_out_of_the_inner_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _ = _run(
        monkeypatch,
        [
            {
                "id": "outer",
                "action": "optional",
                "steps": [
                    {"id": "inner", "action": "optional", "steps": [BOOM]},
                    {"id": "after", "action": "set", "value": "reached"},
                ],
            }
        ],
    )
    # Only the inner block gives way; the outer one runs to the end and stays SUCCESS. The *run*,
    # on the other hand, is PARTIAL: that verdict is read from the results, never propagated.
    assert _statuses(result) == [
        ("outer.inner.bad", RunStatus.FAILED),
        ("outer.inner", RunStatus.PARTIAL),
        ("outer.after", RunStatus.SUCCESS),
        ("outer", RunStatus.SUCCESS),
    ]
    assert result.status == RunStatus.PARTIAL


def test_a_container_inside_a_block_is_still_marked_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The intermediate flow step keeps FAILED under a tolerated block. This is why the run status
    # scans for PARTIAL and never for FAILED: a failed step result is no longer a run verdict.
    result, _ = _run(
        monkeypatch,
        [
            {
                "action": "optional",
                "steps": [{"id": "loop", "action": "repeat", "times": 1, "steps": [BOOM]}],
            }
        ],
    )
    assert result.status == RunStatus.PARTIAL
    assert [s for _, s in _statuses(result)] == [
        RunStatus.FAILED,
        RunStatus.FAILED,
        RunStatus.PARTIAL,
    ]


def test_a_when_guard_on_the_block_decides_first(monkeypatch: pytest.MonkeyPatch) -> None:
    result, _ = _run(
        monkeypatch,
        [{"id": "blk", "action": "optional", "when": "false", "steps": [BOOM]}],
        outputs={"seeded": "{{ steps.bad is defined }}"},
    )
    # The whole block is skipped, the run is an ordinary success, and nothing is seeded: the block
    # was never attempted, so it has nothing to report.
    assert result.status == RunStatus.SUCCESS
    assert _statuses(result) == [("blk", RunStatus.SKIPPED)]
    assert result.outputs == {"seeded": False}
