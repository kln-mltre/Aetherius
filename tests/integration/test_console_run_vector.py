"""End-to-end Console flow: Home -> Library -> Runs, executing the Vector example Blueprint
against a MockTransport that simulates the ADE API, without any real network I/O. Mirrors
tests/integration/test_vector_run.py, but drives the Textual UI instead of calling
Aetherius().run() directly."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens.library import LibraryScreen
from aetherius.console.screens.runs import RunsScreen
from aetherius.console.widgets.event_log import EventLog

from textual.widgets import Button, DataTable, Input

pytestmark = pytest.mark.integration

_API_PAYLOAD = [
    {
        "id": "ev-1",
        "start": "2026-09-07T08:00:00",
        "end": "2026-09-07T10:00:00",
        "eventCategory": "Cours",
        "backgroundColor": "#3b82f6",
        "description": "Mathématiques",
    }
]


def _mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_API_PAYLOAD, headers={"Content-Type": "application/json"})

    return httpx.MockTransport(handler)


async def _wait_until(condition, pilot, attempts: int = 60) -> None:
    for _ in range(attempts):
        await pilot.pause(0.05)
        if condition():
            return
    raise AssertionError("condition was not met in time")


@pytest.mark.asyncio
async def test_console_runs_vector_blueprint_end_to_end(examples_dir: Path) -> None:
    blueprint_path = examples_dir / "ukit-planning-week.blueprint.json"
    app = AetheriusConsoleApp()

    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()

        app.push_screen(LibraryScreen())
        await pilot.pause()
        assert isinstance(app.screen, LibraryScreen)

        table = app.screen.query_one("#library-table", DataTable)
        assert table.row_count >= 1

        app.push_screen(RunsScreen(blueprint_path))
        await pilot.pause()
        assert isinstance(app.screen, RunsScreen)

        app.screen.query_one("#bp-input-group", Input).value = "TP-A1"
        app.screen.query_one("#bp-input-monday", Input).value = "2026-09-07"

        with patch("httpx.Client", return_value=httpx.Client(transport=_mock_transport())):
            await pilot.click("#run-button")
            await _wait_until(
                lambda: not app.screen.query_one("#run-button", Button).disabled, pilot
            )

        event_log = app.screen.query_one("#run-event-log", EventLog)
        assert len(event_log.lines) > 0

        summary_steps = app.screen.query_one("#run-summary-steps", DataTable)
        assert summary_steps.row_count == 1
