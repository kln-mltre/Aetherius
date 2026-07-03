/**
 * Aetherius TypeScript client.
 *
 * Loads an existing Blueprint and runs it through the local daemon. The Console is never involved
 * at runtime: execution is fully code-driven. Event streaming is exposed via `onEvent`.
 *
 * Skeleton: transport wiring is the next milestone.
 */

import { ensureDaemon, type DaemonHandle } from "./daemon.js";
import type { RunEventHandler } from "./events.js";
import type { BlueprintRef, ClientConfig, RunOptions, RunResult } from "./types.js";

export class Aetherius {
  private readonly config: ClientConfig;
  private daemon?: DaemonHandle;

  constructor(config: ClientConfig = {}) {
    this.config = config;
  }

  /** Execute a Blueprint and resolve with its result. */
  async run(_blueprint: BlueprintRef, _options: RunOptions = {}): Promise<RunResult> {
    await this.connect();
    throw new Error(
      "Aetherius.run is not implemented yet. This is the SDK skeleton; the daemon transport is " +
        "the next milestone.",
    );
  }

  /** Subscribe to the live event stream of a run. */
  onEvent(_runId: string, _handler: RunEventHandler): void {
    throw new Error("Aetherius.onEvent is not implemented yet.");
  }

  async close(): Promise<void> {
    await this.daemon?.stop();
  }

  private async connect(): Promise<void> {
    if (this.config.baseUrl) return;
    this.daemon ??= await ensureDaemon(this.config.baseUrl);
  }
}
