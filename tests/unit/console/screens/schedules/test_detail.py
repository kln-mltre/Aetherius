"""Tests for console/screens/schedules/detail.py — info, history, and the manual fire."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aetherius.console.screens.schedules.detail import ScheduleDetailScreen
from aetherius.console.widgets.confirm import ConfirmModal
from aetherius.console.widgets.run_summary import RunSummary
from aetherius.store import RunRecord, Store

from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Static

from .conftest import make_schedule

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def __init__(self, store: Store, schedule_id: str = "sch-1") -> None:
        super().__init__()
        self._store = store
        self._schedule_id = schedule_id

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(ScheduleDetailScreen(self._schedule_id, store=self._store))


@pytest.mark.asyncio
async def test_shows_the_definition_and_history(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    store.runs.record(
        RunRecord(
            run_id="r1",
            blueprint_name="daemon.selftest",
            status="success",
            schedule_id="sch-1",
            outputs={"greeting": "hello"},
            started_at=datetime(2026, 7, 14, 11, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 14, 11, 0, 1, tzinfo=timezone.utc),
        )
    )
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()

        info = str(app.screen.query_one("#schedule-info", Static).render())
        assert "every 3600s" in info
        assert "active" in info
        assert app.screen.query_one("#schedule-history", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_fire_now_runs_and_lands_in_history(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#schedule-fire", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()

        summary = app.screen.query_one("#schedule-summary", RunSummary)
        assert summary.has_class("-revealed")
        assert app.screen.query_one("#schedule-history", DataTable).row_count == 1
        assert app.screen.query_one("#schedule-fire", Button).disabled is False

    runs = store.runs.recent(schedule_id="sch-1")
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].outputs["greeting"] == "hello, console"
    # The cadence stays untouched by a manual fire.
    updated = store.schedules.get("sch-1")
    assert updated is not None and updated.last_run_at is None


@pytest.mark.asyncio
async def test_fire_of_a_broken_blueprint_is_recorded_and_surfaced(
    store: Store, examples_dir: Path
) -> None:
    store.schedules.create(make_schedule(examples_dir, blueprint="/vanished.json"))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#schedule-fire", Button).press()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert app.screen.query_one("#schedule-history", DataTable).row_count == 1

    runs = store.runs.recent(schedule_id="sch-1")
    assert len(runs) == 1 and runs[0].status == "failed"


@pytest.mark.asyncio
async def test_toggle_button_pauses_and_resumes(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        toggle = app.screen.query_one("#schedule-toggle", Button)
        assert str(toggle.label) == "Pause"

        toggle.press()
        await pilot.pause()
        paused = store.schedules.get("sch-1")
        assert paused is not None and paused.enabled is False
        assert str(app.screen.query_one("#schedule-toggle", Button).label) == "Resume"


@pytest.mark.asyncio
async def test_delete_confirms_then_pops(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleDetailScreen)

        screen.action_delete()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        app.screen.query_one("#confirm-ok", Button).press()
        await pilot.pause()

        assert store.schedules.get("sch-1") is None
        assert not isinstance(app.screen, ScheduleDetailScreen)


@pytest.mark.asyncio
async def test_edit_opens_the_prefilled_form(store: Store, examples_dir: Path) -> None:
    store.schedules.create(make_schedule(examples_dir))
    app = _Harness(store)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleDetailScreen)
        screen.action_edit()
        await pilot.pause()

        from aetherius.console.screens.schedules.form import ScheduleFormScreen

        assert isinstance(app.screen, ScheduleFormScreen)


@pytest.mark.asyncio
async def test_a_vanished_schedule_pops_back(store: Store) -> None:
    app = _Harness(store, schedule_id="ghost")

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        assert not isinstance(app.screen, ScheduleDetailScreen)
