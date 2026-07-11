"""Notification: the channel-agnostic alert payload."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Notification(BaseModel):
    """One alert to deliver. Each channel maps these fields onto its own wire format."""

    body: str
    title: str | None = None
    level: NotificationLevel = NotificationLevel.INFO
    # Optional deep link (the product page, the run, ...).
    url: str | None = None
    # Free-form structured context a channel may include (e.g. Discord embed fields).
    data: dict[str, Any] = Field(default_factory=dict)
