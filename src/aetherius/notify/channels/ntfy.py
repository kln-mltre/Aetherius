"""ntfy channel: publish a phone push notification to an ntfy topic.

ntfy.sh (or a self-hosted server) turns a simple HTTP POST into a push notification on a phone, which
is exactly the "alert me on my phone" case without an app to build. The topic acts as the address.
"""

from __future__ import annotations

from ..message import Notification

_PENDING = "Jalon 1.5-C (notify): ntfy delivery not implemented yet."


class NtfyChannel:
    """Deliver a Notification as a push to an ntfy topic (httpx).

    ``topic`` is the address (treat as a secret if the topic is meant to be private); ``server``
    defaults to the public ntfy.sh and can point to a self-hosted instance.
    """

    def __init__(self, topic: str, server: str = "https://ntfy.sh") -> None:
        self._topic = topic
        self._server = server

    def send(self, notification: Notification) -> None:
        raise NotImplementedError(_PENDING)
