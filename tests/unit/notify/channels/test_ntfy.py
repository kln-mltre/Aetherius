"""Tests for notify/channels/ntfy.py — JSON publishing mode, level-to-priority mapping."""

from __future__ import annotations

import httpx
import pytest

from aetherius.notify.channels import NtfyChannel
from aetherius.notify.message import Notification, NotificationLevel

from .conftest import Capture

pytestmark = pytest.mark.unit


def test_publishes_json_to_the_server_root(capture: Capture) -> None:
    channel = NtfyChannel("restock", transport=capture.transport())
    channel.send(
        Notification(
            body="Back in stock",
            title="Alerte accentuée",
            url="https://shop.example/p",
        )
    )
    assert str(capture.only.url) == "https://ntfy.sh"
    assert capture.payload == {
        "topic": "restock",
        "message": "Back in stock",
        "priority": 3,
        "title": "Alerte accentuée",
        "click": "https://shop.example/p",
    }


@pytest.mark.parametrize(
    ("level", "priority"),
    [(NotificationLevel.INFO, 3), (NotificationLevel.WARNING, 4), (NotificationLevel.ERROR, 5)],
)
def test_level_maps_to_ntfy_priority(
    capture: Capture, level: NotificationLevel, priority: int
) -> None:
    channel = NtfyChannel("restock", transport=capture.transport())
    channel.send(Notification(body="ping", level=level))
    assert capture.payload == {"topic": "restock", "message": "ping", "priority": priority}


def test_self_hosted_server_with_trailing_slash(capture: Capture) -> None:
    channel = NtfyChannel("restock", server="https://ntfy.local/", transport=capture.transport())
    channel.send(Notification(body="ping"))
    assert str(capture.only.url) == "https://ntfy.local"


def test_raises_on_http_error(capture: Capture) -> None:
    capture.status = 502
    channel = NtfyChannel("restock", transport=capture.transport())
    with pytest.raises(httpx.HTTPStatusError):
        channel.send(Notification(body="ping"))
