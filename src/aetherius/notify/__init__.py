"""Native notification layer for Aetherius (Phase 1.5, Jalon C).

Sends alerts (product back in stock, run failed, ...) to a notification channel. Every built-in
channel is a thin HTTP POST over ``httpx`` (already a core dependency), so this layer adds no new
dependency yet covers generic webhooks, Discord, Telegram and ntfy (phone push). It is exposed two
ways: the Act-agnostic ``notify`` action inside a Blueprint, and a run-level :class:`NotifySink` that
alerts on failure/success.

Channel targets (webhook URLs, bot tokens, topics) are provided as Blueprint secrets and never
stored. De-duplication (alert once per state transition) is delegated to the store's inter-run state
(``aetherius.store``). See docs/notifications.md.
"""

from __future__ import annotations

import logging

from .base import NotificationChannel
from .message import Notification, NotificationLevel
from .registry import build_channel, register_channel
from .sink import NotifySink

__all__ = [
    "NotificationChannel",
    "Notification",
    "NotificationLevel",
    "NotifySink",
    "build_channel",
    "register_channel",
    "dispatch",
]

_log = logging.getLogger("aetherius.notify")


def dispatch(notification: Notification, channel: NotificationChannel) -> bool:
    """Deliver *notification* through *channel*; True when the channel accepted it.

    A delivery failure is contained (logged, not raised through the run) so an alerting hiccup never
    aborts the work it merely observes — same discipline as the daemon's QueueSink. Callers that
    care (the ``notify`` action exposes ``delivered``) read the returned bool instead.
    """
    try:
        channel.send(notification)
    except Exception:
        _log.exception("Notification delivery through %r failed; continuing.", channel)
        return False
    return True
