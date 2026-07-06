"""Tests for the honest "coming soon" placeholders: Sessions, Settings, Builder."""

from __future__ import annotations

import pytest

from aetherius.console.screens.builder.screen import BlueprintStudioScreen
from aetherius.console.screens.sessions import SessionsScreen
from aetherius.console.screens.settings import SettingsScreen

from textual.app import App, ComposeResult
from textual.widgets import Static

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "screen_cls",
    [SessionsScreen, SettingsScreen, BlueprintStudioScreen],
)
@pytest.mark.asyncio
async def test_pending_screen_states_its_milestone(screen_cls: type) -> None:
    class _Harness(App[None]):
        def compose(self) -> ComposeResult:
            yield from ()

        def on_mount(self) -> None:
            self.push_screen(screen_cls())

    app = _Harness()

    async with app.run_test() as pilot:
        await pilot.pause()

        texts = [str(w.render()) for w in app.screen.query(Static)]
        assert any("Pending:" in t for t in texts)
