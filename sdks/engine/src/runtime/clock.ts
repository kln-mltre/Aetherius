/**
 * The two clocks a run needs, read through `globalThis`.
 *
 * Wall time stamps events (`ts`, ISO-8601 UTC, as the contract requires); a monotonic reading
 * measures durations, because a device changing timezone or syncing its clock mid-run would
 * otherwise produce negative step durations. `performance` is not guaranteed everywhere, so the
 * fallback is explicit rather than assumed.
 */

interface PerformanceLike {
  now(): number;
}

const perf = (globalThis as { performance?: PerformanceLike }).performance;

export function nowIso(): string {
  return new Date().toISOString();
}

export function monotonicMs(): number {
  return perf !== undefined ? perf.now() : Date.now();
}

/** The only way to pause on a device: `wait` and the retry backoff both go through it. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
