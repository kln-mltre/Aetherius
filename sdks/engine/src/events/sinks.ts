/**
 * Ready-made sinks, mirror of `src/aetherius/core/events/sinks.py`.
 *
 * The engine ships only what it can honour anywhere: discarding, collecting, and handing events to
 * a callback. Rendering belongs to the host — a terminal logger would be dead weight in an app, and
 * the application's own UI is the real consumer (milestone 3-E).
 */

import type { RunEvent, RunEventHandler, Sink } from "./models.js";

/** Discards every event. Used in tests and when a caller wants no stream at all. */
export class NullSink implements Sink {
  onEvent(): void {
    /* intentionally empty */
  }
}

/** Keeps every event in order. The assertion surface of the test suite. */
export class CollectingSink implements Sink {
  readonly events: RunEvent[] = [];

  onEvent(event: RunEvent): void {
    this.events.push(event);
  }
}

/** Adapts a plain callback — the shape an application passes as `onEvent`. */
export class HandlerSink implements Sink {
  constructor(private readonly handler: RunEventHandler) {}

  onEvent(event: RunEvent): void {
    this.handler(event);
  }
}

/** Render an event as one human-readable line, mirroring the Python `format_event`. */
export function formatEvent(event: RunEvent): string {
  let line = `[${event.type}]`;
  if (event.step_id !== undefined) line += ` step=${event.step_id}`;
  if (event.message !== undefined) line += ` ${event.message}`;
  return line;
}
