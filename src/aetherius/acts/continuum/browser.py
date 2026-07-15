"""Playwright browser lifecycle: launch, contexts, headed and headless modes, debug options.

Wraps the synchronous Playwright API. The engine (and therefore this driver) is synchronous, so the
sync API is the natural fit: no event loop to juggle inside the driver. Playwright is imported
lazily so ``import aetherius`` never pulls it in; a missing extra surfaces as a typed DependencyError.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from ...core.errors import DependencyError
from ...network.identity import NetworkIdentity
from ...stealth.fingerprint.patch import FINGERPRINT_PATCH_JS
from ...stealth.fingerprint.profile import FingerprintProfile, get_profile
from ...stealth.fingerprint.webrtc import WEBRTC_LAUNCH_FLAGS, webrtc_leak_patch
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
        identity: NetworkIdentity | None = None,
    ) -> None:
        self._debug = debug
        self._timeout_ms = timeout_ms
        self._profile_dir = profile_dir
        self._stealth = stealth
        self._identity = identity
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

        # A browser proxy without WebRTC hardening still leaks the real IP over UDP; the two go
        # together. The launch flag forces proxied-only UDP, the init script neutralises local
        # candidates. Applied only when a proxy is active, so the default path is untouched.
        proxy = self._identity.proxy if self._identity is not None else None
        launch_args = list(WEBRTC_LAUNCH_FLAGS) if proxy is not None else None
        pw_proxy = proxy.for_playwright() if proxy is not None else None

        if self._profile_dir is not None:
            persistent_kwargs: dict[str, Any] = dict(
                headless=headless, slow_mo=slow_mo, **context_options
            )
            if launch_args is not None:
                persistent_kwargs["args"] = launch_args
            if pw_proxy is not None:
                persistent_kwargs["proxy"] = pw_proxy
            self._context = self._pw.chromium.launch_persistent_context(
                str(self._profile_dir), **persistent_kwargs
            )
            pages = self._context.pages
            self._page = pages[0] if pages else self._context.new_page()
        else:
            launch_kwargs: dict[str, Any] = dict(headless=headless, slow_mo=slow_mo)
            if launch_args is not None:
                launch_kwargs["args"] = launch_args
            self._browser = self._pw.chromium.launch(**launch_kwargs)
            new_context_kwargs: dict[str, Any] = dict(context_options)
            if pw_proxy is not None:
                new_context_kwargs["proxy"] = pw_proxy
            self._context = self._browser.new_context(**new_context_kwargs)
            self._page = self._context.new_page()

        self._context.set_default_timeout(self._timeout_ms)
        if proxy is not None:
            self._context.add_init_script(webrtc_leak_patch())
        self._apply_stealth()

        # Attach only after the initial page is set, so the listener reacts to genuine new
        # tabs/popups (a target="_blank" click, window.open) rather than the page we just opened.
        self._context.on("page", self._on_new_page)

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

    def pace_raw_action(self) -> None:
        """Slow a raw (non-humanized) action in debug when slow_mo is off, so it stays watchable.

        Counterpart to :meth:`_slow_mo_ms`: when inputs are humanized, slow_mo is 0 and the humanizer
        paces the gestures it owns — but raw ops it never touches (select, upload, navigate, …) would
        then flash by. Give them the same delay slow_mo would have, so nothing is invisible in debug.
        """
        if self._debug and humanized_actions(self._stealth):
            time.sleep(_DEBUG_SLOW_MO_MS / 1000)

    def _on_new_page(self, page: Any) -> None:
        """Follow a newly opened tab/popup: make it the active page for the steps that follow.

        A target="_blank" click (or window.open) spawns a fresh Playwright page; without this the
        session would keep operating on the old tab and every later step would miss its target. The
        previous tab stays open. HumanInput/HumanMouse cache the page reference, so rebuild the facade
        (a pure, browser-free constructor) to point the humanizer at the new tab.
        """
        self._page = page
        self._rebuild_human()
        page.on("close", self._on_page_close)

    def _on_page_close(self, page: Any) -> None:
        """When the active tab closes, fall back to the most recent surviving page.

        A transient popup (a download stub, a tracking pixel) can open then close; without a fallback
        the session would be stranded on a dead page. Ignore closes of non-active tabs.
        """
        if page is not self._page:
            return
        survivors = [p for p in self._context.pages if p is not page] if self._context else []
        if survivors:
            self._page = survivors[-1]
            self._rebuild_human()

    def _rebuild_human(self) -> None:
        """Repoint the humanizer facade at the current page (no-op when inputs are not humanized)."""
        if self._human is not None:
            self._human = HumanInput(self._page, self._stealth)

    def _effective_profile(self) -> FingerprintProfile | None:
        """The active fingerprint profile, with timezone/locale/languages aligned to the exit-IP geo.

        A US exit IP behind a ``Europe/Paris`` profile is a tell; when the proxy carries a country the
        profile follows it. Returns ``None`` when no fingerprint profile is worn.
        """
        if self._stealth.fingerprint is None:
            return None
        profile = get_profile(self._stealth.fingerprint)
        geo = self._identity.geo if self._identity is not None else None
        if geo is not None:
            profile = replace(
                profile,
                timezone_id=geo.timezone_id,
                locale=geo.locale,
                languages=geo.languages,
            )
        return profile

    def _context_options(self) -> dict[str, Any]:
        """Playwright context options for the fingerprint profile and/or the exit-IP geo (empty when
        neither applies)."""
        profile = self._effective_profile()
        if profile is not None:
            return profile.context_options()
        # No fingerprint profile, but a geo hint still aligns the browser's timezone/locale with the IP.
        geo = self._identity.geo if self._identity is not None else None
        if geo is not None:
            return {"locale": geo.locale, "timezone_id": geo.timezone_id}
        return {}

    def _apply_stealth(self) -> None:
        """Inject the fingerprint patches and, if inputs are humanized, build the HumanInput facade."""
        if not self._stealth.is_active:
            return
        self._context.add_init_script(FINGERPRINT_PATCH_JS)
        profile = self._effective_profile()
        if profile is not None:
            self._context.add_init_script(profile.init_script())
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
