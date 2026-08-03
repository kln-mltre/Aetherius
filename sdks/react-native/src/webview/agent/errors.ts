/**
 * The agent's error shape.
 *
 * The agent runs in the page and cannot import the engine's error hierarchy — bundling
 * `@aetherius/engine` into a script injected on every navigation would be absurd. It therefore
 * reports a *name*, and `rpc.ts` rebuilds the matching class on the other side. Only the names the
 * bridge knows how to rebuild are used here.
 */

export class OpError extends Error {
  /** The class the driver side must rebuild: `ActionError`, `ExtractionError` or `StepTimeoutError`. */
  readonly kind: string;
  /** A Blueprint's `fail:CODE`, carried through the bridge intact. */
  readonly code: string | undefined;

  constructor(message: string, kind = "ActionError", code?: string) {
    super(message);
    this.name = kind;
    this.kind = kind;
    this.code = code;
  }
}

/** A named timeout, the form `on_timeout: "fail:CODE"` turns into. */
export function timeoutError(message: string, code?: string): OpError {
  return new OpError(message, "StepTimeoutError", code);
}

/**
 * A selector that did not resolve on the page.
 *
 * Not an `ActionError`, and the distinction is what an application acts on: a Blueprint whose
 * selector no longer matches is a **source that changed shape** — something to fix and redeliver
 * (milestone 3-F) — where an `ActionError` says "this is a bug in the engine, report it". Sending a
 * stale selector to the second screen is the single most common Act II failure, so it is the one
 * that must be named correctly.
 */
export function selectorError(message: string): OpError {
  return new OpError(message, "ExtractionError");
}

/** The wire form of any thrown value; an unexpected throw must not lose its message. */
export function describeError(error: unknown): { name: string; message: string; code?: string } {
  if (error instanceof OpError) {
    return error.code === undefined
      ? { name: error.kind, message: error.message }
      : { name: error.kind, message: error.message, code: error.code };
  }
  const message = error instanceof Error ? error.message : String(error);
  return { name: "ActionError", message };
}
