"""Tests for console/screens/library.py — DataTable population and row selection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aetherius.console.screens.library import LibraryScreen
from aetherius.console.screens.library_scan import BlueprintEntry
from aetherius.core.blueprint.loader import load_blueprint

from textual.app import App, ComposeResult
from textual.widgets import DataTable

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen())


@pytest.mark.asyncio
async def test_library_lists_repo_examples() -> None:
    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()

        table = app.screen.query_one("#library-table", DataTable)
        assert table.row_count >= 3  # the three examples/*.blueprint.json files


@pytest.mark.asyncio
async def test_selecting_an_invalid_entry_notifies_instead_of_navigating(
    examples_dir: Path,
) -> None:
    bad_entry = BlueprintEntry(
        path=examples_dir / "does-not-exist.blueprint.json",
        blueprint=None,
        act=None,
        error="boom",
    )
    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LibraryScreen)
        screen._entries = [bad_entry]
        screen._render_table()
        await pilot.pause()

        table = screen.query_one("#library-table", DataTable)
        with patch.object(app, "notify") as mock_notify:
            table.action_select_cursor()
            await pilot.pause()

        mock_notify.assert_called_once()
        assert app.screen is screen  # did not navigate away


@pytest.mark.asyncio
async def test_selecting_a_valid_entry_opens_runs_screen(examples_dir: Path) -> None:
    path = examples_dir / "ukit-planning-week.blueprint.json"
    good_entry = BlueprintEntry(path=path, blueprint=load_blueprint(path), act="vector", error=None)
    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LibraryScreen)
        screen._entries = [good_entry]
        screen._render_table()
        await pilot.pause()

        table = screen.query_one("#library-table", DataTable)
        table.action_select_cursor()
        await pilot.pause()

        from aetherius.console.screens.runs import RunsScreen

        assert isinstance(app.screen, RunsScreen)
