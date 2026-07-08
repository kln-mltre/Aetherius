"""Blueprint Studio orchestrator screen.

Guided creation and editing of a Blueprint without hand-writing JSON: pick an Act, declare inputs
and secrets, assemble steps through forms, set the durable options, and watch a live JSON preview
validated against the schema. The screen owns the single :class:`BlueprintDraft`; its child editors
report changes, it re-reads them into the draft and refreshes the preview. Everything is local and
fast, so no worker is needed. Opened with a *path* it edits that file in place; otherwise it creates
a new one under ``./blueprints``.
"""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from ....builder.factory import BlueprintDraft, StepDraft, save_blueprint
from ....builder.templates import list_templates, template_draft
from ....core.blueprint.loader import load_blueprint
from ....core.errors import AetheriusError
from ...theme import starred
from .act_picker import ActPicker
from .io_editor import InputsEditor, VarsOutputsEditor
from .options_editor import OptionsEditor
from .preview import BlueprintPreview
from .step_editor import StepEditorModal, StepList


class BlueprintStudioScreen(Screen[None]):
    """Assemble or edit a Blueprint through forms, with a live validated JSON preview."""

    AUTO_FOCUS = "#studio-name"

    DEFAULT_CSS = """
    BlueprintStudioScreen #studio-save {
        border: double $accent;
        background: $panel;
        color: $accent;
        text-style: bold;
        padding: 0 3;
        margin: 1 0;
    }
    BlueprintStudioScreen #studio-save:hover { background: $accent 20%; }
    BlueprintStudioScreen .studio-field { height: auto; padding: 1 1 0 1; }
    BlueprintStudioScreen #studio-template-row { height: auto; padding: 1 1 0 1; }
    """

    def __init__(self, path: Path | str | None = None) -> None:
        super().__init__()
        self._edit_path: Path | None = Path(path) if path is not None else None
        self._draft = self._initial_draft()

    def _initial_draft(self) -> BlueprintDraft:
        if self._edit_path is None:
            return BlueprintDraft()
        # Prefer the canonical loader; fall back to a raw read so a well-formed-but-act-pending file
        # still opens for editing. A truly unparseable file is caught by Library before we get here.
        try:
            return BlueprintDraft.from_data(load_blueprint(self._edit_path).model_dump())
        except AetheriusError:
            data = json.loads(Path(self._edit_path).read_text(encoding="utf-8"))
            return BlueprintDraft.from_data(data)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(classes="console-body"):
            title = "Blueprint Studio" + (" — editing" if self._edit_path else "")
            yield Static(starred(title), classes="console-title")
            yield Static(
                "Pick an Act, declare inputs, assemble steps, set options. The JSON preview is "
                "validated live; Save writes it to ./blueprints (or overwrites the edited file).",
                classes="console-subtitle",
            )
            if self._edit_path is None:
                with Horizontal(id="studio-template-row"):
                    yield Select(
                        [(t.title + f" ({t.act})", t.key) for t in list_templates()],
                        prompt="Start from a template…",
                        id="studio-template",
                    )
                    yield Button("Load template", id="studio-load-template")
            with VerticalScroll(classes="studio-field"):
                yield Label("Name (e.g. domain.task)")
                yield Input(value=self._draft.name, placeholder="domain.task", id="studio-name")
                yield Label("Description (optional)")
                yield Input(value=self._draft.description or "", id="studio-description")
            yield ActPicker(self._draft.act)
            yield InputsEditor()
            steps = StepList()
            steps.border_title = "✦ Steps ✦"
            yield steps
            yield OptionsEditor()
            yield VarsOutputsEditor()
            preview = BlueprintPreview()
            preview.border_title = "✦ Live preview ✦"
            yield preview
            yield Button("✦ Save Blueprint ✦", id="studio-save", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(InputsEditor).load(self._draft.inputs, self._draft.secrets)
        self.query_one(OptionsEditor).load(self._draft.options)
        self.query_one(VarsOutputsEditor).load(self._draft.vars, self._draft.outputs)
        self._render_steps()
        # Render straight from the draft: the editors were just loaded from it, and their freshly
        # mounted children are not queryable yet, so a sync-back would momentarily read them empty.
        self.query_one(BlueprintPreview).refresh_from(self._draft)

    # ── Draft synchronisation ───────────────────────────────────────────────

    def _sync_from_editors(self) -> None:
        """Read every editor back into the draft (steps are mutated in place elsewhere)."""
        self._draft.name = self.query_one("#studio-name", Input).value.strip()
        description = self.query_one("#studio-description", Input).value.strip()
        self._draft.description = description or None
        self._draft.inputs, self._draft.secrets = self.query_one(InputsEditor).collect()
        self._draft.options = self.query_one(OptionsEditor).collect()
        self._draft.vars, self._draft.outputs = self.query_one(VarsOutputsEditor).collect()

    def _refresh_preview(self) -> None:
        self._sync_from_editors()
        self.query_one(BlueprintPreview).refresh_from(self._draft)

    def _render_steps(self) -> None:
        self.query_one(StepList).refresh_from(self._draft.steps)

    # ── Events ────────────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        self._refresh_preview()

    def on_switch_changed(self, event: object) -> None:
        self._refresh_preview()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "studio-template":
            return  # loaded explicitly via the button, not on selection
        self._refresh_preview()

    def on_text_area_changed(self, event: object) -> None:
        self._refresh_preview()

    def on_act_picker_act_changed(self, event: ActPicker.ActChanged) -> None:
        self._draft.act = event.act
        self._render_steps()
        self._refresh_preview()

    def on_inputs_editor_changed(self, event: InputsEditor.Changed) -> None:
        self._refresh_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "studio-load-template":
            self._load_template()
        elif button == "studio-step-add":
            self.app.push_screen(StepEditorModal(self._draft.act), self._on_step_added)
        elif button == "studio-step-edit":
            self._edit_selected_step()
        elif button == "studio-step-remove":
            self._remove_selected_step()
        elif button == "studio-step-up":
            self._move_selected_step(-1)
        elif button == "studio-step-down":
            self._move_selected_step(1)
        elif button == "studio-save":
            self._save()

    # ── Steps ───────────────────────────────────────────────────────────────

    def _on_step_added(self, step: StepDraft | None) -> None:
        if step is not None:
            self._draft.steps.append(step)
            self._render_steps()
            self._refresh_preview()

    def _edit_selected_step(self) -> None:
        index = self.query_one(StepList).selected_index
        if index is None:
            return

        def _apply(step: StepDraft | None) -> None:
            if step is not None:
                self._draft.steps[index] = step
                self._render_steps()
                self._refresh_preview()

        self.app.push_screen(StepEditorModal(self._draft.act, self._draft.steps[index]), _apply)

    def _remove_selected_step(self) -> None:
        index = self.query_one(StepList).selected_index
        if index is not None:
            self._draft.remove_step(index)
            self._render_steps()
            self._refresh_preview()

    def _move_selected_step(self, delta: int) -> None:
        index = self.query_one(StepList).selected_index
        if index is not None:
            self._draft.move_step(index, delta)
            self._render_steps()
            self._refresh_preview()

    # ── Template & save ─────────────────────────────────────────────────────

    def _load_template(self) -> None:
        select = self.query_one("#studio-template", Select)
        if select.value is Select.BLANK:
            return
        self._draft = template_draft(str(select.value))
        self.query_one("#studio-name", Input).value = self._draft.name
        self.query_one("#studio-description", Input).value = self._draft.description or ""
        self.query_one(ActPicker).query_one("#act-select", Select).value = self._draft.act
        self.query_one(InputsEditor).load(self._draft.inputs, self._draft.secrets)
        self.query_one(OptionsEditor).load(self._draft.options)
        self.query_one(VarsOutputsEditor).load(self._draft.vars, self._draft.outputs)
        self._render_steps()
        self._refresh_preview()
        self.app.notify(f"Loaded template {select.value}.")

    def _save(self) -> None:
        self._sync_from_editors()
        if self.query_one(VarsOutputsEditor).has_errors:
            self.app.notify("Fix the invalid JSON in vars/outputs first.", severity="warning")
            return
        try:
            path = save_blueprint(self._draft, path=self._edit_path)
        except AetheriusError as exc:
            self.app.notify(str(exc), title="Cannot save", severity="error", timeout=8)
            return
        self._edit_path = path  # subsequent saves overwrite the same file
        self.app.notify(f"Saved {path}", timeout=6)
