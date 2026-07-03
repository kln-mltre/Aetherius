"""ActDriver protocol: contract that every Act (I..IV) driver must satisfy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar, Protocol

if TYPE_CHECKING:
    from .events.bus import EventBus
    from .blueprint.models import StepModel
    from .runtime.context import RunContext


class ActDriver(Protocol):
    act: ClassVar[str]

    def setup(self, ctx: "RunContext") -> None:
        """Called once before the first step. Open connections, create sessions, etc."""
        ...

    def teardown(self, ctx: "RunContext") -> None:
        """Called once after the last step (even on failure). Close resources."""
        ...

    def run_step(
        self,
        step: "StepModel",
        ctx: "RunContext",
        bus: "EventBus",
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        """Execute a single step and return its output dict.

        *renderer* is a callable that applies template rendering to any value.
        The driver calls it on step fields before using them.
        """
        ...
