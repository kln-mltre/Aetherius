"""Replay the shared conformance corpus on the Python engine.

The corpus (``conformance/``) is language-agnostic: the same cases are replayed by
``sdks/engine/test/conformance.test.js``. This module holds the Python half — reading a case,
producing the outcome, and comparing it with the expectation — kept separate from the test module
so the comparison itself can be tested (a harness that reports every case as passing would be a
silent hole).

See conformance/README.md for the case format.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aetherius.core.blueprint.loader import load_blueprint, validate_blueprint_data
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.core.errors import AetheriusError

ENGINE = "python"

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "conformance" / "cases"

ACCEPTED = "accepted"
REJECTED = "rejected"


@dataclass(frozen=True)
class Case:
    """One corpus case: a Blueprint, and what each engine is expected to make of it."""

    name: str
    path: Path
    data: dict[str, Any]

    @property
    def expectation(self) -> dict[str, Any]:
        expected = self.data["expect"].get(ENGINE)
        if expected is None:
            raise AssertionError(f"{self.path.name}: no expectation for engine {ENGINE!r}")
        return dict(expected)


@dataclass(frozen=True)
class Outcome:
    """What an engine actually did with the case."""

    outcome: str
    error: str | None = None
    message: str = ""


def load_cases(corpus_dir: Path = CORPUS_DIR) -> list[Case]:
    """Every case in the corpus, sorted by path so both engines enumerate in the same order."""
    cases: list[Case] = []
    for path in sorted(corpus_dir.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cases.append(Case(name=data["name"], path=path, data=data))
    return cases


def run_case(case: Case) -> Outcome:
    """Load and validate the case's Blueprint, reporting what happened rather than raising."""
    try:
        blueprint = _load(case)
        validate_for_act(blueprint)
    except AetheriusError as exc:
        return Outcome(outcome=REJECTED, error=type(exc).__name__, message=str(exc))
    return Outcome(outcome=ACCEPTED)


def _load(case: Case) -> Any:
    """Materialise the case's Blueprint through the production loading path."""
    if "blueprint_path" in case.data:
        return load_blueprint(REPO_ROOT / case.data["blueprint_path"])
    if "blueprint_text" in case.data:
        # Raw text exists to exercise the parsing stage, which only the file loader owns; a
        # throwaway file is the honest way to reach it instead of reimplementing it here.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{case.name}.blueprint.json"
            path.write_text(case.data["blueprint_text"], encoding="utf-8")
            return load_blueprint(path)
    return validate_blueprint_data(case.data["blueprint"], source=case.path.name)


def mismatches(expected: dict[str, Any], actual: Outcome) -> list[str]:
    """Every way *actual* fails to meet *expected*. Empty means the case passes."""
    problems: list[str] = []
    if actual.outcome != expected["outcome"]:
        problems.append(f"expected the Blueprint to be {expected['outcome']}, got {actual.outcome}")
        # The remaining expectations describe a rejection; reporting them too would be noise.
        return problems

    wanted_error = expected.get("error")
    if wanted_error is not None and actual.error != wanted_error:
        problems.append(f"expected error {wanted_error}, got {actual.error}")

    for fragment in expected.get("message_contains", []):
        if fragment not in actual.message:
            problems.append(f"message does not contain {fragment!r}")

    return problems


def describe_failure(case: Case, actual: Outcome, problems: list[str]) -> str:
    """A failure message that says what the corpus wanted and what the engine did."""
    return (
        f"{case.path.name} ({ENGINE}): "
        + "; ".join(problems)
        + f"\n  actual: outcome={actual.outcome} error={actual.error} message={actual.message!r}"
    )
