"""NotifySink: turn a run's outcome into an alert.

A run-level sink (structurally a ``core.events.sinks.Sink``) that watches the event stream and sends
a :class:`Notification` when the run finishes, according to a policy: on failure only, on success, or
always. Pass it into ``RunEngine.run(sinks=...)`` or attach it per schedule from the scheduler.
"""

from __future__ import annotations

from typing import Literal

from ..core.events.models import RunEvent
from .base import NotificationChannel

NotifyOn = Literal["failure", "success", "always"]

_PENDING = "Jalon 1.5-C (notify): run-level alerting not implemented yet."


class NotifySink:
    """Emit a Notification through *channel* when a run finishes, per the *on* policy."""

    def __init__(self, channel: NotificationChannel, *, on: NotifyOn = "failure") -> None:
        self._channel = channel
        self._on = on

    def on_event(self, event: RunEvent) -> None:
        raise NotImplementedError(_PENDING)
