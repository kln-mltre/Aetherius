/**
 * Aetherius TypeScript client.
 *
 * Loads an existing Blueprint and runs it through the local daemon. The Console is never involved
 * at runtime: execution is fully code-driven. Events stream live via the optional `onEvent`
 * callback on `run`, or a standalone `onEvent` subscription.
 */

import { ensureDaemon, type DaemonHandle } from "./daemon.js";
import type { RunEventHandler } from "./events.js";
import { fetchRun, pollUntilDone, streamEvents, submitRun } from "./transport.js";
import type { BlueprintRef, ClientConfig, RunOptions, RunResult } from "./types.js";

export class Aetherius {
  private readonly config: ClientConfig;
  private daemon?: DaemonHandle;

  constructor(config: ClientConfig = {}) {
    this.config = config;
  }

  /** Execute a Blueprint and resolve with its result, streaming events to `options.onEvent`. */
  async run(blueprint: BlueprintRef, options: RunOptions = {}): Promise<RunResult> {
    const baseUrl = await this.connect();
    const token = this.config.token;

    const runId = await submitRun(baseUrl, blueprint, options.inputs, options.secrets, token);
    const onEvent = options.onEvent ?? ((): void => {});

    try {
      // The daemon closes the stream right after the run's `done` event, so this awaits completion.
      await streamEvents(baseUrl, runId, token, onEvent);
    } catch {
      // Streaming is best-effort; fall back to polling for the authoritative result.
      return pollUntilDone(baseUrl, runId, token);
    }
    return fetchRun(baseUrl, runId, token);
  }

  /** Subscribe to the live event stream of a run. Resolves when the run finishes. */
  async onEvent(runId: string, handler: RunEventHandler): Promise<void> {
    const baseUrl = await this.connect();
    await streamEvents(baseUrl, runId, this.config.token, handler);
  }

  /** Stop the spawned daemon, if this client started one. */
  async close(): Promise<void> {
    await this.daemon?.stop();
    this.daemon = undefined;
  }

  private async connect(): Promise<string> {
    if (this.config.baseUrl) return this.config.baseUrl;
    this.daemon ??= await ensureDaemon(this.config);
    return this.daemon.baseUrl;
  }
}
