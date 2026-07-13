"""Tests for notify/sink.py — the on-policy matrix and the containment discipline."""

from __future__ import annotations

import pytest

from aetherius.core.events.models import EventType, RunEvent
from aetherius.notify import Notification, NotificationLevel, NotifySink
from aetherius.notify.sink import NotifyOn

pytestmark = pytest.mark.unit


class RecordingChannel:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


def _done(status: str, error: str | None = None) -> RunEvent:
    return RunEvent(
        run_id="r1",
        type=EventType.DONE,
        message=f"run finished: {status}",
        data={"status": status, "error": error},
    )


@pytest.mark.parametrize(
    ("on", "status", "fires"),
    [
        ("failure", "failed", True),
        ("failure", "success", False),
        ("success", "success", True),
        ("success", "failed", False),
        ("always", "failed", True),
        ("always", "success", True),
    ],
)
def test_policy_matrix(on: NotifyOn, status: str, fires: bool) -> None:
    channel = RecordingChannel()
    NotifySink(channel, on=on).on_event(_done(status))
    assert bool(channel.sent) is fires


def test_failure_notification_carries_the_error_and_context() -> None:
    channel = RecordingChannel()
    NotifySink(channel).on_event(_done("failed", error="LOGIN_FAILED"))
    (notification,) = channel.sent
    assert notification.level is NotificationLevel.ERROR
    assert "run finished: failed" in notification.body
    assert "LOGIN_FAILED" in notification.body
    assert notification.data == {"run_id": "r1", "status": "failed", "error": "LOGIN_FAILED"}


def test_success_notification_is_informational() -> None:
    channel = RecordingChannel()
    NotifySink(channel, on="success").on_event(_done("success"))
    (notification,) = channel.sent
    assert notification.level is NotificationLevel.INFO
    assert notification.title == "Aetherius — run success"


def test_ignores_every_event_but_done() -> None:
    channel = RecordingChannel()
    sink = NotifySink(channel, on="always")
    for type_ in (EventType.PROGRESS, EventType.STEP_FINISHED, EventType.ERROR):
        sink.on_event(RunEvent(run_id="r1", type=type_))
    assert channel.sent == []


def test_delivery_failure_never_reaches_the_run() -> None:
    class ExplodingChannel:
        def send(self, notification: Notification) -> None:
            raise RuntimeError("provider down")

    NotifySink(ExplodingChannel(), on="always").on_event(_done("failed"))
