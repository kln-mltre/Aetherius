"""Tests for console/screens/schedules/screen.py — the schedules list and its actions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aetherius.console.screens.schedules import SchedulesScreen
from aetherius.console.widgets.confirm import ConfirmModal
from aetherius.store import Store

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Static

from .conftest import make_schedule

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def __init__(self, store: Store) -> None:
        super().__init__()
        self._store = store

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(SchedulesScreen(store=self._store, probe_daemon=False))


@pytest.mark.asyncio
async def test_lists_schedules_with_their_state(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    store.schedules.create(
        make_schedule(examples_dir, schedule_id="sch-2", name="paused-watch", enabled=False)
    )
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()

        table = app.screen.query_one("#schedules-table", DataTable)
        assert table.row_count == 2
        hint = app.screen.query_one("#schedules-daemon-hint", Static)
        assert "no daemon" in str(hint.render())


@pytest.mark.asyncio
async def test_toggle_pauses_and_resume_restarts_the_cadence(
    store: Store, examples_dir: Path
) -> None:
    record = make_schedule(examples_dir)
    store.schedules.create(record)
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SchedulesScreen)

        screen.action_toggle_enabled()
        await pilot.pause()
        paused = store.schedules.get(record.id)
        assert paused is not None and paused.enabled is False

        screen.action_toggle_enabled()
        await pilot.pause()
        resumed = store.schedules.get(record.id)
        assert resumed is not None and resumed.enabled is True
        # Resuming restarts the cadence from now instead of catching up the paused window.
        assert resumed.next_run_at is not None
        assert resumed.next_run_at != record.next_run_at


@pytest.mark.asyncio
async def test_delete_asks_for_confirmation_first(store: Store, examples_dir: Path) -> None:
    record = make_schedule(examples_dir)
    store.schedules.create(record)
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SchedulesScreen)

        screen.action_delete()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)

        # Cancel keeps the schedule.
        app.screen.query_one("#confirm-cancel", Button).press()
        await pilot.pause()
        assert store.schedules.get(record.id) is not None

        screen.action_delete()
        await pilot.pause()
        app.screen.query_one("#confirm-ok", Button).press()
        await pilot.pause()
        assert store.schedules.get(record.id) is None
        assert screen.query_one("#schedules-table", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_enter_opens_the_detail_screen(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        table = app.screen.query_one("#schedules-table", DataTable)
        table.action_select_cursor()
        await pilot.pause()

        from aetherius.console.screens.schedules.detail import ScheduleDetailScreen

        assert isinstance(app.screen, ScheduleDetailScreen)


@pytest.mark.asyncio
async def test_new_opens_the_form(store: Store, examples_dir: Path) -> None:
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SchedulesScreen)
        screen.action_new()
        await pilot.pause()

        from aetherius.console.screens.schedules.form import ScheduleFormScreen

        assert isinstance(app.screen, ScheduleFormScreen)


@pytest.mark.asyncio
async def test_actions_on_an_empty_list_are_noops(store: Store) -> None:
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SchedulesScreen)

        with patch.object(app, "notify") as mock_notify:
            screen.action_toggle_enabled()
            screen.action_delete()
            await pilot.pause()

        mock_notify.assert_not_called()
        assert app.screen is screen
