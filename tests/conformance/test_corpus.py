"""The Python engine replays the shared conformance corpus.

Its TypeScript twin is sdks/engine/test/conformance.test.js; `make conformance` runs both. This
module lives under tests/ so the corpus is also replayed by `make test` — a divergence found on
every run beats one found only when someone remembers the dedicated target.

A case may declare ``"requires": "browser"``. On this engine that means Playwright and a real
Chromium: the case skips cleanly without the ``[browser]`` extra, exactly like every other browser
test, and the CI job that runs `make conformance` installs it so the comparison actually happens.
"""

from __future__ import annotations

import importlib.util

import pytest

from .harness import Case, describe_failure, load_cases, mismatches, run_case

pytestmark = pytest.mark.contracts

_CASES = load_cases()

_HAS_PLAYWRIGHT = importlib.util.find_spec("playwright") is not None


def test_corpus_is_not_empty() -> None:
    # A runner that silently finds nothing is the one failure mode a green suite cannot show.
    assert _CASES, "no conformance case found under conformance/cases/"


def test_the_corpus_exercises_a_browser() -> None:
    # A `requires: browser` case that vanished would take the whole Act II comparison with it, and
    # a suite that skips everything looks exactly like a suite that passes everything.
    assert any(case.requires == "browser" for case in _CASES), (
        "no conformance case exercises Act II; the two engines are no longer compared on a browser"
    )


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_case_matches_expectation(case: Case) -> None:
    if case.requires == "browser" and not _HAS_PLAYWRIGHT:
        pytest.skip("needs the [browser] extra (Playwright + Chromium)")
    actual = run_case(case)
    problems = mismatches(case.expectation, actual)
    assert not problems, describe_failure(case, actual, problems)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_case_declares_both_engines(case: Case) -> None:
    # A case expecting only one engine would quietly stop guarding the other.
    assert set(case.data["expect"]) == {"python", "embedded"}, (
        f"{case.path.name}: every case must state what both engines do with it"
    )
