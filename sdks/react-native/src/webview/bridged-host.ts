/**
 * The navigation lifecycle, written once.
 *
 * This is where milestone 3-D's stated major trap lives: every navigation destroys the page
 * context, the agent must be reinstalled, and any operation in flight has to be resolved or
 * cancelled cleanly. Deducing "the page is ready" from a load event alone produces races nobody can
 * reproduce — so readiness here means one thing only: **the agent announced itself on the current
 * generation**.
 *
 * `BridgedHost` implements the whole `WebViewHost` contract on top of the five calls of
 * `PageControl`. The real React Native component and the jsdom test double supply those five calls
 * and nothing more, which is what lets the conformance corpus exercise this logic rather than a
 * simplified copy of it.
 */

import { ActionError, NetworkError, StepTimeoutError } from "@aetherius/engine";

import { sleep } from "../timers.js";
import type { PageControl, SessionConfig, WebViewHost } from "./host.js";
import { evaluateSource } from "./evaluate.js";
import { installSource, type OpName } from "./protocol.js";
import { AgentBridge, DocumentLostError } from "./rpc.js";

/**
 * How long an action that may navigate is given to *start* a navigation before the document is
 * treated as settled.
 *
 * A click on a link or a submit returns long before the new document exists. Without this window
 * the next operation races the swap and fails against a page that is already dead. It is short on
 * purpose: it bounds a decision, not a page load — waiting for the load itself is the next
 * operation's auto-waiting job.
 */
const NAVIGATION_SETTLE_MS = 250;

export class BridgedHost implements WebViewHost {
  private readonly bridge: AgentBridge;
  private generation = 0;
  private loading = false;
  private url = "";
  private disposed = false;
  /** The last load failure the view reported, cleared as soon as a document does load. */
  private loadError: string | undefined;
  /** `options.session.persist` of the run in progress: it decides whether `dispose` keeps the view. */
  private persistent = false;

  constructor(
    private readonly page: PageControl,
    private readonly agentSource: string,
  ) {
    this.bridge = new AgentBridge((source) => {
      this.page.inject(source);
    });
  }

  // -- signals the concrete view pushes in -------------------------------------------------

  /** A document started loading: the current context is gone. */
  onLoadStarted(url: string): void {
    this.loading = true;
    this.url = url;
    // A new attempt clears the previous verdict: a retry after a lost connection must be able to
    // succeed rather than inherit the failure that preceded it.
    this.loadError = undefined;
    this.bridge.invalidate("a new document started loading");
  }

  /**
   * A document finished loading: install the agent, stamped with a fresh generation.
   *
   * Installation happens here rather than through the `injectedJavaScript` prop because the
   * generation is a number the *host* owns — a fresh document remembers nothing, so it cannot count
   * its own. It is also the only value ever interpolated into the install source, and it can never
   * be Blueprint data.
   */
  onDocumentLoaded(url: string): void {
    this.loading = false;
    this.loadError = undefined;
    this.url = url;
    this.generation += 1;
    this.page.inject(installSource(this.agentSource, this.generation));
  }

  /**
   * The same document is still there but may have lost its agent (a fragment navigation, a
   * single-page route change). Re-injecting is idempotent for a generation already installed.
   */
  ensureAgent(): void {
    this.page.inject(installSource(this.agentSource, this.generation));
  }

  /**
   * iOS terminated the web content process (memory pressure, or a view with no rendered area).
   *
   * The document is gone and will not come back on its own. Failing the calls in flight now says
   * what happened; leaving them to their deadline would report a slow page.
   */
  onContentProcessLost(): void {
    this.loading = false;
    this.bridge.invalidate("the WebView's content process was terminated by the system");
  }

  /**
   * The view could not load the document at all: no network, DNS failure, TLS refusal.
   *
   * Without this signal the run only learns that no agent ever announced itself, and reports it as
   * an engine problem — which puts "internal error" on screen when the phone is simply offline.
   * The view *knows*, so it says so, and the failure carries `NetworkError`: `describeFailure`
   * turns that into `unavailable`, the one family an application retries. It is the Act II twin of
   * a `fetch` that never connects.
   */
  onLoadFailed(description: string): void {
    this.loading = false;
    this.loadError = description;
    this.bridge.invalidate(description, new NetworkError(`the WebView could not load: ${description}`));
  }

  /** A message came up from the page. */
  onMessage(raw: string): void {
    this.bridge.receive(raw);
  }

  // -- WebViewHost -------------------------------------------------------------------------

  async configure(config: SessionConfig, _timeoutMs: number): Promise<void> {
    // A host outlives the runs it serves — it belongs to the mounted component. `dispose` releases
    // the *view*, it does not retire the host, so a second run revives it here. Getting this wrong
    // is invisible on the first run and fatal on the second.
    this.disposed = false;
    this.persistent = config.persist;
    // Session options (incognito, shared cookies, user agent) are bound when the view is created on
    // both platforms: changing them means recreating it, not setting a property.
    if (!this.page.applySession(config)) return;
    // Nothing is awaited here on purpose: the recreated view has no document worth waiting for, and
    // the first `navigate` does the waiting anyway. Waiting on a blank page would make the run
    // depend on whether the platform reports a load event for one.
    //
    // The generation counter is *not* reset: it must stay monotonic across remounts, or a `ready`
    // from the new view would look like a straggler from the old one and be dropped.
    this.bridge.invalidate("the session configuration changed");
    this.url = "";
    return Promise.resolve();
  }

  async navigate(url: string, timeoutMs: number): Promise<string> {
    this.assertLive();
    // Handing the same URL back to the view is not guaranteed to reload it — nothing changed, so
    // nothing loads and the run waits for a document that will never be announced. Asking for a
    // reload is.
    //
    // The test is `this.url` alone, deliberately: a kept view (a persistent session between two
    // runs) still *shows* its last document while the agent has been invalidated, and requiring the
    // agent to be present there made the second run hang until its deadline. `this.url` is empty
    // whenever the view was released or recreated, so it says exactly what it must: is this view
    // already on that page?
    if (url === this.url) this.page.reload();
    else this.page.load(url);
    return this.awaitNavigation(timeoutMs);
  }

  goBack(timeoutMs: number): Promise<string> {
    this.assertLive();
    this.page.goBack();
    return this.awaitNavigation(timeoutMs);
  }

  goForward(timeoutMs: number): Promise<string> {
    this.assertLive();
    this.page.goForward();
    return this.awaitNavigation(timeoutMs);
  }

  reload(timeoutMs: number): Promise<string> {
    this.assertLive();
    this.page.reload();
    return this.awaitNavigation(timeoutMs);
  }

  async call(op: OpName, params: Record<string, unknown>, timeoutMs: number): Promise<unknown> {
    this.assertLive();
    return this.throughNavigations(timeoutMs, (remaining) => this.bridge.call(op, params, remaining));
  }

  async evaluate(script: string, arg: unknown, timeoutMs: number): Promise<unknown> {
    this.assertLive();
    return this.throughNavigations(timeoutMs, (remaining) =>
      this.bridge.callRaw("evaluate", (id) => evaluateSource(id, script, arg), remaining),
    );
  }

  currentUrl(): string {
    return this.bridge.agentPresent ? this.bridge.currentUrl : this.url;
  }

  /**
   * Release the view and its session. The host stays usable: the next `configure` revives it.
   *
   * Called by the driver at teardown *and* by the component when it unmounts, hence the guard.
   */
  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.loading = false;
    this.bridge.invalidate("the run ended");

    // **A persistent session keeps its view.** Destroying it recreates a WKWebView on the next run,
    // and a *session* cookie — one without `Expires`, which is what a login usually sets — does not
    // reliably cross that boundary: it lives with the browsing context, not on disk. Keeping the
    // view is therefore what `options.session.persist` actually has to mean on a device; releasing
    // it would make the option promise something the platform never delivers.
    //
    // The cost is explicit: a hidden WebView stays alive until the session options change or the
    // component unmounts. That is the trade `persist: true` asks for, and `persist: false` — the
    // default — still releases everything at the end of every run.
    if (this.persistent) return;

    this.url = "";
    this.page.destroy();
  }

  /**
   * Give the page a bounded window to *begin* a navigation after an action that may cause one.
   *
   * Called by the driver after `click`, `press` and `select`. If a load starts, we wait for the new
   * document; if none does, we move on immediately.
   */
  async settleAfterAction(timeoutMs: number): Promise<void> {
    const started = Date.now();
    while (!this.loading && Date.now() - started < NAVIGATION_SETTLE_MS) {
      await sleep(20);
    }
    if (this.loading) await this.awaitReady(timeoutMs);
  }

  // -- internals ---------------------------------------------------------------------------

  private assertLive(): void {
    if (this.disposed) {
      throw new ActionError(
        "the WebView has been released: a run must call configure() before driving the page.",
      );
    }
  }

  private async awaitNavigation(timeoutMs: number): Promise<string> {
    const before = this.generation;
    // A navigation is over when a *new* generation announces itself; the current one, still ready
    // from the previous document, must not be mistaken for the answer.
    await this.awaitGenerationAfter(before, timeoutMs);
    return this.currentUrl();
  }

  private async awaitGenerationAfter(previous: number, timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (this.generation > previous && this.bridge.agentPresent) return;
      // Reported by the view rather than deduced from silence: waiting out the deadline to then
      // blame the engine would be the wrong answer, slowly.
      if (this.loadError !== undefined) throw this.networkFailure();
      await sleep(10);
    }
    if (this.loadError !== undefined) throw this.networkFailure();
    throw new ActionError(
      `the page did not finish loading within ${timeoutMs} ms ` +
        "(no new document announced itself)",
    );
  }

  private networkFailure(): NetworkError {
    return new NetworkError(`the WebView could not load the document: ${this.loadError}`);
  }

  /**
   * Run an operation, re-issuing it on the new document when a navigation replaces the old one.
   *
   * A login is the case that makes this mandatory, and it is the one a test double cannot show: a
   * form POST answers **302**, so the view loads twice. Between the two, an operation in flight
   * loses its document — and failing there means no Blueprint can wait for anything after a login,
   * which is most of what Act II exists to do. Playwright survives a redirect chain; so must this.
   *
   * The retry is bounded by the step's own deadline, so a page that navigates forever fails on
   * time rather than looping. Only `DocumentLostError` is retried: every other failure means what
   * it says, and repeating a stale selector would just waste the budget.
   *
   * The operations that *cause* a navigation (`click`, `press`, `select`) never come through here
   * as failures — they resolve on it, because that is their result.
   */
  private async throughNavigations<T>(
    timeoutMs: number,
    attempt: (remainingMs: number) => Promise<T>,
  ): Promise<T> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      const remaining = Math.max(0, deadline - Date.now());
      await this.awaitReady(remaining);
      try {
        return await attempt(Math.max(0, deadline - Date.now()));
      } catch (error) {
        if (!(error instanceof DocumentLostError)) throw error;
        if (Date.now() >= deadline) {
          // Giving up on a page that kept navigating is not an engine problem: the page is not the
          // one the Blueprint describes. `StepTimeoutError` without a code says exactly that, and
          // `describeFailure` puts it where a stale selector goes rather than on "report this bug".
          throw new StepTimeoutError(
            `the page kept navigating and the operation never completed within ${timeoutMs} ms ` +
              `(last: ${error.message})`,
          );
        }
      }
    }
  }

  private async awaitReady(timeoutMs: number): Promise<void> {
    if (this.bridge.agentPresent) return;
    // The same rule as `awaitGenerationAfter`: when the view has already said the load failed, say
    // so now instead of waiting out a deadline and blaming the engine.
    if (this.loadError !== undefined) throw this.networkFailure();
    await this.bridge.waitForReady(timeoutMs);
  }
}

/** Exported so a test can assert the settle window is bounded rather than guessed. */
export { NAVIGATION_SETTLE_MS };
