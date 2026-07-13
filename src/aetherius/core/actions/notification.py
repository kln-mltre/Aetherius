"""Notification action: notify.

Spec projected by the builder catalogue. ``notify`` is dispatched by the shared handler
(``acts/_shared.py``) on every runnable Act; the alerting machinery itself lives in
``aetherius.notify`` — this module carries shape only, no behaviour. Reference: docs/notifications.md.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "notify",
        "Send an alert to a notification channel (webhook, Discord, Telegram, ntfy).",
        params=(
            ParamSpec(
                "channel",
                "string",
                required=True,
                help="Channel kind: webhook, discord, telegram or ntfy (plugins may add more).",
                placeholder="discord",
            ),
            ParamSpec(
                "message",
                "string",
                required=True,
                help="Alert body.",
                placeholder="Back in stock: {{ inputs.product }}",
            ),
            ParamSpec("title", "string", help="Optional alert title."),
            ParamSpec(
                "level",
                "string",
                default="info",
                help="Severity: info, warning or error.",
            ),
            ParamSpec(
                "target",
                "string",
                help="Channel address (webhook URL, chat id, topic). Usually a secret.",
                placeholder="{{ secrets.discord_webhook }}",
            ),
            ParamSpec(
                "url",
                "string",
                help="Optional deep link attached to the alert (the product page, ...).",
            ),
            ParamSpec(
                "config",
                "object",
                help="Full channel config for multi-key channels; superset of 'target'.",
                placeholder='{"bot_token": "{{ secrets.tg_token }}", "chat_id": "{{ secrets.tg_chat }}"}',
            ),
        ),
    ),
)
