"""The Python engine replays the shared conformance corpus.

Its TypeScript twin is sdks/engine/test/conformance.test.js; `make conformance` runs both. This
module lives under tests/ so the corpus is also replayed by `make test` — a divergence found on
every run beats one found only when someone remembers the dedicated target.
"""

from __future__ import annotations

import pytest

from .harness import Case, describe_failure, load_cases, mismatches, run_case

pytestmark = pytest.mark.contracts

_CASES = load_cases()


def test_corpus_is_not_empty() -> None:
    # A runner that silently finds nothing is the one failure mode a green suite cannot show.
    assert _CASES, "no conformance case found under conformance/cases/"


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_case_matches_expectation(case: Case) -> None:
    actual = run_case(case)
    problems = mismatches(case.expectation, actual)
    assert not problems, describe_failure(case, actual, problems)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_case_declares_both_engines(case: Case) -> None:
    # A case expecting only one engine would quietly stop guarding the other.
    assert set(case.data["expect"]) == {"python", "embedded"}, (
        f"{case.path.name}: every case must state what both engines do with it"
    )
