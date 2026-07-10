"""Tests for loader.validate_blueprint_data / blueprint_schema — in-memory validation."""

from __future__ import annotations

import pytest

from aetherius.core.blueprint.loader import blueprint_schema, validate_blueprint_data
from aetherius.core.errors import BlueprintSchemaError

pytestmark = pytest.mark.unit

_VALID = {
    "aetherius": "1.0",
    "name": "t.x",
    "act": "vector",
    "steps": [{"action": "set", "value": "1"}],
}


def test_valid_dict_returns_a_model() -> None:
    bp = validate_blueprint_data(_VALID)
    assert bp.name == "t.x"
    assert bp.act == "vector"


def test_schema_violation_mentions_the_source() -> None:
    with pytest.raises(BlueprintSchemaError) as exc:
        validate_blueprint_data({"name": "x"}, source="<studio>")
    assert "<studio>" in str(exc.value)


def test_blueprint_schema_is_cached_singleton() -> None:
    assert blueprint_schema() is blueprint_schema()
    assert "properties" in blueprint_schema()
