"""Manage persistent profiles and sessions, and launch warmup."""

from __future__ import annotations

from ._pending import PendingScreen


class SessionsScreen(PendingScreen):
    title_text = "Sessions"
    description_text = (
        "Will manage persistent browser profiles (cookies, cache) and let you launch a warmup "
        "run to build an authentic history before automation."
    )
    milestone_text = "the discretion/stealth subsystem (src/aetherius/stealth/session/)."
