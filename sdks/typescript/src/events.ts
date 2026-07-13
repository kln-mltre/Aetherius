/**
 * Run event types, mirroring `contracts/events.schema.json`.
 * Streamed over the daemon WebSocket while a run executes.
 */

export type RunEventType =
  | "progress"
  | "step_started"
  | "step_finished"
  | "step_skipped"
  | "debug"
  | "artifact"
  | "error"
  | "done";

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
