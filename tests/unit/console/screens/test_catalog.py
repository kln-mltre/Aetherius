"""Tests for console/screens/catalog.py — Act reference table."""

from __future__ import annotations

import pytest

from aetherius.console.screens.catalog import CatalogScreen

from textual.app import App, ComposeResult
from textual.widgets import DataTable

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(CatalogScreen())


@pytest.mark.asyncio
async def test_catalog_lists_all_four_acts() -> None:
    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()

        table = app.screen.query_one("#catalog-table", DataTable)

        assert table.row_count == 4


@pytest.mark.asyncio
async def test_vector_row_includes_its_capabilities() -> None:
    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()

        table = app.screen.query_one("#catalog-table", DataTable)
        first_row = table.get_row_at(0)
        actions_cell = str(first_row[3])

        assert "http.request" in actions_cell
