"""Browse the Blueprint library: discover, validate, and open one into the Runs screen."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ...core.runtime.engine import IMPLEMENTED_ACTS
from ..theme import ACT_LABELS, AMBER, LAUREL, POMPEIAN, STONE, act_color, starred
from .library_scan import (
    BlueprintEntry,
    EntryStatus,
    discover_blueprint_dirs,
    entry_status,
    scan_blueprints,
)

# How each status reads in the table: label + colour. Runnable is the only "go" state.
_STATUS_STYLE: dict[EntryStatus, tuple[str, str]] = {
    EntryStatus.READY: ("ready", f"bold {LAUREL}"),
    EntryStatus.ACT_PENDING: ("act pending", AMBER),
    EntryStatus.INVALID: ("invalid", f"bold {POMPEIAN}"),
}


class LibraryScreen(Screen[None]):
    """Lists every Blueprint found under the discovered directories."""

    BINDINGS = [
        Binding("r", "rescan", "Rescan"),
        Binding("e", "edit", "Edit in Studio"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: list[BlueprintEntry] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-body"):
            yield Static(starred("Blueprint Library"), classes="console-title")
            yield Static(
                "Enter opens a Blueprint in Runs. 'ready' runs now; 'act pending' is well-formed "
                "but its Act has no driver yet; 'invalid' fails the schema or its Act's actions.",
                classes="console-subtitle",
            )
            yield DataTable(id="library-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        self._rescan()

    def action_rescan(self) -> None:
        self._rescan()

    def action_edit(self) -> None:
        """Open the highlighted Blueprint in the Studio (any file that parsed)."""
        entry = self._highlighted_entry()
        if entry is None:
            return
        if entry.blueprint is None:
            self.app.notify(
                "This file does not parse — edit the JSON by hand.", severity="error", timeout=8
            )
            return
        from .builder.screen import BlueprintStudioScreen

        self.app.push_screen(BlueprintStudioScreen(entry.path))

    def _highlighted_entry(self) -> BlueprintEntry | None:
        table = self.query_one("#library-table", DataTable)
        if table.row_count == 0:
            return None
        row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        return next((e for e in self._entries if str(e.path) == str(row_key.value)), None)

    def _rescan(self) -> None:
        dirs = discover_blueprint_dirs()
        self._entries = scan_blueprints(dirs)
        self._render_table()

    def _render_table(self) -> None:
        table = self.query_one("#library-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Act", "Status", "Path")
        for entry in self._entries:
            status = entry_status(entry)
            label_text, style = _STATUS_STYLE[status]
            # Surface the concrete error inline; keep the muted note for a pending Act.
            if status is EntryStatus.INVALID and entry.error:
                label_text = f"invalid: {entry.error}"
            elif status is EntryStatus.ACT_PENDING:
                label_text = "act pending — no driver yet"
            status_cell = Text(label_text, style=style)

            if entry.act is None:
                act_cell: str | Text = Text("-", style=STONE)
            else:
                act_label = ACT_LABELS.get(entry.act, entry.act)
                act_cell = Text(
                    act_label, style=act_color(entry.act, entry.act in IMPLEMENTED_ACTS)
                )

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
