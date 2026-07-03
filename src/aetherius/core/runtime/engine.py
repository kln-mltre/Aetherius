"""RunEngine: orchestrates Act selection, step pipeline, retries, events, and Result assembly."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from ..blueprint.models import Blueprint
from ..blueprint.template import render_value
from ..blueprint.validator import validate_for_act
from ..errors import AetheriusError, ActionError, RunError
from ..events.bus import EventBus
from ..events.models import EventType, RunEvent
from ..events.sinks import LogSink, NullSink, Sink
from ..runtime.context import RunContext, resolve_inputs
from ..runtime.result import Result, RunStatus, StepResult


IMPLEMENTED_ACTS: frozenset[str] = frozenset({"vector"})


def _make_driver(act: str) -> Any:
    if act not in IMPLEMENTED_ACTS:
        raise ActionError(
            f"Act {act!r} is not implemented yet. Only 'vector' is available in Act I."
        )
    from ...acts.vector.driver import VectorDriver

    return VectorDriver()


class RunEngine:
    def run(
        self,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None = None,
        secrets: Mapping[str, str] | None = None,
        *,
        sinks: list[Sink] | None = None,
    ) -> Result:
        validate_for_act(blueprint)

        run_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)

        resolved_inputs = resolve_inputs(blueprint, inputs)
        ctx = RunContext(
            run_id=run_id,
            blueprint=blueprint,
            inputs=resolved_inputs,
            secrets=dict(secrets or {}),
            started_at=started_at,
        )

        bus = EventBus()
        if sinks is not None:
            for sink in sinks:
                bus.register(sink)
        else:
            default_sink: Sink = (
                LogSink(debug=blueprint.options.debug) if blueprint.options.debug else NullSink()
            )
            bus.register(default_sink)

        driver = _make_driver(blueprint.act)
        driver.setup(ctx)

        bus.emit(
            RunEvent(
                run_id=run_id,
                type=EventType.PROGRESS,
                message=f"run started: {blueprint.name}",
                level="info",
            )
        )

        step_results: list[StepResult] = []
        final_status = RunStatus.SUCCESS
        run_error: str | None = None

        try:
            for i, step in enumerate(blueprint.steps):
                step_key = step.id or f"_step_{i}"

                bus.emit(
                    RunEvent(
                        run_id=run_id, type=EventType.STEP_STARTED, step_id=step.id, level="debug"
                    )
                )
                t0 = time.monotonic()

                def renderer(value: Any) -> Any:
                    return render_value(value, ctx.template_ctx())

                try:
                    outputs = driver.run_step(step, ctx, bus, renderer)
                    ctx.step_outputs[step_key] = outputs
                    duration_ms = (time.monotonic() - t0) * 1000
                    step_results.append(
                        StepResult(
                            step_id=step.id,
                            action=step.action,
                            status=RunStatus.SUCCESS,
                            outputs=outputs,
                            duration_ms=duration_ms,
                        )
                    )
                    bus.emit(
                        RunEvent(
                            run_id=run_id,
                            type=EventType.STEP_FINISHED,
                            step_id=step.id,
                            level="debug",
                        )
                    )

                except AetheriusError as exc:
                    duration_ms = (time.monotonic() - t0) * 1000
                    step_results.append(
                        StepResult(
                            step_id=step.id,
                            action=step.action,
                            status=RunStatus.FAILED,
                            error=str(exc),
                            duration_ms=duration_ms,
                        )
                    )
                    bus.emit(
                        RunEvent(
                            run_id=run_id,
                            type=EventType.ERROR,
                            step_id=step.id,
                            message=str(exc),
                            level="error",
                        )
                    )
                    raise

        except AetheriusError as exc:
            final_status = RunStatus.FAILED
            run_error = str(exc)

        except Exception as exc:
            final_status = RunStatus.FAILED
            run_error = str(exc)
            raise RunError(f"Unexpected error during run {run_id}: {exc}", cause=exc) from exc

        finally:
            driver.teardown(ctx)

        # Render the outputs dict through the template engine.
        final_outputs: dict[str, Any] = {}
        if final_status == RunStatus.SUCCESS and blueprint.outputs:
            final_outputs = render_value(blueprint.outputs, ctx.template_ctx())

        finished_at = datetime.now(timezone.utc)
        bus.emit(
            RunEvent(
                run_id=run_id,
                type=EventType.DONE,
                message=f"run finished: {final_status.value}",
                level="info" if final_status == RunStatus.SUCCESS else "error",
                data={"status": final_status.value, "error": run_error},
            )
        )

        return Result(
            run_id=run_id,
            blueprint_name=blueprint.name,
            status=final_status,
            outputs=final_outputs,
            step_results=step_results,
            error=run_error,
            started_at=started_at,
            finished_at=finished_at,
        )
