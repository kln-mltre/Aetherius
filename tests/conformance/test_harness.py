"""The harness itself must be able to fail.

A conformance runner that reports every case as passing is worse than no runner: it turns a green
suite into a false statement about the two engines agreeing. These tests inject deliberate
divergences and check the comparison notices them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .harness import ACCEPTED, REJECTED, Case, Outcome, mismatches

pytestmark = pytest.mark.contracts

_REJECTED = Outcome(
    outcome=REJECTED,
    error="BlueprintValidationError",
    message="Step 'go': action 'click' is not supported by act='vector' (at steps[0]).",
)


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


def test_a_case_without_an_expectation_for_this_engine_fails_loudly() -> None:
    case = Case(
        name="orphan",
        path=Path("orphan.json"),
        data={"name": "orphan", "expect": {"embedded": {"outcome": ACCEPTED}}},
    )
    with pytest.raises(AssertionError):
        _ = case.expectation
