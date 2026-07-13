"""Generic webhook channel: POST the notification as JSON to a configured URL."""

from __future__ import annotations

from typing import Mapping

import httpx

from ..base import NotificationChannel
from ..message import Notification
from ..registry import register_channel, require
from ._http import post_json


class WebhookChannel:
    """Deliver a Notification as a JSON POST to an arbitrary webhook URL (httpx).

    The payload is the Notification itself (``body``, ``title``, ``level``, ``url``, ``data``), so
    any receiver — webhook.site, httpbin, a custom endpoint — sees the full alert unmapped.
    """

    def __init__(self, url: str, *, transport: httpx.BaseTransport | None = None) -> None:
        self._url = url
        self._transport = transport

    def send(self, notification: Notification) -> None:
        post_json(self._url, notification.model_dump(mode="json"), transport=self._transport)


@register_channel("webhook", target_key="url")
def _build(config: Mapping[str, str]) -> NotificationChannel:
    return WebhookChannel(require(config, "webhook", "url"))
