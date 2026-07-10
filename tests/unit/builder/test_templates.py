"""Tests for builder/templates.py — every starter template must be valid and runnable-shaped."""

from __future__ import annotations

from pathlib import Path

import pytest

from aetherius.builder.factory import build_blueprint
from aetherius.builder.templates import list_templates, template_draft
from aetherius.builder.validation import validate_draft
from aetherius.core.blueprint.loader import load_blueprint
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.core.errors import BuilderError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("info", list_templates(), ids=lambda i: i.key)
def test_template_builds_and_validates(info) -> None:
    draft = template_draft(info.key)
    assert validate_draft(draft) == [], f"{info.key} has issues"
    blueprint = build_blueprint(draft)
    assert blueprint.act == info.act


def test_template_draft_returns_independent_copies() -> None:
    first = template_draft("vector.api-fetch")
    first.name = "mutated"
    assert template_draft("vector.api-fetch").name != "mutated"


def test_list_templates_filters_by_act() -> None:
    assert all(i.act == "continuum" for i in list_templates("continuum"))
    assert list_templates("vector")


def test_unknown_template_raises() -> None:
    with pytest.raises(BuilderError):
        template_draft("nope")


def test_shipped_studio_example_matches_a_template_and_validates() -> None:
    example = Path(__file__).resolve().parents[3] / (
        "examples/vector/jsonplaceholder-posts-studio.blueprint.json"
    )
    blueprint = load_blueprint(example)
    validate_for_act(blueprint)
    assert blueprint.act == "vector"
