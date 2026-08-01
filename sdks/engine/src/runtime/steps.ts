/**
 * The step executor, mirror of `src/aetherius/core/runtime/steps.py`.
 *
 * It walks a step tree, applies the `when` guard, hands leaves to the driver of their effective
 * act, and records one `StepResult` per step. Flow actions are interpreted here (flow.ts) and
 * re-enter the executor for their nested lists, so drivers only ever receive leaf actions.
 *
 * Nested executions carry a display path (`loop[2].fetch`) so events and results stay traceable
 * across branches and iterations; root steps keep their bare id, which is what makes a linear
 * Blueprint read the same on both engines.
 *
 * Not ported: self-healing (`healing.py`). It escalates to Acts III/IV, which stay on the Python
 * engine — there is nothing here to escalate to.
 */

import { nestedStepFields } from "../blueprint/contract.js";
import type { StepModel } from "../blueprint/types.js";
import type { ActDriver, Renderer, RunContext } from "../driver.js";
import { AetheriusError } from "../errors.js";
import type { EventBus, EventLevel, RunEventType } from "../events/index.js";
import { isTruthy, pythonRepr } from "../expr/index.js";
import type { RunStatus, StepResult } from "../result.js";
import { renderValue } from "../template.js";
import { monotonicMs, nowIso } from "./clock.js";
import { templateContext } from "./context.js";
import { runFlow, type FlowHost } from "./flow.js";

/**
 * Internal marker: a step error already recorded further down (`StepResult` + `error` event).
 *
 * Raised in place of the original so enclosing flow steps record their own failure without
 * emitting a duplicate event. It carries the original message, so the engine handles it like any
 * other `AetheriusError`.
 */
export class StepFailed extends AetheriusError {}

/** Resolves the live driver for a step's effective act (satisfied by `DriverManager`). */
export interface DriverResolver {
  resolveDriver(act: string, ctx: RunContext): Promise<ActDriver>;
}

/**
 * Execute *steps* in order, recording one `StepResult` per step into *results*.
 *
 * *driver* is either a resolver honouring per-step `act`, or a single driver serving every step —
 * the shape tests and mono-act callers use.
 *
 * @throws {StepFailed} a step failed after being recorded; the run must abort.
 */
export async function runSteps(
  steps: readonly StepModel[],
  ctx: RunContext,
  bus: EventBus,
  driver: ActDriver | DriverResolver,
  results: StepResult[],
  path = "",
): Promise<void> {
  const resolver = isResolver(driver) ? driver : fixedResolver(driver);
  await new Executor(ctx, bus, resolver, results).run(steps, path);
}

function isResolver(driver: ActDriver | DriverResolver): driver is DriverResolver {
  return typeof (driver as DriverResolver).resolveDriver === "function";
}

function fixedResolver(driver: ActDriver): DriverResolver {
  return { resolveDriver: async () => driver };
}

class Executor implements FlowHost {
  constructor(
    readonly ctx: RunContext,
    private readonly bus: EventBus,
    private readonly drivers: DriverResolver,
    private readonly results: StepResult[],
  ) {}

  async run(steps: readonly StepModel[], path = "", act?: string): Promise<void> {
    const inherited = act ?? this.ctx.blueprint.act;

    for (const [index, step] of steps.entries()) {
      const stepPath = join(path, step.id ?? `_step_${index}`);
      // Root steps keep their bare id (null when anonymous) so linear Blueprints are untouched;
      // nested steps expose their full path.
      const displayId = path === "" ? (step.id ?? null) : stepPath;
      const outputKey = step.id ?? stepPath;
      const effectiveAct = step.act ?? inherited;
      const render: Renderer = (value) => renderValue(value, templateContext(this.ctx));

      const started = monotonicMs();
      try {
        if (step.when !== undefined && !isTruthy(render(step.when))) {
          this.results.push(result(displayId, step.action, "skipped", started));
          // Report the raw expression, never its rendered value: it may derive from a secret.
          this.emit("step_skipped", displayId, {
            message: `skipped: when ${pythonRepr(step.when)} is false`,
            level: "info",
            data: { when: step.when },
          });
          continue;
        }

        this.emit("step_started", displayId, { level: "debug" });

        const outputs = isFlowAction(step.action)
          ? await runFlow(this, step, render, stepPath, effectiveAct)
          : await this.runLeaf(step, effectiveAct, render);

        this.ctx.stepOutputs[outputKey] = outputs;
        this.results.push(result(displayId, step.action, "success", started, { outputs }));
        this.emit("step_finished", displayId, { level: "debug" });
      } catch (error) {
        if (error instanceof StepFailed) {
          // A nested step already recorded the failure and emitted `error`: mark this flow step
          // failed too, without a duplicate event.
          this.results.push(
            result(displayId, step.action, "failed", started, { error: error.message }),
          );
          throw error;
        }
        if (!(error instanceof AetheriusError)) throw error;
        this.results.push(
          result(displayId, step.action, "failed", started, { error: error.message }),
        );
        this.emit("error", displayId, { message: error.message, level: "error" });
        throw new StepFailed(error.message);
      }
    }
  }

  private async runLeaf(
    step: StepModel,
    act: string,
    render: Renderer,
  ): Promise<Record<string, unknown>> {
    const driver = await this.drivers.resolveDriver(act, this.ctx);
    return driver.runStep(step, this.ctx, this.bus, render);
  }

  private emit(
    type: RunEventType,
    stepId: string | null,
    extra: { message?: string; level?: EventLevel; data?: Record<string, unknown> },
  ): void {
    this.bus.emit({
      run_id: this.ctx.runId,
      ts: nowIso(),
      type,
      ...(stepId !== null ? { step_id: stepId } : {}),
      ...(extra.level !== undefined ? { level: extra.level } : {}),
      ...(extra.message !== undefined ? { message: extra.message } : {}),
      ...(extra.data !== undefined ? { data: extra.data } : {}),
    });
  }
}

/** Flow actions are named by the generated contract, not by a list restated here. */
function isFlowAction(action: string): boolean {
  return nestedStepFields(action).length > 0;
}

function result(
  stepId: string | null,
  action: string,
  status: RunStatus,
  started: number,
  extra: { outputs?: Record<string, unknown>; error?: string } = {},
): StepResult {
  return {
    step_id: stepId,
    action,
    status,
    outputs: extra.outputs ?? {},
    ...(extra.error !== undefined ? { error: extra.error } : {}),
    duration_ms: monotonicMs() - started,
  };
}

function join(path: string, key: string): string {
  return path === "" ? key : `${path}.${key}`;
}
