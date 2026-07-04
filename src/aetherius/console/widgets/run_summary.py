"""Renders the final Result of a Blueprint run: status, per-step outcomes, and outputs."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from ...core.runtime.result import Result, RunStatus
from ..theme import AMBER, LAUREL, POMPEIAN
from .json_preview import JsonPreview

_STATUS_STYLE: dict[RunStatus, str] = {
    RunStatus.SUCCESS: f"bold {LAUREL}",
    RunStatus.FAILED: f"bold {POMPEIAN}",
    RunStatus.PARTIAL: f"bold {AMBER}",
}


class RunSummary(Vertical):
    """Hidden until `show(result)` reveals it once a run completes; `reset()` hides it again."""

    DEFAULT_CSS = """
    RunSummary {
        display: none;
        height: auto;
        border: double $success;
        padding: 0 1 1 1;
    }
    RunSummary.-revealed {
        display: block;
    }
    #run-summary-status {
        height: auto;
        padding: 1 0;
    }
    #run-summary-steps {
        height: auto;
        max-height: 12;
    }
    #run-summary-outputs {
        height: auto;
        margin-top: 1;
    }
    """

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
            text.append(f"\n{result.error}", style=POMPEIAN)
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
        self.add_class("-revealed")

    def reset(self) -> None:
        """Hide the previous result while a new run is in flight."""
        self.remove_class("-revealed")
