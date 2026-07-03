"""Event sinks: LogSink for terminal output, NullSink for tests.

WebSocketSink is deferred to the daemon milestone.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from .models import EventType, RunEvent

_log = logging.getLogger("aetherius.events")


@runtime_checkable
class Sink(Protocol):
    def on_event(self, event: RunEvent) -> None: ...


class NullSink:
    """Discards all events. Used in tests."""

    def on_event(self, event: RunEvent) -> None:
        pass


class LogSink:
    """Writes events to Python logging.

    In debug mode every event is logged at DEBUG; otherwise only INFO and above.
    """

    def __init__(self, *, debug: bool = False) -> None:
        self._debug = debug

    def on_event(self, event: RunEvent) -> None:
        level_str = event.level or ("debug" if event.type == EventType.DEBUG else "info")
        level = getattr(logging, level_str.upper(), logging.INFO)
        if not self._debug and level < logging.INFO:
            return
        msg = f"[{event.type.value}]"
        if event.step_id:
            msg += f" step={event.step_id}"
        if event.message:
            msg += f" {event.message}"
        _log.log(level, msg)
