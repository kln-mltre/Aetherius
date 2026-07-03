"""Live event and log stream widget."""

from __future__ import annotations

from rich.text import Text

from textual.widgets import RichLog

from ...core.events.models import EventType, RunEvent
from ...core.events.sinks import format_event

_LEVEL_STYLE: dict[str, str] = {
    "debug": "dim",
    "info": "",
    "warning": "yellow",
    "error": "bold red",
}


class EventLog(RichLog):
    """Scrolling, color-coded view of the RunEvents emitted by a Blueprint run."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(markup=False, wrap=True, auto_scroll=True, **kwargs)  # type: ignore[arg-type]

    def write_event(self, event: RunEvent) -> None:
        level = event.level or ("debug" if event.type == EventType.DEBUG else "info")
        if event.type == EventType.ERROR:
            level = "error"
        elif event.type == EventType.DONE and event.data.get("status") == "success":
            level = "info"
        style = _LEVEL_STYLE.get(level, "")
        self.write(Text(format_event(event), style=style))
