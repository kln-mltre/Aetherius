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


def test_oracle_allows_read_and_the_continuum_set() -> None:
    validate_for_act(_make("oracle", ["read", "navigate", "click", "wait_for"]))


def test_read_below_oracle_is_rejected_with_a_hint() -> None:
    for act in ("vector", "continuum"):
        with pytest.raises(BlueprintValidationError, match="oracle"):
            validate_for_act(_make(act, ["read"]))


def test_error_names_the_step_and_act() -> None:
    bp = _make("vector", ["click"])
    with pytest.raises(BlueprintValidationError) as exc_info:
        validate_for_act(bp)
    assert "vector" in str(exc_info.value)
    assert "click" in str(exc_info.value)


def _goal_only(act: str) -> Blueprint:
    return Blueprint.model_validate(
        {"aetherius": "1.0", "name": "test", "act": act, "goal": "do a thing"}
    )


def test_goal_only_is_allowed_for_phantom() -> None:
    validate_for_act(_goal_only("phantom"))


def test_goal_only_below_phantom_is_rejected() -> None:
    for act in ("vector", "continuum", "oracle"):
        with pytest.raises(BlueprintValidationError, match="phantom"):
            validate_for_act(_goal_only(act))


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


def test_plugin_actions_are_accepted_on_every_act(plugin_action: str) -> None:
    # Plugin actions are act-agnostic (Jalon E, docs/plugins.md): registered = accepted.
    validate_for_act(_make("vector", [plugin_action]))
    validate_for_act(_make("continuum", [plugin_action]))


def test_plugin_actions_are_accepted_inside_flow_branches(plugin_action: str) -> None:
    validate_for_act(
        _make_nested(
            "vector", {"action": "if", "condition": "x", "then": [{"action": plugin_action}]}
        )
    )


def test_unregistered_actions_stay_rejected() -> None:
    with pytest.raises(BlueprintValidationError, match="does.not.exist"):
        validate_for_act(_make("vector", ["does.not.exist"]))
