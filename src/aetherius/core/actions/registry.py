"""Central action registry: single source of truth for all supported action handlers.

Handlers self-register via the @register decorator at module import time.
The engine imports the relevant driver module to trigger registration.
"""

from __future__ import annotations

from typing import Any, Callable

from ..errors import ActionError
from .spec import ActionSpec

# action name → handler callable
ActionHandler = Callable[..., dict[str, Any]]

_registry: dict[str, ActionHandler] = {}

# action name → declarative field spec, aggregated lazily from the family modules on first use.
_specs: dict[str, ActionSpec] | None = None


def register(name: str) -> Callable[[ActionHandler], ActionHandler]:
    """Decorator that registers a handler function under *name* in the registry."""

    def decorator(fn: ActionHandler) -> ActionHandler:
        _registry[name] = fn
        return fn

    return decorator


def get_handler(action_name: str) -> ActionHandler:
    """Return the handler for *action_name* or raise ActionError."""
    try:
        return _registry[action_name]
    except KeyError:
        raise ActionError(f"Unknown action: {action_name!r}. Available: {sorted(_registry)}")


def registered_actions() -> list[str]:
    """Return a sorted list of all registered action names."""
    return sorted(_registry)


def action_specs() -> dict[str, ActionSpec]:
    """Return every action's field spec, keyed by name.

    Aggregates the per-family ``SPECS`` tuples lazily (imported here, not at module load, to keep
    ``import aetherius`` light) and caches the result. The union covers exactly the Capability set,
    a bijection guarded by tests/unit/core/actions/test_specs.py.
    """
    global _specs
    if _specs is None:
        from . import data, flow, interaction, navigation

        collected: dict[str, ActionSpec] = {}
        for module in (navigation, interaction, data, flow):
            for spec in module.SPECS:
                collected[spec.name] = spec
        _specs = collected
    return _specs


def get_spec(name: str) -> ActionSpec:
    """Return the field spec for *name* or raise ActionError."""
    try:
        return action_specs()[name]
    except KeyError:
        raise ActionError(f"Unknown action: {name!r}. Available: {sorted(action_specs())}")
