"""Tests for console/screens/recorder.py: the interactive Blueprint recorder screen.

The recorder engine is faked so the screen's worker -> event log -> result-preview flow is covered
without launching a browser (the real capture is exercised by tests/integration/test_recorder_run.py).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens import recorder as recorder_screen
from aetherius.console.screens.recorder import RecorderScreen
from aetherius.console.widgets.event_log import EventLog
from aetherius.console.widgets.json_preview import JsonPreview

from textual.widgets import Button, Input

pytestmark = pytest.mark.unit


async def _wait_until(condition, pilot, attempts: int = 60) -> None:
    for _ in range(attempts):
        await pilot.pause(0.05)
        if condition():
            return
    raise AssertionError("condition was not met in time")


@pytest.mark.asyncio
async def test_start_requires_a_name_and_url() -> None:
    app = AetheriusConsoleApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.push_screen(RecorderScreen())
        await pilot.pause()

        await pilot.click("#rec-start")
        await pilot.pause()

        # Nothing started: the Start button stays enabled and Stop stays hidden.
        assert not app.screen.query_one("#rec-start", Button).disabled
        assert not app.screen.query_one("#rec-stop", Button).display


@pytest.mark.asyncio
async def test_recording_streams_actions_and_shows_the_saved_blueprint(
    monkeypatch, tmp_path: Path
) -> None:
    saved = tmp_path / "demo.blueprint.json"

    def fake_record_blueprint(name, url, *, on_event, **kwargs):
        on_event(f"navigate  {url}")
        on_event("click  #user")
        blueprint = {
            "aetherius": "1.0",
            "name": name,
            "act": "continuum",
            "steps": [{"action": "navigate", "url": url}],
        }
        saved.write_text(json.dumps(blueprint), encoding="utf-8")
        return saved

    monkeypatch.setattr(recorder_screen, "record_blueprint", fake_record_blueprint)

    app = AetheriusConsoleApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.push_screen(RecorderScreen())
        await pilot.pause()

        app.screen.query_one("#rec-name", Input).value = "demo"
        app.screen.query_one("#rec-url", Input).value = "https://example.test"
        await pilot.click("#rec-start")

        await _wait_until(lambda: not app.screen.query_one("#rec-start", Button).disabled, pilot)

        event_log = app.screen.query_one("#rec-events", EventLog)
        assert len(event_log.lines) >= 2  # navigate + click streamed live

        result = app.screen.query_one("#rec-result", JsonPreview)
        assert result.display is True  # revealed with the recorded Blueprint


@pytest.mark.asyncio
async def test_stop_button_sets_the_stop_event() -> None:
    app = AetheriusConsoleApp()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        screen = RecorderScreen()
        app.push_screen(screen)
        await pilot.pause()

        # Simulate an in-flight recording, then press Stop.
        screen._stop = threading.Event()
        screen._set_recording(True)
        await pilot.pause()
        await pilot.click("#rec-stop")
        await pilot.pause()

        assert screen._stop.is_set()
