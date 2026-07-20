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
import contextlib
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable, Iterator

from textual.pilot import Pilot
from textual.widgets import Select

from .app import AetheriusConsoleApp

if TYPE_CHECKING:
    from ..store import Store
    from .screens.builder.screen import BlueprintStudioScreen

# Repo root, resolved from this module so paths don't depend on the working directory.
_REPO = Path(__file__).resolve().parents[3]
_EXAMPLE = _REPO / "examples" / "vector" / "ukit-planning-week.blueprint.json"
_QUOTES = _REPO / "examples" / "vector" / "quotes-watch.blueprint.json"
_CONFIRM = _REPO / "examples" / "vector" / "confirm-before-post.blueprint.json"

Setup = Callable[[AetheriusConsoleApp, Pilot[None]], Awaitable[None]]


@contextlib.contextmanager
def _pinned_timezone() -> Iterator[None]:
    """Pin the process to Europe/Paris while capturing, restoring the host zone afterwards.

    The Schedules screens render wall-clock times in the *local* timezone; without pinning, the
    committed SVGs would differ per machine. Same save/restore idiom as the scheduler test
    fixture ``paris_tz``.
    """
    import tzlocal

    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Paris"
    time.tzset()
    tzlocal.reload_localzone()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()
        tzlocal.reload_localzone()


# The demo store lives for the process (the TemporaryDirectory must outlive the captures).
_demo_dir: tempfile.TemporaryDirectory[str] | None = None
_demo_store: "Store | None" = None


def _seeded_store() -> "Store":
    """A throwaway store seeded with fixed demo schedules and history (frozen datetimes)."""
    global _demo_dir, _demo_store
    if _demo_store is not None:
        return _demo_store

    from ..store import RunRecord, ScheduleRecord, Store

    _demo_dir = tempfile.TemporaryDirectory(prefix="aetherius-screenshots-")
    store = Store(Path(_demo_dir.name) / "aetherius.db")
    store.schedules.create(
        ScheduleRecord(
            id="demo-quotes",
            name="quotes-watch",
            blueprint=str(_QUOTES),
            trigger={"kind": "interval", "seconds": 3600},
            notify={"channel": "webhook", "target": "{{ secrets.hook_url }}", "on": "change"},
            created_at=datetime(2026, 7, 1, 7, 0, tzinfo=timezone.utc),
            next_run_at=datetime(2026, 7, 14, 15, 0, tzinfo=timezone.utc),
            last_run_at=datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc),
        )
    )
    store.schedules.create(
        ScheduleRecord(
            id="demo-stock",
            name="stock-watch",
            blueprint=str(_REPO / "examples" / "vector" / "books-restock-notify.blueprint.json"),
            trigger={"kind": "cron", "expr": "0 0,3 * * *", "misfire": "skip"},
            notify={"channel": "ntfy", "target": "{{ secrets.ntfy_topic }}", "on": "change"},
            enabled=False,
            created_at=datetime(2026, 6, 20, 9, 30, tzinfo=timezone.utc),
            next_run_at=datetime(2026, 7, 14, 22, 0, tzinfo=timezone.utc),
            last_run_at=datetime(2026, 7, 10, 1, 0, tzinfo=timezone.utc),
        )
    )
    store.runs.record(
        RunRecord(
            run_id="demo-run-1",
            blueprint_name="quotes.watch",
            status="success",
            schedule_id="demo-quotes",
            outputs={"quote": "“The world as we have created it…”", "author": "Albert Einstein"},
            started_at=datetime(2026, 7, 14, 14, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 14, 14, 0, 1, 342000, tzinfo=timezone.utc),
        )
    )
    store.runs.record(
        RunRecord(
            run_id="demo-run-2",
            blueprint_name="quotes.watch",
            status="failed",
            schedule_id="demo-quotes",
            error="Expected HTTP 200, got 503 — https://quotes.toscrape.com/",
            started_at=datetime(2026, 7, 14, 13, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 14, 13, 0, 0, 512000, tzinfo=timezone.utc),
        )
    )
    _demo_store = store
    return store


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


async def _human_in_the_loop(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.runs import RunsScreen
    from .widgets.confirm import ConfirmModal

    app.push_screen(RunsScreen(_CONFIRM))
    await pilot.pause()
    # The approval modal the ConsoleApprovalSink raises when a confirm step parks the run; shown with
    # the message the example renders (jsonplaceholder user 1 is "Leanne Graham").
    app.push_screen(
        ConfirmModal(
            "Publish 'Aetherius demo post' as Leanne Graham? Rejects after 30s.",
            title="Publish this post?",
            confirm_label="Approve",
            cancel_label="Reject",
        )
    )
    await pilot.pause()


async def _catalog(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.catalog import CatalogScreen

    app.push_screen(CatalogScreen())
    await pilot.pause()


async def _schedules(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.schedules import SchedulesScreen

    app.push_screen(SchedulesScreen(store=_seeded_store(), probe_daemon=False))
    await pilot.pause()
    await pilot.pause()


async def _schedule_detail(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.schedules.detail import ScheduleDetailScreen

    app.push_screen(ScheduleDetailScreen("demo-quotes", store=_seeded_store()))
    await pilot.pause()
    await pilot.pause()


async def _schedule_form(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.schedules.form import ScheduleFormScreen

    # ukit-planning-week declares two inputs: the shot shows the Blueprint-driven form section.
    app.push_screen(ScheduleFormScreen(store=_seeded_store(), blueprint_path=_EXAMPLE))
    await pilot.pause()
    await pilot.pause()


async def _recorder(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.recorder import RecorderScreen

    app.push_screen(RecorderScreen())
    await pilot.pause()


async def _settings(app: AetheriusConsoleApp, pilot: Pilot[None]) -> None:
    from .screens.settings import SettingsScreen

    app.push_screen(SettingsScreen())
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
    ("home", (92, 34), _home),
    ("library", (100, 26), _library),
    ("runs", (100, 34), _runs),
    ("human-in-the-loop", (100, 34), _human_in_the_loop),
    ("schedules", (122, 24), _schedules),
    ("schedule-detail", (100, 42), _schedule_detail),
    ("schedule-form", (104, 52), _schedule_form),
    ("catalog", (110, 26), _catalog),
    ("recorder", (100, 30), _recorder),
    ("settings", (100, 26), _settings),
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
    # this also makes the output identical regardless of where the repo is cloned. The home prefix
    # is neutralized too: a path clipped by a narrow table column can end before the repo name,
    # which would otherwise leave the username in the truncated remainder.
    svg = svg.replace(str(_REPO), "/home/user/aetherius")
    svg = svg.replace(str(Path.home()), "/home/user")
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
    with _pinned_timezone():
        return [await _capture(slug, size, setup, out_dir) for slug, size, setup in _SHOTS]


def main() -> None:
    out_dir = _REPO / "docs" / "screenshots"
    paths = asyncio.run(capture_all(out_dir))
    for path in paths:
        print(f"wrote {path.relative_to(_REPO)}")


if __name__ == "__main__":
    main()
