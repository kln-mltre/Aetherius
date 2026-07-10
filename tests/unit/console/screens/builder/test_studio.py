"""Pilot tests for the Blueprint Studio orchestrator: create, save, load a template, edit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aetherius.builder.factory import StepDraft
from aetherius.console.app import AetheriusConsoleApp
from aetherius.console.screens.builder.io_editor import VarsOutputsEditor
from aetherius.console.screens.builder.screen import BlueprintStudioScreen

from textual.widgets import DataTable, Input, Select

pytestmark = pytest.mark.unit


async def _open_studio(pilot, path: Path | None = None) -> BlueprintStudioScreen:
    screen = BlueprintStudioScreen(path)
    await pilot.app.push_screen(screen)
    await pilot.pause()
    await pilot.pause()
    return screen


@pytest.mark.asyncio
async def test_create_and_save_a_blueprint(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot)
        screen.query_one("#studio-name", Input).value = "my.demo"
        await pilot.pause()
        screen._draft.steps.append(StepDraft(action="http.request", params={"url": "https://x"}))
        screen._draft.act = "vector"
        screen._render_steps()
        screen._refresh_preview()
        await pilot.pause()
        screen._save()
        await pilot.pause()

        saved = tmp_path / "blueprints" / "my.demo.blueprint.json"
        assert saved.exists()
        assert json.loads(saved.read_text())["name"] == "my.demo"


@pytest.mark.asyncio
async def test_saving_an_invalid_draft_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot)
        # No name, no steps -> invalid.
        screen._save()
        await pilot.pause()
        assert not (tmp_path / "blueprints").exists() or not any(
            (tmp_path / "blueprints").iterdir()
        )


@pytest.mark.asyncio
async def test_loading_a_template_populates_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot)
        screen.query_one("#studio-template", Select).value = "continuum.scrape"
        await pilot.pause()
        screen._load_template()
        await pilot.pause()
        table = screen.query_one("#studio-steps", DataTable)
        assert table.row_count == 3
        assert screen._draft.act == "continuum"


@pytest.mark.asyncio
async def test_editing_an_existing_file_prefills_and_overwrites(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "blueprints" / "edit.me.blueprint.json"
    target.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "aetherius": "1.0",
                "name": "edit.me",
                "act": "vector",
                "steps": [{"id": "f", "action": "http.request", "url": "https://x"}],
            }
        ),
        encoding="utf-8",
    )
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot, target)
        assert screen.query_one("#studio-name", Input).value == "edit.me"
        assert len(screen._draft.steps) == 1
        screen.query_one("#studio-description", Input).value = "edited"
        await pilot.pause()
        screen._save()
        await pilot.pause()
        assert json.loads(target.read_text())["description"] == "edited"


@pytest.mark.asyncio
async def test_changing_act_surfaces_invalid_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot)  # opens on vector by default
        screen.query_one("#act-select", Select).value = "continuum"
        await pilot.pause()
        screen._draft.steps.append(StepDraft(action="navigate", params={"url": "https://x"}))
        # Switch back to vector, where navigate is unsupported: validation must complain.
        screen.query_one("#act-select", Select).value = "vector"
        await pilot.pause()
        assert screen._draft.act == "vector"
        from aetherius.builder.validation import validate_draft

        messages = [i.message for i in validate_draft(screen._draft)]
        assert any("not supported by act" in m for m in messages)


@pytest.mark.asyncio
async def test_invalid_vars_json_blocks_save(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = AetheriusConsoleApp()
    async with app.run_test(size=(140, 60)) as pilot:
        await pilot.pause()
        screen = await _open_studio(pilot)
        from textual.widgets import TextArea

        screen.query_one("#io-vars", TextArea).text = "{not json"
        await pilot.pause()
        assert screen.query_one(VarsOutputsEditor).has_errors
