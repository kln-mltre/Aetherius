"""Explore and explain the four Acts and their action capabilities."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ..theme import ACT_LABELS, LAUREL, PER_ACT_COLOR, STONE, starred
from ...core.actions.base import ACT_CAPABILITIES
from ...core.runtime.engine import IMPLEMENTED_ACTS

_ACT_ORDER = ("vector", "continuum", "oracle", "phantom")

_ACT_DESCRIPTIONS: dict[str, str] = {
    "vector": "HTTP/API requests. Fastest, no browser. The 'axios' case.",
    "continuum": "Scripted browser (Playwright): login, JS, session, DOM. Stable selectors.",
    "oracle": "Vision-guided browser with discretion. Locates fragile/obfuscated UI on screen.",
    "phantom": "Autonomous agent: perceive, reason, act in a loop. Unscripted goals.",
}


class CatalogScreen(Screen[None]):
    """Read-only reference: the 4 Acts, their status, and their supported actions."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-body"):
            yield Static(starred("Act Catalog"), classes="console-title")
            yield Static(
                "Each Blueprint declares one Act; a step using an unsupported action fails "
                "validation before it ever runs.",
                classes="console-subtitle",
            )
            yield DataTable(id="catalog-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#catalog-table", DataTable)
        table.add_columns("Act", "Status", "Description", "Actions")
        for act in _ACT_ORDER:
            label = ACT_LABELS[act]
            color = PER_ACT_COLOR[act]
            status = (
                Text("implemented", style=f"bold {LAUREL}")
                if act in IMPLEMENTED_ACTS
                else Text("not runnable yet", style=STONE)
            )
            capabilities = ", ".join(sorted(cap.value for cap in ACT_CAPABILITIES[act]))
            table.add_row(
                Text(label, style=color),
                status,
                _ACT_DESCRIPTIONS[act],
                capabilities,
            )
