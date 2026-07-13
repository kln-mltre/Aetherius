"""Step executor: walks a step tree, applies ``when`` guards, and interprets flow actions.

Extracted from RunEngine.run so the pipeline can recurse: ``if``/``repeat``/``for_each`` are
interpreted here — before the driver ever sees the step — and re-enter the executor for their
nested lists. Drivers only ever receive leaf actions, so every Act inherits the flow semantics
without wiring anything. Nested executions carry a display path (``loop[2].fetch``) so events
and StepResults stay traceable across branches and iterations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol, Sequence

from pydantic import ValidationError

from ..actions.base import FLOW_ACTIONS
from ..blueprint.models import StepModel
from ..blueprint.template import render_value
from ..errors import ActionError, AetheriusError
from ..events.bus import EventBus
from ..events.models import EventType, RunEvent
from .context import RunContext
from .result import RunStatus, StepResult

_FLOW_VALUES: frozenset[str] = frozenset(cap.value for cap in FLOW_ACTIONS)

_TRUTHY: frozenset[str] = frozenset({"true", "1", "yes"})

# Template context names a for_each loop variable would shadow (see RunContext.template_ctx).
_RESERVED_NAMES: frozenset[str] = frozenset({"inputs", "secrets", "vars", "env", "steps"})

_DEFAULT_LOOP_VAR = "item"


def is_truthy(value: Any) -> bool:
    """Single truthiness rule shared by ``assert`` conditions and ``when`` guards."""
    return str(value).strip().lower() in _TRUTHY


class StepDriver(Protocol):
    """The slice of ActDriver (core/driver.py) the executor needs."""

    def run_step(
        self,
        step: StepModel,
        ctx: RunContext,
        bus: EventBus,
        renderer: Callable[[Any], Any],
    ) -> dict[str, Any]: ...


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
    driver: StepDriver,
    results: list[StepResult],
    *,
    path: str = "",
) -> None:
    """Execute *steps* in order, recording one StepResult per step into *results*.

    Flow actions recurse with a *path* that prefixes display ids and anonymous output keys;
    root steps keep the historical behaviour (bare ``id``, ``_step_{i}`` fallback).

    Raises:
        StepFailed: a step failed after being recorded; the run must abort.
    """
    _Executor(ctx=ctx, bus=bus, driver=driver, results=results).run(steps, path)


@dataclass
class _Executor:
    ctx: RunContext
    bus: EventBus
    driver: StepDriver
    results: list[StepResult]

    def run(self, steps: Sequence[StepModel], path: str = "") -> None:
        for i, step in enumerate(steps):
            step_path = _join(path, step.id or f"_step_{i}")
            # Root steps keep their bare id (None when anonymous) so linear Blueprints are
            # untouched; nested steps expose their full path for traceability.
            display_id = step.id if not path else step_path
            output_key = step.id or step_path

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

                if step.action in _FLOW_VALUES:
                    outputs = self._run_flow(step, renderer, step_path)
                else:
                    outputs = self.driver.run_step(step, self.ctx, self.bus, renderer)

                self.ctx.step_outputs[output_key] = outputs
                self.results.append(
                    StepResult(
                        step_id=display_id,
                        action=step.action,
                        status=RunStatus.SUCCESS,
                        outputs=outputs,
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
                self.results.append(
                    StepResult(
                        step_id=display_id,
                        action=step.action,
                        status=RunStatus.FAILED,
                        error=str(exc),
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                )
                self._emit(EventType.ERROR, display_id, message=str(exc), level="error")
                raise StepFailed(str(exc)) from exc

    # ── Flow actions ─────────────────────────────────────────────────────────

    def _run_flow(
        self, step: StepModel, renderer: Callable[[Any], Any], path: str
    ) -> dict[str, Any]:
        if step.action == "if":
            return self._flow_if(step, renderer, path)
        if step.action == "repeat":
            return self._flow_repeat(step, renderer, path)
        return self._flow_for_each(step, renderer, path)

    def _flow_if(
        self, step: StepModel, renderer: Callable[[Any], Any], path: str
    ) -> dict[str, Any]:
        p = step.extra_fields
        if "condition" not in p:
            raise ActionError(f"if: missing required parameter 'condition' (step {path!r}).")
        branch = "then" if is_truthy(renderer(p["condition"])) else "else"
        if branch == "else" and "else" not in p:
            return {"branch": None}
        self.run(_nested_steps(step, branch, path), path)
        return {"branch": branch}

    def _flow_repeat(
        self, step: StepModel, renderer: Callable[[Any], Any], path: str
    ) -> dict[str, Any]:
        p = step.extra_fields
        if "times" not in p:
            raise ActionError(f"repeat: missing required parameter 'times' (step {path!r}).")
        times = _coerce_times(renderer(p["times"]), path)
        nested = _nested_steps(step, "steps", path)
        for i in range(times):
            self.run(nested, f"{path}[{i}]")
        return {"iterations": times}

    def _flow_for_each(
        self, step: StepModel, renderer: Callable[[Any], Any], path: str
    ) -> dict[str, Any]:
        p = step.extra_fields
        if "items" not in p:
            raise ActionError(f"for_each: missing required parameter 'items' (step {path!r}).")
        items = renderer(p["items"])
        if not isinstance(items, (list, tuple)):
            raise ActionError(
                f"for_each: 'items' must render to a list, "
                f"got {type(items).__name__} (step {path!r})."
            )
        var = p.get("as", _DEFAULT_LOOP_VAR)
        if not isinstance(var, str) or not var.isidentifier():
            raise ActionError(
                f"for_each: 'as' must be a valid identifier, got {var!r} (step {path!r})."
            )
        if var in _RESERVED_NAMES:
            raise ActionError(
                f"for_each: loop variable {var!r} would shadow a reserved "
                f"template name (step {path!r})."
            )
        nested = _nested_steps(step, "steps", path)

        # Save and restore whatever the variable shadowed so nested loops compose.
        missing = object()
        previous = self.ctx.scope.get(var, missing)
        try:
            for i, item in enumerate(items):
                self.ctx.scope[var] = item
                self.run(nested, f"{path}[{i}]")
        finally:
            if previous is missing:
                self.ctx.scope.pop(var, None)
            else:
                self.ctx.scope[var] = previous
        return {"iterations": len(items)}

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


def _nested_steps(step: StepModel, key: str, path: str) -> list[StepModel]:
    raw = step.extra_fields.get(key)
    if not isinstance(raw, list):
        raise ActionError(f"{step.action}: '{key}' must be a list of steps (step {path!r}).")
    try:
        return [StepModel.model_validate(item) for item in raw]
    except ValidationError as exc:
        raise ActionError(f"{step.action}: invalid step in '{key}' (step {path!r}): {exc}") from exc


def _coerce_times(value: Any, path: str) -> int:
    times: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        times = value
    elif isinstance(value, str):
        try:
            times = int(value.strip())
        except ValueError:
            times = None
    if times is None:
        raise ActionError(f"repeat: 'times' must be an integer, got {value!r} (step {path!r}).")
    if times < 0:
        raise ActionError(f"repeat: 'times' must be >= 0, got {times} (step {path!r}).")
    return times
