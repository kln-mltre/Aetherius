"""Tests for console/widgets/event_log.py — EventLog widget."""

from __future__ import annotations

import pytest

from aetherius.console.widgets.event_log import EventLog
from aetherius.core.events.models import EventType, RunEvent

from textual.app import App, ComposeResult

pytestmark = pytest.mark.unit


class _LogHarness(App[None]):
    def compose(self) -> ComposeResult:
        yield EventLog()


@pytest.mark.asyncio
async def test_write_event_appends_a_line() -> None:
    app = _LogHarness()

    async with app.run_test() as pilot:
        log = app.query_one(EventLog)
        await pilot.pause()

        log.write_event(RunEvent(run_id="r1", type=EventType.PROGRESS, message="started"))
        await pilot.pause()

        assert len(log.lines) == 1


@pytest.mark.asyncio
async def test_write_event_handles_multiple_events() -> None:
    app = _LogHarness()

    async with app.run_test() as pilot:
        log = app.query_one(EventLog)
        await pilot.pause()

        log.write_event(RunEvent(run_id="r1", type=EventType.STEP_STARTED, step_id="s1"))
        log.write_event(RunEvent(run_id="r1", type=EventType.ERROR, message="boom", level="error"))
        await pilot.pause()

        assert len(log.lines) == 2
