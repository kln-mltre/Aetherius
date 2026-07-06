"""Gesture recorder: capture real human mouse traces to extend the stealth gesture library.

The stealth mouse humanizer replays gestures from a source-agnostic library (:mod:`aetherius.stealth
.gestures.library`); the package ships a synthetic seed so it works from day one. This recorder adds
*real* traces in the exact same neutral format: a gesture is a list of ``[dx, dy, t]`` offsets from
its start. The browser wiring captures raw pointer samples; the pure functions here segment them into
aimed gestures (the move leading up to each click) and merge them into the library file.

Segmentation is pure and unit-tested without a browser; only :func:`record_gestures` needs Playwright.
"""

from __future__ import annotations

import json
import math
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from ..stealth.gestures import library as _library
from ..stealth.gestures.library import Point
from ._gesture_js import GESTURE_RECORDER_JS
from ._playwright import import_playwright, pump

# Reuse the library's own path as the single source of truth for where traces live.
_DEFAULT_LIBRARY_FILE = _library._DATA_FILE

# A new gesture starts after a pause this long (s); a gesture must have at least this many points and
# span at least this many pixels, to drop idle jitter and accidental micro-moves.
_PAUSE_S = 0.35
_MIN_POINTS = 5
_MIN_DISTANCE_PX = 12.0

_INSTRUCTION_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{height:100%;margin:0;background:#0f0b1e;color:#e7e2f3;
    font:16px/1.6 system-ui,sans-serif;display:flex;align-items:center;justify-content:center}
  .card{max-width:32rem;text-align:center;padding:2rem}
  h1{font-weight:600;letter-spacing:.02em}
  b{color:#e0b64d}
</style></head><body><div class="card">
  <h1>Gesture recorder</h1>
  <p>Move the mouse naturally across this page and <b>click</b> in different spots, as if using a
  real site. Each move up to a click is captured as one gesture.</p>
  <p>When you have made a few dozen moves, <b>close this window</b> to save.</p>
</div></body></html>"""


def _instruction_url() -> str:
    return "data:text/html," + urllib.parse.quote(_INSTRUCTION_HTML)


def _to_relative(segment: list[Point]) -> list[Point]:
    """Rebase an absolute ``[x, y, t]`` segment onto offsets from its first point."""
    x0, y0, t0 = segment[0]
    return [(round(x - x0, 2), round(y - y0, 2), round(t - t0, 4)) for x, y, t in segment]


def _span(relative: list[Point]) -> float:
    """Total displacement of a rebased gesture (distance of its last offset)."""
    end_x, end_y, _ = relative[-1]
    return math.hypot(end_x, end_y)


def segment_gestures(
    samples: list[Point],
    clicks: list[float],
    *,
    pause_s: float = _PAUSE_S,
    min_points: int = _MIN_POINTS,
    min_distance_px: float = _MIN_DISTANCE_PX,
) -> list[list[Point]]:
    """Split raw absolute pointer samples into aimed gestures in the neutral library format.

    A gesture is the run of samples leading up to a click (the aimed move), also broken on any pause
    longer than *pause_s*. Degenerate runs (too few points or too short a path) are discarded.
    """
    points = sorted(samples, key=lambda s: s[2])
    click_times = sorted(clicks)
    segments: list[list[Point]] = []
    current: list[Point] = []
    click_index = 0

    for x, y, t in points:
        if current and (t - current[-1][2]) > pause_s:
            segments.append(current)
            current = []
        current.append((x, y, t))
        while click_index < len(click_times) and click_times[click_index] <= t + 1e-6:
            # Close only if the click belongs to this run; a click stranded in a pause gap before
            # the current segment started belonged to an already-closed gesture, so just skip it.
            if current and click_times[click_index] >= current[0][2] - 1e-6:
                segments.append(current)
                current = []
            click_index += 1
    if current:
        segments.append(current)

    gestures: list[list[Point]] = []
    for segment in segments:
        if len(segment) < min_points:
            continue
        relative = _to_relative(segment)
        if _span(relative) >= min_distance_px:
            gestures.append(relative)
    return gestures


def merge_into_library(path: Path, gestures: list[list[Point]]) -> int:
    """Append *gestures* to the library file at *path* without dropping what is already there.

    Existing traces (synthetic seed or earlier recordings) are preserved; ``meta`` is updated to mark
    that the library now contains recorded human traces. Returns the number of gestures added.
    """
    existing: list[Any] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = list(data.get("gestures", []))
        except (ValueError, OSError):
            existing = []

    combined = existing + [[list(point) for point in gesture] for gesture in gestures]
    payload = {
        "meta": {
            "source": "recorded-human",
            "generator": "aetherius.recorder.gesture_recorder",
            "count": len(combined),
            "note": "Real captured traces; may include prior seed/recorded gestures (same format).",
        },
        "gestures": combined,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return len(gestures)


def record_gestures(
    *,
    out_path: Path | str | None = None,
    on_event: Callable[[int], None] | None = None,
    stop_event: threading.Event | None = None,
) -> tuple[Path, int]:
    """Capture mouse traces in a live browser, segment them, and merge them into the library.

    Returns the library path written and the number of gestures added. Stops when the window closes
    or *stop_event* is set.
    """
    samples: list[Point] = []
    clicks: list[float] = []

    def on_binding(_source: dict[str, Any], payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        for move in data.get("moves", []):
            samples.append((float(move[0]), float(move[1]), float(move[2])))
        if data.get("click") is not None:
            clicks.append(float(data["click"]))
        if on_event is not None:
            on_event(len(samples))

    sync_playwright = import_playwright()
    pw = sync_playwright().start()
    browser = context = None
    disconnected = threading.Event()
    try:
        browser = pw.chromium.launch(headless=False)
        browser.on("disconnected", lambda: disconnected.set())
        context = browser.new_context()
        context.expose_binding("__aetherius_gesture", on_binding)
        context.add_init_script(GESTURE_RECORDER_JS)
        page = context.new_page()
        page.goto(_instruction_url())
        pump(context, stop_event, disconnected)
    finally:
        for closer in (context, browser):
            if closer is not None:
                try:
                    closer.close()
                except Exception:
                    pass
        try:
            pw.stop()
        except Exception:
            pass

    gestures = segment_gestures(samples, clicks)
    target = Path(out_path) if out_path is not None else _DEFAULT_LIBRARY_FILE
    added = merge_into_library(target, gestures)
    return target, added
