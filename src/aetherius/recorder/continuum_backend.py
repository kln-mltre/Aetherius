"""Continuum recorder backend: capture DOM interactions and picks into a browser Blueprint.

Injects the shared selector primitives, the action-capture script and the pick overlay; collects the
DOM events they report (plus top-level navigations); and transforms them into ``continuum`` steps via
:mod:`._transform`. This is the Act II half of the Act-agnostic recorder (:mod:`.base`).
"""

from __future__ import annotations

import json
from typing import Any

from ._capture_js import RECORDER_JS
from ._overlay_js import OVERLAY_JS
from ._selector_js import SELECTOR_JS
from ._transform import events_to_steps
from .base import RecordingResult, register_backend
from .capture import _OVERLAY_KINDS, RecordedEvent, _descriptor_from_raw
from .selector_synth import synthesize
from .session import RecordingSession


def describe_event(event: RecordedEvent) -> str:
    """Sober one-line description of a captured DOM action, for the Console event log / CLI."""
    if event.kind == "navigate" or (event.kind == "click" and event.url):
        return f"navigate  {event.url or ''}"
    selector = synthesize(event.descriptor).selector if event.descriptor else "?"
    config = event.config or {}
    if event.kind == "extract":
        return f"extract {config.get('name', '?')}  {selector}"
    if event.kind == "extract_records":
        fields = ", ".join(f.get("name", "?") for f in config.get("fields", []))
        return f"extract table {config.get('name', '?')} ({fields})  {selector}"
    if event.kind == "wait_for":
        return f"wait_for  {selector}"
    if event.kind == "parameterize":
        return f"input {config.get('name', '?')}  {selector}"
    if event.kind == "press":
        return f"press {event.key or 'Enter'}  {selector}"
    return f"{event.kind}  {selector}"


class ContinuumRecorder:
    """Records DOM interactions and overlay picks into a ``continuum`` Blueprint."""

    act = "continuum"

    def __init__(self, *, credentials_as_secrets: bool = True) -> None:
        self._credentials_as_secrets = credentials_as_secrets
        self._events: list[RecordedEvent] = []
        self._last_nav_url: str | None = None
        self._session: RecordingSession | None = None

    def init_scripts(self) -> list[str]:
        return [SELECTOR_JS, RECORDER_JS, OVERLAY_JS]

    def attach(self, session: RecordingSession) -> None:
        self._session = session
        session.expose("__aetherius_capture", self._on_binding)
        session.on_new_page(self._wire_page)

    def result(self) -> RecordingResult:
        steps, secrets, inputs, outputs = events_to_steps(
            self._events, credentials_as_secrets=self._credentials_as_secrets
        )
        return RecordingResult(steps=steps, secrets=secrets, inputs=inputs, outputs=outputs)

    # ── capture ────────────────────────────────────────────────────────────────
    def _wire_page(self, page: Any) -> None:
        page.on("framenavigated", self._on_framenavigated)

    def _on_framenavigated(self, frame: Any) -> None:
        if frame.parent_frame is not None:
            return  # only the main frame is a user-visible navigation
        url = frame.url
        if not url or url == "about:blank" or url == self._last_nav_url:
            return
        self._last_nav_url = url
        self._emit(RecordedEvent(kind="navigate", url=url))

    def _on_binding(self, _source: dict[str, Any], payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError):
            return
        kind = str(data.get("kind", ""))
        if kind == "finish":
            if self._session is not None:
                self._session.finish()  # overlay Finish: end without closing the window
            return
        raw = data.get("descriptor")
        descriptor = _descriptor_from_raw(raw) if raw else None
        if kind in _OVERLAY_KINDS:
            config = {k: v for k, v in data.items() if k not in ("kind", "descriptor")}
            self._emit(RecordedEvent(kind=kind, descriptor=descriptor, config=config))
            return
        self._emit(
            RecordedEvent(
                kind=kind,
                descriptor=descriptor,
                value=data.get("value"),
                key=data.get("key"),
                url=data.get("href"),  # set for a link click: replayed as a navigate, not a click
                redacted=bool(data.get("redacted", False)),
            )
        )

    def _emit(self, event: RecordedEvent) -> None:
        self._events.append(event)
        if self._session is not None:
            self._session.notify(describe_event(event))


register_backend(
    "continuum",
    lambda **o: ContinuumRecorder(
        credentials_as_secrets=bool(o.get("credentials_as_secrets", True))
    ),
)
