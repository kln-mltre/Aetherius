"""Home dashboard and main menu."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList, Static
from textual.widgets.option_list import Option

from ...core.runtime.engine import IMPLEMENTED_ACTS
from ...version import __version__
from ..theme import GOLD, LAUREL, MOTTO, STARFIELD, TYRIAN, VIOLET, WORDMARK, frieze, garland

# A gold star marks the sections that are usable today; a dot marks the pending ones.
_MENU: list[tuple[str, str]] = [
    ("library", "✦ Library — browse Blueprints and run one"),
    ("catalog", "✦ Catalog — the 4 Acts and their capabilities"),
    ("recorder", "✦ Recorder — capture a Blueprint by demonstration"),
    ("sessions", "· Sessions — profiles and warmup (coming soon)"),
    ("settings", "· Settings — daemon control and configuration (coming soon)"),
    ("builder", "· Blueprint Studio — guided Blueprint creation (coming soon)"),
]


def _banner() -> Text:
    text = Text(justify="center")
    text.append(frieze() + "\n", style=VIOLET)
    text.append(STARFIELD + "\n", style=GOLD)
    for row in WORDMARK:
        text.append(row + "\n", style=f"bold {GOLD}")
    text.append(garland() + "\n", style=LAUREL)
    text.append("✦  ", style=GOLD)
    text.append(MOTTO, style=f"italic {TYRIAN}")
    text.append("  ✦\n", style=GOLD)
    text.append(frieze(), style=VIOLET)
    return text


class HomeScreen(Screen[None]):
    """Landing screen: wordmark, Act availability, and the section menu."""

    # The menu must own the focus so arrow keys and Enter work immediately,
    # instead of the scroll container grabbing it.
    AUTO_FOCUS = "#home-menu"

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            yield Static(_banner(), id="home-banner")
            yield Static(
                f"v{__version__} · implemented acts: {', '.join(sorted(IMPLEMENTED_ACTS))} "
                "(the rest are visible in Catalog, not runnable yet)",
                id="home-status",
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
