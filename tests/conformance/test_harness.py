"""The harness itself must be able to fail.

A conformance runner that reports every case as passing is worse than no runner: it turns a green
suite into a false statement about the two engines agreeing. These tests inject deliberate
divergences and check the comparison notices them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .harness import ACCEPTED, ERROR, RENDERED, REJECTED, Case, Outcome, mismatches, run_case

pytestmark = pytest.mark.contracts

_REJECTED = Outcome(
    outcome=REJECTED,
    error="BlueprintValidationError",
    message="Step 'go': action 'click' is not supported by act='vector' (at steps[0]).",
)


def _case(kind: str, **data: object) -> Case:
    payload: dict[str, object] = {"name": kind, "kind": kind, "expect": {}, **data}
    return Case(name=kind, path=Path(f"{kind}.json"), data=payload)


def test_a_matching_outcome_reports_nothing() -> None:
    expected = {
        "outcome": REJECTED,
        "error": "BlueprintValidationError",
        "message_contains": ["'click'", "act='vector'"],
    }
    assert mismatches(expected, _REJECTED) == []


def test_a_divergent_verdict_is_reported() -> None:
    assert mismatches({"outcome": ACCEPTED}, _REJECTED)


def test_a_divergent_error_type_is_reported() -> None:
    problems = mismatches({"outcome": REJECTED, "error": "BlueprintSchemaError"}, _REJECTED)
    assert problems == ["expected error BlueprintSchemaError, got BlueprintValidationError"]


def test_a_missing_message_fragment_is_reported() -> None:
    expected = {"outcome": REJECTED, "message_contains": ["file chooser"]}
    assert mismatches(expected, _REJECTED) == ["message does not contain 'file chooser'"]


def test_a_divergent_rendered_value_is_reported() -> None:
    # The failure mode that matters for the execution kinds: same verdict, different data.
    actual = Outcome(outcome=RENDERED, value=[1, 2])
    assert mismatches({"outcome": RENDERED, "value": [1, 2]}, actual) == []
    assert mismatches({"outcome": RENDERED, "value": [1, 3]}, actual)


def test_a_value_expectation_is_order_insensitive_on_keys_only() -> None:
    actual = Outcome(outcome=RENDERED, value={"b": 1, "a": 2})
    assert mismatches({"outcome": RENDERED, "value": {"a": 2, "b": 1}}, actual) == []
    assert mismatches(
        {"outcome": RENDERED, "value": [1, 2]}, Outcome(outcome=RENDERED, value=[2, 1])
    )


def test_an_execution_case_missing_its_value_is_reported() -> None:
    assert mismatches({"outcome": RENDERED, "value": 1}, Outcome(outcome=RENDERED)) == [
        "expected a value, the case produced none"
    ]


def test_each_execution_kind_runs_through_the_production_path() -> None:
    rendered = run_case(_case("expression", context={"x": [1, 2]}, value="{{ x }}"))
    assert rendered == Outcome(outcome=RENDERED, value=[1, 2])

    extracted = run_case(
        _case("extraction", body='{"a": 1}', spec={"a": {"from": "json", "path": "$.a"}})
    )
    assert extracted.value == {"a": [1]}

    truthy = run_case(_case("truthy", values=["True", "0"]))
    assert truthy.value == [True, False]


def test_a_run_case_plays_the_blueprint_and_summarises_the_stream() -> None:
    case = _case(
        "run",
        server={"GET /ping": {"json": {"pong": True}}},
        blueprint={
            "aetherius": "1.0",
            "name": "harness.run",
            "act": "vector",
            "inputs": {"base_url": {"type": "string", "required": True}},
            "steps": [
                {
                    "id": "call",
                    "action": "http.request",
                    "url": "{{ inputs.base_url }}/ping",
                    "expect": {"status": 200},
                    "extract": {"pong": {"from": "json", "path": "$.pong"}},
                }
            ],
            "outputs": {"pong": "{{ steps.call.pong | first }}"},
        },
    )
    outcome = run_case(case)

    assert outcome.outcome == RENDERED
    assert outcome.value["status"] == "success"
    assert outcome.value["outputs"] == {"pong": True}
    assert outcome.value["steps"] == [
        {"step_id": "call", "action": "http.request", "status": "success"}
    ]
    # Run ids and durations are deliberately absent: they differ by nature, and a case that
    # compared them would fail for reasons unrelated to the two engines agreeing.
    assert outcome.value["events"][0] == {"type": "progress", "step_id": None}
    assert outcome.value["events"][-1] == {"type": "done", "step_id": None}


def test_a_run_case_reports_a_failed_run_as_a_result_with_its_message() -> None:
    case = _case(
        "run",
        server={"GET /down": {"status": 500, "body": "boom"}},
        blueprint={
            "aetherius": "1.0",
            "name": "harness.run.failed",
            "act": "vector",
            "inputs": {"base_url": {"type": "string", "required": True}},
            "steps": [
                {
                    "id": "call",
                    "action": "http.request",
                    "url": "{{ inputs.base_url }}/down",
                    "expect": {"status": 200},
                }
            ],
        },
    )
    outcome = run_case(case)

    # A failed run is an answer, not an exception: the outcome stays `rendered` so the corpus can
    # pin *how* it failed, and the message is where message_contains looks.
    assert outcome.outcome == RENDERED
    assert outcome.value["status"] == "failed"
    assert "Expected HTTP 200, got 500" in outcome.message


def test_a_divergent_event_sequence_is_reported() -> None:
    actual = Outcome(outcome=RENDERED, value={"events": [{"type": "done", "step_id": None}]})
    expected = {
        "outcome": RENDERED,
        "value": {"events": [{"type": "error", "step_id": "x"}, {"type": "done", "step_id": None}]},
    }
    assert mismatches(expected, actual)


def test_a_failing_execution_case_reports_the_typed_error() -> None:
    outcome = run_case(_case("expression", context={}, value="{{ missing }}"))
    assert outcome.outcome == ERROR
    assert outcome.error == "TemplateError"


def test_an_unknown_kind_fails_loudly_rather_than_passing() -> None:
    with pytest.raises(AssertionError):
        run_case(_case("telepathy"))


def test_a_case_without_an_expectation_for_this_engine_fails_loudly() -> None:
    case = Case(
        name="orphan",
        path=Path("orphan.json"),
        data={"name": "orphan", "expect": {"embedded": {"outcome": ACCEPTED}}},
    )
    with pytest.raises(AssertionError):
        _ = case.expectation
