"""Tests for console/screens/home.py — menu content and navigation."""

from __future__ import annotations

from pathlib import Path

import pytest

from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens.catalog import CatalogScreen
from aetherius.console.screens.home import HomeScreen
from aetherius.console.screens.library import LibraryScreen

from textual.widgets import OptionList

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_home_is_the_initial_screen() -> None:
    app = AetheriusConsoleApp()

    async with app.run_test() as pilot:
        await pilot.pause()

        assert isinstance(app.screen, HomeScreen)


@pytest.mark.asyncio
async def test_home_menu_lists_all_sections() -> None:
    app = AetheriusConsoleApp()

    async with app.run_test() as pilot:
        await pilot.pause()

        option_list = app.screen.query_one(OptionList)
        ids = {option_list.get_option_at_index(i).id for i in range(option_list.option_count)}

        assert ids == {
            "library",
            "schedules",
            "catalog",
            "sessions",
            "settings",
            "recorder",
            "builder",
        }


@pytest.mark.asyncio
async def test_selecting_library_navigates_there() -> None:
    app = AetheriusConsoleApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        option_list = app.screen.query_one(OptionList)
        option_list.highlighted = 0  # "library" is the first entry
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, LibraryScreen)


@pytest.mark.asyncio
async def test_selecting_schedules_navigates_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The Schedules screen reads the process-wide store: keep it on a temp file.
    from aetherius.config import settings as settings_mod
    from aetherius.store import engine as engine_mod

    monkeypatch.setenv("AETHERIUS_DATA_DIR", str(tmp_path))
    settings_mod.get_settings.cache_clear()
    engine_mod.get_store.cache_clear()
    app = AetheriusConsoleApp()

    try:
        async with app.run_test() as pilot:
            await pilot.pause()
            option_list = app.screen.query_one(OptionList)
            option_list.highlighted = 1  # "schedules" is the second entry
            await pilot.press("enter")
            await pilot.pause()

            from aetherius.console.screens.schedules import SchedulesScreen

            assert isinstance(app.screen, SchedulesScreen)
    finally:
        settings_mod.get_settings.cache_clear()
        engine_mod.get_store.cache_clear()


@pytest.mark.asyncio
async def test_selecting_catalog_navigates_there() -> None:
    app = AetheriusConsoleApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        option_list = app.screen.query_one(OptionList)
        option_list.highlighted = 2  # "catalog" is the third entry (after Library and Schedules)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, CatalogScreen)
