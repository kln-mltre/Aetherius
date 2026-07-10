"""Explore and explain the four Acts and their action capabilities."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ..theme import ACT_LABELS, LAUREL, STONE, act_color, starred
from ...builder.catalog import act_infos, actions_for_act


class CatalogScreen(Screen[None]):
    """Read-only reference: the 4 Acts, their status, and their supported actions.

    A pure projection of the shared builder catalogue (``builder/catalog.py``), so the Act
    descriptions and the runnable/pending status never drift from what the Studio offers.
    """

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
        for info in act_infos():
            color = act_color(info.act, info.implemented)
            status = (
                Text("implemented", style=f"bold {LAUREL}")
                if info.implemented
                else Text("not runnable yet", style=STONE)
            )
            # A dagger marks actions declared but not yet dispatched by the Act's driver.
            names = [a.spec.name + ("" if a.runnable else " †") for a in actions_for_act(info.act)]
            table.add_row(
                Text(ACT_LABELS[info.act], style=color),
                status,
                info.summary,
                ", ".join(names),
            )
