"""Tests for core/blueprint/validator.py"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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


# ── Per-step act (Jalon 2-D) ──────────────────────────────────────────────────


def test_step_act_override_allows_a_higher_act_action() -> None:
    validate_for_act(_make_nested("continuum", {"action": "read", "act": "oracle", "vision": "x"}))


def test_step_without_override_keeps_the_blueprint_act_rule() -> None:
    with pytest.raises(BlueprintValidationError, match="on this step"):
        validate_for_act(_make("continuum", ["read"]))


def test_step_act_can_also_lower_the_act() -> None:
    # A vector step inside a browser Blueprint is legal: the frontier is documented as a
    # driver boundary, not a validation error.
    validate_for_act(
        _make_nested("oracle", {"action": "http.request", "act": "vector", "url": "http://x"})
    )
    with pytest.raises(BlueprintValidationError, match="navigate"):
        validate_for_act(_make_nested("oracle", {"action": "navigate", "act": "vector"}))


def test_nested_steps_inherit_the_enclosing_step_act() -> None:
    validate_for_act(
        _make_nested(
            "continuum",
            {
                "action": "if",
                "act": "oracle",
                "condition": "x",
                "then": [{"action": "read", "vision": "y"}],
            },
        )
    )


def test_nested_step_may_override_the_inherited_act() -> None:
    bp = _make_nested(
        "oracle",
        {
            "action": "if",
            "condition": "x",
            "then": [{"action": "read", "act": "continuum", "vision": "y"}],
        },
    )
    with pytest.raises(BlueprintValidationError, match="read"):
        validate_for_act(bp)


def test_invalid_step_act_is_rejected_by_the_model() -> None:
    with pytest.raises(ValidationError, match="act"):
        Blueprint.model_validate(
            {
                "aetherius": "1.0",
                "name": "test",
                "act": "continuum",
                "steps": [{"action": "click", "act": "wizard"}],
            }
        )


# ── Self-healing chains (Jalon 2-D) ──────────────────────────────────────────


def test_options_fallback_accepts_the_browser_escalation_acts() -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "continuum",
            "options": {"fallback": ["oracle", "phantom"]},
            "steps": [{"action": "click", "selector": "#x", "describe": "the button"}],
        }
    )
    validate_for_act(bp)


@pytest.mark.parametrize("entry", ["vector", "continuum", "wizard"])
def test_options_fallback_rejects_non_escalation_acts(entry: str) -> None:
    bp = Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "continuum",
            "options": {"fallback": [entry]},
            "steps": [{"action": "click", "selector": "#x"}],
        }
    )
    with pytest.raises(BlueprintValidationError, match="options.fallback"):
        validate_for_act(bp)


def test_step_fallback_is_validated_with_its_path() -> None:
    bp = _make_nested("continuum", {"action": "click", "selector": "#x", "fallback": ["vector"]})
    with pytest.raises(BlueprintValidationError, match="steps\\[0\\].fallback"):
        validate_for_act(bp)


def _with_extract(spec: dict[str, object]) -> Blueprint:
    return Blueprint.model_validate(
        {
            "aetherius": "1.0",
            "name": "test",
            "act": "vector",
            "steps": [
                {"id": "cal", "action": "http.request", "url": "x", "extract": {"raw": spec}}
            ],
        }
    )


def test_text_extraction_needs_nothing_else() -> None:
    validate_for_act(_with_extract({"from": "text"}))


@pytest.mark.parametrize(
    "key", ["path", "where", "fields", "selector", "selector_type", "attr", "multiple"]
)
def test_text_extraction_rejects_the_other_dialects_keys(key: str) -> None:
    # A spec that carries one believes it filters, and it does not: from='text' renders the whole
    # body. Refused at validation, and by the embedded engine too (blueprint/validator.ts).
    with pytest.raises(BlueprintValidationError, match=key) as exc_info:
        validate_for_act(_with_extract({"from": "text", key: "anything"}))
    assert "steps[0].extract.raw" in str(exc_info.value)


def test_other_dialects_keep_their_keys() -> None:
    validate_for_act(_with_extract({"from": "json", "path": "$[*]"}))
    validate_for_act(_with_extract({"from": "html", "selector": "h1", "multiple": False}))


def test_text_extraction_is_checked_inside_flow_branches() -> None:
    bp = _make_nested(
        "vector",
        {
            "action": "if",
            "condition": "{{ true }}",
            "then": [{"action": "http.request", "extract": {"raw": {"from": "text", "path": "$"}}}],
        },
    )
    with pytest.raises(BlueprintValidationError, match="steps\\[0\\].then\\[0\\].extract.raw"):
        validate_for_act(bp)


# ── optional (Jalon 3-J) ─────────────────────────────────────────────────────


def test_optional_without_steps_is_refused_at_validation() -> None:
    # The one flow action that must not fail late: an `optional` block whose interpretation raises
    # would be tolerated *by itself* and become a silent no-op — the exact opposite of a milestone
    # whose point is that a failure stays visible. Its three sisters keep reporting at run time.
    with pytest.raises(BlueprintValidationError, match="'steps'") as exc_info:
        validate_for_act(_make_nested("vector", {"id": "blk", "action": "optional"}))
    assert "steps[0].steps" in str(exc_info.value)


def test_optional_with_a_non_list_steps_is_refused() -> None:
    with pytest.raises(BlueprintValidationError):
        validate_for_act(_make_nested("vector", {"action": "optional", "steps": "nope"}))


def test_optional_is_accepted_on_every_act() -> None:
    for act in ("vector", "continuum", "oracle", "phantom"):
        validate_for_act(_make_nested(act, {"action": "optional", "steps": [{"action": "emit"}]}))


def test_optional_validates_its_nested_steps() -> None:
    # The block is a flow action like any other: the walk descends into it, with a readable path.
    bp = _make_nested("vector", {"action": "optional", "steps": [{"action": "click"}]})
    with pytest.raises(BlueprintValidationError, match="steps\\[0\\].steps\\[0\\]"):
        validate_for_act(bp)
