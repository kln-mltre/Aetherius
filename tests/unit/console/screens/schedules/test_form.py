"""Tests for console/screens/schedules/form.py — guided creation and edition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aetherius.console.screens.schedules.form import ScheduleFormScreen
from aetherius.console.widgets.form import BlueprintInputForm
from aetherius.store import ScheduleRecord, Store

from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Select

from .conftest import make_schedule

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def __init__(
        self,
        store: Store,
        blueprint_path: Path | None = None,
        edit: ScheduleRecord | None = None,
    ) -> None:
        super().__init__()
        self._store = store
        self._blueprint_path = blueprint_path
        self._edit = edit

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(
            ScheduleFormScreen(
                store=self._store, blueprint_path=self._blueprint_path, edit=self._edit
            )
        )


def _selftest(examples_dir: Path) -> Path:
    return examples_dir / "vector" / "daemon-selftest.blueprint.json"


@pytest.mark.asyncio
async def test_create_a_schedule_end_to_end(store: Store, examples_dir: Path) -> None:
    app = _Harness(store, blueprint_path=_selftest(examples_dir))

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)

        # The name is pre-filled from the Blueprint file, the inputs form from its declaration.
        assert screen.query_one("#sf-name", Input).value == "daemon-selftest"
        screen.query_one("#sf-trigger-value", Input).value = "60"
        form = screen.query_one(BlueprintInputForm)
        form.query_one(Input).value = "scheduled"

        screen.query_one("#sf-save", Button).press()
        await pilot.pause()

    records = store.schedules.all()
    assert len(records) == 1
    record = records[0]
    assert record.name == "daemon-selftest"
    assert Path(record.blueprint).is_absolute()
    assert record.trigger == {"kind": "interval", "seconds": 60}
    assert record.inputs == {"subject": "scheduled"}
    assert record.secrets == []
    assert record.next_run_at is not None


@pytest.mark.asyncio
async def test_notify_policy_and_misfire_are_carried(store: Store, examples_dir: Path) -> None:
    app = _Harness(store, blueprint_path=_selftest(examples_dir))

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)

        screen.query_one("#sf-kind", Select).value = "cron"
        screen.query_one("#sf-trigger-value", Input).value = "0 0,3 * * *"
        screen.query_one("#sf-misfire", Select).value = "skip"
        screen.query_one("#sf-channel", Select).value = "ntfy"
        screen.query_one("#sf-target", Input).value = "{{ secrets.topic }}"
        screen.query_one("#sf-on", Select).value = "change"
        screen.query_one("#sf-save", Button).press()
        await pilot.pause()

    record = store.schedules.all()[0]
    assert record.trigger == {"kind": "cron", "expr": "0 0,3 * * *", "misfire": "skip"}
    assert record.notify == {"channel": "ntfy", "target": "{{ secrets.topic }}", "on": "change"}


@pytest.mark.asyncio
async def test_an_invalid_trigger_is_rejected_without_writing(
    store: Store, examples_dir: Path
) -> None:
    app = _Harness(store, blueprint_path=_selftest(examples_dir))

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)

        screen.query_one("#sf-kind", Select).value = "cron"
        screen.query_one("#sf-trigger-value", Input).value = "not a cron"
        with patch.object(app, "notify") as mock_notify:
            screen.query_one("#sf-save", Button).press()
            await pilot.pause()

        mock_notify.assert_called_once()
        assert app.screen is screen  # still on the form

    assert store.schedules.all() == []


@pytest.mark.asyncio
async def test_a_non_numeric_interval_is_rejected(store: Store, examples_dir: Path) -> None:
    app = _Harness(store, blueprint_path=_selftest(examples_dir))

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)

        screen.query_one("#sf-trigger-value", Input).value = "soon"
        with patch.object(app, "notify") as mock_notify:
            screen.query_one("#sf-save", Button).press()
            await pilot.pause()

        mock_notify.assert_called_once()

    assert store.schedules.all() == []


@pytest.mark.asyncio
async def test_edit_prefills_and_a_new_trigger_restarts_the_cadence(
    store: Store, examples_dir: Path
) -> None:
    record = make_schedule(examples_dir)
    store.schedules.create(record)
    app = _Harness(store, edit=record)

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)

        assert screen.query_one("#sf-name", Input).value == "selftest-watch"
        assert screen.query_one("#sf-trigger-value", Input).value == "3600"
        # The stored input value wins over the spec default in the pre-filled form.
        assert screen.query_one(BlueprintInputForm).query_one(Input).value == "console"

        screen.query_one("#sf-trigger-value", Input).value = "120"
        screen.query_one("#sf-save", Button).press()
        await pilot.pause()

    updated = store.schedules.get(record.id)
    assert updated is not None
    assert updated.trigger == {"kind": "interval", "seconds": 120}
    assert updated.next_run_at != record.next_run_at  # cadence restarted from now
    assert len(store.schedules.all()) == 1  # updated, not duplicated


@pytest.mark.asyncio
async def test_edit_without_trigger_change_keeps_the_cadence(
    store: Store, examples_dir: Path
) -> None:
    record = make_schedule(examples_dir)
    store.schedules.create(record)
    app = _Harness(store, edit=record)

    async with app.run_test(size=(100, 50)) as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ScheduleFormScreen)
        screen.query_one("#sf-name", Input).value = "renamed"
        screen.query_one("#sf-save", Button).press()
        await pilot.pause()

    updated = store.schedules.get(record.id)
    assert updated is not None
    assert updated.name == "renamed"
    assert updated.next_run_at == record.next_run_at
