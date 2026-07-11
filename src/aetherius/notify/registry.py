"""Channel-type registry: maps a channel kind (e.g. "discord") to a factory.

Built-in channels register here; the same table is the seam third-party plugins hook into through the
``aetherius.notify_channels`` entry-point group (Phase 1.5, Jalon E). ``build_channel`` turns a kind
plus a resolved config (secrets already substituted) into a ready :class:`NotificationChannel`.
"""

from __future__ import annotations

from typing import Callable, Mapping

from .base import NotificationChannel

# A factory builds a channel from its resolved config (webhook url, bot token + chat id, topic, ...).
ChannelFactory = Callable[[Mapping[str, str]], NotificationChannel]

_channels: dict[str, ChannelFactory] = {}

_PENDING = "Jalon 1.5-C (notify): channel construction not implemented yet."


def register_channel(kind: str) -> Callable[[ChannelFactory], ChannelFactory]:
    """Decorator registering *factory* under a channel *kind* (e.g. "discord")."""

    def decorator(factory: ChannelFactory) -> ChannelFactory:
        _channels[kind] = factory
        return factory

    return decorator


def build_channel(kind: str, config: Mapping[str, str]) -> NotificationChannel:
    """Construct the channel registered under *kind* from its resolved config."""
    raise NotImplementedError(_PENDING)
