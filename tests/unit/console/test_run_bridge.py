"""Tests for console/run_bridge.py — TextualRunSink, in isolation from any running App."""

from __future__ import annotations

import pytest

from aetherius.console.run_bridge import TextualRunSink
from aetherius.core.events.models import EventType, RunEvent

pytestmark = pytest.mark.unit


class _FakeApp:
    """Stands in for textual.app.App: call_from_thread runs the callback synchronously."""

    def call_from_thread(self, callback, *args, **kwargs):  # type: ignore[no-untyped-def]
        return callback(*args, **kwargs)


class _FakeWriter:
    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def write_event(self, event: RunEvent) -> None:
        self.events.append(event)


class _RaisingWriter:
    def write_event(self, event: RunEvent) -> None:
        raise RuntimeError("boom")


def test_on_event_forwards_to_writer() -> None:
    writer = _FakeWriter()
    sink = TextualRunSink(_FakeApp(), writer)  # type: ignore[arg-type]

    event = RunEvent(run_id="r1", type=EventType.PROGRESS, message="hello")
    sink.on_event(event)

    assert writer.events == [event]


def test_on_event_never_raises_when_writer_fails() -> None:
    sink = TextualRunSink(_FakeApp(), _RaisingWriter())  # type: ignore[arg-type]

    sink.on_event(RunEvent(run_id="r1", type=EventType.DONE))  # must not raise
