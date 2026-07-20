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


def test_confirm_callback_becomes_tappable_action_buttons(capture: Capture) -> None:
    """Human-in-the-loop (Jalon 2-E): a confirm callback under data['confirm'] adds Approve/Reject."""
    channel = NtfyChannel("approvals", transport=capture.transport())
    channel.send(
        Notification(
            body="Publish this post?",
            data={
                "confirm": {
                    "decisions_url": "https://box.example/v1/runs/r1/decisions",
                    "token": "tok-abc",
                    "auth": "Bearer s3cr3t",
                }
            },
        )
    )
    actions = capture.payload["actions"]
    assert [a["label"] for a in actions] == ["Approve", "Reject"]
    assert all(a["action"] == "http" and a["method"] == "POST" for a in actions)
    assert all(a["url"] == "https://box.example/v1/runs/r1/decisions" for a in actions)
    assert actions[0]["body"] == '{"token": "tok-abc", "approved": true}'
    assert actions[0]["headers"]["Authorization"] == "Bearer s3cr3t"


def test_no_action_buttons_without_a_reachable_callback(capture: Capture) -> None:
    # An informational confirm alert (no decisions_url) carries no dead buttons.
    channel = NtfyChannel("approvals", transport=capture.transport())
    channel.send(Notification(body="Approve?", data={"confirm": {"token": "x"}}))
    assert "actions" not in capture.payload
