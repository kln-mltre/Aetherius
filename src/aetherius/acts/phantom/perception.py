"""Phantom perception: the shared browser perception, as the loop's seam for it.

Phantom perceives via the shared ``capture()`` (viewport screenshot + geometry + URL) on
Continuum's already-open page — no separate browser is launched. This thin seam is where richer
fusion (DOM + accessibility tree into the planner state) will be added later; today the screenshot
plus the URL is the planner's context, which is the primary channel a VLM planner reasons over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._perception import Perception, capture

if TYPE_CHECKING:
    from playwright.sync_api import Page


def perceive(page: "Page") -> Perception:
    """Snapshot *page* for one planning iteration (screenshot + geometry + URL)."""
    return capture(page)
