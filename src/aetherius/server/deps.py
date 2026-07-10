"""Shared FastAPI dependencies: run-manager access and optional bearer authentication.

The manager and config live on ``app.state`` (set by the application factory) so routers stay
decoupled from construction. Authentication is a no-op unless a token is configured, in which case
every ``/v1`` request must present it as ``Authorization: Bearer <token>``.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection

from .config import DaemonConfig
from .jobs import RunManager


def get_config(conn: HTTPConnection) -> DaemonConfig:
    """Injected for both HTTP requests and WebSocket connections (their common base)."""
    config = conn.app.state.config
    assert isinstance(config, DaemonConfig)
    return config


def get_manager(conn: HTTPConnection) -> RunManager:
    manager = conn.app.state.manager
    assert isinstance(manager, RunManager)
    return manager


def require_auth(request: HTTPConnection) -> None:
    """Reject the request when a token is configured and the bearer credential does not match."""
    config = get_config(request)
    if config.token is None:
        return
    if request.headers.get("Authorization") != f"Bearer {config.token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def websocket_authorized(config: DaemonConfig, header: str | None, query_token: str | None) -> bool:
    """WebSocket auth: browsers cannot set headers on the upgrade, so a ``?token=`` query is also
    accepted. Returns True when no token is configured."""
    if config.token is None:
        return True
    if header == f"Bearer {config.token}":
        return True
    return query_token == config.token
