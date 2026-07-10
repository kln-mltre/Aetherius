"""Generic recording session: owns the live browser, driven by an Act-specific backend.

This is the shared shell every recorder reuses — launch, context, page, the synchronous pump, and the
seams a backend needs (expose a binding, hook new pages, stream a description, end the session). It
holds no Act logic: what to inject and how to interpret captures is the backend's job (:mod:`.base`).
Synchronous throughout (runs on the caller's thread); Playwright is imported lazily.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from ._playwright import import_playwright, pump
from .base import RecorderBackend, RecordingResult

# A backend streams human-readable descriptions of what it captures; the Console/CLI render them.
NotifyCallback = Callable[[str], None]
PageHook = Callable[[Any], None]


class RecordingSession:
    """Owns a visible browser for a demonstration and returns the backend's RecordingResult.

    Stops when the user closes the window, when ``stop_event`` is set (the Console's Stop button), or
    when the backend calls :meth:`finish` (e.g. the overlay's Finish button).
    """

    def __init__(
        self,
        start_url: str,
        backend: RecorderBackend,
        *,
        on_event: NotifyCallback | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._start_url = start_url
        self._backend = backend
        self._on_event = on_event
        self._stop = stop_event
        self._done = threading.Event()
        self._context: Any = None
        self._page_hooks: list[PageHook] = []

    def record(self) -> RecordingResult:
        """Launch the browser, let the backend capture until the session ends, return its result."""
        sync_playwright = import_playwright()
        pw = sync_playwright().start()
        browser = None
        disconnected = threading.Event()
        try:
            browser = pw.chromium.launch(headless=False)
            browser.on("disconnected", lambda: disconnected.set())
            self._context = browser.new_context()
            for script in self._backend.init_scripts():
                self._context.add_init_script(script)
            self._backend.attach(
                self
            )  # backend registers bindings + page hooks now that ctx exists
            self._context.on("page", self._wire_page)

            page = self._context.new_page()
            self._wire_page(page)
            page.goto(self._start_url)

            pump(self._context, disconnected, self._stop, self._done)
        finally:
            for closer in (self._context, browser):
                if closer is not None:
                    try:
                        closer.close()
                    except Exception:  # teardown must never mask what was already captured
                        pass
            try:
                pw.stop()
            except Exception:
                pass
            self._context = None
        return self._backend.result()

    # ── backend-facing seams ──────────────────────────────────────────────────
    def expose(self, name: str, handler: Callable[..., Any]) -> None:
        """Expose a page binding ``window[name]`` that calls *handler* (context-wide, all pages)."""
        self._context.expose_binding(name, handler)

    def on_new_page(self, hook: PageHook) -> None:
        """Register *hook* to run on the first page and any later popup/tab."""
        self._page_hooks.append(hook)

    def notify(self, description: str) -> None:
        """Stream one human-readable description of a captured item (never raises)."""
        if self._on_event is not None:
            self._on_event(description)

    def finish(self) -> None:
        """End the session from the backend (e.g. the overlay Finish control message)."""
        self._done.set()

    def _wire_page(self, page: Any) -> None:
        for hook in self._page_hooks:
            hook(page)
