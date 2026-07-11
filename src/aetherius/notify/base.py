"""The NotificationChannel protocol: any destination that can deliver a Notification."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .message import Notification


@runtime_checkable
class NotificationChannel(Protocol):
    """A destination that delivers a :class:`Notification` (webhook, Discord, Telegram, ntfy, ...).

    Structural, like ``core.events.sinks.Sink``: a built-in channel or a third-party plugin channel
    (Jalon E) satisfies it just by exposing ``send``.
    """

    def send(self, notification: Notification) -> None: ...
