/**
 * Synchronous event fan-out, mirror of `src/aetherius/core/events/bus.py`.
 *
 * Ordering is the observable part of the contract: sinks see events in emission order, and each
 * `emit` returns only once every sink has been offered the event. Nothing is queued or deferred —
 * a run that finished has already delivered its stream.
 */

import type { EventBus, RunEvent, Sink } from "./models.js";

/** Where a misbehaving sink is reported. Overridable so a host app can route it to its own logger. */
export type BusLogger = (message: string, error: unknown) => void;

const defaultLogger: BusLogger = (message, error) => {
  console.error(message, error);
};

export class SimpleEventBus implements EventBus {
  private readonly sinks: Sink[] = [];

  constructor(private readonly log: BusLogger = defaultLogger) {}

  register(sink: Sink): void {
    this.sinks.push(sink);
  }

  emit(event: RunEvent): void {
    for (const sink of this.sinks) {
      try {
        sink.onEvent(event);
      } catch (error) {
        // A consumer's bug is not a run failure: log it and keep delivering to the others.
        this.log("Event sink raised an error; continuing.", error);
      }
    }
  }
}
