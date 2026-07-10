"""Generic form widget rendering fields from a Blueprint's inputs and secrets."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, Switch

from ...core.blueprint.models import InputSpec

_INPUT_ID_PREFIX = "bp-input-"
_SECRET_ID_PREFIX = "bp-secret-"


class BlueprintInputForm(Vertical):
    """Renders one field per declared Blueprint input and secret.

    Boolean inputs get a Switch; everything else gets a text Input (secrets are masked).
    ``collect()`` reads the current values back out; ``validation_errors()`` runs a client-side
    pre-check for required fields before a run is allowed to start.
    """

    # height: auto everywhere: fields must keep their natural height and let the screen scroll,
    # never get squeezed into overlapping fractions when the terminal is short.
    DEFAULT_CSS = """
    BlueprintInputForm {
        height: auto;
        padding: 1 1 0 1;
    }
    BlueprintInputForm .form-field {
        height: auto;
        padding-bottom: 1;
    }
    """

    def __init__(
        self,
        inputs: dict[str, InputSpec],
        secrets: list[str],
        available_secrets: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._inputs = inputs
        self._secrets = secrets
        # Secrets already resolvable from the environment (.env): shown optional, not required.
        self._available_secrets = available_secrets or set()

    def compose(self) -> ComposeResult:
        for name, spec in self._inputs.items():
            label = name + (" *" if spec.required else "")
            if spec.description:
                label += f" - {spec.description}"
            with Vertical(classes="form-field"):
                yield Label(label)
                if spec.type == "boolean":
                    yield Switch(value=bool(spec.default), id=_INPUT_ID_PREFIX + name)
                else:
                    default = "" if spec.default is None else str(spec.default)
                    yield Input(
                        value=default,
                        placeholder=spec.type,
                        id=_INPUT_ID_PREFIX + name,
                    )
        for name in self._secrets:
            from_env = name in self._available_secrets
            label = f"{name} (secret · loaded from .env)" if from_env else f"{name} (secret)"
            placeholder = "leave blank to use .env value" if from_env else ""
            with Vertical(classes="form-field"):
                yield Label(label)
                yield Input(password=True, placeholder=placeholder, id=_SECRET_ID_PREFIX + name)

    def collect(self) -> tuple[dict[str, Any], dict[str, str]]:
        """Read the current form values into (inputs, secrets) dicts."""
        input_values: dict[str, Any] = {}
        for name, spec in self._inputs.items():
            widget_id = "#" + _INPUT_ID_PREFIX + name
            if spec.type == "boolean":
                input_values[name] = self.query_one(widget_id, Switch).value
            else:
                value = self.query_one(widget_id, Input).value
                if value:
                    input_values[name] = value

        secret_values: dict[str, str] = {}
        for name in self._secrets:
            value = self.query_one("#" + _SECRET_ID_PREFIX + name, Input).value
            if value:
                secret_values[name] = value

        return input_values, secret_values

    def validation_errors(self) -> list[str]:
        """Client-side pre-check; the engine's own input resolution remains authoritative."""
        input_values, _ = self.collect()
        errors = []
        for name, spec in self._inputs.items():
            if spec.required and name not in input_values:
                errors.append(f"Missing required input '{name}'.")
        return errors
