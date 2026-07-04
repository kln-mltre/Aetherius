"""Shared base for the Console sections whose backing subsystem doesn't exist yet.

Kept intentionally minimal: a static explanation of what the screen will do and which
milestone it depends on, framed by mosaic columns. No interactivity to fake.
"""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from ..theme import TYRIAN, frieze, frieze_column, starred


class PendingScreen(Screen[None]):
    """Base class for a Console section pending its underlying subsystem."""

    title_text: str = ""
    description_text: str = ""
    milestone_text: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="console-placeholder"):
            with Horizontal(classes="pending-frame"):
                yield Static(Text(frieze_column(7), style=TYRIAN), classes="pending-column")
                with Vertical(classes="pending-content"):
                    yield Static(Text(frieze(24), style=TYRIAN))
                    yield Static(starred(self.title_text), classes="console-title")
                    yield Static(self.description_text, classes="console-subtitle")
                    yield Static(f"Pending: {self.milestone_text}", classes="console-footer-hint")
                    yield Static(Text(frieze(24), style=TYRIAN))
                yield Static(Text(frieze_column(7), style=TYRIAN), classes="pending-column")
        yield Footer()
