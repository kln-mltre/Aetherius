/**
 * What the embedded engine can honour on a device — a **strict subset** of the shared contract.
 *
 * The invariant, guarded by a test: a Blueprint this engine accepts is always accepted by the
 * Python engine; the reverse is not true. Two reasons an action is missing here, and they must not
 * be confused, because they send the author to two different fixes:
 *
 *   - the act is too weak (`click` under `vector`) — the contract already says so, and the message
 *     names the act to switch to. Same story on both engines;
 *   - the action has no honest equivalent on a device (`upload` needs a file chooser a WebView does
 *     not expose). The Blueprint is correct; it simply belongs to the Python engine.
 *
 * Declared here rather than derived, because it is a statement about *this* platform, not a
 * projection of the registry. See docs/embedded.md and docs/phase-3/README.md (decision 6).
 */

import type { ActName } from "./types.js";

/** Acts the embedded engine runs. Oracle and Phantom stay on the Python engine. */
export const EMBEDDED_ACTS = ["vector", "continuum"] as const satisfies readonly ActName[];

export type EmbeddedAct = (typeof EMBEDDED_ACTS)[number];

export function isEmbeddedAct(act: string): act is EmbeddedAct {
  return (EMBEDDED_ACTS as readonly string[]).includes(act);
}

/**
 * Actions the shared contract grants to an embedded act but that this engine cannot run, each with
 * the reason shown to the author. Written as data so the message is never invented at the call site.
 */
export const NOT_PORTABLE: Readonly<Record<string, string>> = {
  upload: "a WebView exposes no file chooser",
  drag: "a WebView has no trusted pointer-drag sequence",
  screenshot: "capturing the WebView is the host application's business, not the engine's",
  notify: "the application already owns its notifications",
};

const VECTOR_CAPABILITIES: readonly string[] = [
  "http.request",
  "extract",
  "set",
  "assert",
  "emit",
  "wait",
  "if",
  "repeat",
  "for_each",
  "confirm",
];

const CONTINUUM_CAPABILITIES: readonly string[] = [
  ...VECTOR_CAPABILITIES,
  "navigate",
  "back",
  "forward",
  "reload",
  "click",
  "fill",
  "type",
  "press",
  "select",
  "hover",
  "scroll",
  "evaluate",
  "wait_for",
];

const TABLE: Readonly<Record<EmbeddedAct, ReadonlySet<string>>> = {
  vector: new Set(VECTOR_CAPABILITIES),
  continuum: new Set(CONTINUUM_CAPABILITIES),
};

/** The actions *act* supports on this engine. Empty for an act the engine does not run. */
export function embeddedCapabilities(act: string): ReadonlySet<string> {
  return isEmbeddedAct(act) ? TABLE[act] : new Set<string>();
}
