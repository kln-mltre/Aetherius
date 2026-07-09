"""Editors for a Blueprint's inputs, secrets, vars and outputs.

``InputsEditor`` renders typed input rows (name, type, required) plus a secrets list, and preserves
any extra keys of an existing input (default, format, description) so editing a file never drops
them. ``VarsOutputsEditor`` edits the two free-form maps as JSON, keeping the last valid parse so the
live preview stays consistent while the user is mid-edit.
"""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Input, Label, Select, Switch, TextArea

_INPUT_TYPES = ("string", "number", "integer", "boolean", "date", "path", "object", "array")


class _InputRow(Horizontal):
    """One input declaration; keeps the original spec's extra keys to stay lossless."""

    DEFAULT_CSS = "_InputRow { height: auto; padding: 0 0 1 0; } _InputRow Input { width: 20; }"

    def __init__(self, name: str = "", spec: dict[str, Any] | None = None) -> None:
        super().__init__()
        spec = dict(spec or {})
        self._name = name
        self._type = str(spec.pop("type", "string"))
        self._required = bool(spec.pop("required", False))
        self._extra = spec  # format / default / description preserved verbatim

    def compose(self) -> ComposeResult:
        yield Input(value=self._name, placeholder="name", classes="io-input-name")
        yield Select(
            [(t, t) for t in _INPUT_TYPES],
            value=self._type,
            allow_blank=False,
            classes="io-input-type",
        )
        yield Switch(value=self._required, classes="io-input-required")
        yield Label("required")
        yield Button("✕", classes="io-input-remove")

    def collect(self) -> tuple[str, dict[str, Any]] | None:
        """Return (name, spec), or None when the row has no name yet or is still mounting."""
        if not self.query(".io-input-name"):
            return None  # children not composed yet (just mounted)
        name = self.query_one(".io-input-name", Input).value.strip()
        if not name:
            return None
        spec: dict[str, Any] = dict(self._extra)
        spec["type"] = str(self.query_one(".io-input-type", Select).value)
        if self.query_one(".io-input-required", Switch).value:
            spec["required"] = True
        return name, spec


class InputsEditor(Vertical):
    """Typed input rows plus a comma-separated secrets list."""

    DEFAULT_CSS = """
    InputsEditor { height: auto; padding: 1 1 0 1; }
    /* Without this the empty rows container grabs 1fr and inflates the whole editor. */
    InputsEditor #io-input-rows { height: auto; }
    InputsEditor #io-add-input { margin: 0 0 1 0; }
    """

    class Changed(Message):
        """Posted when a row is added or removed (text edits bubble as Input/Switch changes)."""

    def compose(self) -> ComposeResult:
        yield Label("Inputs")
        yield Vertical(id="io-input-rows")
        yield Button("+ Add input", id="io-add-input")
        yield Label("Secrets (comma-separated names)")
        yield Input(placeholder="password, api_key", id="io-secrets")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "io-add-input":
            event.stop()
            self.query_one("#io-input-rows", Vertical).mount(_InputRow())
            self.post_message(self.Changed())
        elif event.button.has_class("io-input-remove"):
            event.stop()
            row = event.button.parent
            if isinstance(row, _InputRow):
                row.remove()
            self.post_message(self.Changed())

    def collect(self) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """Read the rows and the secrets field into (inputs, secrets)."""
        inputs: dict[str, dict[str, Any]] = {}
        for row in self.query(_InputRow):
            collected = row.collect()
            if collected is not None:
                inputs[collected[0]] = collected[1]
        raw = self.query_one("#io-secrets", Input).value
        secrets = [s.strip() for s in raw.split(",") if s.strip()]
        return inputs, secrets

    def load(self, inputs: dict[str, dict[str, Any]], secrets: list[str]) -> None:
        rows = self.query_one("#io-input-rows", Vertical)
        rows.remove_children()
        for name, spec in inputs.items():
            rows.mount(_InputRow(name, spec))
        self.query_one("#io-secrets", Input).value = ", ".join(secrets)


class VarsOutputsEditor(Vertical):
    """JSON editors for the two free-form maps, tolerant of mid-edit invalid JSON."""

    DEFAULT_CSS = """
    VarsOutputsEditor { height: auto; padding: 1 1 0 1; }
    VarsOutputsEditor TextArea { height: 6; margin: 0 0 1 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._vars: dict[str, Any] = {}
        self._outputs: dict[str, Any] = {}
        self._invalid: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Label("Vars (JSON object)")
        yield TextArea(id="io-vars")
        yield Label("Outputs (JSON object)")
        yield TextArea(id="io-outputs")

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        which = event.text_area.id
        parsed = self._parse(event.text_area.text)
        if parsed is None:
            self._invalid.add(str(which))
            return
        self._invalid.discard(str(which))
        if which == "io-vars":
            self._vars = parsed
        else:
            self._outputs = parsed

    @staticmethod
    def _parse(text: str) -> dict[str, Any] | None:
        if not text.strip():
            return {}
        try:
            value = json.loads(text)
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    @property
    def has_errors(self) -> bool:
        return bool(self._invalid)

    def collect(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return the last valid (vars, outputs)."""
        return dict(self._vars), dict(self._outputs)

    def load(self, vars: dict[str, Any], outputs: dict[str, Any]) -> None:
        self._vars, self._outputs, self._invalid = dict(vars), dict(outputs), set()
        self.query_one("#io-vars", TextArea).text = json.dumps(vars, indent=2) if vars else ""
        self.query_one("#io-outputs", TextArea).text = (
            json.dumps(outputs, indent=2) if outputs else ""
        )
