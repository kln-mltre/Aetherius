/**
 * Local daemon lifecycle: spawn `aetherius serve` as a child process when no base URL is provided,
 * wait for it to become healthy, and expose its address. Kept separate from the client so the
 * client can also target an already-running daemon.
 */

import { spawn } from "node:child_process";
import { createServer } from "node:net";

import { isHealthy } from "./transport.js";
import type { ClientConfig } from "./types.js";

export interface DaemonHandle {
  baseUrl: string;
  stop(): Promise<void>;
}

const DEFAULT_COMMAND = ["aetherius", "serve"];
const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** Ask the OS for a free loopback port by binding to 0 and reading the assigned port back. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

async function waitForHealth(baseUrl: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await isHealthy(baseUrl)) return;
    await delay(100);
  }
  throw new Error(`Daemon at ${baseUrl} did not become healthy within ${timeoutMs}ms.`);
}

/** Return a handle to a daemon: the one at `config.baseUrl`, or a freshly spawned local process. */
export async function ensureDaemon(config: ClientConfig = {}): Promise<DaemonHandle> {
  if (config.baseUrl) {
    return { baseUrl: config.baseUrl, stop: async () => {} };
  }

  const port = await freePort();
  const [command, ...baseArgs] = config.command ?? DEFAULT_COMMAND;
  const args = [...baseArgs, "--host", "127.0.0.1", "--port", String(port)];

  const env = { ...process.env };
  if (config.token) env.AETHERIUS_DAEMON_TOKEN = config.token;

  const child = spawn(command, args, { env, stdio: "ignore" });
  const baseUrl = `http://127.0.0.1:${port}`;

  // Race health against an early failure so a missing `aetherius` binary surfaces a clear error
  // instead of hanging until the health timeout.
  let settled = false;
  await new Promise<void>((resolve, reject) => {
    child.once("error", (err) => {
      if (!settled) {
        settled = true;
        reject(new Error(`Failed to spawn the daemon (${command}): ${err.message}`));
      }
    });
    child.once("exit", (code) => {
      if (!settled) {
        settled = true;
        reject(new Error(`Daemon exited before becoming healthy (code ${code}). Is 'aetherius' installed?`));
      }
    });
    waitForHealth(baseUrl, config.startTimeoutMs ?? 10_000).then(
      () => {
        if (!settled) {
          settled = true;
          resolve();
        }
      },
      (err) => {
        if (!settled) {
          settled = true;
          reject(err);
        }
      },
    );
  });

  const stop = (): Promise<void> =>
    new Promise((resolve) => {
      if (child.exitCode !== null || child.signalCode !== null) return resolve();
      child.once("exit", () => resolve());
      child.kill("SIGTERM");
    });

  return { baseUrl, stop };
}
