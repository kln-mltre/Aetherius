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
from ..core.errors import (
    ActionError,
    NotificationError,
    StatusAssertionError,
    StepTimeoutError,
)
from ..core.events.bus import EventBus
from ..core.events.models import EventType, RunEvent
from ..core.runtime.approvals import ApprovalRequest
from ..core.runtime.context import RunContext
from ..core.runtime.steps import is_truthy
from ..notify import Notification, NotificationChannel, NotificationLevel, dispatch
from ..notify.registry import build_channel, target_key

# Mandatory upper bound for a parked ``confirm`` (5 min): a Blueprint may shorten it via
# ``timeout_ms``, but a run never parks forever.
_DEFAULT_CONFIRM_TIMEOUT_MS = 300_000


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
        channel, kind = self._build_channel(p, renderer)
        level = self._resolve_level(str(renderer(p.get("level", "info")) or "info"))
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

    def _build_channel(
        self, p: dict[str, Any], renderer: Callable[[Any], Any]
    ) -> tuple[NotificationChannel, str]:
        """Resolve a notify channel from a step's ``channel``/``target``/``config`` (shared by notify
        and confirm).

        A broken channel config is a Blueprint bug and fails the step (typed NotificationError from
        build_channel); only the delivery itself is contained, via dispatch.
        """
        kind = str(renderer(p.get("channel", "")) or "")
        raw_config = renderer(p.get("config") or {})
        if not isinstance(raw_config, dict):
            raise ActionError(f"'config' must be an object, got {type(raw_config).__name__}.")
        config = {str(k): str(v) for k, v in raw_config.items()}
        target = renderer(p.get("target"))
        if target:
            key = target_key(kind)
            if key is not None:
                config.setdefault(key, str(target))
        return build_channel(kind, config), kind

    def _resolve_level(self, raw_level: str) -> NotificationLevel:
        try:
            return NotificationLevel(raw_level)
        except ValueError as exc:
            allowed = ", ".join(lv.value for lv in NotificationLevel)
            raise NotificationError(
                f"invalid level {raw_level!r}; expected one of: {allowed}."
            ) from exc

    def _confirm(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]:
        """Park the run until a human decides, then resume; apply ``on_timeout`` on expiry.

        Blocks the worker thread on a rendezvous (approvals.py) exactly as ``_wait`` blocks on
        ``time.sleep`` — the decision arrives from a surface (console/daemon/CLI/notification) and
        wakes it. Unattended runs (no gateway) apply the timeout policy at once, never parking.
        """
        p = step.extra_fields
        message = str(renderer(p.get("message", "")) or "")
        title = renderer(p.get("title")) or None
        on_timeout = str(renderer(p.get("on_timeout", "reject")) or "reject")
        timeout_ms = float(renderer(p.get("timeout_ms", _DEFAULT_CONFIRM_TIMEOUT_MS)))

        gateway = ctx.approvals
        if gateway is None:
            return self._apply_confirm_timeout(on_timeout, message)

        request = ApprovalRequest.create(
            ctx.run_id, message, step_id=step.id, title=title, timeout_ms=timeout_ms
        )
        rendezvous = gateway.open(request)
        try:
            bus.emit(
                RunEvent(
                    run_id=ctx.run_id,
                    type=EventType.INPUT_REQUESTED,
                    step_id=step.id,
                    message=message,
                    level="warning",
                    data={"token": request.token, "title": title, "timeout_ms": timeout_ms},
                )
            )
            self._notify_confirm(request, ctx, step, bus, renderer, gateway)
            decision = rendezvous.wait(timeout_ms / 1000)
        finally:
            gateway.close(request)

        if decision is None:
            self._emit_input_provided(
                ctx, bus, step, request.token, approved=False, decided_by="timeout"
            )
            return self._apply_confirm_timeout(on_timeout, message)

        self._emit_input_provided(
            ctx,
            bus,
            step,
            request.token,
            approved=decision.approved,
            decided_by=decision.decided_by,
        )
        return {
            "approved": decision.approved,
            "decision": "approved" if decision.approved else "rejected",
            "value": decision.value,
            "decided_by": decision.decided_by,
        }

    def _notify_confirm(
        self,
        request: ApprovalRequest,
        ctx: RunContext,
        step: StepModel,
        bus: EventBus,
        renderer: Callable[[Any], Any],
        gateway: Any,
    ) -> None:
        """Alert a channel that a decision is pending, if the step names one (best-effort)."""
        p = step.extra_fields
        if not renderer(p.get("channel")):
            return
        channel, kind = self._build_channel(p, renderer)
        level = self._resolve_level(str(renderer(p.get("level", "warning")) or "warning"))
        notification = Notification(
            body=request.message,
            title=request.title or "Approval required",
            level=level,
            data=gateway.notification_data(request),
        )
        delivered = dispatch(notification, channel)
        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.PROGRESS,
                step_id=step.id,
                message=f"confirm: request sent via {kind}"
                if delivered
                else f"confirm: {kind} delivery failed",
                level="info" if delivered else "warning",
            )
        )

    def _apply_confirm_timeout(self, on_timeout: str, message: str) -> dict[str, Any]:
        """Map the ``on_timeout`` policy onto a step outcome (deny-by-default).

        ``fail:CODE`` raises with the named code (same convention as ``wait_for``); ``approve``
        proceeds; anything else — including the ``reject`` default — denies without failing the run,
        so the guarded sensitive step is simply skipped by its ``when``.
        """
        if on_timeout.startswith("fail:"):
            code = on_timeout.split(":", 1)[1] or None
            raise StepTimeoutError(f"confirm timed out awaiting a decision: {message!r}", code=code)
        approved = on_timeout == "approve"
        return {
            "approved": approved,
            "decision": "approved" if approved else "rejected",
            "value": None,
            "decided_by": "timeout",
        }

    def _emit_input_provided(
        self,
        ctx: RunContext,
        bus: EventBus,
        step: StepModel,
        token: str,
        *,
        approved: bool,
        decided_by: str | None,
    ) -> None:
        verb = "approved" if approved else "rejected"
        bus.emit(
            RunEvent(
                run_id=ctx.run_id,
                type=EventType.INPUT_PROVIDED,
                step_id=step.id,
                message=f"confirm: {verb} by {decided_by or 'unknown'}",
                level="info",
                data={"token": token, "approved": approved, "decided_by": decided_by},
            )
        )
