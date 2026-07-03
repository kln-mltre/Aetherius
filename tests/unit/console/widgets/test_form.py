"""Tests for console/widgets/form.py — BlueprintInputForm, via Textual's headless Pilot."""

from __future__ import annotations

import pytest

from aetherius.console.widgets.form import BlueprintInputForm
from aetherius.core.blueprint.models import InputSpec

from textual.app import App, ComposeResult
from textual.widgets import Input, Switch

pytestmark = pytest.mark.unit


class _FormHarness(App[None]):
    def __init__(self, inputs: dict[str, InputSpec], secrets: list[str]) -> None:
        super().__init__()
        self._inputs = inputs
        self._secrets = secrets

    def compose(self) -> ComposeResult:
        yield BlueprintInputForm(self._inputs, self._secrets)


@pytest.mark.asyncio
async def test_collect_returns_filled_values() -> None:
    inputs = {
        "group": InputSpec(type="string", required=True),
        "verbose": InputSpec(type="boolean", default=False),
    }
    app = _FormHarness(inputs, secrets=["token"])

    async with app.run_test() as pilot:
        form = app.query_one(BlueprintInputForm)
        app.query_one("#bp-input-group", Input).value = "TP-A1"
        app.query_one("#bp-input-verbose", Switch).value = True
        app.query_one("#bp-secret-token", Input).value = "s3cret"
        await pilot.pause()

        input_values, secret_values = form.collect()

        assert input_values == {"group": "TP-A1", "verbose": True}
        assert secret_values == {"token": "s3cret"}


@pytest.mark.asyncio
async def test_validation_errors_flags_missing_required_input() -> None:
    inputs = {"group": InputSpec(type="string", required=True)}
    app = _FormHarness(inputs, secrets=[])

    async with app.run_test() as pilot:
        form = app.query_one(BlueprintInputForm)
        await pilot.pause()

        errors = form.validation_errors()

        assert any("group" in e for e in errors)
