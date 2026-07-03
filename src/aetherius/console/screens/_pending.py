"""Shared base for the Console sections whose backing subsystem doesn't exist yet.

Kept intentionally minimal: a static explanation of what the screen will do and which
milestone it depends on, plus the standard chrome. No interactivity to fake.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class PendingScreen(Screen[None]):
    """Base class for a Console section pending its underlying subsystem."""

    title_text: str = ""
    description_text: str = ""
    milestone_text: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-placeholder"):
            yield Static(self.title_text, classes="console-title")
            yield Static(self.description_text, classes="console-subtitle")
            yield Static(f"Pending: {self.milestone_text}", classes="console-footer-hint")
        yield Footer()
