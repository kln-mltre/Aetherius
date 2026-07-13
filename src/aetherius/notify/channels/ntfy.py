"""ntfy channel: publish a phone push notification to an ntfy topic.

ntfy.sh (or a self-hosted server) turns a simple HTTP POST into a push notification on a phone, which
is exactly the "alert me on my phone" case without an app to build. The topic acts as the address.
"""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from ..base import NotificationChannel
from ..message import Notification, NotificationLevel
from ..registry import register_channel, require
from ._http import post_json

_DEFAULT_SERVER = "https://ntfy.sh"

# ntfy priorities: 3 is the default, 4 rings, 5 rings insistently.
_LEVEL_PRIORITY: dict[NotificationLevel, int] = {
    NotificationLevel.INFO: 3,
    NotificationLevel.WARNING: 4,
    NotificationLevel.ERROR: 5,
}


class NtfyChannel:
    """Deliver a Notification as a push to an ntfy topic (httpx).

    ``topic`` is the address (treat it as a secret: anyone knowing it can read and publish);
    ``server`` defaults to the public ntfy.sh and can point to a self-hosted instance. Publishing
    uses ntfy's JSON mode (one POST to the server root) rather than headers, because HTTP headers
    are latin-1 only and would corrupt accented titles.
    """

    def __init__(
        self,
        topic: str,
        server: str = _DEFAULT_SERVER,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._topic = topic
        self._server = server.rstrip("/")
        self._transport = transport

    def send(self, notification: Notification) -> None:
        payload: dict[str, Any] = {
            "topic": self._topic,
            "message": notification.body,
            "priority": _LEVEL_PRIORITY[notification.level],
        }
        if notification.title:
            payload["title"] = notification.title
        if notification.url:
            payload["click"] = notification.url
        post_json(self._server, payload, transport=self._transport)


@register_channel("ntfy", target_key="topic")
def _build(config: Mapping[str, str]) -> NotificationChannel:
    return NtfyChannel(
        require(config, "ntfy", "topic"),
        config.get("server") or _DEFAULT_SERVER,
    )
