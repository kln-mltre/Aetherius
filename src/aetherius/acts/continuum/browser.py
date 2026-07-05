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
from ...stealth.fingerprint.patch import FINGERPRINT_PATCH_JS
from ...stealth.fingerprint.profile import get_profile
from ...stealth.humanizer.input import HumanInput
from ...stealth.policy import OFF, StealthPolicy
from .debug_overlay import DEBUG_OVERLAY_JS
from .human_actions import humanized_actions

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
    watched. ``stealth`` is the assembled :class:`StealthPolicy`: an active one wears a fingerprint
    profile (context options + init patches) and exposes a :class:`HumanInput` for the driver to
    route interactive actions through.
    """

    def __init__(
        self,
        *,
        debug: bool = False,
        timeout_ms: int = 30_000,
        profile_dir: Path | None = None,
        stealth: StealthPolicy = OFF,
    ) -> None:
        self._debug = debug
        self._timeout_ms = timeout_ms
        self._profile_dir = profile_dir
        self._stealth = stealth
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._human: HumanInput | None = None

    def start(self) -> None:
        """Launch the browser and open the working page. Idempotent per session."""
        sync_playwright = _import_playwright()
        self._pw = sync_playwright().start()

        headless = not self._debug
        slow_mo = self._slow_mo_ms()
        context_options = self._context_options()

        if self._profile_dir is not None:
            self._context = self._pw.chromium.launch_persistent_context(
                str(self._profile_dir),
                headless=headless,
                slow_mo=slow_mo,
                **context_options,
            )
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            self._browser = self._pw.chromium.launch(headless=headless, slow_mo=slow_mo)
            self._context = self._browser.new_context(**context_options)
            self._page = self._context.new_page()

        self._context.set_default_timeout(self._timeout_ms)
        self._apply_stealth()

        if self._debug:
            # Visible cursor + red click ripple, re-installed on every navigation.
            self._context.add_init_script(DEBUG_OVERLAY_JS)

    def _slow_mo_ms(self) -> int:
        """Debug slow-motion delay, but 0 whenever inputs are humanized.

        slow_mo delays *every* Playwright op. That is fine for plain actions, but the humanizer
        issues dozens of mouse.move/wheel calls per gesture and supplies its own realistic timing;
        stacking slow_mo on top would shred each gesture into a slow, ugly stutter. So when discretion
        humanizes inputs, the humanizer owns the pacing and slow_mo stays off, even in debug.
        """
        if self._debug and not humanized_actions(self._stealth):
            return _DEBUG_SLOW_MO_MS
        return 0

    def _context_options(self) -> dict[str, Any]:
        """Playwright context options for the active fingerprint profile (empty when none)."""
        if self._stealth.fingerprint is None:
            return {}
        return get_profile(self._stealth.fingerprint).context_options()

    def _apply_stealth(self) -> None:
        """Inject the fingerprint patches and, if inputs are humanized, build the HumanInput facade."""
        if not self._stealth.is_active:
            return
        self._context.add_init_script(FINGERPRINT_PATCH_JS)
        if self._stealth.fingerprint is not None:
            self._context.add_init_script(get_profile(self._stealth.fingerprint).init_script())
        if humanized_actions(self._stealth):
            self._human = HumanInput(self._page, self._stealth)

    @property
    def human(self) -> HumanInput | None:
        """The humanized input facade when discretion humanizes inputs, else ``None``."""
        return self._human

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
        self._human = None
