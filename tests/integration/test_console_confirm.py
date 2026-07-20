"""End-to-end Console flow for human-in-the-loop (Jalon 2-E).

Drives the real Textual UI: a network-free Blueprint parks on a ``confirm`` step, the
ConsoleApprovalSink raises the ConfirmModal, and pressing Approve/Reject resumes the run. Verifies the
guarded step runs on approval and is skipped on rejection — the console decision surface, exercised
without mocking the sink.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual.widgets import Button, DataTable

from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens.runs import RunsScreen
from aetherius.console.widgets.confirm import ConfirmModal

pytestmark = pytest.mark.integration

_CONFIRM_BP = {
    "aetherius": "1.0",
    "name": "demo.confirm.console",
    "act": "vector",
    "steps": [
        {"id": "approve", "action": "confirm", "message": "Run it?", "timeout_ms": 15000},
        {
            "id": "sensitive",
            "when": "{{ steps.approve.approved }}",
            "action": "set",
            "value": "ran",
        },
    ],
    "outputs": {"approved": "{{ steps.approve.approved }}"},
}


def _write_bp(tmp_path: Path) -> Path:
    path = tmp_path / "confirm.blueprint.json"
    path.write_text(json.dumps(_CONFIRM_BP), encoding="utf-8")
    return path


async def _wait_until(condition, pilot, attempts: int = 120) -> None:
    for _ in range(attempts):
        await pilot.pause(0.05)
        if condition():
            return
    raise AssertionError("condition was not met in time")


def _sensitive_status(screen: RunsScreen) -> str | None:
    table = screen.query_one("#run-summary-steps", DataTable)
    for row_key in table.rows:
        row = table.get_row(row_key)
        if str(row[0]) == "sensitive":
            return str(row[2])
    return None


async def _run_and_decide(tmp_path: Path, button_id: str) -> str | None:
    app = AetheriusConsoleApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        screen = RunsScreen(_write_bp(tmp_path))
        app.push_screen(screen)
        await pilot.pause()

        await pilot.click("#run-button")
        # The worker parks on confirm; the ConsoleApprovalSink raises the modal on the UI thread.
        await _wait_until(lambda: isinstance(app.screen, ConfirmModal), pilot)

        await pilot.click(button_id)
        # Query the retained RunsScreen (it stays in the stack under the popped modal) to avoid
        # racing app.screen during the modal dismissal.
        await _wait_until(lambda: not screen.query_one("#run-button", Button).disabled, pilot)
        return _sensitive_status(screen)


async def test_approving_in_the_console_runs_the_guarded_step(tmp_path: Path) -> None:
    assert await _run_and_decide(tmp_path, "#confirm-ok") == "success"


async def test_rejecting_in_the_console_skips_the_guarded_step(tmp_path: Path) -> None:
    assert await _run_and_decide(tmp_path, "#confirm-cancel") == "skipped"
