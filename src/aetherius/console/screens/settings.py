"""Daemon control (start and stop) and configuration.

Starts and stops the local daemon (`aetherius serve`) without leaving the terminal, and shows its
bind address and auth state. The daemon is session-scoped: it keeps running as you navigate the
Console and is stopped when the Console exits. For a daemon that outlives the Console, run
`aetherius serve` in its own terminal instead.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

from rich.text import Text

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

from ..theme import LAUREL, STONE, starred

if TYPE_CHECKING:
    from ..app import AetheriusConsoleApp
    from ..daemon_control import DaemonController


class SettingsScreen(Screen[None]):
    """Start and stop the local daemon, and see its configuration."""

    DEFAULT_CSS = """
    SettingsScreen #settings-status, SettingsScreen #settings-config {
        padding: 1 2 0 2;
    }
    SettingsScreen #settings-start, SettingsScreen #settings-stop {
        border: double $accent;
        background: $panel;
        color: $accent;
        text-style: bold;
        padding: 0 3;
    }
    SettingsScreen #settings-start:hover, SettingsScreen #settings-stop:hover {
        background: $accent 20%;
    }
    SettingsScreen #settings-start:disabled, SettingsScreen #settings-stop:disabled {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            yield Static(starred("Settings"), classes="console-title")
            yield Static(
                "Start or stop the local daemon that exposes the engine over HTTP and WebSocket. "
                "It binds to loopback and is stopped when the Console exits.",
                classes="console-subtitle",
            )
            yield Static(id="settings-status")
            yield Static(id="settings-config")
            with Horizontal(classes="run-actions"):
                yield Button("✦ Start daemon ✦", id="settings-start", variant="primary")
                yield Button("Stop daemon", id="settings-stop")
            yield Static(
                "Once running, drive it from any language via the SDKs "
                "(see docs/daemon.md). Configure host/port/token with AETHERIUS_DAEMON_*.",
                classes="console-footer-hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh()

    @property
    def _controller(self) -> DaemonController:
        return cast("AetheriusConsoleApp", self.app).daemon

    def _refresh(self, health: str = "") -> None:
        """Repaint status, config and button states from the controller. Tolerant of a popped screen."""
        controller = self._controller
        running = controller.is_running()
        config = controller.config
        try:
            status = self.query_one("#settings-status", Static)
            if running:
                line = Text.assemble(("● running", f"bold {LAUREL}"), f"  {controller.base_url}")
                if health:
                    line.append(f" · {health}")
                status.update(line)
            else:
                status.update(Text("● stopped", style=f"bold {STONE}"))
            self.query_one("#settings-config", Static).update(
                f"host {config.host} · port {config.port} · "
                f"token {'set' if config.token else 'none'}"
            )
            self.query_one("#settings-start", Button).disabled = running
            self.query_one("#settings-stop", Button).disabled = not running
        except NoMatches:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-start":
            self._controller.start()
            self.app.notify(f"Daemon starting on {self._controller.base_url}…", timeout=4)
            self._refresh()
            self._probe_health()
        elif event.button.id == "settings-stop":
            self._controller.stop()
            self.app.notify("Daemon stopped.", timeout=3)
            self._refresh()

    @work(thread=True, exclusive=True)
    def _probe_health(self) -> None:
        """Poll health off the UI thread until the daemon answers or exits."""
        for _ in range(50):
            if self._controller.healthy():
                self.app.call_from_thread(self._on_healthy)
                return
            if not self._controller.is_running():
                self.app.call_from_thread(self._on_exited)
                return
            time.sleep(0.1)

    def _on_healthy(self) -> None:
        self._refresh(health="healthy")
        self.app.notify("Daemon is healthy.", timeout=3)

    def _on_exited(self) -> None:
        self._refresh()
        self.app.notify("Daemon failed to start.", severity="error", timeout=6)
