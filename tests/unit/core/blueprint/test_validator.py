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
