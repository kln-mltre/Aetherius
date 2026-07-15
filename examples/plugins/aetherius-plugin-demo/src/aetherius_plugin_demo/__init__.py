"""Demo Aetherius plugin: a custom action and a custom notification channel.

Importing this module registers both — that is the whole plugin contract: the entry points in
pyproject.toml target this module and ``aetherius.plugins.load_plugins()`` imports it at startup.
Everything a plugin needs is imported from the single ``aetherius.plugins`` surface. Reference:
docs/plugins.md.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any, Callable, Mapping

from aetherius.plugins import (
    ActionSpec,
    EventBus,
    Notification,
    NotificationChannel,
    ParamSpec,
    RunContext,
    StepModel,
    register_action,
    register_channel,
    require,
)

# The spec is registered with the handler so the action shows up in the Studio catalogue and
# passes validation like a built-in. Namespacing the action ("demo.") avoids ever colliding with a
# future core action, which registration would refuse.
_SLUGIFY_SPEC = ActionSpec(
    "demo.slugify",
    "Turn any text into a URL-safe slug (demo plugin action).",
    params=(
        ParamSpec(
            "value",
            "string",
            required=True,
            help="Text to slugify; templates welcome.",
            placeholder="{{ vars.title }}",
        ),
    ),
)


@register_action(_SLUGIFY_SPEC)
def slugify_action(
    step: StepModel,
    ctx: RunContext,
    bus: EventBus,
    renderer: Callable[[Any], Any],
) -> dict[str, Any]:
    """Handler signature is the drivers' dispatch shape; the returned dict lands in steps.<id>."""
    value = str(renderer(step.extra_fields.get("value", "")))
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return {"slug": slug}


class LogFileChannel:
    """Append each notification as one plain-text line to a local file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def send(self, notification: Notification) -> None:
        title = f" {notification.title}:" if notification.title else ""
        line = f"[{notification.level.value}]{title} {notification.body}\n"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line)


# target_key lets a Blueprint address the channel with the notify action's 'target' shorthand.
@register_channel("logfile", target_key="path")
def build_logfile_channel(config: Mapping[str, str]) -> NotificationChannel:
    return LogFileChannel(require(config, "logfile", "path"))
