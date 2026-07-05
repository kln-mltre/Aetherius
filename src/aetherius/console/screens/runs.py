"""Run a Blueprint and follow its events, logs and artifacts live."""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ...core.blueprint.loader import load_blueprint
from ...core.blueprint.models import Blueprint
from ...core.blueprint.validator import validate_for_act
from ...core.errors import AetheriusError
from ...core.runtime.engine import IMPLEMENTED_ACTS, RunEngine
from ...core.runtime.result import Result
from ..run_bridge import TextualRunSink
from ..theme import starred
from ..widgets.event_log import EventLog
from ..widgets.form import BlueprintInputForm
from ..widgets.run_summary import RunSummary


class RunsScreen(Screen[None]):
    """Load a Blueprint, collect its inputs, run it, and show live events + the final result.

    The body is a VerticalScroll so every section stays reachable in short terminals.
    """

    # Land directly in the first form field instead of the scroll container.
    AUTO_FOCUS = "BlueprintInputForm Input"

    def __init__(self, blueprint_path: Path) -> None:
        super().__init__()
        self._blueprint_path = blueprint_path
        self._blueprint: Blueprint | None = None
        self._load_error: str | None = None

        try:
            self._blueprint = load_blueprint(blueprint_path)
            validate_for_act(self._blueprint)
        except AetheriusError as exc:
            self._load_error = str(exc)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            if self._load_error is not None:
                yield Static(f"Cannot load Blueprint: {self._load_error}", classes="console-title")
                yield Footer()
                return

            assert self._blueprint is not None
            bp = self._blueprint
            yield Static(starred(f"Run — {bp.name}"), classes="console-title")
            yield Static(f"Path: {self._blueprint_path}", classes="console-subtitle")

            if bp.act not in IMPLEMENTED_ACTS:
                yield Static(
                    f"Act {bp.act!r} has no driver yet — only Vector (Act I) is runnable. "
                    "This Blueprint is valid but cannot be executed from the Console.",
                    classes="console-subtitle",
                )
                yield Footer()
                return

            from ...config.secrets import available_from_env

            form = BlueprintInputForm(bp.inputs, bp.secrets, available_from_env(bp.secrets))
            form.border_title = "✦ Inputs ✦"
            yield form
            with Horizontal(classes="run-actions"):
                yield Button("✦ Run ✦", id="run-button", variant="primary")
            event_log = EventLog(id="run-event-log")
            event_log.border_title = "✦ Events ✦"
            yield event_log
            summary = RunSummary(id="run-summary")
            summary.border_title = "✦ Result ✦"
            yield summary
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "run-button":
            return
        assert self._blueprint is not None

        form = self.query_one(BlueprintInputForm)
        errors = form.validation_errors()
        if errors:
            self.app.notify("\n".join(errors), title="Missing inputs", severity="warning")
            return

        input_values, secret_values = form.collect()
        event.button.disabled = True
        self.query_one("#run-event-log", EventLog).clear()
        self.query_one("#run-summary", RunSummary).reset()
        self._run_blueprint(input_values, secret_values)

    @work(thread=True, exclusive=True)
    def _run_blueprint(self, inputs: dict[str, object], secrets: dict[str, str]) -> None:
        assert self._blueprint is not None
        event_log = self.query_one("#run-event-log", EventLog)
        sink = TextualRunSink(self.app, event_log)

        try:
            result = RunEngine().run(self._blueprint, inputs=inputs, secrets=secrets, sinks=[sink])
        except AetheriusError as exc:
            self.app.call_from_thread(self._notify_error, exc)
            self.app.call_from_thread(self._reenable_run_button)
            return

        self.app.call_from_thread(self._show_result, result)

    def _show_result(self, result: Result) -> None:
        summary = self.query_one("#run-summary", RunSummary)
        summary.show(result)
        summary.scroll_visible()
        self._reenable_run_button()

    def _reenable_run_button(self) -> None:
        # The screen may have been popped while the worker was still running; that's fine,
        # there's nothing left to re-enable.
        try:
            self.query_one("#run-button", Button).disabled = False
        except NoMatches:
            pass

    def _notify_error(self, exc: Exception) -> None:
        self.app.notify(str(exc), title="Error", severity="error", timeout=8)
