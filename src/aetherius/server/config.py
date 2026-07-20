"""Daemon configuration (bind address, auth token, limits).

Resolved from the environment (prefix ``AETHERIUS_DAEMON_``) with CLI overrides. The daemon binds to
loopback by default: it exposes the engine to local processes only, never the network. A token is
optional; when set, every HTTP request and WebSocket upgrade must present it as a bearer credential.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DaemonConfig(BaseSettings):
    """Runtime configuration for the local daemon."""

    model_config = SettingsConfigDict(env_prefix="AETHERIUS_DAEMON_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8787
    token: str | None = None
    # Publicly reachable base URL (behind a reverse proxy), used only to build the decision callback
    # embedded in ``confirm`` notifications so an ntfy action button can reach this daemon. Unset (the
    # loopback default) keeps confirm alerts informational — see docs/human-in-the-loop.md.
    public_url: str | None = None

    @field_validator("token", "public_url", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        """Treat a blank string as unset.

        Deployment tooling (compose interpolation, env files) easily materialises an env var as an
        empty string; enforcing auth against an empty bearer would lock every client out for no
        security gain, and a blank public URL must not build a dead callback.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # Scheduler polling period (Jalon D): the resolution at which due schedules are noticed.
    # Lowered in demos/tests via AETHERIUS_DAEMON_SCHEDULER_TICK_SECONDS.
    scheduler_tick_seconds: float = 30.0

    @property
    def base_url(self) -> str:
        """The HTTP address the daemon serves on."""
        return f"http://{self.host}:{self.port}"
