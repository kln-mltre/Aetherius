/**
 * How a run finds a live WebView.
 *
 * The engine resolves a driver from a registry rather than a `match`, precisely so a platform
 * package can add one without the neutral package knowing it exists. This module is the other half:
 * importing `@aetherius/react-native` registers the Continuum driver, and the mounted
 * `<AetheriusWebView />` publishes the host it will use.
 *
 * A module-level slot rather than a parameter on `RunOptions`, for a reason that is not laziness: a
 * WebView is a *mounted component*, and its lifetime belongs to the application's tree, not to a
 * run. The facade (`aetherius.ts`) hides this from an application, but the shape stays honest.
 *
 * There being a single view, there is a single Act II run at a time — the lease that enforces it
 * lives in `webview/lease.ts`, and is re-exported here because that is where a caller looks.
 */

import { registerDriver } from "@aetherius/engine";

import { ContinuumDriver, type HostProvider } from "./continuum/driver.js";
import type { WebViewHost } from "./webview/host.js";

let mounted: WebViewHost | undefined;

/** Publish the host a mounted `<AetheriusWebView />` drives. Pass `undefined` on unmount. */
export function setWebViewHost(host: WebViewHost | undefined): void {
  mounted = host;
}

/** The host a run will use, or `undefined` when no WebView is mounted. */
export function currentWebViewHost(): WebViewHost | undefined {
  return mounted;
}

export { acquireWebViewHost, releaseWebViewHost, webViewLease } from "./webview/lease.js";

/**
 * Register the Continuum driver with the engine.
 *
 * Called on import with the default provider (the mounted component). An application — or a test —
 * may call it again with a provider of its own; the engine's registry replaces the previous entry,
 * which is what lets the conformance corpus drive a jsdom-backed host.
 */
export function registerContinuum(provider: HostProvider = currentWebViewHost): void {
  registerDriver("continuum", () => new ContinuumDriver(provider));
}
