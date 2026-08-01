/**
 * Event types emitted during a run, mirror of `src/aetherius/core/events/models.py`.
 *
 * The wire contract is `contracts/events.schema.json`: the embedded engine emits exactly the same
 * types as the Python engine, so one UI consumes both. Types belonging to layers outside the
 * embedded scope stay declared — the contract defines them — but are never emitted here.
 */

/**
 * The event types, as a value.
 *
 * A union type alone would vanish at compile time, and the enumeration is a *contract*: a runtime
 * array is what lets a test compare it with `contracts/events.schema.json`. That test is how the
 * drift `@aetherius/client` carried until milestone 3-A (two missing types) gets caught next time.
 */
export const RUN_EVENT_TYPES = [
  "progress",
  "step_started",
  "step_finished",
  "step_skipped",
  "debug",
  "artifact",
  "error",
  "done",
  "input_requested",
  "input_provided",
] as const;

export type RunEventType = (typeof RUN_EVENT_TYPES)[number];

export const EVENT_LEVELS = ["debug", "info", "warning", "error"] as const;

export type EventLevel = (typeof EVENT_LEVELS)[number];

export interface RunEvent {
  readonly run_id: string;
  /** ISO-8601 UTC. */
  readonly ts: string;
  readonly type: RunEventType;
  readonly step_id?: string;
  readonly level?: EventLevel;
  readonly message?: string;
  readonly data?: Readonly<Record<string, unknown>>;
}

export type RunEventHandler = (event: RunEvent) => void;

/**
 * A sink consumes the stream. As on the Python side, an exception thrown by a sink is logged and
 * swallowed: a faulty consumer never breaks a run.
 */
export interface Sink {
  onEvent(event: RunEvent): void;
}

/** Fans an event out to every registered sink. */
export interface EventBus {
  emit(event: RunEvent): void;
  register(sink: Sink): void;
}
