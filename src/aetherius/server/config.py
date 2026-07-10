"""Daemon configuration (bind address, auth token, limits).

Resolved from the environment (prefix ``AETHERIUS_DAEMON_``) with CLI overrides. The daemon binds to
loopback by default: it exposes the engine to local processes only, never the network. A token is
optional; when set, every HTTP request and WebSocket upgrade must present it as a bearer credential.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class DaemonConfig(BaseSettings):
    """Runtime configuration for the local daemon."""

    model_config = SettingsConfigDict(env_prefix="AETHERIUS_DAEMON_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8787
    token: str | None = None

    @property
    def base_url(self) -> str:
        """The HTTP address the daemon serves on."""
        return f"http://{self.host}:{self.port}"
