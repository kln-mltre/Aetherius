"""Replay the shared conformance corpus on the Python engine.

The corpus (``conformance/``) is language-agnostic: the same cases are replayed by
``sdks/engine/test/conformance.test.js``. This module holds the Python half — reading a case,
producing the outcome, and comparing it with the expectation — kept separate from the test module
so the comparison itself can be tested (a harness that reports every case as passing would be a
silent hole).

A case declares its ``kind``. ``validation`` (the default) answers "is this Blueprint accepted";
the execution kinds added at milestone 3-B answer "and does it produce the same value". Adding a
*case* touches no executor; adding a *kind* touches both, on purpose.

See conformance/README.md for the case format.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aetherius.core.blueprint.loader import load_blueprint, validate_blueprint_data
from aetherius.core.blueprint.template import render_value
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.core.errors import AetheriusError
from aetherius.core.extraction.dispatch import dispatch_extract
from aetherius.core.runtime.flow import is_truthy

ENGINE = "python"

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "conformance" / "cases"

ACCEPTED = "accepted"
REJECTED = "rejected"
RENDERED = "rendered"
ERROR = "error"

_MISSING = object()


@dataclass(frozen=True)
class Case:
    """One corpus case: an input, and what each engine is expected to make of it."""

    name: str
    path: Path
    data: dict[str, Any]

    @property
    def kind(self) -> str:
        return str(self.data.get("kind", "validation"))

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
    value: Any = _MISSING


def load_cases(corpus_dir: Path = CORPUS_DIR) -> list[Case]:
    """Every case in the corpus, sorted by path so both engines enumerate in the same order."""
    cases: list[Case] = []
    for path in sorted(corpus_dir.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cases.append(Case(name=data["name"], path=path, data=data))
    return cases


def run_case(case: Case) -> Outcome:
    """Run the case through the production code path, reporting what happened rather than raising."""
    if case.kind == "validation":
        return _run_validation(case)
    try:
        return Outcome(outcome=RENDERED, value=_execute(case))
    except AetheriusError as exc:
        return Outcome(outcome=ERROR, error=type(exc).__name__, message=str(exc))


def _run_validation(case: Case) -> Outcome:
    try:
        validate_for_act(_load(case))
    except AetheriusError as exc:
        return Outcome(outcome=REJECTED, error=type(exc).__name__, message=str(exc))
    return Outcome(outcome=ACCEPTED)


def _execute(case: Case) -> Any:
    if case.kind == "expression":
        return render_value(case.data["value"], case.data.get("context", {}))
    if case.kind == "extraction":
        body: str = case.data["body"]
        return dispatch_extract(body.encode("utf-8"), case.data["spec"])
    if case.kind == "truthy":
        return [is_truthy(value) for value in case.data["values"]]
    raise AssertionError(f"{case.path.name}: unknown case kind {case.kind!r}")


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


def canonical(value: Any) -> str:
    """A value's comparable form. Both engines serialise the same way, keys sorted."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def mismatches(expected: dict[str, Any], actual: Outcome) -> list[str]:
    """Every way *actual* fails to meet *expected*. Empty means the case passes."""
    problems: list[str] = []
    if actual.outcome != expected["outcome"]:
        # Name what the case is about: a validation case judges a Blueprint, an execution case
        # judges a rendered value.
        subject = "the Blueprint" if expected["outcome"] in (ACCEPTED, REJECTED) else "the case"
        problems.append(f"expected {subject} to be {expected['outcome']}, got {actual.outcome}")
        # The remaining expectations describe the other branch; reporting them too would be noise.
        return problems

    wanted_error = expected.get("error")
    if wanted_error is not None and actual.error != wanted_error:
        problems.append(f"expected error {wanted_error}, got {actual.error}")

    for fragment in expected.get("message_contains", []):
        if fragment not in actual.message:
            problems.append(f"message does not contain {fragment!r}")

    if "value" in expected:
        if actual.value is _MISSING:
            problems.append("expected a value, the case produced none")
        elif canonical(actual.value) != canonical(expected["value"]):
            problems.append(f"expected value {canonical(expected['value'])}")

    return problems


def describe_failure(case: Case, actual: Outcome, problems: list[str]) -> str:
    """A failure message that says what the corpus wanted and what the engine did."""
    detail = f" value={canonical(actual.value)}" if actual.value is not _MISSING else ""
    return (
        f"{case.path.name} ({ENGINE}): "
        + "; ".join(problems)
        + f"\n  actual: outcome={actual.outcome} error={actual.error} "
        + f"message={actual.message!r}{detail}"
    )
