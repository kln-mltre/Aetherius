"""Tests for core/blueprint/models.py"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aetherius.core.blueprint.models import Blueprint, InputSpec, Options, RetriesOptions, StepModel

pytestmark = pytest.mark.unit


def _minimal_blueprint(**overrides: object) -> dict:
    base = {
        "aetherius": "1.0",
        "name": "test.blueprint",
        "act": "vector",
        "steps": [{"action": "http.request", "url": "https://example.com"}],
    }
    base.update(overrides)
    return base


def test_minimal_blueprint_parses() -> None:
    bp = Blueprint.model_validate(_minimal_blueprint())
    assert bp.name == "test.blueprint"
    assert bp.act == "vector"
    assert len(bp.steps) == 1


def test_blueprint_requires_steps_or_goal() -> None:
    data = {
        "aetherius": "1.0",
        "name": "test",
        "act": "vector",
    }
    with pytest.raises(ValidationError, match="steps.*goal|goal.*steps"):
        Blueprint.model_validate(data)


def test_blueprint_accepts_goal_without_steps() -> None:
    data = {
        "aetherius": "1.0",
        "name": "test",
        "act": "phantom",
        "goal": "Find the best deal.",
    }
    bp = Blueprint.model_validate(data)
    assert bp.goal == "Find the best deal."
    assert bp.steps == []


def test_input_spec_defaults() -> None:
    spec = InputSpec(type="string")
    assert spec.required is False
    assert spec.default is None


def test_retries_options_defaults() -> None:
    opts = RetriesOptions()
    assert opts.max == 0
    assert opts.backoff == "none"


def test_options_defaults() -> None:
    opts = Options()
    assert opts.debug is False
    assert opts.timeout_ms is None


def test_step_model_extra_fields() -> None:
    step = StepModel(action="http.request", url="https://example.com", method="GET")
    assert step.extra_fields["url"] == "https://example.com"
    assert step.extra_fields["method"] == "GET"


def test_step_model_when_is_typed_not_extra() -> None:
    step = StepModel.model_validate({"action": "emit", "when": "{{ steps.a.ok }}"})
    assert step.when == "{{ steps.a.ok }}"
    assert "when" not in step.extra_fields


def test_step_model_when_rejects_a_json_boolean() -> None:
    with pytest.raises(ValidationError):
        StepModel.model_validate({"action": "emit", "when": True})


def test_blueprint_with_inputs_and_vars() -> None:
    data = _minimal_blueprint(
        inputs={"group": {"type": "string", "required": True}},
        vars={"domain": "https://example.com"},
    )
    bp = Blueprint.model_validate(data)
    assert bp.inputs["group"].required is True
    assert bp.vars["domain"] == "https://example.com"


def test_blueprint_rejects_unknown_act() -> None:
    with pytest.raises(ValidationError):
        Blueprint.model_validate(_minimal_blueprint(act="unknown"))
