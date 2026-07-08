"""Live JSON preview with real-time schema validation.

Renders the draft's assembled JSON and, below it, the issues from ``validate_draft`` — errors in
pompeian red, warnings in amber, or a laurel "ready to save" when clean. Colours come from the
theme; the widget owns no validation logic, it only displays what the builder reports.
"""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ....builder.factory import BlueprintDraft
from ....builder.validation import validate_draft
from ...theme import AMBER, LAUREL, POMPEIAN
from ...widgets.json_preview import JsonPreview


class BlueprintPreview(Vertical):
    """Syntax-highlighted JSON plus a live list of validation issues."""

    DEFAULT_CSS = """
    BlueprintPreview {
        height: auto;
        border: double $primary;
        padding: 0 1;
    }
    BlueprintPreview #preview-issues {
        height: auto;
        padding: 1 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield JsonPreview(id="preview-json")
        yield Static(id="preview-issues")

    def refresh_from(self, draft: BlueprintDraft) -> None:
        """Re-render the JSON and the issue list from *draft*."""
        self.query_one("#preview-json", JsonPreview).show(draft.to_data())
        self.query_one("#preview-issues", Static).update(self._issue_text(draft))

    def _issue_text(self, draft: BlueprintDraft) -> Text:
        issues = validate_draft(draft)
        if not issues:
            return Text("Valid — ready to save.", style=f"bold {LAUREL}")
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        text = Text()
        for issue in errors:
            text.append(f"✗ {issue.path}: {issue.message}\n", style=POMPEIAN)
        for issue in warnings:
            text.append(f"! {issue.path}: {issue.message}\n", style=AMBER)
        return text
