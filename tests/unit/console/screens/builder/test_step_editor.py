"""Pilot tests for the step editor modal."""

from __future__ import annotations

import pytest

from aetherius.builder.factory import StepDraft
from aetherius.console.screens.builder.step_editor import StepEditorModal

from textual.app import App, ComposeResult
from textual.widgets import Input, Select, Switch, TextArea

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def __init__(self, act: str = "continuum", step: StepDraft | None = None) -> None:
        super().__init__()
        self._act = act
        self._step = step
        self.result: StepDraft | None = None
        self.dismissed = False

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(StepEditorModal(self._act, self._step), self._store)

    def _store(self, step: StepDraft | None) -> None:
        self.result = step
        self.dismissed = True


@pytest.mark.asyncio
async def test_picking_navigate_renders_url_and_saves() -> None:
    app = _Harness()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        modal = app.screen
        modal.query_one("#step-action", Select).value = "navigate"
        await pilot.pause()
        modal.query_one("#param-url", Input).value = "https://example.com"
        await pilot.pause()
        await pilot.click("#step-ok")
        await pilot.pause()
        assert app.result == StepDraft(action="navigate", params={"url": "https://example.com"})


@pytest.mark.asyncio
async def test_object_param_uses_a_text_area() -> None:
    app = _Harness()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        modal = app.screen
        modal.query_one("#step-action", Select).value = "extract"
        await pilot.pause()
        assert isinstance(modal.query_one("#param-outputs"), TextArea)


@pytest.mark.asyncio
async def test_raw_json_mode_sets_arbitrary_params() -> None:
    app = _Harness()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        modal = app.screen
        modal.query_one("#step-action", Select).value = "navigate"
        await pilot.pause()
        modal.query_one("#step-raw-toggle", Switch).value = True
        await pilot.pause()
        modal.query_one("#step-raw", TextArea).text = '{"url": "https://raw", "wait_until": "load"}'
        await pilot.pause()
        await pilot.click("#step-ok")
        await pilot.pause()
        assert app.result is not None
        assert app.result.params == {"url": "https://raw", "wait_until": "load"}


@pytest.mark.asyncio
async def test_invalid_raw_json_keeps_modal_open() -> None:
    app = _Harness()
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        modal = app.screen
        modal.query_one("#step-raw-toggle", Switch).value = True
        await pilot.pause()
        modal.query_one("#step-raw", TextArea).text = "{not valid"
        await pilot.pause()
        await pilot.click("#step-ok")
        await pilot.pause()
        assert not app.dismissed  # still open, nothing dismissed


@pytest.mark.asyncio
async def test_editing_prefills_existing_params() -> None:
    step = StepDraft(action="fill", id="u", params={"selector": "#user", "value": "alice"})
    app = _Harness(step=step)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        modal = app.screen
        assert modal.query_one("#param-selector", Input).value == "#user"
        assert modal.query_one("#step-id", Input).value == "u"
