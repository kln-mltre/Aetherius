"""Tests for notify/channels/telegram.py — sendMessage wire format, plain text on purpose."""

from __future__ import annotations

import httpx
import pytest

from aetherius.notify.channels import TelegramChannel
from aetherius.notify.message import Notification

from .conftest import Capture

pytestmark = pytest.mark.unit


def test_posts_send_message_with_joined_text(capture: Capture) -> None:
    channel = TelegramChannel("123:token", "42", transport=capture.transport())
    channel.send(Notification(body="Back in stock", title="Alert", url="https://shop.example/p"))
    assert str(capture.only.url) == "https://api.telegram.org/bot123:token/sendMessage"
    assert capture.payload == {
        "chat_id": "42",
        "text": "Alert\n\nBack in stock\n\nhttps://shop.example/p",
    }


def test_never_sets_parse_mode_so_bodies_cannot_break_on_escaping(capture: Capture) -> None:
    channel = TelegramChannel("123:token", "42", transport=capture.transport())
    channel.send(Notification(body="_raw_ *markdown* [x](y)"))
    assert capture.payload == {"chat_id": "42", "text": "_raw_ *markdown* [x](y)"}


def test_raises_on_http_error(capture: Capture) -> None:
    capture.status = 403
    channel = TelegramChannel("123:token", "42", transport=capture.transport())
    with pytest.raises(httpx.HTTPStatusError):
        channel.send(Notification(body="ping"))
