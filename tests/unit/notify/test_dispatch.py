"""Tests for notify.dispatch — delivery failures are contained, never propagated."""

from __future__ import annotations

import logging

import pytest

from aetherius.notify import Notification, dispatch

pytestmark = pytest.mark.unit


class RecordingChannel:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


class ExplodingChannel:
    def send(self, notification: Notification) -> None:
        raise RuntimeError("provider down")


def test_successful_delivery_returns_true() -> None:
    channel = RecordingChannel()
    assert dispatch(Notification(body="ping"), channel) is True
    assert [n.body for n in channel.sent] == ["ping"]


def test_failure_is_logged_and_contained(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="aetherius.notify"):
        assert dispatch(Notification(body="ping"), ExplodingChannel()) is False
    assert any("failed" in record.message for record in caplog.records)
