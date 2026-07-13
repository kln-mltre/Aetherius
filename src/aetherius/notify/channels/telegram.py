"""Telegram channel: send a message through the Telegram Bot API."""

from __future__ import annotations

from typing import Mapping

import httpx

from ..base import NotificationChannel
from ..message import Notification
from ..registry import register_channel, require
from ._http import post_json


class TelegramChannel:
    """Deliver a Notification via the Telegram Bot API ``sendMessage`` (httpx).

    ``bot_token`` and ``chat_id`` are Blueprint secrets. Title, body and deep link are joined into
    the message text, sent without ``parse_mode`` on purpose: plain text means an arbitrary alert
    body can never break on Markdown/HTML escaping.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._transport = transport

    def send(self, notification: Notification) -> None:
        parts = [p for p in (notification.title, notification.body, notification.url) if p]
        post_json(
            f"https://api.telegram.org/bot{self._bot_token}/sendMessage",
            {"chat_id": self._chat_id, "text": "\n\n".join(parts)},
            transport=self._transport,
        )


@register_channel("telegram", target_key="chat_id")
def _build(config: Mapping[str, str]) -> NotificationChannel:
    return TelegramChannel(
        require(config, "telegram", "bot_token"),
        require(config, "telegram", "chat_id"),
    )
