"""SchedulerService: the async tick loop that fires due schedules through the RunManager.

Started and stopped from the FastAPI ``lifespan`` (see server/app.py, whose ``lifespan=`` seam is
wired for this jalon). Each tick asks the store for due schedules and submits them via
``RunManager.submit`` — reusing the daemon's existing worker-thread + event-stream machinery, so a
scheduled run behaves exactly like a manually submitted one.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...store import Store
    from ..jobs import RunManager

_PENDING = "Jalon 1.5-D (scheduler): service loop not implemented yet."


class SchedulerService:
    """Owns the scheduler tick loop for the daemon's lifetime."""

    def __init__(
        self,
        manager: "RunManager",
        store: "Store",
        *,
        tick_seconds: float = 30.0,
    ) -> None:
        self._manager = manager
        self._store = store
        self._tick_seconds = tick_seconds

    async def start(self) -> None:
        """Begin the background tick loop (called from the daemon's lifespan startup)."""
        raise NotImplementedError(_PENDING)

    async def stop(self) -> None:
        """Stop the tick loop and let in-flight runs settle (lifespan shutdown)."""
        raise NotImplementedError(_PENDING)

    async def tick(self, now: datetime) -> None:
        """Fire every schedule due at *now*. Driven by the loop; exposed for tests."""
        raise NotImplementedError(_PENDING)
