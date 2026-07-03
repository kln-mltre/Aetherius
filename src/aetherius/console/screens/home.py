"""Home dashboard and main menu."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ...core.runtime.engine import IMPLEMENTED_ACTS
from ...version import __version__

_MENU: list[tuple[str, str]] = [
    ("library", "Library — browse and validate Blueprints"),
    ("runs", "Runs — launch a Blueprint (open one from Library)"),
    ("catalog", "Catalog — the 4 Acts and their capabilities"),
    ("sessions", "Sessions — profiles and warmup (coming soon)"),
    ("settings", "Settings — daemon control and configuration (coming soon)"),
    ("recorder", "Recorder — capture a Blueprint by demonstration (coming soon)"),
    ("builder", "Blueprint Studio — guided Blueprint creation (coming soon)"),
]


class HomeScreen(Screen[None]):
    """Landing screen: package version, Act availability, and the section menu."""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-body"):
            yield Static(f"Aetherius v{__version__}", classes="console-title")
            yield Static(
                f"Implemented Acts: {', '.join(sorted(IMPLEMENTED_ACTS))} "
                "(the rest are visible in Catalog, not runnable yet).",
                classes="console-subtitle",
            )
            yield OptionList(
                *(Option(label, id=key) for key, label in _MENU),
                id="home-menu",
            )
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        key = event.option.id
        if key == "library":
            from .library import LibraryScreen

            self.app.push_screen(LibraryScreen())
        elif key == "runs":
            from .library import LibraryScreen

            self.app.notify("Pick a Blueprint from Library first.", timeout=5)
            self.app.push_screen(LibraryScreen())
        elif key == "catalog":
            from .catalog import CatalogScreen

            self.app.push_screen(CatalogScreen())
        elif key == "sessions":
            from .sessions import SessionsScreen

            self.app.push_screen(SessionsScreen())
        elif key == "settings":
            from .settings import SettingsScreen

            self.app.push_screen(SettingsScreen())
        elif key == "recorder":
            from .recorder import RecorderScreen

            self.app.push_screen(RecorderScreen())
        elif key == "builder":
            from .builder.screen import BlueprintStudioScreen

            self.app.push_screen(BlueprintStudioScreen())
