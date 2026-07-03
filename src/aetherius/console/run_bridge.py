"""Bridges RunEngine events (emitted on a worker thread) into a Textual widget on the UI thread.

RunEngine.run() is synchronous and blocking (HTTP calls), so the Console drives it from a
Textual `@work(thread=True)` worker. Sinks are called from that worker thread, but Textual
widgets may only be touched from the app's own thread — `App.call_from_thread` is Textual's
documented mechanism for crossing that boundary safely.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from textual.app import App

from ..core.events.models import RunEvent

_log = logging.getLogger("aetherius.console")


@runtime_checkable
class SupportsWriteEvent(Protocol):
    """Structural type for the widget passed to TextualRunSink (e.g. EventLog)."""

    def write_event(self, event: RunEvent) -> None: ...


class TextualRunSink:
    """Sink that forwards each RunEvent to an EventLog-like widget's `write_event` method.

    Structurally satisfies core.events.sinks.Sink; never raises, so a widget failure cannot
    abort the Blueprint run it is merely observing.
    """

    def __init__(self, app: App[object], writer: SupportsWriteEvent) -> None:
        self._app = app
        self._writer = writer

    def on_event(self, event: RunEvent) -> None:
        try:
            self._app.call_from_thread(self._writer.write_event, event)
        except Exception:
            _log.exception("Failed to forward run event %r to the Console.", event.type)
