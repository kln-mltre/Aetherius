"""Telegram channel: send a message through the Telegram Bot API."""

from __future__ import annotations

from ..message import Notification

_PENDING = "Jalon 1.5-C (notify): Telegram delivery not implemented yet."


class TelegramChannel:
    """Deliver a Notification via the Telegram Bot API ``sendMessage`` (httpx).

    ``bot_token`` and ``chat_id`` are Blueprint secrets; title/body map onto the message text.
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, notification: Notification) -> None:
        raise NotImplementedError(_PENDING)
