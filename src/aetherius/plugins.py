"""Plugin discovery and the import surface plugin authors code against (Phase 1.5, Jalon E).

A third-party package extends Aetherius without forking it through two entry-point groups declared
in its own ``pyproject.toml``:

- ``aetherius.actions`` — custom Blueprint actions, registered with :func:`register_action`;
- ``aetherius.notify_channels`` — notification channels, registered with :func:`register_channel`.

Each entry point targets a module whose *import* performs the registration (decorators at module
level — the same mechanics the built-in channels use). :func:`load_plugins` runs discovery at
startup: the CLI callback, the daemon lifespan and ``RunEngine.run`` all call it, so plugins are
visible wherever Blueprints are validated, built or executed. Library consumers that only use the
builder call it themselves.

Failure isolation: a plugin that raises while loading is logged and skipped — it never prevents
startup. Trust: loading a plugin executes its code; there is no sandbox. Contract, naming rules and
limits: docs/plugins.md.
"""

from __future__ import annotations

import logging
import threading
from importlib.metadata import entry_points

from .core.actions.registry import register as register_action
from .core.actions.spec import ActionSpec, ParamSpec
from .core.blueprint.models import StepModel
from .core.events.bus import EventBus
from .core.runtime.context import RunContext
from .notify import Notification, NotificationChannel, register_channel
from .notify.registry import require

__all__ = [
    "ACTIONS_GROUP",
    "NOTIFY_CHANNELS_GROUP",
    "load_plugins",
    # Plugin-author surface: one import point, decoupled from the internal module layout.
    "register_action",
    "register_channel",
    "require",
    "ActionSpec",
    "ParamSpec",
    "StepModel",
    "RunContext",
    "EventBus",
    "Notification",
    "NotificationChannel",
]

_log = logging.getLogger("aetherius.plugins")

ACTIONS_GROUP = "aetherius.actions"
NOTIFY_CHANNELS_GROUP = "aetherius.notify_channels"

_lock = threading.Lock()
_loaded = False


def load_plugins(*, force: bool = False) -> list[str]:
    """Discover and load every installed plugin; return the entry points loaded as ``group:name``.

    Idempotent and thread-safe: the engine calls this on every run, so repeat calls are no-ops
    (``force`` re-runs discovery — meant for tests). Built-in channels are imported first so the
    registries' collision guards always resolve a name conflict in favour of the built-in: the
    conflicting plugin is the one skipped, with a warning naming it.
    """
    global _loaded
    with _lock:
        if _loaded and not force:
            return []

        # Built-ins must hold their names before any plugin registers (collision guards).
        from .notify import channels  # noqa: F401

        loaded: list[str] = []
        for group in (ACTIONS_GROUP, NOTIFY_CHANNELS_GROUP):
            for ep in entry_points(group=group):
                try:
                    ep.load()
                except Exception as exc:
                    _log.warning(
                        "Skipping plugin %r (group %r): failed to load: %s", ep.name, group, exc
                    )
                else:
                    loaded.append(f"{group}:{ep.name}")
        _loaded = True
        return loaded
