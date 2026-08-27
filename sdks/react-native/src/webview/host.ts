/**
 * The seam between the Continuum driver and a real WebView.
 *
 * Playwright does not exist on a device: there is no locator engine, no auto-waiting, and no
 * synchronous call into the page. The driver therefore talks to an injected agent through a
 * correlated RPC (`injectJavaScript` one way, `window.ReactNativeWebView.postMessage` the other).
 *
 * This interface is deliberately the only thing the driver knows of React Native. It keeps the
 * driver testable outside a simulator — the conformance corpus drives a jsdom-backed implementation
 * of exactly these methods — and keeps the package compilable without its peer dependencies.
 *
 * Structuring rule: an operation's parameters cross **encoded as JSON**, never interpolated into
 * the source of the injected script. `evaluate` is the single, documented exception, and it has its
 * own method here precisely so it cannot be mistaken for the general case.
 */

import type { OpName } from "./protocol.js";

/** What the Blueprint's `options` ask of the view. Changing any of it remounts the WebView. */
export interface SessionConfig {
  /**
   * `options.session.persist`. `false` gives an incognito view: an empty store at every run, and a
   * fresh authentication each time. `true` shares the platform's cookie store: no re-login, but the
   * state outlives the run and cannot be isolated from the rest of the application.
   */
  readonly persist: boolean;
  /**
   * `options.session.share_native_cookies`, **off by default**, and the default is the point.
   *
   * It bridges the platform's *native* cookie jar — the one URLSession fills, so the one Act I
   * writes to — into this WebView. Two WebViews already share their cookies without it: a
   * non-incognito `WKWebView` uses the process-wide default data store. So this is **only** useful
   * to a Blueprint that mixes Act I and Act II and needs one to see the other's session.
   *
   * It is off by default because it is **expensive, and grows with the application**. On iOS the
   * bridge copies *every* cookie the application holds — not those of the target URL, all of them —
   * one at a time, each a round trip, on the main queue. An application that has made many native
   * requests therefore freezes visibly when the view is created, and it gets worse the longer the
   * application has been used. It was previously tied to `persist`, which made persisting a session
   * cost a freeze nobody had asked for.
   */
  readonly shareNativeCookies: boolean;
  /** `options.debug`. Shows the WebView instead of parking it off-screen. */
  readonly debug: boolean;
  /** The user agent to serve. A portal often serves a different DOM to a mobile UA. */
  readonly userAgent: string | undefined;
}

export interface WebViewHost {
  /** Apply the Blueprint's session options, remounting the view when they changed. */
  configure(config: SessionConfig, timeoutMs: number): Promise<void>;

  /** Load *url* and resolve when the document is ready and the agent is installed. */
  navigate(url: string, timeoutMs: number): Promise<string>;

  /** Move through history, resolving on the new document. */
  goBack(timeoutMs: number): Promise<string>;
  goForward(timeoutMs: number): Promise<string>;
  reload(timeoutMs: number): Promise<string>;

  /** Send one operation to the injected agent and await its correlated answer. */
  call(op: OpName, params: Record<string, unknown>, timeoutMs: number): Promise<unknown>;

  /** Run a Blueprint-supplied script in the page; `arg` still crosses as JSON. */
  evaluate(script: string, arg: unknown, timeoutMs: number): Promise<unknown>;

  /**
   * Give the page a bounded window to *begin* a navigation after an action that may cause one.
   *
   * A click on a link returns long before the new document exists; without this the next operation
   * races the swap. Part of the seam because only the view knows a load has started.
   */
  settleAfterAction(timeoutMs: number): Promise<void>;

  /** The URL of the current document. */
  currentUrl(): string;

  /** Release the view (and, per `SessionConfig.persist`, its session). */
  dispose(): Promise<void>;
}

/**
 * The minimum a concrete view must offer for `BridgedHost` to drive it.
 *
 * Everything in `WebViewHost` is implemented once, on top of these calls: the real WebView
 * component and the jsdom double differ only here. That is what makes the conformance corpus
 * exercise the same navigation lifecycle the phone runs, rather than a simplified copy of it.
 */
export interface PageControl {
  /**
   * Start loading *url*. Completion is signalled back through `BridgedHost.onDocumentLoaded`.
   *
   * **Even when the view already carries that URL.** The host asks for a `load` rather than a
   * `reload` in exactly one case — the previous navigation failed, so there is no document to
   * reload — and an implementation that treats "same URL" as "nothing to do" would turn that retry
   * into a silent wait. Reusing a prop is not honouring this call.
   */
  load(url: string): void;
  goBack(): void;
  goForward(): void;
  reload(): void;
  /** Hand source to the current document. */
  inject(source: string): void;
  /** Apply session options; returns `true` when the view had to be recreated. */
  applySession(config: SessionConfig): boolean;
  /** Release the view. */
  destroy(): void;
}

export type { OpName };
