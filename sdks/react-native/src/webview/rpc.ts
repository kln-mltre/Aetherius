/**
 * Correlated RPC over the WebView bridge.
 *
 * `injectJavaScript` returns nothing — the only channel out of the page is `postMessage`. So every
 * operation is an asynchronous round trip, and something has to match answers to calls. Doing
 * without (the hand-written way: one script type, emitted at most once per session, matched by its
 * message type) works right up to the moment two reads are in flight or a page navigates mid-call.
 *
 * This bridge owns four things, and each exists because of a failure seen in the wild:
 *
 *   - **correlation by id**, so two concurrent calls cannot swap answers;
 *   - **a deadline per call**, so a page that never answers fails at a known time instead of
 *     hanging the run;
 *   - **reassembly of split messages**, so a wide extraction is segmented by the protocol rather
 *     than truncated by the bridge;
 *   - **generation invalidation**, so an answer produced by a document that has since been
 *     replaced is *dropped*, never handed to the call that happens to be waiting.
 *
 * The bridge knows nothing about React Native: it is fed raw message strings and hands back source
 * to inject. That is what makes it testable without a simulator.
 */

import { ActionError, ExtractionError, StepTimeoutError } from "@aetherius/engine";

import { startTimer, stopTimer, type TimerHandle } from "../timers.js";

import {
  dispatchSource,
  isAgentMessage,
  isChunk,
  isReady,
  MAY_NAVIGATE,
  PROTOCOL_VERSION,
  type AgentChunk,
  type AgentReady,
  type AgentResult,
  type OpName,
} from "./protocol.js";

/** How the bridge hands source to the page. Satisfied by `WebView.injectJavaScript`. */
export type Inject = (source: string) => void;

interface Pending {
  readonly gen: number;
  readonly resolve: (value: unknown) => void;
  readonly reject: (error: unknown) => void;
  readonly timer: TimerHandle;
  /**
   * Whether a navigation starting under this call is its *expected* outcome.
   *
   * A click on a link or a submit is complete the moment the page starts loading — the answer is
   * lost with the document, and that is success, not failure. For everything else (a read, a wait)
   * the lost answer really is a failure, and saying so is more useful than a silent empty result.
   */
  readonly navigable: boolean;
}

interface Assembly {
  readonly total: number;
  readonly parts: (string | undefined)[];
  received: number;
}

interface ReadyWaiter {
  readonly resolve: (ready: AgentReady) => void;
  readonly reject: (error: unknown) => void;
  readonly timer: TimerHandle;
}

/**
 * Rebuild the typed error the agent reported, so a `fail:CODE` — and the *kind* of failure —
 * survive the bridge.
 *
 * `ExtractionError` matters as much as the code: it is what tells an application that the **page**
 * did not match the Blueprint, rather than that the engine has a bug. Collapsing everything into
 * `ActionError` would send every stale selector to the "report this" screen (see failure.ts).
 */
function rebuild(error: { name: string; message: string; code?: string }): Error {
  if (error.name === "StepTimeoutError") return new StepTimeoutError(error.message, error.code);
  if (error.name === "ExtractionError") return new ExtractionError(error.message);
  return new ActionError(error.message);
}

/**
 * The document was replaced while an operation was in flight.
 *
 * A distinct class, not a message to match: the caller **can** recover from this one — the page it
 * was talking to is gone, but another has taken its place, and the operation deserves to be tried
 * on it. Every other failure means what it says. See `BridgedHost.throughNavigations`.
 */
export class DocumentLostError extends ActionError {}

/**
 * The page never answered, and its own deadline never came back either.
 *
 * A distinct class because the caller is the **only dependable clock**. iOS throttles — and can
 * suspend — timers in a WKWebView that is not on screen, which is exactly how this engine runs one:
 * off-screen by default. The agent's `setTimeout` deadline is therefore best-effort, and a silence
 * past the caller's own deadline usually means the wait it was told to perform simply expired.
 *
 * The driver turns this into the failure the Blueprint *named* (`on_timeout: "fail:CODE"`), which
 * is the whole point: a login that fails must say `LOGIN_FAILED`, not "the engine has a bug".
 */
export class NoAnswerError extends ActionError {}

export class AgentBridge {
  private readonly pending = new Map<string, Pending>();
  private readonly assemblies = new Map<string, Assembly>();
  private readyWaiters: ReadyWaiter[] = [];

  /** Increments on every fresh document. 0 means "no agent has ever announced itself". */
  private generation = 0;
  private present = false;
  private url = "";
  private nextId = 0;

  constructor(private readonly inject: Inject) {}

  /** The URL the agent last announced. The host may know better; this is what the *page* said. */
  get currentUrl(): string {
    return this.url;
  }

  /** Whether an agent is installed on the current document. */
  get agentPresent(): boolean {
    return this.present;
  }

  /**
   * A message came up from the page.
   *
   * Anything that is not ours is ignored in silence: a page is free to postMessage for its own
   * reasons, and a scraper that crashed on someone else's telemetry would be a poor guest.
   */
  receive(raw: string): void {
    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return;
    }
    if (!isAgentMessage(parsed)) return;

    if (isReady(parsed)) {
      this.onReady(parsed);
      return;
    }
    if (isChunk(parsed)) {
      this.onChunk(parsed);
      return;
    }
    this.settle(parsed);
  }

  /**
   * A navigation started: the current document is going away.
   *
   * Every call in flight is settled now rather than left to its deadline — a timeout would send the
   * reader looking for a slow page instead of a navigation. Which way it settles depends on whether
   * the call was the *cause*: see `Pending.navigable`.
   */
  invalidate(reason: string, cause?: Error): void {
    this.present = false;
    this.assemblies.clear();
    // *cause* lets the caller name what happened when it knows better than "the document went
    // away" — a load that failed outright is a network problem, not a navigation.
    const error = cause ?? new DocumentLostError(`the operation lost its document (${reason})`);
    for (const id of [...this.pending.keys()]) {
      const pending = this.pending.get(id);
      if (pending === undefined) continue;
      this.pending.delete(id);
      stopTimer(pending.timer);
      // A click that caused the navigation has done its job; a read that lost its page has not.
      if (pending.navigable) pending.resolve({});
      else pending.reject(error);
    }
  }

  /** Resolve once an agent is installed on the current document. */
  waitForReady(timeoutMs: number): Promise<AgentReady> {
    if (this.present) {
      return Promise.resolve({
        aeth: PROTOCOL_VERSION,
        gen: this.generation,
        ready: true,
        url: this.url,
      });
    }
    return new Promise<AgentReady>((resolve, reject) => {
      const timer = startTimer(() => {
        this.readyWaiters = this.readyWaiters.filter((waiter) => waiter.timer !== timer);
        reject(
          new ActionError(
            `the page did not become ready within ${timeoutMs} ms ` +
              "(no agent announced itself: the document may have failed to load)",
          ),
        );
      }, timeoutMs);
      this.readyWaiters.push({ resolve, reject, timer });
    });
  }

  /**
   * Send one operation and await its answer.
   *
   * The deadline is applied on both sides: the agent gives up on its own (it can say *what* it was
   * waiting for), and the caller gives up slightly later in case the page never answers at all.
   */
  call(op: OpName, params: Record<string, unknown>, timeoutMs: number): Promise<unknown> {
    return this.callRaw(
      `operation '${op}'`,
      (id) => dispatchSource({ aeth: PROTOCOL_VERSION, id, op, params, timeoutMs }),
      timeoutMs,
      MAY_NAVIGATE.indexOf(op) !== -1,
    );
  }

  /**
   * Correlate an answer to source the caller builds itself.
   *
   * The seam `evaluate` needs, and the only place it can exist: a Blueprint's `script` *is* code by
   * contract, so it cannot cross as a JSON parameter like everything else. Keeping that on its own
   * entry point is what makes the exception visible instead of quietly generalised.
   */
  callRaw(
    label: string,
    makeSource: (id: string) => string,
    timeoutMs: number,
    navigable = false,
  ): Promise<unknown> {
    if (!this.present) {
      // `DocumentLostError`, because from the host's point of view this is the same event as an
      // answer lost to a navigation — only seen a moment earlier. The window is narrow but real: a
      // load can start between the host's readiness check and this dispatch, and treating the two
      // differently would make a redirect fail or succeed depending on timing.
      return Promise.reject(
        new DocumentLostError(`no agent is installed on the current document (${label})`),
      );
    }

    const id = `c${(this.nextId += 1)}`;
    const gen = this.generation;

    return new Promise<unknown>((resolve, reject) => {
      const timer = startTimer(() => {
        this.pending.delete(id);
        this.assemblies.delete(id);
        reject(new NoAnswerError(`${label} did not answer within ${timeoutMs} ms`));
      }, timeoutMs + CALLER_GRACE_MS);

      this.pending.set(id, { gen, resolve, reject, timer, navigable });
      try {
        this.inject(makeSource(id));
      } catch (error) {
        stopTimer(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  private onReady(message: AgentReady): void {
    // A `ready` from a document we have already left is a straggler; the newest generation wins.
    if (message.gen < this.generation) return;
    this.generation = message.gen;
    this.present = true;
    this.url = message.url;

    const waiters = this.readyWaiters;
    this.readyWaiters = [];
    for (const waiter of waiters) {
      stopTimer(waiter.timer);
      waiter.resolve(message);
    }
  }

  private onChunk(chunk: AgentChunk): void {
    if (!this.isCurrent(chunk.id, chunk.gen)) return;

    let assembly = this.assemblies.get(chunk.id);
    if (assembly === undefined) {
      assembly = { total: chunk.total, parts: new Array<string | undefined>(chunk.total), received: 0 };
      this.assemblies.set(chunk.id, assembly);
    }
    if (assembly.parts[chunk.seq] !== undefined) return; // a duplicate part changes nothing
    assembly.parts[chunk.seq] = chunk.part;
    assembly.received += 1;
    if (assembly.received < assembly.total) return;

    this.assemblies.delete(chunk.id);
    const joined = assembly.parts.join("");
    let payload: unknown;
    try {
      payload = JSON.parse(joined);
    } catch {
      this.reject(chunk.id, new ActionError("the split answer did not reassemble into valid JSON"));
      return;
    }
    this.settle(payload as AgentResult);
  }

  private settle(result: AgentResult): void {
    if (!this.isCurrent(result.id, result.gen)) return;
    const pending = this.pending.get(result.id);
    if (pending === undefined) return;

    this.pending.delete(result.id);
    stopTimer(pending.timer);
    if (result.ok) pending.resolve(result.value);
    else pending.reject(rebuild(result.error ?? { name: "ActionError", message: "unknown failure" }));
  }

  /** An answer belongs to the call only when it comes from the document the call was sent to. */
  private isCurrent(id: string, gen: number): boolean {
    const pending = this.pending.get(id);
    return pending !== undefined && pending.gen === gen;
  }

  private reject(id: string, error: unknown): void {
    const pending = this.pending.get(id);
    if (pending === undefined) return;
    this.pending.delete(id);
    stopTimer(pending.timer);
    pending.reject(error);
  }
}

/**
 * How long the caller waits *past* the agent's own deadline before declaring silence.
 *
 * The agent answers its own timeout with a message naming what it was waiting for, which is far
 * more useful than "no answer". This grace exists only for the case where nothing comes back at
 * all — a crashed renderer, a bridge that dropped the message.
 */
const CALLER_GRACE_MS = 2000;
