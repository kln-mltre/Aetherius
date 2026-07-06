"""Shared Playwright plumbing for the recorders: lazy import and the synchronous pump loop.

Both recorders drive a visible browser and collect callbacks that the sync Playwright API only
dispatches while a Playwright call is in flight. They share the same lazy import (so ``import
aetherius`` stays light and a missing extra is a typed error) and the same idle pump, kept here once.
"""

from __future__ import annotations

import threading
from typing import Any

from ..core.errors import DependencyError

# How often the pump wakes to let the sync Playwright API dispatch pending binding/event callbacks.
_PUMP_INTERVAL_MS = 200


def import_playwright() -> Any:
    """Import the sync Playwright entry point, or raise a typed, actionable error."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # extra [browser] not installed
        raise DependencyError(
            "The recorder requires Playwright. Install it with:\n"
            '    pip install "aetherius[browser]" && playwright install chromium',
            extra="browser",
        ) from exc
    return sync_playwright


def pump(context: Any, disconnected: threading.Event, *stop_events: threading.Event | None) -> None:
    """Keep the sync API alive so callbacks fire, until the window closes or a stop event is set.

    Several stop events are accepted (e.g. the caller's Stop and the overlay's Finish); any one ends
    the loop. ``None`` entries are ignored so callers can pass optional events directly.
    """
    while not disconnected.is_set() and not any(_is_set(e) for e in stop_events):
        pages = context.pages
        if not pages:
            break
        try:
            pages[0].wait_for_timeout(_PUMP_INTERVAL_MS)
        except Exception:  # the page or context went away: the demonstration is over
            break


def _is_set(event: threading.Event | None) -> bool:
    return event is not None and event.is_set()
