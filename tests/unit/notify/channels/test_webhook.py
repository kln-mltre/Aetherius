"""Tests for notify/channels/webhook.py — httpx.MockTransport, wire format exact."""

from __future__ import annotations

import httpx
import pytest

from aetherius.notify.channels import WebhookChannel
from aetherius.notify.message import Notification, NotificationLevel

from .conftest import Capture

pytestmark = pytest.mark.unit


def test_posts_the_full_notification_as_json(capture: Capture) -> None:
    channel = WebhookChannel("https://hooks.example/x", transport=capture.transport())
    channel.send(
        Notification(
            body="Back in stock",
            title="Alert",
            level=NotificationLevel.WARNING,
            url="https://shop.example/p",
            data={"sku": "42"},
        )
    )
    assert capture.only.method == "POST"
    assert str(capture.only.url) == "https://hooks.example/x"
    assert capture.payload == {
        "body": "Back in stock",
        "title": "Alert",
        "level": "warning",
        "url": "https://shop.example/p",
        "data": {"sku": "42"},
    }


def test_defaults_serialize_as_nulls_not_omissions(capture: Capture) -> None:
    channel = WebhookChannel("https://hooks.example/x", transport=capture.transport())
    channel.send(Notification(body="ping"))
    assert capture.payload == {
        "body": "ping",
        "title": None,
        "level": "info",
        "url": None,
        "data": {},
    }


def test_raises_on_http_error(capture: Capture) -> None:
    capture.status = 500
    channel = WebhookChannel("https://hooks.example/x", transport=capture.transport())
    with pytest.raises(httpx.HTTPStatusError):
        channel.send(Notification(body="ping"))
