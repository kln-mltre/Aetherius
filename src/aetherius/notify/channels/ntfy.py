"""ntfy channel: publish a phone push notification to an ntfy topic.

ntfy.sh (or a self-hosted server) turns a simple HTTP POST into a push notification on a phone, which
is exactly the "alert me on my phone" case without an app to build. The topic acts as the address.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

import httpx

from ..base import NotificationChannel
from ..message import Notification, NotificationLevel
from ..registry import register_channel, require
from ._http import post_json

_DEFAULT_SERVER = "https://ntfy.sh"


def _confirm_actions(confirm: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """Turn a confirm callback (server/approvals.py) into tappable ntfy Approve/Reject buttons.

    Each is an ntfy ``http`` action that POSTs the decision to the daemon's ``/decisions`` route with
    the request token — the "approve from my phone" case, without an app to build. Returns None when
    the callback is incomplete (no reachable URL), so the alert stays purely informational.
    """
    url = confirm.get("decisions_url")
    token = confirm.get("token")
    if not url or not token:
        return None
    headers: dict[str, str] = {"Content-Type": "application/json"}
    auth = confirm.get("auth")
    if auth:
        headers["Authorization"] = str(auth)

    def action(label: str, approved: bool) -> dict[str, Any]:
        return {
            "action": "http",
            "label": label,
            "url": url,
            "method": "POST",
            "headers": headers,
            "body": json.dumps({"token": token, "approved": approved}),
            "clear": True,
        }

    return [action("Approve", True), action("Reject", False)]


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
        # Human-in-the-loop (Jalon 2-E): a confirm request carries a decision callback under
        # data["confirm"]; expose it as tappable Approve/Reject buttons.
        confirm = notification.data.get("confirm")
        if isinstance(confirm, Mapping):
            actions = _confirm_actions(confirm)
            if actions is not None:
                payload["actions"] = actions
        post_json(self._server, payload, transport=self._transport)


@register_channel("ntfy", target_key="topic")
def _build(config: Mapping[str, str]) -> NotificationChannel:
    return NtfyChannel(
        require(config, "ntfy", "topic"),
        config.get("server") or _DEFAULT_SERVER,
    )
