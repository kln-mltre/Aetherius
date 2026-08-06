"""Tests for core/blueprint/template.py"""

from __future__ import annotations

import pytest

from aetherius.core.blueprint.template import render_value
from aetherius.core.errors import TemplateError

pytestmark = pytest.mark.unit

_CTX = {
    "inputs": {"monday": "2026-09-07", "group": "TP-A1"},
    "secrets": {},
    "vars": {"domain": "https://example.com"},
    "env": {},
    "steps": {},
}


def test_simple_variable() -> None:
    assert render_value("{{ vars.domain }}", _CTX) == "https://example.com"


def test_nested_variable() -> None:
    assert render_value("{{ inputs.group }}", _CTX) == "TP-A1"


def test_add_days_filter() -> None:
    result = render_value("{{ inputs.monday | add_days(7) }}", _CTX)
    assert result == "2026-09-14"


def test_sub_days_filter() -> None:
    result = render_value("{{ inputs.monday | sub_days(1) }}", _CTX)
    assert result == "2026-09-06"


def test_format_date_filter() -> None:
    result = render_value("{{ inputs.monday | format_date('%d/%m/%Y') }}", _CTX)
    assert result == "07/09/2026"


def test_dict_rendered_recursively() -> None:
    result = render_value({"url": "{{ vars.domain }}/api", "key": 42}, _CTX)
    assert result == {"url": "https://example.com/api", "key": 42}


def test_list_rendered_recursively() -> None:
    result = render_value(["{{ inputs.group }}", "static"], _CTX)
    assert result == ["TP-A1", "static"]


def test_non_string_passthrough() -> None:
    assert render_value(42, _CTX) == 42
    assert render_value(None, _CTX) is None
    assert render_value(True, _CTX) is True


def test_undefined_variable_raises() -> None:
    with pytest.raises(TemplateError):
        render_value("{{ inputs.nonexistent }}", _CTX)


def test_step_output_in_context() -> None:
    ctx = {**_CTX, "steps": {"step1": {"value": "hello"}}}
    result = render_value("{{ steps.step1.value }}", ctx)
    assert result == "hello"


def test_two_expressions_without_surrounding_text_interpolate() -> None:
    # A URL built from two variables is the most ordinary Blueprint string there is. The bare
    # expression pattern used to backtrack past the first '}}' and read the whole thing as one
    # malformed expression, so this raised instead of rendering.
    ctx = {**_CTX, "inputs": {"group": "TP-A1"}}
    assert render_value("{{ vars.domain }}/{{ inputs.group }}", ctx) == "https://example.com/TP-A1"


def test_the_bare_expression_rule_still_returns_raw_values() -> None:
    # The counterpart the fix must not break: exactly one expression still yields the object.
    ctx = {**_CTX, "steps": {"week": {"events": [{"id": 1}, {"id": 2}]}}}
    assert render_value("  {{ steps.week.events }}  ", ctx) == [{"id": 1}, {"id": 2}]
