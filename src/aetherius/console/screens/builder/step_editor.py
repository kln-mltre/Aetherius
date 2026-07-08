"""Add and edit steps through forms driven by the builder catalog.

``StepEditorModal`` renders one form field per parameter of the chosen action (a JSON text area for
object/array parameters), plus a "raw JSON" escape hatch so any parameter combination — including
actions the forms do not fully model — stays reachable. ``StepList`` is the read-only table of steps
with its add/edit/remove/reorder controls; it owns no state, the Studio screen does.
"""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Select, Static, Switch, TextArea

from ....builder.catalog import actions_for_act
from ....builder.factory import StepDraft
from ....core.actions.registry import get_spec
from ....core.actions.spec import ParamSpec

_JSON_KINDS = ("object", "array")


def _params_summary(params: dict[str, Any]) -> str:
    """A short, one-line digest of a step's parameters for the table."""
    parts = []
    for key, value in list(params.items())[:3]:
        text = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        parts.append(f"{key}={text[:24]}")
    return ", ".join(parts)


class StepEditorModal(ModalScreen[StepDraft | None]):
    """Edit one step: pick an action, fill its parameters, dismiss with the resulting StepDraft."""

    DEFAULT_CSS = """
    StepEditorModal { align: center middle; }
    StepEditorModal #step-dialog {
        width: 80%;
        max-width: 90;
        height: auto;
        max-height: 90%;
        border: double $primary;
        background: $surface;
        padding: 1 2;
    }
    StepEditorModal .step-field { height: auto; padding: 0 0 1 0; }
    StepEditorModal TextArea { height: 5; }
    StepEditorModal #step-raw { height: 8; }
    StepEditorModal .step-actions { height: auto; padding: 1 0 0 0; }
    """

    def __init__(self, act: str, step: StepDraft | None = None) -> None:
        super().__init__()
        self._act = act
        self._editing = step
        self._action = step.action if step and step.action else self._default_action()

    def _default_action(self) -> str:
        actions = actions_for_act(self._act)
        return actions[0].spec.name if actions else ""

    def compose(self) -> ComposeResult:
        options = [
            (info.spec.name + ("" if info.runnable else " (not runnable yet)"), info.spec.name)
            for info in actions_for_act(self._act)
        ]
        with VerticalScroll(id="step-dialog"):
            yield Static("Edit step", classes="console-title")
            with Vertical(classes="step-field"):
                yield Label("Action")
                yield Select(options, value=self._action, allow_blank=False, id="step-action")
            with Vertical(classes="step-field"):
                yield Label("Step id (optional)")
                yield Input(
                    value=(self._editing.id or "") if self._editing else "",
                    placeholder="e.g. login",
                    id="step-id",
                )
            with Horizontal(classes="step-field"):
                yield Switch(value=False, id="step-raw-toggle")
                yield Label("Edit raw JSON params")
            yield Vertical(id="step-params")
            yield TextArea(id="step-raw")
            with Horizontal(classes="step-actions"):
                yield Button("Save", id="step-ok", variant="primary")
                yield Button("Cancel", id="step-cancel")

    def on_mount(self) -> None:
        self.query_one("#step-raw", TextArea).display = False
        self._render_params(self._action)

    # ── Parameter form ────────────────────────────────────────────────────────

    def _render_params(self, action: str) -> None:
        container = self.query_one("#step-params", Vertical)
        container.remove_children()
        try:
            spec = get_spec(action)
        except Exception:
            return
        existing = self._editing.params if self._editing and self._editing.action == action else {}
        for param in spec.params:
            container.mount(self._field(param, existing.get(param.name)))

    def _field(self, param: ParamSpec, value: Any) -> Vertical:
        wid = f"param-{param.name}"
        label = (
            param.name
            + (" *" if param.required else "")
            + (f" — {param.help}" if param.help else "")
        )
        editor: Switch | TextArea | Input
        if param.kind == "boolean":
            editor = Switch(value=bool(value), id=wid)
        elif param.kind in _JSON_KINDS:
            text = json.dumps(value, indent=2) if value not in (None, "", {}, []) else ""
            editor = TextArea(text=text, id=wid)
        else:
            shown = "" if value in (None, "") else str(value)
            editor = Input(value=shown, placeholder=param.placeholder or param.kind, id=wid)
        return Vertical(Label(label), editor, classes="step-field")

    # ── Events ──────────────────────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "step-action":
            event.stop()
            self._action = str(event.value)
            self._render_params(self._action)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id != "step-raw-toggle":
            return
        event.stop()
        raw = self.query_one("#step-raw", TextArea)
        params_box = self.query_one("#step-params", Vertical)
        if event.value:
            raw.text = json.dumps(self._collect_fields() or {}, indent=2)
            raw.display = True
            params_box.display = False
        else:
            raw.display = False
            params_box.display = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "step-cancel":
            self.dismiss(None)
        elif event.button.id == "step-ok":
            self._save()

    # ── Collection ────────────────────────────────────────────────────────────

    def _collect_fields(self) -> dict[str, Any] | None:
        """Read the per-parameter widgets; None if a JSON field does not parse."""
        try:
            spec = get_spec(self._action)
        except Exception:
            return {}
        params: dict[str, Any] = {}
        for param in spec.params:
            widget = self.query_one(f"#param-{param.name}")
            if param.kind == "boolean":
                if isinstance(widget, Switch) and widget.value:
                    params[param.name] = True
            elif param.kind in _JSON_KINDS:
                text = widget.text.strip() if isinstance(widget, TextArea) else ""
                if text:
                    try:
                        params[param.name] = json.loads(text)
                    except ValueError:
                        self.app.notify(f"Invalid JSON in '{param.name}'.", severity="error")
                        return None
            else:
                value = widget.value.strip() if isinstance(widget, Input) else ""
                if value:
                    params[param.name] = self._coerce(param, value)
        return params

    @staticmethod
    def _coerce(param: ParamSpec, value: str) -> Any:
        if param.kind in ("number", "integer"):
            try:
                return int(value) if param.kind == "integer" else float(value)
            except ValueError:
                return value  # leave it; the preview's schema check will flag it
        return value

    def _save(self) -> None:
        if self.query_one("#step-raw-toggle", Switch).value:
            text = self.query_one("#step-raw", TextArea).text.strip()
            try:
                params = json.loads(text) if text else {}
            except ValueError:
                self.app.notify("Invalid raw JSON.", severity="error")
                return
            if not isinstance(params, dict):
                self.app.notify("Raw params must be a JSON object.", severity="error")
                return
        else:
            collected = self._collect_fields()
            if collected is None:
                return
            params = collected
        step_id = self.query_one("#step-id", Input).value.strip() or None
        self.dismiss(StepDraft(action=self._action, id=step_id, params=params))


class StepList(Vertical):
    """The steps table with add / edit / remove / reorder controls (a pure view of the draft)."""

    DEFAULT_CSS = """
    StepList { height: auto; }
    StepList DataTable { height: auto; max-height: 16; }
    StepList .step-list-actions { height: auto; padding: 1 0 0 0; }
    """

    def compose(self) -> ComposeResult:
        yield DataTable(id="studio-steps", cursor_type="row")
        with Horizontal(classes="step-list-actions"):
            yield Button("+ Add", id="studio-step-add")
            yield Button("Edit", id="studio-step-edit")
            yield Button("Remove", id="studio-step-remove")
            yield Button("↑", id="studio-step-up")
            yield Button("↓", id="studio-step-down")

    def on_mount(self) -> None:
        self.query_one("#studio-steps", DataTable).add_columns("#", "Action", "Id", "Parameters")

    def refresh_from(self, steps: list[StepDraft]) -> None:
        table = self.query_one("#studio-steps", DataTable)
        table.clear()
        for index, step in enumerate(steps):
            table.add_row(str(index + 1), step.action, step.id or "", _params_summary(step.params))

    @property
    def selected_index(self) -> int | None:
        table = self.query_one("#studio-steps", DataTable)
        if table.row_count == 0:
            return None
        return table.cursor_row
