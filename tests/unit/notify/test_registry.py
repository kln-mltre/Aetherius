"""Tests for notify/registry.py — built-in table, target keys, plugin seam, typed errors."""

from __future__ import annotations

from typing import Mapping

import pytest

from aetherius.core.errors import NotificationError
from aetherius.notify import Notification, NotificationChannel, build_channel, register_channel
from aetherius.notify import registry
from aetherius.notify.channels import DiscordChannel, NtfyChannel, TelegramChannel, WebhookChannel

pytestmark = pytest.mark.unit


def test_builtins_build_from_their_target_key() -> None:
    assert isinstance(build_channel("webhook", {"url": "https://h"}), WebhookChannel)
    assert isinstance(build_channel("discord", {"webhook_url": "https://d"}), DiscordChannel)
    assert isinstance(build_channel("ntfy", {"topic": "t"}), NtfyChannel)
    assert isinstance(
        build_channel("telegram", {"bot_token": "123:t", "chat_id": "42"}), TelegramChannel
    )


@pytest.mark.parametrize(
    ("kind", "key"),
    [("webhook", "url"), ("discord", "webhook_url"), ("ntfy", "topic"), ("telegram", "chat_id")],
)
def test_builtin_target_keys(kind: str, key: str) -> None:
    assert registry.target_key(kind) == key


def test_unknown_kind_raises_and_names_the_known_channels() -> None:
    with pytest.raises(NotificationError, match="slack.*discord.*ntfy.*telegram.*webhook"):
        build_channel("slack", {})


def test_missing_required_key_raises_a_channel_aware_error() -> None:
    with pytest.raises(NotificationError, match="'telegram'.*'bot_token'"):
        build_channel("telegram", {"chat_id": "42"})
    with pytest.raises(NotificationError, match="'webhook'.*'url'"):
        build_channel("webhook", {})


def test_third_party_channels_register_through_the_same_seam() -> None:
    # The Jalon E plugin seam: registering a custom kind makes it buildable like a built-in.
    class EchoChannel:
        def __init__(self, address: str) -> None:
            self.address = address

        def send(self, notification: Notification) -> None:
            pass

    @register_channel("echo", target_key="address")
    def _build(config: Mapping[str, str]) -> NotificationChannel:
        return EchoChannel(registry.require(config, "echo", "address"))

    try:
        channel = build_channel("echo", {"address": "anywhere"})
        assert isinstance(channel, EchoChannel)
        assert channel.address == "anywhere"
        assert registry.target_key("echo") == "address"
    finally:
        registry._channels.pop("echo", None)
        registry._target_keys.pop("echo", None)
