"""Tests for core/blueprint/validator.py"""

from __future__ import annotations

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.blueprint.validator import validate_for_act
from aetherius.core.errors import BlueprintValidationError

pytestmark = pytest.mark.unit


def _make(act: str, actions: list[str]) -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": act,
            "steps": [{"action": a} for a in actions],
        }
    )


def test_vector_allows_http_request() -> None:
    validate_for_act(_make("vector", ["http.request", "set", "assert", "emit", "wait"]))


def test_vector_rejects_navigate() -> None:
    with pytest.raises(BlueprintValidationError, match="navigate"):
        validate_for_act(_make("vector", ["navigate"]))


def test_vector_rejects_click() -> None:
    with pytest.raises(BlueprintValidationError, match="click"):
        validate_for_act(_make("vector", ["click"]))


def test_continuum_allows_navigate() -> None:
    validate_for_act(_make("continuum", ["navigate", "click", "http.request"]))


def test_error_names_the_step_and_act() -> None:
    bp = _make("vector", ["click"])
    with pytest.raises(BlueprintValidationError) as exc_info:
        validate_for_act(bp)
    assert "vector" in str(exc_info.value)
    assert "click" in str(exc_info.value)


def _make_nested(act: str, step: dict) -> Blueprint:
    return Blueprint.model_validate(
        {"aetherius": "1.0", "name": "test", "act": act, "steps": [step]}
    )


def test_vector_allows_flow_actions() -> None:
    validate_for_act(
        _make_nested(
            "vector",
            {
                "action": "if",
                "condition": "{{ true }}",
                "then": [
                    {"action": "repeat", "times": 2, "steps": [{"action": "emit"}]},
                    {"action": "for_each", "items": "{{ [] }}", "steps": [{"action": "set"}]},
                ],
            },
        )
    )


def test_nested_unsupported_action_is_rejected_with_its_path() -> None:
    bp = _make_nested(
        "vector",
        {
            "action": "if",
            "condition": "{{ true }}",
            "then": [
                {"action": "for_each", "items": "{{ [] }}", "steps": [{"action": "navigate"}]}
            ],
        },
    )
    with pytest.raises(BlueprintValidationError, match="navigate") as exc_info:
        validate_for_act(bp)
    assert "steps[0].then[0].steps[0]" in str(exc_info.value)


def test_non_list_flow_branch_is_rejected() -> None:
    bp = _make_nested("vector", {"action": "if", "condition": "x", "then": {"action": "emit"}})
    with pytest.raises(BlueprintValidationError, match="then"):
        validate_for_act(bp)


def test_invalid_nested_step_shape_is_rejected() -> None:
    bp = _make_nested("vector", {"action": "repeat", "times": 1, "steps": [{"id": "x"}]})
    with pytest.raises(BlueprintValidationError, match="steps\\[0\\].steps\\[0\\]"):
        validate_for_act(bp)
