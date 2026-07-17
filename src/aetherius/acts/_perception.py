"""Perception: turn a live browser page into the state a cognition provider reasons over.

A ``Perception`` fuses a viewport screenshot (PNG bytes) with the page geometry and, optionally, a
serialized DOM / accessibility snapshot. Built once per perceived step by the browser Acts — Oracle
and Phantom reuse Continuum's already-open page, so perception never launches its own browser.
Skeleton for Jalon 2-A.
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

    Implemented in Jalon 2-A. ``playwright`` is the ``[browser]`` extra; this signature only names it
    for typing — the runtime import stays inside the browser Acts.
    """
    raise NotImplementedError
