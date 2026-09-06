/**
 * Flow actions (`if` / `repeat` / `for_each` / `optional`), mirror of
 * `src/aetherius/core/runtime/flow.py`.
 *
 * They are interpreted before any driver sees them, so every Act inherits the semantics without
 * wiring anything. The executor re-enters itself through `FlowHost` for the nested lists.
 *
 * **The loops are sequential `await`s, never `Promise.all`.** Turning them into parallel work
 * because "we are async now" would make runs non-reproducible and break every Blueprint whose
 * iterations share a session or read the previous one's outputs. The order of steps is observable
 * — it is in the event stream — so it is part of the contract, not an implementation detail.
 */

import { nestedStepFields } from "../blueprint/contract.js";
import type { StepModel } from "../blueprint/types.js";
import type { Renderer, RunContext } from "../driver.js";
import { ActionError } from "../errors.js";
import { isTruthy, pythonRepr } from "../expr/index.js";
import type { RunStatus } from "../result.js";

/** Template names a `for_each` loop variable would shadow (see `templateContext`). */
const RESERVED_NAMES = new Set(["inputs", "secrets", "vars", "env", "steps"]);

const DEFAULT_LOOP_VAR = "item";

/**
 * ASCII only, where Python's `str.isidentifier()` accepts any Unicode letter.
 *
 * Deliberately narrower: Unicode property escapes (`\p{L}`) are not guaranteed by the mobile JS
 * engine, and a regexp literal that fails to compile takes the whole module down at load time —
 * a crash on a device instead of a rejected loop variable. Refusing more than Python does is the
 * safe direction here, and it is the one the phase already assumes (a strict subset). Documented
 * in docs/embedded.md.
 */
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * What a flow step reports back: its outputs, and the status the executor must record.
 *
 * Only `optional` ever reports anything but `success`. Carrying the status here rather than
 * inferring it in the executor keeps a single rule — the step that *interpreted* the block says
 * how it went.
 */
export interface FlowOutcome {
  readonly outputs: Record<string, unknown>;
  readonly status: RunStatus;
}

/** The slice of the executor a flow action needs: recursion, plus the run scope. */
export interface FlowHost {
  readonly ctx: RunContext;
  run(steps: readonly StepModel[], path: string, act: string): Promise<void>;
  runTolerant(steps: readonly StepModel[], path: string, act: string): Promise<boolean>;
}

/** Interpret one flow step; nested lists re-enter *host* with the step's effective *act*. */
export async function runFlow(
  host: FlowHost,
  step: StepModel,
  render: Renderer,
  path: string,
  act: string,
): Promise<FlowOutcome> {
  if (step.action === "if") return done(await flowIf(host, step, render, path, act));
  if (step.action === "repeat") return done(await flowRepeat(host, step, render, path, act));
  // Explicit, because `for_each` is the fallback below: without this branch an `optional` block
  // would be interpreted as a malformed loop, and fail on a missing `items`.
  if (step.action === "optional") return flowOptional(host, step, path, act);
  return done(await flowForEach(host, step, render, path, act));
}

function done(outputs: Record<string, unknown>): FlowOutcome {
  return { outputs, status: "success" };
}

/**
 * Run a block whose failure is an acceptable outcome (milestone 3-J).
 *
 * The block publishes no data of its own: what happened is read from `Result.step_results`, never
 * from the template context — the same split the milestone installs everywhere.
 */
async function flowOptional(
  host: FlowHost,
  step: StepModel,
  path: string,
  act: string,
): Promise<FlowOutcome> {
  const nested = nestedSteps(step, "steps", path);
  const gaveWay = await host.runTolerant(nested, path, act);
  return { outputs: {}, status: gaveWay ? "partial" : "success" };
}

/**
 * Publish `{}` for every identified step of an `optional` block that produced nothing.
 *
 * Both engines reject the undefined at the point of *use*, so `steps.coord.city | default(null)`
 * throws when `steps.coord` is missing altogether — the filter never sees the value, the member
 * access already failed. Seeding an empty object is what makes the documented writing rule true.
 * `??=` is the whole subtlety: a step that published before giving way keeps what it published.
 *
 * It recurses through nested blocks so the rule holds at any depth inside the block, and never
 * touches anything outside it. The consequence is deliberate and documented: `steps.coord` is
 * defined even when the block gave way — the template context carries *data*, while
 * `Result.step_results` carries what *happened*.
 */
export function seedBlockOutputs(ctx: RunContext, step: StepModel): void {
  seed(ctx, step.id, step.action, step as Record<string, unknown>);
}

function seed(ctx: RunContext, stepId: unknown, action: string, fields: Record<string, unknown>): void {
  if (typeof stepId === "string" && stepId !== "") ctx.stepOutputs[stepId] ??= {};
  for (const name of nestedStepFields(action)) {
    const nested = fields[name];
    if (!Array.isArray(nested)) continue;
    for (const item of nested) {
      if (item !== null && typeof item === "object") {
        const child = item as Record<string, unknown>;
        seed(ctx, child["id"], typeof child["action"] === "string" ? child["action"] : "", child);
      }
    }
  }
}

async function flowIf(
  host: FlowHost,
  step: StepModel,
  render: Renderer,
  path: string,
  act: string,
): Promise<Record<string, unknown>> {
  if (!has(step, "condition")) {
    throw new ActionError(`if: missing required parameter 'condition' (step '${path}').`);
  }
  const branch = isTruthy(render(step["condition"])) ? "then" : "else";
  if (branch === "else" && !has(step, "else")) return { branch: null };
  await host.run(nestedSteps(step, branch, path), path, act);
  return { branch };
}

async function flowRepeat(
  host: FlowHost,
  step: StepModel,
  render: Renderer,
  path: string,
  act: string,
): Promise<Record<string, unknown>> {
  if (!has(step, "times")) {
    throw new ActionError(`repeat: missing required parameter 'times' (step '${path}').`);
  }
  const times = coerceTimes(render(step["times"]), path);
  const nested = nestedSteps(step, "steps", path);
  for (let i = 0; i < times; i += 1) {
    await host.run(nested, `${path}[${i}]`, act);
  }
  return { iterations: times };
}

async function flowForEach(
  host: FlowHost,
  step: StepModel,
  render: Renderer,
  path: string,
  act: string,
): Promise<Record<string, unknown>> {
  if (!has(step, "items")) {
    throw new ActionError(`for_each: missing required parameter 'items' (step '${path}').`);
  }
  const items = render(step["items"]);
  if (!Array.isArray(items)) {
    throw new ActionError(
      `for_each: 'items' must render to a list, got ${typeName(items)} (step '${path}').`,
    );
  }
  const variable = has(step, "as") ? step["as"] : DEFAULT_LOOP_VAR;
  if (typeof variable !== "string" || !IDENTIFIER.test(variable)) {
    throw new ActionError(
      `for_each: 'as' must be a valid identifier, got ${pythonRepr(variable)} (step '${path}').`,
    );
  }
  if (RESERVED_NAMES.has(variable)) {
    throw new ActionError(
      `for_each: loop variable '${variable}' would shadow a reserved template name ` +
        `(step '${path}').`,
    );
  }
  const nested = nestedSteps(step, "steps", path);

  // Save and restore whatever the variable shadowed, so nested loops compose.
  const { scope } = host.ctx;
  const had = Object.prototype.hasOwnProperty.call(scope, variable);
  const previous = scope[variable];
  try {
    for (let i = 0; i < items.length; i += 1) {
      scope[variable] = items[i];
      await host.run(nested, `${path}[${i}]`, act);
    }
  } finally {
    if (had) scope[variable] = previous;
    else delete scope[variable];
  }
  return { iterations: items.length };
}

function nestedSteps(step: StepModel, key: string, path: string): StepModel[] {
  const raw = step[key];
  if (!Array.isArray(raw)) {
    throw new ActionError(`${step.action}: '${key}' must be a list of steps (step '${path}').`);
  }
  return raw.map((item, index) => {
    if (item === null || typeof item !== "object" || typeof (item as StepModel).action !== "string") {
      throw new ActionError(
        `${step.action}: invalid step in '${key}' at index ${index} (step '${path}'): ` +
          "each entry must be an object with an 'action'.",
      );
    }
    return item as StepModel;
  });
}

function coerceTimes(value: unknown, path: string): number {
  let times: number | null = null;
  if (typeof value === "number" && Number.isInteger(value)) {
    times = value;
  } else if (typeof value === "string" && /^[+-]?\d+$/.test(value.trim())) {
    times = Number(value.trim());
  }
  if (times === null) {
    throw new ActionError(
      `repeat: 'times' must be an integer, got ${pythonRepr(value)} (step '${path}').`,
    );
  }
  if (times < 0) {
    throw new ActionError(`repeat: 'times' must be >= 0, got ${times} (step '${path}').`);
  }
  return times;
}

/** Python-flavoured type name, so the two engines' messages stay recognisable side by side. */
function typeName(value: unknown): string {
  if (value === null || value === undefined) return "NoneType";
  if (Array.isArray(value)) return "list";
  if (typeof value === "string") return "str";
  if (typeof value === "boolean") return "bool";
  if (typeof value === "number") return Number.isInteger(value) ? "int" : "float";
  return "dict";
}

function has(step: StepModel, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(step, key);
}
