"""Pilot tests for the Studio's Act picker."""

from __future__ import annotations

import pytest

from aetherius.console.screens.builder.act_picker import ActPicker, _option_label

from textual.app import App, ComposeResult
from textual.widgets import Select, Static

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.changed_to: str | None = None

    def compose(self) -> ComposeResult:
        yield ActPicker("vector")

    def on_act_picker_act_changed(self, event: ActPicker.ActChanged) -> None:
        self.changed_to = event.act


@pytest.mark.asyncio
async def test_picker_defaults_to_its_act() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(ActPicker).act == "vector"


@pytest.mark.asyncio
async def test_changing_act_emits_message_and_updates_explanation() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#act-select", Select).value = "continuum"
        await pilot.pause()
        assert app.changed_to == "continuum"
        explanation = str(app.query_one("#act-explanation", Static).render())
        assert "browser" in explanation.lower()


def test_option_label_marks_pending_acts() -> None:
    assert "not runnable yet" not in _option_label("vector", implemented=True)
    assert "not runnable yet" in _option_label("oracle", implemented=False)
