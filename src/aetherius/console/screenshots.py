"""Generate SVG screenshots of the Console for the documentation.

Dev-only utility (never imported at runtime): it drives the Textual app **headlessly** through
``run_test``/``Pilot`` — the same mechanism the tests use — and exports each key screen to a
deterministic SVG under ``docs/screenshots/``. Determinism matters so the committed files change only
when the UI actually changes: Rich stamps every export with a random id, which we normalise to a
stable per-file token, and the external web-font ``@font-face`` blocks are stripped so each SVG is
self-contained. Regenerate with ``make screenshots`` after any Console UI change.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from textual.pilot import Pilot
from textual.widgets import Select

from .app import AetheriusConsoleApp

if TYPE_CHECKING:
    from .screens.builder.screen import BlueprintStudioScreen

# Repo root, resolved from this module so paths don't depend on the working directory.
_REPO = Path(__file__).resolve().parents[3]
_EXAMPLE = _REPO / "examples" / "vector" / "ukit-planning-week.blueprint.json"

Setup = Callable[[AetheriusConsoleApp, Pilot[None]], Awaitable[None]]


async def _home(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    pass  # HomeScreen is already pushed on mount


async def _library(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.library import LibraryScreen

    app.push_screen(LibraryScreen())
    await pilot.pause()


async def _runs(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.runs import RunsScreen

    app.push_screen(RunsScreen(_EXAMPLE))
    await pilot.pause()


async def _catalog(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.catalog import CatalogScreen

    app.push_screen(CatalogScreen())
    await pilot.pause()


async def _recorder(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.recorder import RecorderScreen

    app.push_screen(RecorderScreen())
    await pilot.pause()


async def _open_studio_with_template(
    app: AetheriusConsoleApp, pilot: Pilot[None]
) -> BlueprintStudioScreen:
    from .screens.builder.screen import BlueprintStudioScreen

    screen = BlueprintStudioScreen()
    app.push_screen(screen)
    await pilot.pause()
    await pilot.pause()
    screen.query_one("#studio-template", Select).value = "continuum.scrape"
    await pilot.pause()
    screen._load_template()
    await pilot.pause()
    await pilot.pause()
    return screen


async def _studio(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    await _open_studio_with_template(app, pilot)


async def _studio_preview(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from textual.widgets import Button

    screen = await _open_studio_with_template(app, pilot)
    # Scroll the Save button into view: the frame then shows the tail of the validated JSON, the green
    # "Valid — ready to save.", and the Save button — the flagship live-validation moment.
    screen.query_one("#studio-save", Button).scroll_visible(animate=False)
    await pilot.pause()


async def _studio_step_editor(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.builder.screen import BlueprintStudioScreen
    from .screens.builder.step_editor import StepEditorModal

    screen = BlueprintStudioScreen()
    app.push_screen(screen)
    await pilot.pause()
    await pilot.pause()
    modal = StepEditorModal("continuum")
    app.push_screen(modal)
    await pilot.pause()
    modal.query_one("#step-action", Select).value = "fill"
    await pilot.pause()


# slug -> (terminal size, setup). Sizes are chosen per screen for a legible, well-framed capture.
_SHOTS: list[tuple[str, tuple[int, int], Setup]] = [
    ("home", (92, 32), _home),
    ("library", (100, 26), _library),
    ("runs", (100, 34), _runs),
    ("catalog", (110, 26), _catalog),
    ("recorder", (100, 30), _recorder),
    ("studio", (104, 50), _studio),
    ("studio-preview", (104, 40), _studio_preview),
    ("studio-step-editor", (100, 40), _studio_step_editor),
]


def _normalize(svg: str, slug: str) -> str:
    """Make the exported SVG deterministic and self-contained.

    Rich uses a random ``terminal-<n>`` id per export (only source of run-to-run churn); we pin it to
    the slug. The two web-font ``@font-face`` blocks reference an external CDN (blocked on GitHub
    anyway) — dropping them leaves the ``monospace`` fallback and keeps the file self-contained.
    """
    svg = re.sub(r"terminal-\d+", f"terminal-{slug}", svg)
    svg = re.sub(r"@font-face \{[^}]*\}", "", svg)
    # Never bake the author's absolute checkout path (username, machine) into a committed doc asset;
    # this also makes the output identical regardless of where the repo is cloned.
    svg = svg.replace(str(_REPO), "/home/user/aetherius")
    return svg


async def _capture(slug: str, size: tuple[int, int], setup: Setup, out_dir: Path) -> Path:
    app = AetheriusConsoleApp()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await setup(app, pilot)
        await pilot.pause()
        svg = app.export_screenshot(title="Aetherius")
    path = out_dir / f"{slug}.svg"
    path.write_text(_normalize(svg, slug), encoding="utf-8")
    return path


async def capture_all(out_dir: Path) -> list[Path]:
    """Render every Console screen to ``out_dir/<slug>.svg`` and return the written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return [await _capture(slug, size, setup, out_dir) for slug, size, setup in _SHOTS]


def main() -> None:
    out_dir = _REPO / "docs" / "screenshots"
    paths = asyncio.run(capture_all(out_dir))
    for path in paths:
        print(f"wrote {path.relative_to(_REPO)}")


if __name__ == "__main__":
    main()
