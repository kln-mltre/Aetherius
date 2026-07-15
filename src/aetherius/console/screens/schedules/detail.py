"""Schedule detail: full definition, run history, and a manual fire with live events.

The manual fire executes in-process through ``fire_schedule`` (the exact code path of
``aetherius schedule run``): the outcome lands in the history under the schedule's id, the alert
policy applies, and the cadence stays untouched. Events stream through the Console's usual Sink
pattern (worker thread → ``TextualRunSink`` → ``EventLog``).
"""

from __future__ import annotations

import json

from rich.text import Text

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from ....core.errors import AetheriusError
from ....core.runtime.result import Result
from ....server.scheduler import describe_trigger, fire_schedule
from ....store import RunRecord, ScheduleRecord, Store
from ...run_bridge import TextualRunSink
from ...theme import LAUREL, POMPEIAN, STONE, starred
from ...widgets.confirm import ConfirmModal
from ...widgets.event_log import EventLog
from ...widgets.run_summary import RunSummary
from ._common import format_local, get_default_store, notify_summary, toggle_enabled

_HISTORY_LIMIT = 20

_STATUS_STYLE: dict[str, str] = {
    "success": f"bold {LAUREL}",
    "failed": f"bold {POMPEIAN}",
}


def _outcome_digest(record: RunRecord) -> str:
    """One cell summarizing what the run produced: the error if any, else compact outputs."""
    if record.error:
        return record.error[:60]
    if record.outputs:
        digest = json.dumps(record.outputs, ensure_ascii=False, default=str)
        return digest if len(digest) <= 60 else digest[:60] + "…"
    return "-"


def _duration(record: RunRecord) -> str:
    if record.finished_at is None:
        return "-"
    return f"{(record.finished_at - record.started_at).total_seconds() * 1000:.0f} ms"


class ScheduleDetailScreen(Screen[None]):
    """One schedule: definition, actions (fire/pause/edit/delete) and its recent run history."""

    BINDINGS = [
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, schedule_id: str, store: Store | None = None) -> None:
        super().__init__()
        self._schedule_id = schedule_id
        self._store = store if store is not None else get_default_store()
        self._record: ScheduleRecord | None = None
        self._suspended = False
        self._deleted = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            yield Static(id="schedule-title", classes="console-title")
            yield Static(id="schedule-info", classes="schedule-info")
            with Horizontal(classes="run-actions"):
                yield Button("✦ Fire now ✦", id="schedule-fire", variant="primary")
                yield Button("Pause", id="schedule-toggle")
            event_log = EventLog(id="schedule-event-log")
            event_log.border_title = "✦ Events ✦"
            yield event_log
            summary = RunSummary(id="schedule-summary")
            summary.border_title = "✦ Result ✦"
            yield summary
            yield Static(starred("History"), classes="console-title")
            yield Static(
                f"Last {_HISTORY_LIMIT} runs of this schedule (manual fires included).",
                classes="console-subtitle",
            )
            yield DataTable(id="schedule-history", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#schedule-history", DataTable).add_columns(
            "Started", "Status", "Duration", "Outcome"
        )
        self._refresh()

    def on_screen_suspend(self) -> None:
        self._suspended = True

    def on_screen_resume(self) -> None:
        # Coming back from the edit form: reflect whatever it changed. Resume also fires on the
        # initial push, where re-clearing the freshly filled history DataTable in the same layout
        # pass would freeze its column widths — hence the suspended flag.
        if self._suspended:
            self._suspended = False
            self._refresh()

    # ── rendering ─────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        record = self._store.schedules.get(self._schedule_id)
        if record is None:
            # Deleted from this screen: the confirm callback owns the exit. Deleted elsewhere
            # (CLI, API) meanwhile: nothing left to show, leave with an explanation.
            if not self._deleted:
                self.app.notify("This schedule no longer exists.", severity="warning", timeout=6)
                self._leave()
            return
        self._record = record

        self.query_one("#schedule-title", Static).update(starred(f"Schedule — {record.name}"))
        self.query_one("#schedule-info", Static).update(self._info_text(record))
        self.query_one("#schedule-toggle", Button).label = "Pause" if record.enabled else "Resume"
        self._refresh_history()

    def _info_text(self, record: ScheduleRecord) -> Text:
        state = (
            Text("✦ active", style=f"bold {LAUREL}")
            if record.enabled
            else Text("paused", style=f"bold {STONE}")
        )
        text = Text()
        rows: list[tuple[str, Text | str]] = [
            ("Status", state),
            ("Blueprint", record.blueprint),
            ("Trigger", describe_trigger(record.trigger)),
            ("Notify", notify_summary(record.notify)),
            ("Inputs", json.dumps(record.inputs, ensure_ascii=False) if record.inputs else "-"),
            (
                "Secrets",
                ", ".join(record.secrets) + " (resolved from .env at fire time)"
                if record.secrets
                else "-",
            ),
            ("Next run", format_local(record.next_run_at) if record.enabled else "-"),
            ("Last run", format_local(record.last_run_at)),
            ("Created", format_local(record.created_at)),
        ]
        for index, (label, value) in enumerate(rows):
            if index:
                text.append("\n")
            text.append(f"{label:<10}", style=STONE)
            if isinstance(value, Text):
                text.append_text(value)
            else:
                text.append(value)
        return text

    def _refresh_history(self) -> None:
        table = self.query_one("#schedule-history", DataTable)
        table.clear()
        for run in self._store.runs.recent(schedule_id=self._schedule_id, limit=_HISTORY_LIMIT):
            table.add_row(
                format_local(run.started_at),
                Text(run.status, style=_STATUS_STYLE.get(run.status, "")),
                _duration(run),
                _outcome_digest(run),
                key=run.run_id,
            )

    # ── actions ───────────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "schedule-fire":
            self._start_fire(event.button)
        elif event.button.id == "schedule-toggle":
            self._toggle()

    def _start_fire(self, button: Button) -> None:
        if self._record is None:
            return
        button.disabled = True
        self.query_one("#schedule-event-log", EventLog).clear()
        self.query_one("#schedule-summary", RunSummary).reset()
        self._fire()

    @work(thread=True, exclusive=True)
    def _fire(self) -> None:
        assert self._record is not None
        sink = TextualRunSink(self.app, self.query_one("#schedule-event-log", EventLog))
        try:
            result, delivered = fire_schedule(self._record, self._store, sinks=[sink])
        except AetheriusError as exc:
            # Recorded as a failed run by fire_schedule; surface it and show the fresh history.
            self.app.call_from_thread(self._notify_error, exc)
            self.app.call_from_thread(self._after_fire, None, None)
            return
        self.app.call_from_thread(self._after_fire, result, delivered)

    def _after_fire(self, result: Result | None, delivered: bool | None) -> None:
        try:
            if result is not None:
                summary = self.query_one("#schedule-summary", RunSummary)
                summary.show(result)
                summary.scroll_visible()
                if delivered is not None:
                    outcome = "alert sent" if delivered else "alert delivery failed"
                    self.app.notify(
                        outcome, severity="information" if delivered else "warning", timeout=4
                    )
            self._refresh_history()
            self.query_one("#schedule-fire", Button).disabled = False
        except NoMatches:
            pass  # screen popped while the worker was still running

    def _toggle(self) -> None:
        if self._record is None:
            return
        updated = toggle_enabled(self._store, self._record)
        state = "resumed" if updated.enabled else "paused"
        self.app.notify(f"Schedule {updated.name!r} {state}.", timeout=4)
        self._refresh()

    def action_edit(self) -> None:
        if self._record is None:
            return
        from .form import ScheduleFormScreen

        self.app.push_screen(ScheduleFormScreen(store=self._store, edit=self._record))

    def action_delete(self) -> None:
        if self._record is None:
            return
        record = self._record

        def _on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            # Flag first: the resume-triggered refresh must not race this exit with its own pop.
            self._deleted = True
            self._store.schedules.delete(record.id)
            self.app.notify(f"Schedule {record.name!r} deleted.", timeout=4)
            self.app.call_later(self._leave)

        self.app.push_screen(
            ConfirmModal(
                f"Delete schedule {record.name!r}? Its run history is kept.",
                title="Delete schedule",
                confirm_label="Delete",
            ),
            _on_confirm,
        )

    def _leave(self) -> None:
        """Pop this screen if it is still the active one (tolerates racing exits)."""
        if self.is_current:
            self.app.pop_screen()

    def action_refresh(self) -> None:
        self._refresh()

    def _notify_error(self, exc: Exception) -> None:
        self.app.notify(str(exc), title="Error", severity="error", timeout=8)
