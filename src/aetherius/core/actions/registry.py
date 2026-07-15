"""Central action registry: the single source of truth for actions and their specs.

Two tables live here. The *spec* table describes every action's shape: the static ``SPECS`` tuples
of the built-in family modules, aggregated lazily, plus the specs plugins register at runtime. The
*handler* table maps plugin action names to their callables; built-in actions are dispatched by the
drivers' own ``match`` statements (fast path), so only plugin actions ever sit in it. Drivers fall
back to :func:`find_handler` after their built-in match, before raising ActionError.

Plugin actions are deliberately outside the Capability table (core/actions/base.py): they are
act-agnostic — validated dynamically by the Blueprint validator and dispatched by every runnable
Act's driver. A handler that needs Act-specific behaviour reads ``ctx.blueprint.act``. See
docs/plugins.md for the extension contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ..errors import ActionError
from .spec import ActionSpec

if TYPE_CHECKING:
    from ..blueprint.models import StepModel
    from ..events.bus import EventBus
    from ..runtime.context import RunContext

# The exact signature drivers dispatch with (the same shape as ActDriver.run_step): the step, the
# run context, the event bus, and the template renderer closure.
ActionHandler = Callable[
    ["StepModel", "RunContext", "EventBus", Callable[[Any], Any]], dict[str, Any]
]

# Plugin action name → handler callable.
_registry: dict[str, ActionHandler] = {}

# Plugin action name → declarative field spec, registered together with the handler.
_plugin_specs: dict[str, ActionSpec] = {}

# Built-in action name → spec, aggregated lazily from the family modules on first use.
_builtin_specs: dict[str, ActionSpec] | None = None


def register(spec: ActionSpec) -> Callable[[ActionHandler], ActionHandler]:
    """Decorator registering a plugin action: its handler under ``spec.name``, plus its spec.

    The spec is mandatory so the action stays visible to the builder catalogue and the validator
    (the "registry is the source, the catalogue a projection" invariant). Registration refuses to
    shadow a built-in action or an already-registered plugin: built-ins stay authoritative, and a
    conflicting plugin fails loudly at load time instead of silently winning by import order.

    Raises:
        ActionError: ``spec.name`` collides with a built-in action or a registered plugin.
    """

    def decorator(fn: ActionHandler) -> ActionHandler:
        if spec.name in builtin_action_specs():
            raise ActionError(
                f"Cannot register plugin action {spec.name!r}: it would shadow a built-in action."
            )
        if spec.name in _registry:
            raise ActionError(f"Plugin action {spec.name!r} is already registered.")
        _registry[spec.name] = fn
        _plugin_specs[spec.name] = spec
        return fn

    return decorator


def find_handler(action_name: str) -> ActionHandler | None:
    """Return the plugin handler for *action_name*, or None if no plugin provides it.

    Non-raising on purpose: drivers call this as a fallback after their built-in ``match`` and keep
    their own "unsupported action" error when nothing is found.
    """
    return _registry.get(action_name)


def registered_actions() -> list[str]:
    """Return a sorted list of all registered plugin action names."""
    return sorted(_registry)


def plugin_actions() -> frozenset[str]:
    """The plugin action names currently registered (valid on every Act)."""
    return frozenset(_registry)


def builtin_action_specs() -> dict[str, ActionSpec]:
    """The built-in actions' field specs, keyed by name.

    Aggregates the per-family ``SPECS`` tuples lazily (imported here, not at module load, to keep
    ``import aetherius`` light) and caches the result. This static union covers exactly the
    Capability set, a bijection guarded by tests/unit/core/actions/test_specs.py.
    """
    global _builtin_specs
    if _builtin_specs is None:
        from . import data, flow, interaction, navigation, notification

        collected: dict[str, ActionSpec] = {}
        for module in (navigation, interaction, data, flow, notification):
            for spec in module.SPECS:
                collected[spec.name] = spec
        _builtin_specs = collected
    return _builtin_specs


def action_specs() -> dict[str, ActionSpec]:
    """Every action's field spec, keyed by name: built-ins plus the loaded plugins."""
    return {**builtin_action_specs(), **_plugin_specs}


def get_spec(name: str) -> ActionSpec:
    """Return the field spec for *name* or raise ActionError."""
    try:
        return action_specs()[name]
    except KeyError:
        raise ActionError(f"Unknown action: {name!r}. Available: {sorted(action_specs())}")
