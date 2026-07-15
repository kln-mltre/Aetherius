"""FastAPI application factory wiring routes, config, the run manager and the scheduler."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI

from ..plugins import load_plugins
from ..store import get_store
from ..version import __version__
from .config import DaemonConfig
from .jobs import RunManager
from .routes import blueprints, recorder, runs, schedules, stream
from .scheduler import SchedulerService

_log = logging.getLogger("aetherius.daemon")


def create_app(config: DaemonConfig | None = None) -> FastAPI:
    """Build the daemon application. One :class:`RunManager` lives for the app's lifetime."""
    config = config or DaemonConfig()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Plugin actions and notify channels must be visible before any run or schedule validation,
        # even when the app is created programmatically rather than through the CLI (Jalon E).
        loaded_plugins = load_plugins()
        if loaded_plugins:
            _log.info("Loaded plugins: %s", ", ".join(loaded_plugins))
        # The scheduler shares the app's manager and store: scheduled runs go through the same
        # submit path (same events, same history) and the same durable file the CLI writes to.
        scheduler = SchedulerService(
            app.state.manager, app.state.store, tick_seconds=config.scheduler_tick_seconds
        )
        app.state.scheduler = scheduler
        await scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    app = FastAPI(
        title="Aetherius Daemon",
        version=__version__,
        summary="Local HTTP + WebSocket gateway to the Aetherius engine.",
        lifespan=lifespan,
    )
    app.state.config = config
    # Runs persist their outcome to the durable store so history survives daemon restarts (Jalon A).
    store = get_store()
    app.state.store = store
    app.state.manager = RunManager(runs=store.runs)

    app.include_router(runs.router)
    app.include_router(blueprints.router)
    app.include_router(recorder.router)
    app.include_router(schedules.router)
    app.include_router(stream.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        """Unauthenticated readiness probe used by the SDK and the Console when spawning the daemon."""
        return {"status": "ok", "version": __version__}

    return app
