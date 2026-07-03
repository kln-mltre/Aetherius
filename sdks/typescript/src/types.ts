/**
 * Public types for the Aetherius TypeScript client.
 *
 * These mirror `contracts/blueprint.schema.json` and the daemon DTOs in `contracts/openapi.yaml`.
 * They are hand-written stubs for now; the intent is to generate them from the contracts so there
 * is a single source of truth across languages.
 */

/** A Blueprint passed either inline as an object or as a path the daemon can resolve. */
export type BlueprintRef = string | Record<string, unknown>;

export interface RunOptions {
  inputs?: Record<string, unknown>;
  secrets?: Record<string, string>;
}

export type RunStatus = "queued" | "running" | "succeeded" | "failed";

export interface RunResult {
  runId: string;
  status: RunStatus;
  outputs: Record<string, unknown>;
  error?: string | null;
}

export interface ClientConfig {
  /** Base URL of a already-running daemon. If omitted, the client spawns a local one. */
  baseUrl?: string;
  /** Optional bearer token expected by the daemon. */
  token?: string;
}
