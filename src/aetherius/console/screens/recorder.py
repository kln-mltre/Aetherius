"""Launch and drive the Blueprint recorder from the Console.

Captures a browser demonstration and synthesizes a clean Blueprint with robust selectors, instead of
writing steps by hand. The recorder engine (`aetherius.recorder`) is synchronous and blocking (it
owns a live browser), so it runs in a Textual `@work(thread=True)` worker, exactly like a Blueprint
run. Captured actions stream into the event log through the same Sink pattern (`run_bridge`); Stop
sets a threading.Event the recorder's pump loop honors to close the browser.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static, Switch

from ...core.errors import AetheriusError
from ...core.events.models import EventType, RunEvent
from ...recorder import record_blueprint
from ...recorder.base import recorder_acts
from ..run_bridge import TextualRunSink
from ..theme import starred
from ..widgets.event_log import EventLog
from ..widgets.json_preview import JsonPreview

# How each recorder Act reads in the picker. Derived list stays in sync with recorder_acts().
_ACT_LABELS: dict[str, str] = {
    "continuum": "Continuum — browser (DOM)",
    "vector": "Vector — API (network)",
}


class RecorderScreen(Screen[None]):
    """Record a Blueprint by demonstration: enter a name and start URL, act in the browser, save."""

    AUTO_FOCUS = "#rec-name"

    DEFAULT_CSS = """
    RecorderScreen .rec-field {
        height: auto;
        padding: 1 1 0 1;
    }
    RecorderScreen #rec-creds-row {
        height: auto;
        padding: 1 1 0 1;
    }
    RecorderScreen #rec-creds-label {
        padding: 1 1 0 0;
    }
    RecorderScreen #rec-start, RecorderScreen #rec-stop {
        border: double $accent;
        background: $panel;
        color: $accent;
        text-style: bold;
        padding: 0 3;
    }
    RecorderScreen #rec-start:hover, RecorderScreen #rec-stop:hover {
        background: $accent 20%;
    }
    RecorderScreen #rec-result {
        border: double $primary;
        padding: 0 1;
        margin: 1 0;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._stop = threading.Event()
        self._sink: TextualRunSink | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            yield Static(starred("Recorder"), classes="console-title")
            yield Static(
                "Pick an Act, enter a name and a start URL, then Start: a browser opens. Continuum "
                "records DOM actions and the floating menu picks data; Vector observes API calls. "
                "Closing the window (or Stop) saves the Blueprint to ./blueprints.",
                classes="console-subtitle",
            )
            with Vertical(classes="rec-field"):
                yield Label("Act")
                yield Select(
                    [(_ACT_LABELS.get(a, a), a) for a in sorted(recorder_acts())],
                    value="continuum",
                    allow_blank=False,
                    id="rec-act",
                )
            with Vertical(classes="rec-field"):
                yield Label("Blueprint name (e.g. quotes.login)")
                yield Input(placeholder="domain.task", id="rec-name")
            with Vertical(classes="rec-field"):
                yield Label("Start URL")
                yield Input(placeholder="https://…", id="rec-url")
            with Horizontal(id="rec-creds-row"):
                yield Static("Turn credential fields into secrets", id="rec-creds-label")
                yield Switch(value=True, id="rec-creds")
            with Horizontal(classes="run-actions"):
                yield Button("✦ Start recording ✦", id="rec-start", variant="primary")
                stop = Button("Stop", id="rec-stop")
                stop.display = False
                yield stop
            event_log = EventLog(id="rec-events")
            event_log.border_title = "✦ Captured actions ✦"
            yield event_log
            result = JsonPreview(id="rec-result")
            result.border_title = "✦ Result ✦"
            result.display = False
            yield result
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "rec-stop":
            self._stop.set()
            self.app.notify("Stopping — closing the browser…", timeout=4)
            return
        if event.button.id != "rec-start":
            return

        name = self.query_one("#rec-name", Input).value.strip()
        url = self.query_one("#rec-url", Input).value.strip()
        if not name or not url:
            self.app.notify("A name and a start URL are required.", severity="warning")
            return

        act = str(self.query_one("#rec-act", Select).value)
        credentials = self.query_one("#rec-creds", Switch).value
        self._stop = threading.Event()
        self._sink = TextualRunSink(self.app, self.query_one("#rec-events", EventLog))
        self.query_one("#rec-events", EventLog).clear()
        self.query_one("#rec-result", JsonPreview).display = False
        self._set_recording(True)
        self._record(name, url, act, credentials)

    @work(thread=True, exclusive=True)
    def _record(self, name: str, url: str, act: str, credentials: bool) -> None:
        try:
            path = record_blueprint(
                name,
                url,
                act=act,
                on_event=self._push_event,
                stop_event=self._stop,
                credentials_as_secrets=credentials,
            )
        except AetheriusError as exc:
            self.app.call_from_thread(self._fail, exc)
            return
        self.app.call_from_thread(self._finish, path)

    def _push_event(self, description: str) -> None:
        """Forward one captured action's description into the event log (from the worker thread)."""
        if self._sink is None:
            return
        self._sink.on_event(
            RunEvent(
                run_id="recorder",
                type=EventType.STEP_FINISHED,
                level="info",
                message=description,
            )
        )

    def _finish(self, path: Path) -> None:
        self._set_recording(False)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        result = self.query_one("#rec-result", JsonPreview)
        result.display = True
        result.show(data)
        result.scroll_visible()
        self.app.notify(f"Saved {path}", timeout=6)

    def _fail(self, exc: Exception) -> None:
        self._set_recording(False)
        self.app.notify(str(exc), title="Recorder error", severity="error", timeout=8)

    def _set_recording(self, recording: bool) -> None:
        """Toggle the Start/Stop buttons; tolerate the screen being popped mid-run."""
        try:
            self.query_one("#rec-start", Button).disabled = recording
            self.query_one("#rec-stop", Button).display = recording
        except NoMatches:
            pass
