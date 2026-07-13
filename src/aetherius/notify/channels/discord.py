"""Discord channel: POST to a Discord incoming webhook URL."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from ..base import NotificationChannel
from ..message import Notification, NotificationLevel
from ..registry import register_channel, require
from ._http import post_json

# Discord embed accent colors, matching the level's conventional severity hue.
_LEVEL_COLORS: dict[NotificationLevel, int] = {
    NotificationLevel.INFO: 0x3498DB,
    NotificationLevel.WARNING: 0xE67E22,
    NotificationLevel.ERROR: 0xE74C3C,
}


class DiscordChannel:
    """Deliver a Notification to a Discord channel via its incoming webhook (httpx).

    A bare body maps onto ``content``; a title or a deep link upgrades to an embed so the alert
    stays structured (title, colored accent, clickable link). The webhook URL is a Blueprint secret.
    """

    def __init__(self, webhook_url: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._webhook_url = webhook_url
        self._transport = transport

    def send(self, notification: Notification) -> None:
        payload: dict[str, Any]
        if notification.title or notification.url:
            embed: dict[str, Any] = {
                "description": notification.body,
                "color": _LEVEL_COLORS[notification.level],
            }
            if notification.title:
                embed["title"] = notification.title
            if notification.url:
                embed["url"] = notification.url
            payload = {"embeds": [embed]}
        else:
            payload = {"content": notification.body}
        post_json(self._webhook_url, payload, transport=self._transport)


@register_channel("discord", target_key="webhook_url")
def _build(config: Mapping[str, str]) -> NotificationChannel:
    return DiscordChannel(require(config, "discord", "webhook_url"))
