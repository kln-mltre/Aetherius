"""Playwright browser lifecycle: launch, contexts, headed and headless modes, debug options.

Wraps the synchronous Playwright API. The engine (and therefore this driver) is synchronous, so the
sync API is the natural fit: no event loop to juggle inside the driver. Playwright is imported
lazily so ``import aetherius`` never pulls it in; a missing extra surfaces as a typed DependencyError.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ...core.errors import DependencyError
from .debug_overlay import DEBUG_OVERLAY_JS

# Slow-motion delay (ms) inserted before every action when debug is on, so a human can follow along.
_DEBUG_SLOW_MO_MS = 500
# How long the window lingers after the last step (or a failure) in debug, so it does not just
# flash and vanish before the final state can be read.
_DEBUG_LINGER_MS = 2500


def _import_playwright() -> Any:
    """Import the sync Playwright entry point, or raise a typed, actionable error."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # extra [browser] not installed
        raise DependencyError(
            "Act II (Continuum) requires Playwright. Install it with:\n"
            '    pip install "aetherius[browser]" && playwright install chromium',
            extra="browser",
        ) from exc
    return sync_playwright


class BrowserSession:
    """Owns a Playwright instance, context and page for the duration of a run.

    An ephemeral context by default; a *persistent* context (reused cookies/cache/history) when a
    profile directory is supplied. ``debug`` opens a headed window with slow-motion so a step can be
    watched. ``stealth`` is accepted for forward-compatibility and ignored until the discretion layer
    lands.
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        timeout_ms: int = 30_000,
        profile_dir: Path | None = None,
        stealth: Any | None = None,
    ) -> None:
        self._debug = debug
        self._timeout_ms = timeout_ms
        self._profile_dir = profile_dir
        self._stealth = stealth  # reserved: discretion layer plugs in here later
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def start(self) -> None:
        """Launch the browser and open the working page. Idempotent per session."""
        sync_playwright = _import_playwright()
        self._pw = sync_playwright().start()

        headless = not self._debug
        slow_mo = _DEBUG_SLOW_MO_MS if self._debug else 0

        if self._profile_dir is not None:
            self._context = self._pw.chromium.launch_persistent_context(
                str(self._profile_dir),
                headless=headless,
                slow_mo=slow_mo,
            )
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=slow_mo)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()

        self._context.set_default_timeout(self._timeout_ms)

        if self._debug:
            # Visible cursor + red click ripple, re-installed on every navigation.
            self._context.add_init_script(DEBUG_OVERLAY_JS)

    @property
    def page(self) -> Any:
        """The active Playwright page. Valid only between ``start`` and ``close``."""
        if self._page is None:
            raise RuntimeError("BrowserSession.page accessed before start() or after close().")
        return self._page

    def close(self) -> None:
        """Tear down page, context, browser and Playwright, tolerating partial startup.

        In debug mode, linger briefly first so the final page (or the point of failure) stays on
        screen instead of vanishing the instant the run ends.
        """
        if self._debug and self._page is not None:
            time.sleep(_DEBUG_LINGER_MS / 1000)

        for closer in (
            self._context,
            self._browser,
        ):
            if closer is not None:
                try:
                    closer.close()
                except Exception:  # teardown must never mask the original run error
                    pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
        self._page = self._context = self._browser = self._pw = None
