/**
 * Timers, read through `globalThis` and typed structurally.
 *
 * Same posture as the engine's `src/http.ts`: this package borrows neither `lib: ["DOM"]` nor
 * `@types/node`. A React Native runtime is neither, and pulling in Node's globals would let
 * `Buffer` or `process` slip into code that ships to a phone — where they do not exist.
 *
 * The handle stays opaque on purpose: it is a number on the web, an object under Node, and nothing
 * here needs to know which.
 */

export type TimerHandle = unknown;

interface TimerHost {
  setTimeout(handler: () => void, ms: number): TimerHandle;
  clearTimeout(handle: TimerHandle): void;
  setInterval(handler: () => void, ms: number): TimerHandle;
  clearInterval(handle: TimerHandle): void;
}

const host = globalThis as unknown as TimerHost;

export function startTimer(handler: () => void, ms: number): TimerHandle {
  return host.setTimeout(handler, ms);
}

export function stopTimer(handle: TimerHandle): void {
  host.clearTimeout(handle);
}

export function startInterval(handler: () => void, ms: number): TimerHandle {
  return host.setInterval(handler, ms);
}

export function stopInterval(handle: TimerHandle): void {
  host.clearInterval(handle);
}

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    host.setTimeout(resolve, ms);
  });
}
