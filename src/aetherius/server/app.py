"""FastAPI application factory wiring routes, config and the run manager."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from ..store import get_store
from ..version import __version__
from .config import DaemonConfig
from .jobs import RunManager
from .routes import blueprints, recorder, runs, stream


def create_app(config: DaemonConfig | None = None) -> FastAPI:
    """Build the daemon application. One :class:`RunManager` lives for the app's lifetime."""
    config = config or DaemonConfig()

    app = FastAPI(
        title="Aetherius Daemon",
        version=__version__,
        summary="Local HTTP + WebSocket gateway to the Aetherius engine.",
    )
    app.state.config = config
    # Runs persist their outcome to the durable store so history survives daemon restarts (Jalon A).
    app.state.manager = RunManager(runs=get_store().runs)

    app.include_router(runs.router)
    app.include_router(blueprints.router)
    app.include_router(recorder.router)
    app.include_router(stream.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        """Unauthenticated readiness probe used by the SDK and the Console when spawning the daemon."""
        return {"status": "ok", "version": __version__}

    return app
