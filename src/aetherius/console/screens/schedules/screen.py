"""Schedules list: every persistent schedule, its cadence and its state at a glance."""

from __future__ import annotations

from rich.text import Text

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ....server.config import DaemonConfig
from ....server.scheduler import describe_trigger
from ....store import ScheduleRecord, Store
from ...theme import LAUREL, STONE, starred
from ...widgets.confirm import ConfirmModal
from ._common import format_local, get_default_store, notify_summary, toggle_enabled


class SchedulesScreen(Screen[None]):
    """Lists the persistent schedules from the durable store.

    Schedules only fire while a daemon runs; the hint line probes the configured daemon address
    once (off the UI thread) so the screen is honest about whether the cadence is live. The probe
    can be disabled (``probe_daemon=False``) for deterministic tests and screenshots.
    """

    BINDINGS = [
        Binding("n", "new", "New"),
        Binding("p", "toggle_enabled", "Pause/Resume"),
        Binding("d", "delete", "Delete"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, store: Store | None = None, *, probe_daemon: bool = True) -> None:
        super().__init__()
        self._store = store if store is not None else get_default_store()
        self._probe_daemon = probe_daemon
        self._records: list[ScheduleRecord] = []
        self._suspended = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-body"):
            yield Static(starred("Schedules"), classes="console-title")
            yield Static(
                "Enter opens a schedule (history, manual fire). "
                "'n' creates one, 'p' pauses/resumes, 'd' deletes, 'r' refreshes.",
                classes="console-subtitle",
            )
            yield Static(id="schedules-daemon-hint", classes="console-subtitle")
            yield DataTable(id="schedules-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._show_daemon_state(healthy=False)
        self._refresh()
        if self._probe_daemon:
            self._probe()

    def on_screen_suspend(self) -> None:
        self._suspended = True

    def on_screen_resume(self) -> None:
        # Coming back from the detail or the form: reflect whatever they changed. Resume also
        # fires on the initial push, where re-clearing the freshly filled DataTable in the same
        # layout pass would freeze its column widths — hence the suspended flag.
        if self._suspended:
            self._suspended = False
            self._refresh()

    # ── data ──────────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._records = self._store.schedules.all()
        table = self.query_one("#schedules-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Trigger", "Notify", "Status", "Next run", "Last run")
        for record in self._records:
            status = (
                Text("✦ active", style=f"bold {LAUREL}")
                if record.enabled
                else Text("paused", style=STONE)
            )
            table.add_row(
                record.name,
                describe_trigger(record.trigger),
                notify_summary(record.notify),
                status,
                format_local(record.next_run_at) if record.enabled else "-",
                format_local(record.last_run_at),
                key=record.id,
            )

    def _highlighted(self) -> ScheduleRecord | None:
        table = self.query_one("#schedules-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return next((r for r in self._records if r.id == row_key.value), None)

    # ── daemon hint ───────────────────────────────────────────────────────────

    def _show_daemon_state(self, *, healthy: bool) -> None:
        try:
            hint = self.query_one("#schedules-daemon-hint", Static)
        except NoMatches:  # screen popped while the probe was in flight
            return
        if healthy:
            hint.update(Text("● daemon healthy — schedules fire on time", style=f"bold {LAUREL}"))
        else:
            hint.update(
                Text(
                    "○ no daemon — schedules only fire while `aetherius serve` runs (see Settings)",
                    style=STONE,
                )
            )

    @work(thread=True, exclusive=True)
    def _probe(self) -> None:
        import httpx

        try:
            healthy = httpx.get(f"{DaemonConfig().base_url}/health", timeout=1.0).status_code == 200
        except Exception:  # noqa: BLE001 - any failure simply means "not reachable"
            healthy = False
        if healthy:
            self.app.call_from_thread(self._show_daemon_state, healthy=True)

    # ── actions ───────────────────────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        record = next((r for r in self._records if r.id == event.row_key.value), None)
        if record is None:
            return
        from .detail import ScheduleDetailScreen

        self.app.push_screen(ScheduleDetailScreen(record.id, store=self._store))

    def action_new(self) -> None:
        from .form import ScheduleFormScreen

        self.app.push_screen(ScheduleFormScreen(store=self._store))

    # Named toggle_enabled: DOMNode already defines an action_toggle(attribute) we must not shadow.
    def action_toggle_enabled(self) -> None:
        record = self._highlighted()
        if record is None:
            return
        updated = toggle_enabled(self._store, record)
        state = "resumed" if updated.enabled else "paused"
        self.app.notify(f"Schedule {updated.name!r} {state}.", timeout=4)
        self._refresh()

    def action_delete(self) -> None:
        record = self._highlighted()
        if record is None:
            return

        def _on_confirm(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self._store.schedules.delete(record.id)
            self.app.notify(f"Schedule {record.name!r} deleted.", timeout=4)
            self._refresh()

        self.app.push_screen(
            ConfirmModal(
                f"Delete schedule {record.name!r}? Its run history is kept.",
                title="Delete schedule",
                confirm_label="Delete",
            ),
            _on_confirm,
        )

    def action_refresh(self) -> None:
        self._refresh()
        if self._probe_daemon:
            self._probe()
