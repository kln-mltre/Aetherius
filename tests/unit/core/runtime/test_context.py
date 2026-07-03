"""Tests for core/runtime/context.py"""

from __future__ import annotations

import pytest

from aetherius.core.blueprint.models import Blueprint
from aetherius.core.errors import BlueprintValidationError
from aetherius.core.runtime.context import RunContext, resolve_inputs

pytestmark = pytest.mark.unit


def _bp(inputs: dict) -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "vector",
            "inputs": inputs,
            "steps": [{"action": "http.request"}],
        }
    )


def test_resolve_required_input_present() -> None:
    bp = _bp({"group": {"type": "string", "required": True}})
    resolved = resolve_inputs(bp, {"group": "TP-A1"})
    assert resolved["group"] == "TP-A1"


def test_resolve_missing_required_raises() -> None:
    bp = _bp({"group": {"type": "string", "required": True}})
    with pytest.raises(BlueprintValidationError, match="group"):
        resolve_inputs(bp, {})


def test_resolve_applies_default() -> None:
    bp = _bp({"limit": {"type": "integer", "required": False, "default": 10}})
    resolved = resolve_inputs(bp, {})
    assert resolved["limit"] == 10


def test_template_ctx_structure() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "vector",
            "vars": {"domain": "https://example.com"},
            "steps": [{"action": "http.request"}],
        }
    )
    ctx = RunContext(run_id="r1", blueprint=bp, inputs={"x": "1"}, secrets={"tok": "secret"})
    tctx = ctx.template_ctx()
    assert tctx["inputs"] == {"x": "1"}
    assert tctx["secrets"] == {"tok": "secret"}
    assert tctx["vars"]["domain"] == "https://example.com"
    assert "steps" in tctx
    assert "env" in tctx
