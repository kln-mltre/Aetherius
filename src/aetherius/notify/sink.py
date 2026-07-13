"""NotifySink: turn a run's outcome into an alert.

A run-level sink (structurally a ``core.events.sinks.Sink``) that watches the event stream and sends
a :class:`Notification` when the run finishes, according to a policy: on failure only, on success, or
always. Pass it into ``RunEngine.run(sinks=...)`` or attach it per schedule from the scheduler.
"""

from __future__ import annotations

from typing import Literal

from ..core.events.models import EventType, RunEvent
from ..core.runtime.result import RunStatus
from .base import NotificationChannel
from .message import Notification, NotificationLevel

NotifyOn = Literal["failure", "success", "always"]


class NotifySink:
    """Emit a Notification through *channel* when a run finishes, per the *on* policy."""

    def __init__(self, channel: NotificationChannel, *, on: NotifyOn = "failure") -> None:
        self._channel = channel
        self._on = on

    def on_event(self, event: RunEvent) -> None:
        if event.type is not EventType.DONE:
            return
        status = str(event.data.get("status", ""))
        failed = status != RunStatus.SUCCESS.value
        if (self._on == "failure" and not failed) or (self._on == "success" and failed):
            return

        error = event.data.get("error")
        body = event.message or f"run finished: {status or 'unknown'}"
        if error:
            body = f"{body}\n{error}"

        # Deferred import: the package __init__ imports this module before dispatch exists.
        from . import dispatch

        dispatch(
            Notification(
                body=body,
                title=f"Aetherius — run {status or 'finished'}",
                level=NotificationLevel.ERROR if failed else NotificationLevel.INFO,
                data={"run_id": event.run_id, "status": status, "error": error},
            ),
            self._channel,
        )
