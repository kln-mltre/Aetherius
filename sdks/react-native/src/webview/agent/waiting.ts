/**
 * Auto-waiting — the layer that makes the difference.
 *
 * A mature browser driver waits for an element to exist, be visible and be stable before acting on
 * it. A WebView offers nothing of the sort. Without this layer every Blueprint would have to sow
 * fixed waits, which is exactly the fragility this project exists to remove: the hand-written
 * WebViews this milestone replaces carry the same pattern copy-pasted once per script, each with
 * its own hard-coded timeout.
 *
 * The pattern, written once: **try immediately; if that fails, observe the document until the
 * deadline; at the deadline, produce an explicit failure rather than staying blocked.**
 *
 * Observation is a `MutationObserver` *and* a poll, and the poll is not belt-and-braces: a
 * MutationObserver does not fire when an element becomes visible because a stylesheet finished
 * loading, or when a transition ends. Relying on mutations alone would hang on exactly the pages
 * that need waiting most.
 */

import { OpError, timeoutError } from "./errors.js";

/** How often the fallback poll runs, in milliseconds. */
const POLL_MS = 100;

/** The delay used to check that an element's box stopped moving. One frame, generously. */
const STABLE_MS = 32;

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Resolve as soon as *probe* returns something other than `null`, or fail at the deadline.
 *
 * `describe` is called only on failure, so the message can say what was being waited for without
 * costing anything on the happy path.
 */
export function waitFor<T>(
  probe: () => T | null,
  timeoutMs: number,
  describe: () => string,
  code?: string,
): Promise<T> {
  const immediate = probe();
  if (immediate !== null) return Promise.resolve(immediate);

  return new Promise<T>((resolve, reject) => {
    let done = false;

    const finish = (action: () => void): void => {
      if (done) return;
      done = true;
      observer.disconnect();
      clearInterval(poll);
      clearTimeout(deadline);
      action();
    };

    const attempt = (): void => {
      if (done) return;
      let value: T | null;
      try {
        value = probe();
      } catch (error) {
        finish(() => {
          reject(error);
        });
        return;
      }
      if (value !== null) {
        finish(() => {
          resolve(value as T);
        });
      }
    };

    const observer = new MutationObserver(attempt);
    const poll = setInterval(attempt, POLL_MS);
    const deadline = setTimeout(() => {
      finish(() => {
        reject(timeoutError(describe(), code));
      });
    }, timeoutMs);

    // `characterData` matters: a counter that goes from "0" to "3" changes no node, only text.
    // `attributes` matters just as much: a spinner usually disappears behind a class change.
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
    });

    // The document may have changed between the first probe and the observer being wired.
    attempt();
  });
}

/** Visible the way a browser means it: a non-empty box, and not `visibility: hidden`. */
export function isVisible(element: Element): boolean {
  if (!element.isConnected) return false;
  const style = getComputedStyle(element);
  if (style.visibility === "hidden" || style.visibility === "collapse") return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

/** Enabled: not a disabled form control, and not inside a disabled fieldset. */
export function isEnabled(element: Element): boolean {
  try {
    return !element.matches(":disabled");
  } catch {
    return (element as HTMLInputElement).disabled !== true;
  }
}

/**
 * Wait until *element* is worth acting on: present, connected, visible, enabled, and no longer
 * moving.
 *
 * `resolveElement` returns `null` for "not there **yet**", which is why it is allowed to: a portal
 * that renders its form a few hundred milliseconds after load is the normal case, and failing on
 * the first look would defeat the whole point of auto-waiting. Playwright waits, the Python engine
 * waits, and so does this.
 *
 * Stability is the one people forget. An element that is still animating into place receives the
 * click at its old coordinates, which is the classic "the test passes locally" bug.
 */
export async function waitActionable(
  resolveElement: () => Element | null,
  timeoutMs: number,
  describe: () => string,
): Promise<Element> {
  const started = Date.now();
  const element = await waitFor(
    () => {
      const candidate = resolveElement();
      if (candidate === null) return null;
      return isVisible(candidate) && isEnabled(candidate) ? candidate : null;
    },
    timeoutMs,
    () => `${describe()} never became visible and enabled`,
  );

  const first = element.getBoundingClientRect();
  await sleep(STABLE_MS);
  const second = element.getBoundingClientRect();
  if (first.top !== second.top || first.left !== second.left) {
    // Still moving: give it what is left of the budget to settle, then act regardless — refusing
    // to click on a page with a permanent animation would be worse than clicking a little late.
    const left = Math.max(0, timeoutMs - (Date.now() - started));
    await settle(element, Math.min(left, timeoutMs));
  }
  return element;
}

async function settle(element: Element, budgetMs: number): Promise<void> {
  const deadline = Date.now() + budgetMs;
  let previous = element.getBoundingClientRect();
  while (Date.now() < deadline) {
    await sleep(STABLE_MS);
    const current = element.getBoundingClientRect();
    if (current.top === previous.top && current.left === previous.left) return;
    previous = current;
  }
}

/** The four states `wait_for` understands, mirroring Playwright's vocabulary. */
export type WaitState = "visible" | "attached" | "hidden" | "detached";

export function parseState(raw: unknown): WaitState {
  const state = typeof raw === "string" && raw !== "" ? raw.toLowerCase() : "visible";
  if (state === "visible" || state === "attached" || state === "hidden" || state === "detached") {
    return state;
  }
  throw new OpError(
    `Unknown wait_for state ${JSON.stringify(state)} (expected visible, attached, hidden or detached).`,
  );
}

/** Whether *element* (possibly absent) satisfies *state*. */
export function satisfies(element: Element | null, state: WaitState): boolean {
  switch (state) {
    case "attached":
      return element !== null;
    case "detached":
      return element === null;
    case "hidden":
      return element === null || !isVisible(element);
    default:
      return element !== null && isVisible(element);
  }
}
