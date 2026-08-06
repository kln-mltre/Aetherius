"""Step executor: walks a step tree, applies ``when`` guards, and routes each leaf to a driver.

Extracted from RunEngine.run so the pipeline can recurse: ``if``/``repeat``/``for_each`` are
interpreted (flow.py) before the driver ever sees the step, and re-enter the executor for their
nested lists. Drivers only ever receive leaf actions, so every Act inherits the flow semantics
without wiring anything. Nested executions carry a display path (``loop[2].fetch``) so events
and StepResults stay traceable across branches and iterations.

Since Jalon 2-D each step runs on its *effective act* — ``step.act`` or, for nested steps, the
act inherited from the enclosing flow step, the Blueprint act otherwise — resolved to a live
driver through a ``DriverResolver`` (the engine's DriverManager). A failing leaf is offered to
the self-healing layer (healing.py) before its failure propagates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol, Sequence, runtime_checkable

from ..actions.base import FLOW_ACTIONS
from ..blueprint.models import StepModel
from ..blueprint.template import render_value
from ..errors import AetheriusError
from ..events.bus import EventBus
from ..events.models import EventType, RunEvent
from .context import RunContext
from .flow import is_truthy as is_truthy  # re-export: historical home of the truthiness rule
from .flow import run_flow
from .healing import attempt_healing
from .result import RunStatus, StepResult

_FLOW_VALUES: frozenset[str] = frozenset(cap.value for cap in FLOW_ACTIONS)


class StepDriver(Protocol):
    """The slice of ActDriver (core/driver.py) the executor needs."""

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]: ...


@runtime_checkable
class DriverResolver(Protocol):
    """Resolves the live driver for a step's effective act (satisfied by DriverManager)."""

    def resolve_driver(self, act: str, ctx: RunContext) -> StepDriver: ...


class StepFailed(AetheriusError):
    """Internal marker: a step error already recorded (StepResult + ERROR event) further down.

    Raised in place of the original error so enclosing flow steps record their own FAILED
    StepResult without emitting a duplicate ERROR event. Carries the original message, so the
    engine handles it like any AetheriusError.
    """


def run_steps(
    steps: Sequence[StepModel],
    ctx: RunContext,
    bus: EventBus,
    driver: StepDriver | DriverResolver,
    results: list[StepResult],
    *,
    path: str = "",
) -> None:
    """Execute *steps* in order, recording one StepResult per step into *results*.

    *driver* is either a DriverResolver (the engine's DriverManager, honouring per-step ``act``)
    or a plain StepDriver, which then serves every step — the historical single-driver pipeline.
    Flow actions recurse with a *path* that prefixes display ids and anonymous output keys;
    root steps keep the historical behaviour (bare ``id``, ``_step_{i}`` fallback).

    Raises:
        StepFailed: a step failed after being recorded; the run must abort.
    """
    resolver = driver if isinstance(driver, DriverResolver) else _FixedResolver(driver)
    _Executor(ctx=ctx, bus=bus, drivers=resolver, results=results).run(steps, path)


@dataclass
class _FixedResolver:
    """Adapter: every act resolves to the same driver (mono-driver callers and tests)."""

    driver: StepDriver

    def resolve_driver(self, act: str, ctx: RunContext) -> StepDriver:
        return self.driver


@dataclass
class _Executor:
    ctx: RunContext
    bus: EventBus
    drivers: DriverResolver
    results: list[StepResult]

    def run(self, steps: Sequence[StepModel], path: str = "", act: str | None = None) -> None:
        inherited = act or self.ctx.blueprint.act
        for i, step in enumerate(steps):
            step_path = _join(path, step.id or f"_step_{i}")
            # Root steps keep their bare id (None when anonymous) so linear Blueprints are
            # untouched; nested steps expose their full path for traceability.
            display_id = step.id if not path else step_path
            output_key = step.id or step_path
            effective_act = step.act or inherited

            def renderer(value: Any) -> Any:
                return render_value(value, self.ctx.template_ctx())

            t0 = time.monotonic()
            try:
                if step.when is not None and not is_truthy(renderer(step.when)):
                    self.results.append(
                        StepResult(
                            step_id=display_id,
                            action=step.action,
                            status=RunStatus.SKIPPED,
                            duration_ms=(time.monotonic() - t0) * 1000,
                        )
                    )
                    # Report the raw expression, never its rendered value: it may derive from
                    # a secret.
                    self._emit(
                        EventType.STEP_SKIPPED,
                        display_id,
                        message=f"skipped: when {step.when!r} is false",
                        level="info",
                        data={"when": step.when},
                    )
                    continue

                self._emit(EventType.STEP_STARTED, display_id, level="debug")

                healed_by: str | None = None
                if step.action in _FLOW_VALUES:
                    outputs = run_flow(self, step, renderer, step_path, effective_act)
                else:
                    outputs, healed_by = self._run_leaf(step, effective_act, display_id, renderer)

                self.ctx.step_outputs[output_key] = outputs
                self.results.append(
                    StepResult(
                        step_id=display_id,
                        action=step.action,
                        status=RunStatus.SUCCESS,
                        outputs=outputs,
                        healed_by=healed_by,
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                )
                self._emit(EventType.STEP_FINISHED, display_id, level="debug")

            except StepFailed as exc:
                # A nested step already recorded the failure and emitted ERROR: mark this flow
                # step failed too, without a duplicate event.
                self.results.append(
                    StepResult(
                        step_id=display_id,
                        action=step.action,
                        status=RunStatus.FAILED,
                        error=str(exc),
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                )
                raise
            except AetheriusError as exc:
                message = _named(exc)
                self.results.append(
                    StepResult(
                        step_id=display_id,
                        action=step.action,
                        status=RunStatus.FAILED,
                        error=message,
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                )
                self._emit(EventType.ERROR, display_id, message=message, level="error")
                raise StepFailed(message) from exc

    def _run_leaf(
        self,
        step: StepModel,
        act: str,
        display_id: str | None,
        renderer: Callable[[Any], Any],
    ) -> tuple[dict[str, Any], str | None]:
        """Dispatch a leaf step to its act's driver; a failure is offered to self-healing.

        The healing seam catches broadly on purpose: a broken selector surfaces as a raw
        Playwright TimeoutError, not an AetheriusError. When no escalation applies the original
        error is re-raised unchanged, preserving the historical failure paths.
        """
        driver = self.drivers.resolve_driver(act, self.ctx)
        try:
            return driver.run_step(step, self.ctx, self.bus, renderer), None
        except Exception as exc:
            healed = attempt_healing(
                step,
                act,
                exc,
                ctx=self.ctx,
                bus=self.bus,
                drivers=self.drivers,
                results=self.results,
                renderer=renderer,
                step_id=display_id,
            )
            if healed is None:
                raise
            return healed

    def _emit(
        self,
        type_: EventType,
        step_id: str | None,
        *,
        message: str | None = None,
        level: Literal["debug", "info", "warning", "error"] = "debug",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.bus.emit(
            RunEvent(
                run_id=self.ctx.run_id,
                type=type_,
                step_id=step_id,
                message=message,
                level=level,
                data=data or {},
            )
        )


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _named(exc: AetheriusError) -> str:
    """Prefix a failure the Blueprint named (`on_timeout: "fail:CODE"`) with its code.

    The code was set on the exception and read by nobody, so a caller could not tell "wrong
    password" from "the page changed" — which is the entire point of naming it. The embedded engine
    exposes it as a field of the failure it describes; here the Result is a serialisable model that
    cannot carry an exception, so the name rides at the front of the message, in a fixed position.
    """
    code = getattr(exc, "code", None)
    return f"{code}: {exc}" if code else str(exc)
