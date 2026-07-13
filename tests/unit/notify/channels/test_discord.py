"""Tests for notify/channels/discord.py — content vs embed mapping."""

from __future__ import annotations

import httpx
import pytest

from aetherius.notify.channels import DiscordChannel
from aetherius.notify.message import Notification, NotificationLevel

from .conftest import Capture

pytestmark = pytest.mark.unit

_URL = "https://discord.com/api/webhooks/1/token"


def test_bare_body_maps_to_content(capture: Capture) -> None:
    channel = DiscordChannel(_URL, transport=capture.transport())
    channel.send(Notification(body="Back in stock"))
    assert str(capture.only.url) == _URL
    assert capture.payload == {"content": "Back in stock"}


def test_title_and_url_upgrade_to_an_embed(capture: Capture) -> None:
    channel = DiscordChannel(_URL, transport=capture.transport())
    channel.send(
        Notification(
            body="Back in stock",
            title="Alert",
            url="https://shop.example/p",
            level=NotificationLevel.ERROR,
        )
    )
    assert capture.payload == {
        "embeds": [
            {
                "description": "Back in stock",
                "color": 0xE74C3C,
                "title": "Alert",
                "url": "https://shop.example/p",
            }
        ]
    }


def test_raises_on_http_error(capture: Capture) -> None:
    capture.status = 429
    channel = DiscordChannel(_URL, transport=capture.transport())
    with pytest.raises(httpx.HTTPStatusError):
        channel.send(Notification(body="ping"))
