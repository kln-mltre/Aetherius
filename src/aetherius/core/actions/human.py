"""Human-in-the-loop action: confirm.

Spec projected by the builder catalogue. ``confirm`` parks the run until a human decides, then
resumes with ``{{ steps.<id>.approved }}``. Like ``notify`` it is dispatched by the shared handler
(``acts/_shared.py``) on every runnable Act; this module carries shape only, no behaviour.
Reference: docs/human-in-the-loop.md.
"""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "confirm",
        "Park the run until a human approves or rejects (console, daemon API, or notification).",
        params=(
            ParamSpec(
                "message",
                "string",
                required=True,
                help="What the human is being asked to approve.",
                placeholder="Buy {{ inputs.product }} for {{ steps.price.value }}?",
            ),
            ParamSpec("title", "string", help="Optional short title for the request."),
            ParamSpec(
                "timeout_ms",
                "integer",
                default=300000,
                help="How long to wait for a decision before applying on_timeout (mandatory bound).",
            ),
            ParamSpec(
                "on_timeout",
                "string",
                default="reject",
                help="On expiry: 'approve', 'reject', or 'fail:CODE'. Deny-by-default.",
                placeholder="reject",
            ),
            ParamSpec(
                "channel",
                "string",
                help="Optional notify channel to alert on: webhook, discord, telegram, ntfy.",
                placeholder="ntfy",
            ),
            ParamSpec(
                "target",
                "string",
                help="Channel address for the alert (topic, chat id, webhook URL). Usually a secret.",
                placeholder="{{ secrets.ntfy_topic }}",
            ),
            ParamSpec(
                "config",
                "object",
                help="Full channel config for multi-key channels; superset of 'target'.",
                placeholder='{"bot_token": "{{ secrets.tg_token }}", "chat_id": "{{ secrets.tg_chat }}"}',
            ),
            ParamSpec(
                "level",
                "string",
                default="warning",
                help="Severity of the request notification: info, warning or error.",
            ),
        ),
    ),
)
