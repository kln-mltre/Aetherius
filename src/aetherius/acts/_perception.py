"""Perception: turn a live browser page into the state a cognition provider reasons over.

A ``Perception`` fuses a viewport screenshot (PNG bytes) with the page geometry and, optionally, a
serialized DOM / accessibility snapshot. Built once per perceived step by the browser Acts — Oracle
and Phantom reuse Continuum's already-open page, so perception never launches its own browser.

The screenshot is taken with ``scale="css"`` so one image pixel equals one CSS pixel: the boxes a
grounder returns on the image land directly in the coordinate space of ``page.mouse`` — no
device-pixel-ratio math anywhere downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass(frozen=True)
class Perception:
    """A snapshot of the page for the cognition layer."""

    screenshot: bytes
    viewport: tuple[int, int]
    url: str | None = None
    dom: str | None = None


def capture(page: "Page", *, include_dom: bool = False) -> Perception:
    """Snapshot *page* into a ``Perception`` (screenshot + geometry; DOM when *include_dom*).

    ``playwright`` is the ``[browser]`` extra; this signature only names it for typing — the
    function itself speaks plain Playwright methods on an already-open page, so the runtime
    import stays inside the browser Acts.
    """
    screenshot = page.screenshot(type="png", scale="css")
    size = page.viewport_size
    if size is None:
        # No fixed viewport (headed browser without one): fall back to the live window size.
        size = page.evaluate("() => ({ width: window.innerWidth, height: window.innerHeight })")
    return Perception(
        screenshot=screenshot,
        viewport=(int(size["width"]), int(size["height"])),
        url=page.url,
        dom=page.content() if include_dom else None,
    )
