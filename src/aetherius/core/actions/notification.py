"""Notification action: notify.

Spec projected by the builder catalogue. ``notify`` is declared in the capability table but not yet
dispatched by any driver (Phase 1.5, Jalon C), so the builder marks it "not runnable yet"; the
parameter shape here is indicative and will firm up when the shared handler lands. The alerting
machinery itself lives in ``aetherius.notify`` — this module carries shape only, no behaviour.
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
                help="Channel type or configured name (webhook, discord, telegram, ntfy).",
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
        ),
    ),
)
