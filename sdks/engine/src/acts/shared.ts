/**
 * Act-agnostic action handlers, mirror of `src/aetherius/acts/_shared.py`.
 *
 * `set`, `assert`, `emit`, `wait` and `confirm` carry no Act-specific behaviour: they manipulate
 * the run context or the event bus, never a transport or a browser. Every driver dispatches to
 * them instead of carrying its own copy — Python does it with a mixin, this engine with a lookup,
 * because a driver here composes a client rather than inheriting one.
 *
 * `notify` is deliberately absent: the embedded engine refuses it at validation (the application
 * already owns its notifications). See `blueprint/capabilities.ts`.
 */

import type { Renderer, RunContext } from "../driver.js";
import { ActionError, StatusAssertionError, StepTimeoutError } from "../errors.js";
import type { EventBus } from "../events/index.js";
import { isTruthy } from "../expr/index.js";
import { nowIso, sleep } from "../runtime/clock.js";
import type { StepModel } from "../blueprint/types.js";

export type SharedHandler = (
  step: StepModel,
  ctx: RunContext,
  bus: EventBus,
  render: Renderer,
) => Promise<Record<string, unknown>>;

/**
 * Mandatory upper bound for a parked `confirm` (5 min), as in Python: a Blueprint may shorten it
 * through `timeout_ms`, but a run never parks forever.
 */
const DEFAULT_CONFIRM_TIMEOUT_MS = 300_000;

const HANDLERS: Readonly<Record<string, SharedHandler>> = {
  set: actionSet,
  assert: actionAssert,
  emit: actionEmit,
  wait: actionWait,
  confirm: actionConfirm,
};

/** The handler for *action*, or `undefined` when the action belongs to an Act. */
export function sharedAction(action: string): SharedHandler | undefined {
  return HANDLERS[action];
}

async function actionSet(
  step: StepModel,
  _ctx: RunContext,
  _bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  // `?? null` rather than a bare read: a missing `value` is `None` in Python, and `undefined`
  // would serialise differently in the outputs of the step that follows.
  return { value: render(step["value"] ?? null) };
}

async function actionAssert(
  step: StepModel,
  _ctx: RunContext,
  _bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  const condition = render(step["condition"] ?? "");
  if (!isTruthy(condition)) {
    // Python builds the fallback from the *raw* condition and then renders the whole message, so
    // the expression is evaluated a second time and its value ends up in the text. Reproduced as
    // is: it is the observable behaviour, and an assert message is meant to say what was seen.
    const fallback = `Assertion failed: ${String(step["condition"])}`;
    const message = String(render(step["message"] ?? fallback));
    throw new StatusAssertionError(assertionMessage(message));
  }
  return {};
}

async function actionEmit(
  step: StepModel,
  ctx: RunContext,
  bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  const message = String(render(step["event"] ?? step["message"] ?? ""));
  bus.emit({
    run_id: ctx.runId,
    ts: nowIso(),
    type: "progress",
    ...(step.id !== undefined ? { step_id: step.id } : {}),
    level: "info",
    message,
  });
  return {};
}

async function actionWait(
  step: StepModel,
  _ctx: RunContext,
  _bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  let ms: number;
  if (Object.prototype.hasOwnProperty.call(step, "ms")) {
    ms = milliseconds(render(step["ms"] ?? 0), "wait: 'ms'");
  } else {
    // No fixed duration: draw uniformly from [min_ms, max_ms] — the non-deterministic pause the
    // stealth-minded Blueprints use, since a fixed inter-step delay is a tell.
    const low = milliseconds(render(step["min_ms"] ?? 0) || 0, "wait: 'min_ms'");
    const high = milliseconds(render(step["max_ms"] ?? low) || low, "wait: 'max_ms'");
    if (high < low) {
      throw new ActionError(`wait: max_ms (${high}) must be >= min_ms (${low}).`);
    }
    ms = low + Math.random() * (high - low);
  }
  if (ms > 0) await sleep(ms);
  return {};
}

/**
 * `confirm` with nobody to answer.
 *
 * The human rendezvous — a native modal — is milestone 3-E. What this engine already owes is the
 * *unattended* path Python takes when no approval gateway is attached: apply `on_timeout` at once,
 * deny by default. Leaving the action unimplemented instead would let a Blueprint pass validation
 * and then die mid-run, which is precisely what the embedded engine promises never to do.
 */
async function actionConfirm(
  step: StepModel,
  _ctx: RunContext,
  _bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  const message = String(render(step["message"] ?? "") || "");
  const onTimeout = String(render(step["on_timeout"] ?? "reject") || "reject");
  // Read even though nothing waits on it: a Blueprint whose timeout is unusable should say so here
  // and not at 3-E, when the value suddenly starts being honoured.
  milliseconds(render(step["timeout_ms"] ?? DEFAULT_CONFIRM_TIMEOUT_MS), "confirm: 'timeout_ms'");

  if (onTimeout.startsWith("fail:")) {
    const code = onTimeout.slice("fail:".length);
    throw new StepTimeoutError(
      `confirm timed out awaiting a decision: ${JSON.stringify(message)}`,
      code === "" ? undefined : code,
    );
  }
  const approved = onTimeout === "approve";
  return {
    approved,
    decision: approved ? "approved" : "rejected",
    value: null,
    decided_by: "timeout",
  };
}

/** `StatusAssertionError`'s message, built the way `core/errors.py` builds it. */
function assertionMessage(preview: string): string {
  return `Expected HTTP 1, got 0 — <assert>` + (preview !== "" ? `\n${preview.slice(0, 200)}` : "");
}

function milliseconds(value: unknown, field: string): number {
  const ms = Number(value);
  if (!Number.isFinite(ms)) {
    throw new ActionError(`${field} must be a number, got ${JSON.stringify(value)}.`);
  }
  return ms;
}
