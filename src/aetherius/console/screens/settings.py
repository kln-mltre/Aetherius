"""Daemon control (start and stop) and configuration."""

from __future__ import annotations

from ._pending import PendingScreen


class SettingsScreen(PendingScreen):
    title_text = "Settings"
    description_text = (
        "Will start/stop the local daemon (`aetherius serve`) and manage its configuration."
    )
    milestone_text = "the FastAPI daemon (src/aetherius/server/)."
