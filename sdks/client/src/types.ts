/**
 * Public types for the Aetherius TypeScript client.
 *
 * These mirror `contracts/blueprint.schema.json` and the daemon DTOs in `contracts/openapi.yaml`.
 * They are hand-written on purpose: the surface is small and this keeps the ergonomic client types
 * (camelCase, a streaming callback) decoupled from the wire shapes. A contract test keeps the enums
 * aligned with `contracts/` so the two never drift.
 */

import type { RunEventHandler } from "./events.js";

/** A Blueprint passed either inline as an object or as a path the daemon can resolve. */
export type BlueprintRef = string | Record<string, unknown>;

export interface RunOptions {
  inputs?: Record<string, unknown>;
  secrets?: Record<string, string>;
  /** Called for each event as the run streams, in order. */
  onEvent?: RunEventHandler;
}

export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export interface RunResult {
  runId: string;
  status: RunStatus;
  outputs: Record<string, unknown>;
  error?: string | null;
}

export interface ClientConfig {
  /** Base URL of an already-running daemon. If omitted, the client spawns a local one. */
  baseUrl?: string;
  /** Optional bearer token expected by the daemon. */
  token?: string;
  /**
   * Command used to spawn the local daemon, as an argv array. Defaults to `["aetherius", "serve"]`.
   * Override to pin an interpreter, e.g. `["python3", "-m", "aetherius", "serve"]`.
   */
  command?: string[];
  /** How long to wait for the spawned daemon to become healthy, in milliseconds (default 10000). */
  startTimeoutMs?: number;
}
