"""Pilot tests for the Studio's live preview."""

from __future__ import annotations

import pytest

from aetherius.builder.factory import BlueprintDraft, StepDraft
from aetherius.console.screens.builder.preview import BlueprintPreview

from textual.app import App, ComposeResult
from textual.widgets import Static

pytestmark = pytest.mark.unit


class _Harness(App[None]):
    def compose(self) -> ComposeResult:
        yield BlueprintPreview()


@pytest.mark.asyncio
async def test_empty_draft_shows_errors() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        preview = app.query_one(BlueprintPreview)
        preview.refresh_from(BlueprintDraft())
        await pilot.pause()
        issues = str(app.query_one("#preview-issues", Static).render())
        assert "✗" in issues


@pytest.mark.asyncio
async def test_valid_draft_shows_ready_and_json() -> None:
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        draft = BlueprintDraft(name="t.ok", act="vector")
        draft.steps.append(StepDraft(action="http.request", params={"url": "https://x"}))
        preview = app.query_one(BlueprintPreview)
        preview.refresh_from(draft)
        await pilot.pause()
        issues = str(app.query_one("#preview-issues", Static).render())
        assert "ready to save" in issues.lower()
