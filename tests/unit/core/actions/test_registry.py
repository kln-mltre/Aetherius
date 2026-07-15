"""Tests for core/actions/registry.py — the plugin action seam (Jalon E).

Built-in actions never sit in the handler table (drivers dispatch them from their own match
statements), so the registry is exercised the way a plugin uses it: register a handler with its
spec, look both up, and verify the collision guards that keep built-ins authoritative.
"""

from __future__ import annotations

from typing import Any

import pytest

from aetherius.core.actions import registry
from aetherius.core.actions.registry import (
    action_specs,
    builtin_action_specs,
    find_handler,
    get_spec,
    plugin_actions,
    registered_actions,
)
from aetherius.core.actions.spec import ActionSpec
from aetherius.core.errors import ActionError

pytestmark = pytest.mark.unit


def _noop_handler(*args: Any) -> dict[str, Any]:
    return {}


def test_registered_action_exposes_handler_and_spec(plugin_action: str) -> None:
    assert find_handler(plugin_action) is not None
    assert plugin_action in plugin_actions()
    assert plugin_action in registered_actions()
    assert action_specs()[plugin_action].summary
    assert get_spec(plugin_action).name == plugin_action


def test_find_handler_returns_none_for_unknown_actions() -> None:
    assert find_handler("does.not.exist") is None


def test_builtin_specs_stay_pure_while_the_merged_view_includes_plugins(
    plugin_action: str,
) -> None:
    assert plugin_action not in builtin_action_specs()
    assert plugin_action in action_specs()


def test_registering_a_builtin_name_is_refused() -> None:
    with pytest.raises(ActionError, match="shadow"):
        registry.register(ActionSpec("click", "Shadowing a built-in."))(_noop_handler)
    assert find_handler("click") is None


def test_double_registration_is_refused(plugin_action: str) -> None:
    with pytest.raises(ActionError, match="already registered"):
        registry.register(ActionSpec(plugin_action, "Registered twice."))(_noop_handler)
