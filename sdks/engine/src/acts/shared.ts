/**
 * Act-agnostic action handlers, mirror of `src/aetherius/acts/_shared.py`.
 *
 * `set`, `assert`, `emit`, `wait` and `confirm` carry no Act-specific behaviour: they manipulate
 * the run context or the event bus, never a transport or a browser. Every driver dispatches to
 * them instead of carrying its own copy — Python does it with a mixin, this engine with a lookup,
 * because a driver here composes a client rather than inheriting one.
 *
 * `confirm` lives in its own file: it is the one shared action with a lifecycle (open, park, close)
 * and two events of its own.
 *
 * `notify` is deliberately absent: the embedded engine refuses it at validation (the application
 * already owns its notifications). See `blueprint/capabilities.ts`.
 */

import type { Renderer, RunContext } from "../driver.js";
import { ActionError, StatusAssertionError } from "../errors.js";
import type { EventBus } from "../events/index.js";
import { isTruthy } from "../expr/index.js";
import { cancellableSleep } from "../runtime/cancel.js";
import { nowIso } from "../runtime/clock.js";
import type { StepModel } from "../blueprint/types.js";
import { actionConfirm } from "./confirm.js";

export type SharedHandler = (
  step: StepModel,
  ctx: RunContext,
  bus: EventBus,
  render: Renderer,
) => Promise<Record<string, unknown>>;

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
  ctx: RunContext,
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
  // Cancellable: a thirty-second `wait` must not be how long it takes to leave a screen.
  if (ms > 0) await cancellableSleep(ms, ctx.signal);
  return {};
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
