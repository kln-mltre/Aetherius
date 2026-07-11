"""Generic webhook channel: POST the notification as JSON to a configured URL."""

from __future__ import annotations

from ..message import Notification

_PENDING = "Jalon 1.5-C (notify): webhook delivery not implemented yet."


class WebhookChannel:
    """Deliver a Notification as a JSON POST to an arbitrary webhook URL (httpx)."""

    def __init__(self, url: str) -> None:
        self._url = url

    def send(self, notification: Notification) -> None:
        raise NotImplementedError(_PENDING)
