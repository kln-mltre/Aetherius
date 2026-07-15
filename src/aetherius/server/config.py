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

    @field_validator("token", mode="before")
    @classmethod
    def _empty_token_is_none(cls, value: object) -> object:
        """Treat a blank token as no token at all.

        Deployment tooling (compose interpolation, env files) easily materialises
        AETHERIUS_DAEMON_TOKEN as an empty string; enforcing auth against an empty bearer
        would lock every client out for no security gain.
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
