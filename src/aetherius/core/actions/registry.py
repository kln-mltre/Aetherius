"""Central action registry: single source of truth for all supported action handlers.

Handlers self-register via the @register decorator at module import time.
The engine imports the relevant driver module to trigger registration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ..errors import ActionError

if TYPE_CHECKING:
    pass

# action name → handler callable
ActionHandler = Callable[..., dict[str, Any]]

_registry: dict[str, ActionHandler] = {}


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
