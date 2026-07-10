"""Tests for console/screens/home.py — menu content and navigation."""

from __future__ import annotations

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
async def test_selecting_catalog_navigates_there() -> None:
    app = AetheriusConsoleApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        option_list = app.screen.query_one(OptionList)
        option_list.highlighted = 1  # "catalog" is the second entry (Runs removed from Home)
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, CatalogScreen)
