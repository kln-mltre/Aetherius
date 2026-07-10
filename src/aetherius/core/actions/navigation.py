"""Navigation actions: navigate, back, forward, reload. Specs projected by the builder catalogue."""

from __future__ import annotations

from typing import Final

from .spec import ActionSpec, ParamSpec

SPECS: Final[tuple[ActionSpec, ...]] = (
    ActionSpec(
        "navigate",
        "Open a URL in the browser.",
        params=(
            ParamSpec(
                "url",
                "string",
                required=True,
                help="Absolute URL to open.",
                placeholder="https://example.com",
            ),
            ParamSpec(
                "wait_until",
                "string",
                default="load",
                help="Load state to wait for: load, domcontentloaded, networkidle or commit.",
            ),
        ),
    ),
    ActionSpec("back", "Go back one entry in the browser history."),
    ActionSpec("forward", "Go forward one entry in the browser history."),
    ActionSpec("reload", "Reload the current page."),
)
