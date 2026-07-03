"""Renders the final Result of a Blueprint run: status, per-step outcomes, and outputs."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ...core.runtime.result import Result, RunStatus
from .json_preview import JsonPreview

_STATUS_STYLE: dict[RunStatus, str] = {
    RunStatus.SUCCESS: "bold green",
    RunStatus.FAILED: "bold red",
    RunStatus.PARTIAL: "bold yellow",
}


class RunSummary(Vertical):
    """Composed once, then populated by `show(result)` after a worker completes."""

    def compose(self) -> ComposeResult:
        yield Static("", id="run-summary-status")
        yield DataTable(id="run-summary-steps", cursor_type="none")
        yield JsonPreview(id="run-summary-outputs")

    def on_mount(self) -> None:
        self.query_one("#run-summary-steps", DataTable).add_columns(
            "Step", "Action", "Status", "Duration"
        )

    def show(self, result: Result) -> None:
        status_line = self.query_one("#run-summary-status", Static)
        style = _STATUS_STYLE.get(result.status, "")
        text = Text(f"{result.status.value} — {result.duration_ms:.1f} ms", style=style)
        if result.error:
            text.append(f"\n{result.error}", style="red")
        status_line.update(text)

        steps = self.query_one("#run-summary-steps", DataTable)
        steps.clear()
        for step in result.step_results:
            steps.add_row(
                step.step_id or "-",
                step.action,
                Text(step.status.value, style=_STATUS_STYLE.get(step.status, "")),
                f"{step.duration_ms:.1f} ms",
            )

        self.query_one("#run-summary-outputs", JsonPreview).show(result.outputs)
