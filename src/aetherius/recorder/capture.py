"""Low-level action capture via a live browser.

Drives a visible Chromium where the user demonstrates a task, and collects the DOM events the
in-page script (:mod:`._capture_js`) reports through the ``__aetherius_capture`` binding, plus the
top-level navigations Playwright surfaces. Synchronous throughout, like the rest of the engine, so it
runs on the caller's thread (a Console worker or the CLI's main thread); Playwright is imported
lazily so ``import aetherius`` never pulls it in and a missing extra surfaces as a typed error.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ._capture_js import RECORDER_JS
from ._playwright import import_playwright, pump
from .selector_synth import Candidate, ElementDescriptor

EventCallback = Callable[["RecordedEvent"], None]


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """One captured user action, before it is transformed into a Blueprint step.

    ``descriptor`` is present for element actions (click/fill/select/press) and ``None`` for a
    navigation. A password field never carries its value: ``redacted`` is set instead.
    """

    kind: str  # "navigate" | "click" | "fill" | "select" | "press"
    descriptor: ElementDescriptor | None = None
    value: str | None = None
    key: str | None = None
    url: str | None = None
    redacted: bool = False
    ts: float = field(default_factory=time.monotonic)


def _descriptor_from_raw(raw: dict[str, Any]) -> ElementDescriptor:
    """Build an :class:`ElementDescriptor` from the JSON the in-page script sent."""
    candidates = tuple(
        Candidate(
            strategy=str(c["strategy"]),
            selector=str(c["selector"]),
            selector_type=str(c.get("selector_type", "css")),
            unique=bool(c["unique"]),
        )
        for c in raw.get("candidates", [])
    )
    return ElementDescriptor(
        tag=str(raw.get("tag", "")),
        css_path=str(raw.get("css_path", "")),
        candidates=candidates,
        text=raw.get("text"),
        name=raw.get("name"),
        field_type=raw.get("field_type"),
        autocomplete=raw.get("autocomplete"),
    )


class RecordingSession:
    """Owns a visible browser for the duration of a demonstration and yields the captured events.

    Stops when the user closes the window or when ``stop_event`` is set (the Console's Stop button).
    ``on_event`` is invoked for each captured action as it happens, for live streaming.
    """

    def __init__(
        self,
        start_url: str,
        *,
        on_event: EventCallback | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._start_url = start_url
        self._on_event = on_event
        self._stop = stop_event
        self._events: list[RecordedEvent] = []
        self._last_nav_url: str | None = None

    def record(self) -> list[RecordedEvent]:
        """Launch the browser, capture until the session ends, and return the ordered events."""
        sync_playwright = import_playwright()
        pw = sync_playwright().start()
        browser = context = None
        disconnected = threading.Event()
        try:
            browser = pw.chromium.launch(headless=False)
            browser.on("disconnected", lambda: disconnected.set())
            context = browser.new_context()
            context.expose_binding("__aetherius_capture", self._on_binding)
            context.add_init_script(RECORDER_JS)
            context.on("page", self._wire_page)

            page = context.new_page()
            self._wire_page(page)
            page.goto(self._start_url)

            pump(context, self._stop, disconnected)
        finally:
            for closer in (context, browser):
                if closer is not None:
                    try:
                        closer.close()
                    except Exception:  # teardown must never mask what was already captured
                        pass
            try:
                pw.stop()
            except Exception:
                pass
        return self._events

    def _wire_page(self, page: Any) -> None:
        """Attach navigation capture to a page (the first one and any later popup/tab)."""
        page.on("framenavigated", self._on_framenavigated)

    def _on_framenavigated(self, frame: Any) -> None:
        """Record a top-level navigation, ignoring sub-frames and blank pages."""
        if frame.parent_frame is not None:
            return  # only the main frame is a user-visible navigation
        url = frame.url
        if not url or url == "about:blank" or url == self._last_nav_url:
            return
        self._last_nav_url = url
        self._emit(RecordedEvent(kind="navigate", url=url))

    def _on_binding(self, _source: dict[str, Any], payload: str) -> None:
        """Handle one JSON action reported by the in-page capture script."""
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        raw_descriptor = data.get("descriptor")
        descriptor = _descriptor_from_raw(raw_descriptor) if raw_descriptor else None
        self._emit(
            RecordedEvent(
                kind=str(data.get("kind", "")),
                descriptor=descriptor,
                value=data.get("value"),
                key=data.get("key"),
                redacted=bool(data.get("redacted", False)),
            )
        )

    def _emit(self, event: RecordedEvent) -> None:
        self._events.append(event)
        if self._on_event is not None:
            self._on_event(event)
