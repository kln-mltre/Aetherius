"""Synchronous event fan-out: emits RunEvents to all registered sinks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .sinks import Sink

from .models import RunEvent

_log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._sinks: list[Sink] = []

    def register(self, sink: "Sink") -> None:
        self._sinks.append(sink)

    def emit(self, event: RunEvent) -> None:
        for sink in self._sinks:
            try:
                sink.on_event(event)
            except Exception:
                _log.exception("Event sink %r raised an error; continuing.", sink)
