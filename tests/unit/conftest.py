"""Shared unit-test fixtures.

``plugin_action`` registers a standard action ("testplugin.shout") through the real Jalon E plugin
seam and unregisters it afterwards, so any test can exercise the plugin path (registry, drivers,
validator, catalogue) without leaking state into the anti-drift tests — the same pop-in-finally
discipline as the notify channel fixtures.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

import pytest

from aetherius.core.actions import registry
from aetherius.core.actions.spec import ActionSpec, ParamSpec

PLUGIN_ACTION = "testplugin.shout"


@pytest.fixture()
def plugin_action() -> Iterator[str]:
    """Register an uppercase-echo plugin action for the test's lifetime; yield its name."""
    spec = ActionSpec(
        PLUGIN_ACTION,
        "Uppercase a value (test plugin action).",
        params=(ParamSpec("value", "string", required=True),),
    )

    @registry.register(spec)
    def _shout(step: Any, ctx: Any, bus: Any, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        return {"shout": str(renderer(step.extra_fields.get("value", ""))).upper()}

    try:
        yield PLUGIN_ACTION
    finally:
        registry._registry.pop(PLUGIN_ACTION, None)
        registry._plugin_specs.pop(PLUGIN_ACTION, None)
