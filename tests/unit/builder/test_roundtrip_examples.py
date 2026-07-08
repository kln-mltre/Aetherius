"""Losslessness guard for edit mode: every shipped example survives a Studio open/save round-trip.

Opening an existing Blueprint in the Studio parses it into a ``BlueprintDraft`` and saving re-emits
it. That must not drop or alter anything — the key use case is refining a recorder-produced file. We
assert the strongest property that holds: ``from_data(raw).to_data()`` reproduces the file exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.builder.factory import BlueprintDraft

pytestmark = pytest.mark.unit

_EXAMPLES = sorted((Path(__file__).resolve().parents[3] / "examples").rglob("*.blueprint.json"))


def test_examples_are_present() -> None:
    assert _EXAMPLES


@pytest.mark.parametrize("example", _EXAMPLES, ids=lambda p: p.name)
def test_example_round_trips_through_a_draft(example: Path) -> None:
    raw = json.loads(example.read_text(encoding="utf-8"))
    assert BlueprintDraft.from_data(raw).to_data() == raw
