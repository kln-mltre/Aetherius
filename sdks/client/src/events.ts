/**
 * Run event types, mirroring `contracts/events.schema.json`.
 * Streamed over the daemon WebSocket while a run executes.
 */

/**
 * The event types, as a value.
 *
 * A union type alone disappears at compile time, and this enumeration is a contract: the runtime
 * array is what a test can compare with `contracts/events.schema.json`. That guard was missing
 * until milestone 3-A, and the list had quietly fallen two types behind the daemon
 * (`input_requested` / `input_provided`, emitted since the human-in-the-loop milestone).
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

export interface RunEvent {
  runId: string;
  ts: string;
  type: RunEventType;
  stepId?: string;
  level?: "debug" | "info" | "warning" | "error";
  message?: string;
  data?: Record<string, unknown>;
  artifact?: { kind: "screenshot" | "har" | "dom" | "log"; path: string };
}

export type RunEventHandler = (event: RunEvent) => void;
