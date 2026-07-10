"""Tests for the graduated Settings screen: daemon start/stop wiring and status rendering.

A fake controller stands in for the real subprocess-backed one, so no daemon is ever spawned.
"""

from __future__ import annotations

import pytest

from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens.settings import SettingsScreen
from aetherius.server.config import DaemonConfig

from textual.widgets import Button, Static

pytestmark = pytest.mark.unit


class _FakeDaemon:
    def __init__(self, *, running: bool = False) -> None:
        self.config = DaemonConfig()
        self.started = False
        self.stopped = False
        self._running = running

    @property
    def base_url(self) -> str:
        return self.config.base_url

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self.started = True
        self._running = True

    def stop(self) -> None:
        self.stopped = True
        self._running = False

    def healthy(self) -> bool:
        return self._running


def _status(app: AetheriusConsoleApp) -> str:
    return str(app.screen.query_one("#settings-status", Static).render())


async def _open_settings(app: AetheriusConsoleApp, pilot: object) -> None:
    await pilot.pause()  # type: ignore[attr-defined]
    app.push_screen(SettingsScreen())
    await pilot.pause()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_settings_reports_stopped_initially() -> None:
    app = AetheriusConsoleApp()
    app._daemon = _FakeDaemon()  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await _open_settings(app, pilot)

        assert "stopped" in _status(app)
        assert app.screen.query_one("#settings-start", Button).disabled is False
        assert app.screen.query_one("#settings-stop", Button).disabled is True


@pytest.mark.asyncio
async def test_settings_start_launches_the_daemon() -> None:
    app = AetheriusConsoleApp()
    fake = _FakeDaemon()
    app._daemon = fake  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await _open_settings(app, pilot)
        await pilot.click("#settings-start")
        await pilot.pause()

        assert fake.started is True
        assert "running" in _status(app)


@pytest.mark.asyncio
async def test_settings_stop_terminates_the_daemon() -> None:
    app = AetheriusConsoleApp()
    fake = _FakeDaemon(running=True)
    app._daemon = fake  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await _open_settings(app, pilot)
        await pilot.click("#settings-stop")
        await pilot.pause()

        assert fake.stopped is True
        assert "stopped" in _status(app)
