"""Discord channel: POST to a Discord incoming webhook URL."""

from __future__ import annotations

from ..message import Notification

_PENDING = "Jalon 1.5-C (notify): Discord delivery not implemented yet."


class DiscordChannel:
    """Deliver a Notification to a Discord channel via its incoming webhook (httpx).

    Maps title/body onto Discord's ``content``/``embeds``; the webhook URL is a Blueprint secret.
    """

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send(self, notification: Notification) -> None:
        raise NotImplementedError(_PENDING)
