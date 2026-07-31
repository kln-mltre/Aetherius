/**
 * Transport helpers for the daemon: HTTP over the native `fetch` (Node 20+), event streaming over a
 * WebSocket (`ws`). Kept separate from the client so the orchestration in client.ts stays thin.
 */

import WebSocket from "ws";

import type { RunEvent, RunEventHandler } from "./events.js";
import type { BlueprintRef, RunResult, RunStatus } from "./types.js";

function authHeaders(token?: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function requestJson(url: string, init: RequestInit): Promise<Record<string, unknown>> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Daemon request to ${url} failed: ${response.status} ${response.statusText} ${body}`);
  }
  return (await response.json()) as Record<string, unknown>;
}

/** Health probe used by the daemon spawner; resolves true on a 200. */
export async function isHealthy(baseUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${baseUrl}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

export async function submitRun(
  baseUrl: string,
  blueprint: BlueprintRef,
  inputs: Record<string, unknown> | undefined,
  secrets: Record<string, string> | undefined,
  token?: string,
): Promise<string> {
  const data = await requestJson(`${baseUrl}/v1/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ blueprint, inputs: inputs ?? {}, secrets: secrets ?? {} }),
  });
  return data.run_id as string;
}

export async function fetchRun(baseUrl: string, runId: string, token?: string): Promise<RunResult> {
  const data = await requestJson(`${baseUrl}/v1/runs/${runId}`, { headers: authHeaders(token) });
  return {
    runId: data.run_id as string,
    status: data.status as RunStatus,
    outputs: (data.outputs as Record<string, unknown>) ?? {},
    error: (data.error as string | null) ?? null,
  };
}

/** ws:// URL for a run's event stream, derived from the http(s) base URL. */
export function eventsUrl(baseUrl: string, runId: string): string {
  return `${baseUrl.replace(/^http/, "ws")}/v1/runs/${runId}/events`;
}

/**
 * Open the run's event stream and forward every event to `onEvent`. Resolves when the daemon closes
 * the socket (which it does right after the run's `done` event). Rejects on a transport error.
 */
export function streamEvents(
  baseUrl: string,
  runId: string,
  token: string | undefined,
  onEvent: RunEventHandler,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(eventsUrl(baseUrl, runId), { headers: authHeaders(token) });
    socket.on("message", (data) => {
      try {
        onEvent(JSON.parse(data.toString()) as RunEvent);
      } catch {
        // Ignore a malformed frame rather than aborting the whole stream.
      }
    });
    socket.on("close", () => resolve());
    socket.on("error", (err) => reject(err));
  });
}

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** Fallback completion path when streaming is unavailable: poll until the run reaches a terminal state. */
export async function pollUntilDone(
  baseUrl: string,
  runId: string,
  token: string | undefined,
  intervalMs = 100,
  timeoutMs = 120_000,
): Promise<RunResult> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const run = await fetchRun(baseUrl, runId, token);
    if (run.status === "succeeded" || run.status === "failed") return run;
    if (Date.now() > deadline) throw new Error(`Run ${runId} did not finish within ${timeoutMs}ms.`);
    await delay(intervalMs);
  }
}
