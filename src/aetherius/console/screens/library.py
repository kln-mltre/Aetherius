"""Browse the Blueprint library: discover, validate, and open one into the Runs screen."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ..theme import ACT_LABELS, LAUREL, PER_ACT_COLOR, POMPEIAN, starred
from .library_scan import BlueprintEntry, discover_blueprint_dirs, scan_blueprints


class LibraryScreen(Screen[None]):
    """Lists every Blueprint found under the discovered directories."""

    BINDINGS = [Binding("r", "rescan", "Rescan")]

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[BlueprintEntry] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-body"):
            yield Static(starred("Blueprint Library"), classes="console-title")
            yield Static(
                "Select a valid Blueprint and press Enter to open it in Runs.",
                classes="console-subtitle",
            )
            yield DataTable(id="library-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._rescan()

    def action_rescan(self) -> None:
        self._rescan()

    def _rescan(self) -> None:
        dirs = discover_blueprint_dirs()
        self._entries = scan_blueprints(dirs)
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Act", "Status", "Path")
        for entry in self._entries:
            if entry.error:
                act_cell: str | Text = "-"
                status_cell: str | Text = Text(f"invalid: {entry.error}", style=f"bold {POMPEIAN}")
            else:
                assert entry.blueprint is not None and entry.act is not None
                label = ACT_LABELS.get(entry.act, entry.act)
                color = PER_ACT_COLOR.get(entry.act, "white")
                act_cell = Text(label, style=color)
                status_cell = Text("valid", style=f"bold {LAUREL}")
            name = entry.blueprint.name if entry.blueprint else entry.path.stem
            table.add_row(name, act_cell, status_cell, str(entry.path), key=str(entry.path))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        entry = next((e for e in self._entries if str(e.path) == str(event.row_key.value)), None)
        if entry is None:
            return
        if entry.error or entry.blueprint is None:
            self.app.notify(
                f"Cannot open an invalid Blueprint: {entry.error}", severity="error", timeout=8
            )
            return

        from .runs import RunsScreen

        self.app.push_screen(RunsScreen(entry.path))
