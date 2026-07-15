"""Textual application: screen routing and global bindings for the Console."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App
from textual.binding import Binding

from .theme import AETHERIUS_THEME

if TYPE_CHECKING:
    from .daemon_control import DaemonController


class AetheriusConsoleApp(App[None]):
    """The Aetherius Console: navigation shell for Home, Library, Runs, Schedules, Catalog,
    Recorder, the Blueprint Studio and the daemon Settings (Sessions is still pending)."""

    CSS_PATH = Path(__file__).parent / "console.tcss"
    TITLE = "Aetherius"
    SUB_TITLE = "Console"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "pop_screen", "Back"),
        Binding("h", "go_home", "Home"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Created lazily the first time Settings is opened; a single session-scoped daemon so its
        # running state survives navigation. Its own atexit guard stops it when the process exits.
        self._daemon: DaemonController | None = None

    @property
    def daemon(self) -> DaemonController:
        """The session's local daemon controller (lazily created)."""
        if self._daemon is None:
            from .daemon_control import DaemonController

            self._daemon = DaemonController()
        return self._daemon

    def on_mount(self) -> None:
        self.register_theme(AETHERIUS_THEME)
        self.theme = "aetherius"

        from .screens.home import HomeScreen

        self.push_screen(HomeScreen())

    async def action_pop_screen(self) -> None:
        # screen_stack[0] is Textual's own default screen, never shown to the user (HomeScreen
        # is pushed on top of it in on_mount) — never pop back down to it.
        if len(self.screen_stack) > 2:
            self.pop_screen()

    def action_go_home(self) -> None:
        from .screens.home import HomeScreen

        while len(self.screen_stack) > 1:
            self.pop_screen()
        if not isinstance(self.screen, HomeScreen):
            self.push_screen(HomeScreen())
