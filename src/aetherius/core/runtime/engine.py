"""RunEngine: orchestrates Act selection, step pipeline, retries, events, and Result assembly."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from ..blueprint.models import Blueprint
from ..blueprint.template import render_value
from ..blueprint.validator import validate_for_act
from ..errors import AetheriusError, RunError
from ..events.bus import EventBus
from ..events.models import EventType, RunEvent
from ..events.sinks import LogSink, NullSink, Sink
from ..runtime.approvals import ApprovalGateway
from ..runtime.context import RunContext, resolve_inputs
from ..runtime.drivers import IMPLEMENTED_ACTS as IMPLEMENTED_ACTS  # re-export (public surface)
from ..runtime.drivers import DriverManager
from ..runtime.result import Result, RunStatus, StepResult
from ..runtime.steps import run_steps


class RunEngine:
    def run(
        self,
        blueprint: Blueprint,
        inputs: Mapping[str, Any] | None = None,
        secrets: Mapping[str, str] | None = None,
        *,
        sinks: list[Sink] | None = None,
        run_id: str | None = None,
        approvals: ApprovalGateway | None = None,
    ) -> Result:
        # Plugins must be visible before validation: a Blueprint may use a plugin action. Imported
        # lazily (like resolve_secrets below) and idempotent, so per-run cost is a flag check.
        from ...plugins import load_plugins

        load_plugins()
        validate_for_act(blueprint)

        # The daemon assigns the id it returned to the caller (HTTP 202) before the run starts, so
        # the streamed events carry a run_id the client already holds. In-process callers omit it.
        run_id = run_id or uuid.uuid4().hex
        started_at = datetime.now(timezone.utc)

        from ...config.secrets import resolve_secrets

        resolved_inputs = resolve_inputs(blueprint, inputs)
        resolved_secrets = resolve_secrets(blueprint.secrets, secrets)
        ctx = RunContext(
            run_id=run_id,
            blueprint=blueprint,
            inputs=resolved_inputs,
            secrets=resolved_secrets,
            started_at=started_at,
            approvals=approvals,
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

        # Eager root bind: the Blueprint's own driver starts before the first step, exactly like
        # the historical single-driver engine (mono-Act runs are untouched). Other Acts named by
        # per-step overrides or fallback chains start lazily, at the first step that needs them.
        manager = DriverManager(blueprint)
        driver = manager.resolve_driver(blueprint.act, ctx)

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
            if blueprint.steps:
                run_steps(blueprint.steps, ctx, bus, manager, step_results)
            else:
                # Goal-only Blueprint (Phantom): the agent loop replaces the step pipeline. The
                # model guarantees a goal is present when steps is empty (_require_steps_or_goal).
                driver.run_goal(ctx, bus, step_results)

        except AetheriusError as exc:
            final_status = RunStatus.FAILED
            run_error = str(exc)

        except Exception as exc:
            final_status = RunStatus.FAILED
            run_error = str(exc)
            raise RunError(f"Unexpected error during run {run_id}: {exc}", cause=exc) from exc

        finally:
            manager.teardown_all(ctx)

        # Render the outputs dict through the template engine.
        final_outputs: dict[str, Any] = {}
        if final_status == RunStatus.SUCCESS:
            if blueprint.outputs:
                final_outputs = render_value(blueprint.outputs, ctx.template_ctx())
            elif not blueprint.steps and isinstance(ctx.step_outputs.get("agent"), dict):
                # A goal-only run with no declared outputs returns the agent outcome directly, so
                # `client.run(...).outputs` is useful without boilerplate.
                final_outputs = ctx.step_outputs["agent"]

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
