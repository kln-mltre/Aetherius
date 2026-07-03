/**
 * Local daemon lifecycle: spawn `aetherius serve` as a child process when no base URL is provided,
 * wait for it to become healthy, and expose its address. Kept separate from the client so the
 * client can also target an already-running daemon.
 *
 * Skeleton: the process management is not implemented yet.
 */

export interface DaemonHandle {
  baseUrl: string;
  stop(): Promise<void>;
}

export async function ensureDaemon(_baseUrl?: string): Promise<DaemonHandle> {
  throw new Error(
    "ensureDaemon is not implemented yet. This is the SDK skeleton; the daemon and its process " +
      "management are upcoming milestones.",
  );
}
