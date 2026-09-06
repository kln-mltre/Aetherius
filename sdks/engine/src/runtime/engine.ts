/**
 * `RunEngine`, mirror of `src/aetherius/core/runtime/engine.py`.
 *
 * It orchestrates the same pipeline as the Python engine, with `await` in front of it: validate,
 * resolve inputs and secrets, bind the root driver, walk the steps, tear down, render the outputs,
 * return a `Result`. The observable behaviour is the contract — order of steps, events emitted,
 * shape of the `Result` — and the conformance corpus compares it case by case.
 *
 * Two failure paths, exactly as in Python: an `AetheriusError` is a clean run failure recorded in
 * the `Result`, anything else is wrapped in a `RunError` and rethrown. Swallowing the second kind
 * would turn a bug in the engine into a run that merely "did not work".
 */

import { validateForAct } from "../blueprint/validator.js";
import type { Blueprint } from "../blueprint/types.js";
import type { HostServices } from "../driver.js";
import { AetheriusError, RunError } from "../errors.js";
import { SimpleEventBus } from "../events/bus.js";
import { HandlerSink, formatEvent } from "../events/sinks.js";
import type { Sink } from "../events/models.js";
import type { AbortSignalLike, FetchLike } from "../http.js";
import type { Result, RunStatus, StepResult } from "../result.js";
import { renderValue } from "../template.js";
import type { ApprovalGateway } from "./approvals.js";
import { throwIfCancelled } from "./cancel.js";
import { nowIso } from "./clock.js";
import { createContext, resolveInputs, resolveSecrets, templateContext } from "./context.js";
import { DriverManager } from "./drivers.js";
import { StepFailed, runSteps } from "./steps.js";

export interface RunOptions {
  readonly inputs?: Readonly<Record<string, unknown>>;
  readonly secrets?: Readonly<Record<string, string>>;
  /** Event consumers. When omitted, `options.debug` decides whether the run logs to the console. */
  readonly sinks?: readonly Sink[];
  /** Supplied by a caller that already handed an id to its user (the daemon does this in Python). */
  readonly runId?: string;
  /** The table behind `{{ env.X }}`. A device has no environment; the host decides what to expose. */
  readonly env?: Readonly<Record<string, string>>;
  /** Overrides the host's `fetch` — how the test suite runs Act I without a network. */
  readonly fetch?: FetchLike;
  /**
   * The decision channel `confirm` steps consult. Omitted means *unattended*: `confirm` applies its
   * `on_timeout` policy at once, deny-by-default, exactly as a Python library run does.
   */
  readonly approvals?: ApprovalGateway;
  /**
   * Cancels the run. No Python twin — see `runtime/cancel.ts` for why a device needs one.
   */
  readonly signal?: AbortSignalLike;
}

export class RunEngine {
  async run(blueprint: Blueprint, options: RunOptions = {}): Promise<Result> {
    validateForAct(blueprint);

    const runId = options.runId ?? newRunId();
    const startedAt = nowIso();

    const ctx = createContext({
      runId,
      blueprint,
      inputs: resolveInputs(blueprint, options.inputs),
      secrets: resolveSecrets(blueprint.secrets, options.secrets),
      ...(options.env !== undefined ? { env: { ...options.env } } : {}),
      ...(options.approvals !== undefined ? { approvals: options.approvals } : {}),
      ...(options.signal !== undefined ? { signal: options.signal } : {}),
    });

    const bus = new SimpleEventBus();
    for (const sink of options.sinks ?? defaultSinks(blueprint)) bus.register(sink);

    const host: HostServices = options.fetch !== undefined ? { fetch: options.fetch } : {};
    const manager = new DriverManager(host);

    // Eager root bind: the Blueprint's own driver starts before the first step, so a run that
    // cannot even set up its Act fails before claiming to have started. A caller who cancelled
    // before this point gets nothing set up at all — no WebView is created to be torn down.
    throwIfCancelled(options.signal);
    await manager.resolveDriver(blueprint.act, ctx);

    bus.emit({
      run_id: runId,
      ts: nowIso(),
      type: "progress",
      level: "info",
      message: `run started: ${blueprint.name}`,
    });

    const stepResults: StepResult[] = [];
    let status: RunStatus = "success";
    let error: string | undefined;
    let cause: AetheriusError | undefined;

    try {
      // A goal-only Blueprint is the Phantom contract; the validator already refused it here.
      await runSteps(blueprint.steps ?? [], ctx, bus, manager, stepResults);
    } catch (thrown) {
      status = "failed";
      error = thrown instanceof Error ? thrown.message : String(thrown);
      if (!(thrown instanceof AetheriusError)) {
        await manager.teardownAll(ctx);
        throw new RunError(`Unexpected error during run ${runId}: ${error}`, thrown);
      }
      // The typed error, kept alongside its message: an application branches on the *kind* of
      // failure, and a message string would force it to parse prose. `StepFailed` is unwrapped —
      // it is an internal marker, and reporting it would tell an application only that "a step
      // failed", which is the loss of information `failure.ts` exists to prevent.
      cause = thrown instanceof StepFailed ? thrown.original : thrown;
    }
    await manager.teardownAll(ctx);

    // An `optional` block that gave way (milestone 3-J) reports `partial` without throwing, so the
    // verdict is read from the results rather than propagated. The guard is what makes a hard
    // failure always win — and the scan looks for `partial`, never for `failed`: a step marked
    // failed inside a tolerated block is no longer a verdict on the run.
    if (status === "success" && stepResults.some((step) => step.status === "partial")) {
      status = "partial";
    }

    // Outside the failure handling on purpose, exactly as in Python: a `TemplateError` in the
    // outputs is the caller's problem to see, not a run quietly reported as failed. A partial run
    // renders them too: holding them back would lose the readings that did arrive.
    let outputs: Record<string, unknown> = {};
    if (status !== "failed" && blueprint.outputs !== undefined) {
      outputs = renderValue(blueprint.outputs, templateContext(ctx)) as Record<string, unknown>;
    }

    bus.emit({
      run_id: runId,
      ts: nowIso(),
      type: "done",
      level: status === "failed" ? "error" : "info",
      message: `run finished: ${status}`,
      data: { status, error: error ?? null },
    });

    return {
      run_id: runId,
      blueprint_name: blueprint.name,
      status,
      outputs,
      step_results: stepResults,
      ...(error !== undefined ? { error } : {}),
      ...(cause !== undefined ? { cause } : {}),
      started_at: startedAt,
      finished_at: nowIso(),
    };
  }
}

/** Convenience twin of `aetherius.Aetherius().run(...)`; the full facade arrives at milestone 3-E. */
export function runBlueprint(blueprint: Blueprint, options?: RunOptions): Promise<Result> {
  return new RunEngine().run(blueprint, options);
}

function defaultSinks(blueprint: Blueprint): readonly Sink[] {
  // `options.debug` is the Blueprint asking to be watched; anything else is the host's call.
  if (blueprint.options?.debug !== true) return [];
  return [new HandlerSink((event) => console.log(formatEvent(event)))];
}

/**
 * A run id: 32 hex characters, like Python's `uuid4().hex`.
 *
 * `crypto.randomUUID` is not guaranteed on a mobile JS engine, so the fallback is explicit. The id
 * labels a run in a log and correlates events; it is not a secret and carries no authority.
 */
function newRunId(): string {
  const uuid = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto?.randomUUID?.();
  if (uuid !== undefined) return uuid.replace(/-/g, "");
  let out = "";
  for (let i = 0; i < 32; i += 1) out += Math.floor(Math.random() * 16).toString(16);
  return out;
}
