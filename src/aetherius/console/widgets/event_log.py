"""Live event and log stream widget."""

from __future__ import annotations

from rich.text import Text

from textual.widgets import RichLog

from ...core.events.models import EventType, RunEvent
from ...core.events.sinks import format_event
from ..theme import AMBER, POMPEIAN, STONE

_LEVEL_STYLE: dict[str, str] = {
    "debug": STONE,
    "info": "",
    "warning": AMBER,
    "error": f"bold {POMPEIAN}",
}


class EventLog(RichLog):
    """Scrolling, color-coded view of the RunEvents emitted by a Blueprint run."""

    # Fixed height with internal scroll: the stream must never push the result summary
    # (or anything else) out of the screen.
    DEFAULT_CSS = """
    EventLog {
        height: 12;
        border: double $primary;
        padding: 0 1;
    }
    """

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
