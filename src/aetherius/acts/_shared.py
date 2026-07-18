"""Act-agnostic action handlers shared by every driver.

``emit``, ``wait``, ``set``, ``assert`` and ``notify`` carry no Act-specific behaviour: they
manipulate the run context, the event bus or the notification layer, never a transport or a browser.
They live here so each driver (Vector, Continuum, ...) inherits one implementation instead of
duplicating it. Drivers dispatch to these from their own ``run_step`` ``match`` statement.
"""

from __future__ import annotations

import random
import time
from typing import Any, Callable

from ..core.blueprint.models import StepModel
from ..core.errors import ActionError, NotificationError, StatusAssertionError
from ..core.events.bus import EventBus
from ..core.events.models import EventType, RunEvent
from ..core.runtime.context import RunContext
from ..core.runtime.steps import is_truthy
from ..notify import Notification, NotificationLevel, dispatch
from ..notify.registry import build_channel, target_key


class SharedActionsMixin:
    """Provides the Act-agnostic handlers (``emit``/``wait``/``set``/``assert``/``notify``)."""

    def _set(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        value = renderer(step.extra_fields.get("value"))
        return {"value": value}

    def _assert(self, step: StepModel, renderer: Callable[[Any], Any]) -> dict[str, Any]:
        p = step.extra_fields
        condition: str = renderer(p.get("condition", ""))
        if not is_truthy(condition):
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
        if "ms" in p:
            ms: float = float(renderer(p.get("ms", 0)))
        else:
            # No fixed duration: draw uniformly from [min_ms, max_ms], the non-deterministic
            # pause the stealth-minded Blueprints use (a fixed inter-step delay is a tell).
            low = float(renderer(p.get("min_ms", 0)) or 0)
            high = float(renderer(p.get("max_ms", low)) or low)
            if high < low:
                raise ActionError(f"wait: max_ms ({high:g}) must be >= min_ms ({low:g}).")
            ms = random.uniform(low, high)
        if ms > 0:
            time.sleep(ms / 1000)
        return {}

    def _notify(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        p = step.extra_fields
        kind = str(renderer(p.get("channel", "")) or "")

        # A broken channel config is a Blueprint bug and fails the step (typed NotificationError
        # from build_channel); only the delivery itself is contained, via dispatch.
        raw_config = renderer(p.get("config") or {})
        if not isinstance(raw_config, dict):
            raise ActionError(
                f"notify: 'config' must be an object, got {type(raw_config).__name__}."
            )
        config = {str(k): str(v) for k, v in raw_config.items()}
        target = renderer(p.get("target"))
        if target:
            key = target_key(kind)
            if key is not None:
                config.setdefault(key, str(target))
        channel = build_channel(kind, config)

        raw_level = str(renderer(p.get("level", "info")) or "info")
        try:
            level = NotificationLevel(raw_level)
        except ValueError as exc:
            allowed = ", ".join(lv.value for lv in NotificationLevel)
            raise NotificationError(
                f"notify: invalid level {raw_level!r}; expected one of: {allowed}."
            ) from exc

        notification = Notification(
            body=str(renderer(p.get("message", "")) or ""),
            title=renderer(p.get("title")) or None,
            level=level,
            url=renderer(p.get("url")) or None,
        )
        delivered = dispatch(notification, channel)
        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.PROGRESS,
                step_id=step.id,
                message=f"notify: {kind} {'delivered' if delivered else 'delivery failed'}",
                level="info" if delivered else "warning",
            )
        )
        return {"delivered": delivered, "channel": kind}
