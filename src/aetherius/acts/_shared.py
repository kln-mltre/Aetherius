"""Act-agnostic action handlers shared by every driver.

``emit``, ``wait``, ``set`` and ``assert`` carry no Act-specific behaviour: they manipulate the run
context and the event bus, never a transport or a browser. They live here so each driver (Vector,
Continuum, ...) inherits one implementation instead of duplicating it. Drivers dispatch to these
from their own ``run_step`` ``match`` statement.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..core.blueprint.models import StepModel
from ..core.errors import StatusAssertionError
from ..core.events.bus import EventBus
from ..core.events.models import EventType, RunEvent
from ..core.runtime.context import RunContext


class SharedActionsMixin:
    """Provides the Act-agnostic handlers (``emit``/``wait``/``set``/``assert``)."""

    def _set(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        value = renderer(step.extra_fields.get("value"))
        return {"value": value}

    def _assert(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        p = step.extra_fields
        condition: str = renderer(p.get("condition", ""))
        if str(condition).strip().lower() not in {"true", "1", "yes"}:
            message = renderer(p.get("message", f"Assertion failed: {p.get('condition')}"))
            raise StatusAssertionError(expected=1, actual=0, url="<assert>", body_preview=message)
        return {}

    def _emit(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        p = step.extra_fields
        message: str = renderer(p.get("event", p.get("message", "")))
        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.PROGRESS,
                step_id=step.id,
                message=message,
                level="info",
            )
        )
        return {}

    def _wait(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        p = step.extra_fields
        ms: float = float(renderer(p.get("ms", 0)))
        if ms > 0:
            time.sleep(ms / 1000)
        return {}
