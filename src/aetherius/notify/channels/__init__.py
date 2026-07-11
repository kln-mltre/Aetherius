"""Built-in notification channels.

Each channel is a thin ``httpx`` POST that maps a :class:`~aetherius.notify.message.Notification`
onto a provider's wire format. They cover the common targets without any new dependency:

- ``webhook``  — generic JSON POST to an arbitrary URL.
- ``discord``  — Discord incoming webhook.
- ``telegram`` — Telegram Bot API ``sendMessage``.
- ``ntfy``     — ntfy.sh (or a self-hosted server) for phone push.
"""

from __future__ import annotations

from .discord import DiscordChannel
from .ntfy import NtfyChannel
from .telegram import TelegramChannel
from .webhook import WebhookChannel

__all__ = ["WebhookChannel", "DiscordChannel", "TelegramChannel", "NtfyChannel"]
