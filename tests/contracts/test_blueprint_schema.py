"""The contracts are the source of truth: the schema is a valid JSON Schema and every shipped
example conforms to it. This keeps the schema and the examples honest as both evolve."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema.validators import validator_for

pytestmark = pytest.mark.contracts

_EXAMPLES = sorted((Path(__file__).resolve().parents[2] / "examples").glob("*.blueprint.json"))


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def test_blueprint_schema_is_valid(contracts_dir: Path) -> None:
    schema = _load(contracts_dir / "blueprint.schema.json")
    validator_for(schema).check_schema(schema)


def test_examples_are_present() -> None:
    assert _EXAMPLES, "no *.blueprint.json example found under examples/"


@pytest.mark.parametrize("example", _EXAMPLES, ids=lambda p: p.name)
def test_example_matches_schema(example: Path, contracts_dir: Path) -> None:
    schema = _load(contracts_dir / "blueprint.schema.json")
    validator = validator_for(schema)(schema)
    errors = sorted(validator.iter_errors(_load(example)), key=lambda err: list(err.path))
    assert not errors, "; ".join(f"{list(err.path)}: {err.message}" for err in errors)
