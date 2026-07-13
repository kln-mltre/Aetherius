"""Channel-type registry: maps a channel kind (e.g. "discord") to a factory.

Built-in channels register here; the same table is the seam third-party plugins hook into through the
``aetherius.notify_channels`` entry-point group (Phase 1.5, Jalon E). ``build_channel`` turns a kind
plus a resolved config (secrets already substituted) into a ready :class:`NotificationChannel`.

Each kind may also declare a *target key*: the config entry the ``notify`` action's ``target``
parameter is shorthand for (webhook -> ``url``, ntfy -> ``topic``, ...). Multi-key channels
(Telegram) provide their remaining keys through the action's ``config`` object.
"""

from __future__ import annotations

from typing import Callable, Mapping

from ..core.errors import NotificationError
from .base import NotificationChannel

# A factory builds a channel from its resolved config (webhook url, bot token + chat id, topic, ...).
ChannelFactory = Callable[[Mapping[str, str]], NotificationChannel]

_channels: dict[str, ChannelFactory] = {}
_target_keys: dict[str, str] = {}


def register_channel(
    kind: str, *, target_key: str | None = None
) -> Callable[[ChannelFactory], ChannelFactory]:
    """Decorator registering *factory* under a channel *kind* (e.g. "discord").

    ``target_key`` names the config entry the ``notify`` action's ``target`` parameter fills for
    this kind; omit it for a channel that cannot be addressed by a single value.
    """

    def decorator(factory: ChannelFactory) -> ChannelFactory:
        _channels[kind] = factory
        if target_key is not None:
            _target_keys[kind] = target_key
        return factory

    return decorator


def target_key(kind: str) -> str | None:
    """The config key the ``target`` shorthand fills for *kind*, if it declares one."""
    _ensure_builtins()
    return _target_keys.get(kind)


def build_channel(kind: str, config: Mapping[str, str]) -> NotificationChannel:
    """Construct the channel registered under *kind* from its resolved config.

    Raises:
        NotificationError: unknown kind, or a required config key is missing.
    """
    _ensure_builtins()
    factory = _channels.get(kind)
    if factory is None:
        known = ", ".join(sorted(_channels))
        raise NotificationError(f"Unknown notification channel {kind!r}. Known channels: {known}.")
    return factory(config)


def require(config: Mapping[str, str], kind: str, key: str) -> str:
    """Fetch a required *key* from a channel config, with a channel-aware error."""
    value = config.get(key)
    if not value:
        raise NotificationError(
            f"Notification channel {kind!r} requires the config key {key!r} "
            f"(provided via the step's 'target' or 'config' parameter)."
        )
    return value


def _ensure_builtins() -> None:
    # Built-in channels register themselves on import (dogfooding this registry). Importing lazily
    # here keeps registry -> channels -> registry from becoming an import cycle while guaranteeing
    # the table is populated no matter which module the caller imported first.
    from . import channels  # noqa: F401
