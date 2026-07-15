"""Generic confirmation dialog for destructive actions (delete a schedule, ...)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from ..theme import starred


class ConfirmModal(ModalScreen[bool]):
    """Ask the user to confirm an action; dismisses with True (confirm) or False (cancel)."""

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    ConfirmModal #confirm-dialog {
        width: 60%;
        max-width: 70;
        height: auto;
        border: double $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfirmModal #confirm-message { height: auto; padding: 0 0 1 0; }
    ConfirmModal .step-actions { height: auto; padding: 1 0 0 0; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self, message: str, *, title: str = "Confirm", confirm_label: str = "Confirm"
    ) -> None:
        super().__init__()
        self._message = message
        self._title = title
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Static(starred(self._title), classes="console-title")
            yield Static(self._message, id="confirm-message")
            with Horizontal(classes="step-actions"):
                yield Button(self._confirm_label, id="confirm-ok", variant="primary")
                yield Button("Cancel", id="confirm-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm-ok")

    def action_cancel(self) -> None:
        self.dismiss(False)
