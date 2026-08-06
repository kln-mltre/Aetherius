/**
 * Act II — Continuum on a WebView, mirror of `acts/continuum/driver.py`.
 *
 * The driver follows the Blueprint literally, exactly as its Python twin does, but through a
 * WebView instead of Playwright: navigation is the host's business, everything else is an operation
 * sent to the injected agent, and the act-agnostic actions come from the engine's shared handlers —
 * one implementation, not a copy.
 *
 * Two divergences from the Python engine are deliberate, and both are declared in docs/embedded.md:
 *
 *   - **`navigate` publishes no `status`.** A WebView exposes no HTTP status for its main document.
 *     Returning `null` would let `{{ steps.nav.status }}` render a wrong value in silence; omitting
 *     the key makes reading it raise, at the step that reads it, naming the variable.
 *   - **new windows are refused, not followed.** In a hidden WebView, opening a window has no
 *     meaning; keeping navigation inside the same view is the correct behaviour and is explicit.
 */

import {
  ActionError,
  DependencyError,
  StepTimeoutError,
  raceCancel,
  sharedAction,
  type ActDriver,
  type EventBus,
  type Renderer,
  type RunContext,
  type StepModel,
} from "@aetherius/engine";

import { acquireWebViewHost, releaseWebViewHost } from "../webview/lease.js";
import { MAY_NAVIGATE, type OpName } from "../webview/protocol.js";
import type { SessionConfig, WebViewHost } from "../webview/host.js";
import { NoAnswerError } from "../webview/rpc.js";
import { AGENT_ACTIONS, failureCode } from "./actions.js";

/** Playwright's context default, and therefore this engine's: `options.timeout_ms or 30_000`. */
const DEFAULT_TIMEOUT_MS = 30_000;

/** How a run gets hold of a live WebView. Supplied by the application (or by a test double). */
export type HostProvider = () => WebViewHost | undefined;

export class ContinuumDriver implements ActDriver {
  readonly act = "continuum";

  private host: WebViewHost | undefined;
  private timeoutMs = DEFAULT_TIMEOUT_MS;
  private leased: string | undefined;

  constructor(private readonly provider: HostProvider) {}

  async setup(ctx: RunContext): Promise<void> {
    const options = ctx.blueprint.options ?? {};
    // `|| DEFAULT` rather than `??`: Python reads `opts.timeout_ms or 30_000`, so a zero means
    // "unset" there too.
    this.timeoutMs = Number(options.timeout_ms) || DEFAULT_TIMEOUT_MS;

    const host = this.provider();
    if (host === undefined) {
      throw new DependencyError(
        "Act II (Continuum) needs a WebView. Mount <AetheriusWebView /> from " +
          "'@aetherius/react-native' in the application tree, or register a host with " +
          "registerContinuum(provider), before running a 'continuum' Blueprint.",
      );
    }
    // Before configuring, not after: a refused second run must leave the first one's view exactly
    // as it found it.
    acquireWebViewHost(ctx.runId);
    this.leased = ctx.runId;
    this.host = host;
    await host.configure(sessionConfig(ctx), this.timeoutMs);
  }

  async teardown(): Promise<void> {
    const host = this.host;
    const leased = this.leased;
    this.host = undefined;
    this.leased = undefined;
    try {
      if (host !== undefined) await host.dispose();
    } finally {
      // Even if disposing threw: holding the lease after a failed teardown would lock Act II out
      // for the rest of the process, which is worse than the failure that caused it.
      if (leased !== undefined) releaseWebViewHost(leased);
    }
  }

  async runStep(
    step: StepModel,
    ctx: RunContext,
    bus: EventBus,
    render: Renderer,
  ): Promise<Record<string, unknown>> {
    const host = this.host;
    if (host === undefined) throw new ActionError("ContinuumDriver.runStep called before setup().");
    const timeoutMs = this.stepTimeout(step, render);
    // Every call to the view races the run's cancellation. A WebView cannot recall a message it has
    // already been sent, so the answer is *abandoned* rather than interrupted — and the teardown
    // that follows releases the view. Politely waiting out a thirty-second auto-wait would make
    // leaving a screen take thirty seconds.
    const call = <T>(pending: Promise<T>): Promise<T> => raceCancel(pending, ctx.signal);

    switch (step.action) {
      case "navigate": {
        const url = String(render(step["url"] ?? ""));
        if (url === "") throw new ActionError("navigate requires a 'url'.");
        // `wait_until` is read and ignored: a WebView signals one load event, and pretending to
        // honour four load states would be a promise this engine cannot keep.
        return { url: await call(host.navigate(url, timeoutMs)) };
      }
      case "back":
        return { url: await call(host.goBack(timeoutMs)) };
      case "forward":
        return { url: await call(host.goForward(timeoutMs)) };
      case "reload":
        return { url: await call(host.reload(timeoutMs)) };
      case "evaluate": {
        const script = String(render(step["script"] ?? step["expression"] ?? ""));
        if (script === "") throw new ActionError("evaluate requires a 'script' or 'expression'.");
        const arg = Object.prototype.hasOwnProperty.call(step, "arg")
          ? render(step["arg"])
          : undefined;
        return { result: await call(host.evaluate(script, arg, timeoutMs)) };
      }
      default:
        break;
    }

    const builder = AGENT_ACTIONS[step.action];
    if (builder !== undefined) {
      const { op, params } = builder(step, render);
      let value: unknown;
      try {
        value = await call(host.call(op, params, timeoutMs));
      } catch (error) {
        throw this.nameTheSilence(error, step, params, timeoutMs, render);
      }
      await this.settle(host, op, timeoutMs);
      return isRecord(value) ? value : {};
    }

    const shared = sharedAction(step.action);
    if (shared !== undefined) return shared(step, ctx, bus, render);

    // No plugin registry on this engine (docs/embedded.md): an unknown action is unknown, and the
    // validator has already refused every action the capability table does not carry.
    throw new ActionError(`ContinuumDriver: unsupported action '${step.action}'`);
  }

  /**
   * A page that never answered is a wait that expired — say so with the name the Blueprint chose.
   *
   * The caller is the only dependable clock: iOS throttles, and can suspend, timers inside a
   * WKWebView that is not on screen, and this engine deliberately keeps it off screen. So the
   * agent's own deadline is best-effort, and a `wait_for` on a page that never shows what it waits
   * for can come back as *silence* rather than as the agent's own named timeout.
   *
   * Reporting that silence as an `ActionError` sent a failed login to the "this is an engine bug"
   * screen, when the Blueprint had already said what to call it (`on_timeout: "fail:LOGIN_FAILED"`).
   * Found on a real device — a jsdom double answers instantly and never produces the case.
   *
   * Only silence is renamed. An error the agent *did* send back keeps its own class and message.
   */
  private nameTheSilence(
    error: unknown,
    step: StepModel,
    params: Record<string, unknown>,
    timeoutMs: number,
    render: Renderer,
  ): unknown {
    if (!(error instanceof NoAnswerError)) return error;
    const code =
      step.action === "wait_for"
        ? ((params["fail_code"] as string | undefined) ?? failureCode(render(step["on_timeout"])))
        : undefined;
    // Name what the step was looking at. Without it, an `extract` with five outputs reports a
    // deadline and nothing else, and the only way to learn which selector was involved is to edit
    // the Blueprint and run again — which is exactly what the reference port had to do.
    const targets = describeTargets(step.action, params);
    return new StepTimeoutError(
      `${step.action} timed out after ${timeoutMs} ms${targets}: the page never reported back ` +
        "(an off-screen WebView throttles its own timers, so the deadline is the caller's)",
      code,
    );
  }

  /**
   * Let a page that was about to navigate get on with it.
   *
   * Only meaningful for the operations that can trigger one. The host owns the bounded window; the
   * driver only says when to open it.
   */
  private async settle(host: WebViewHost, op: OpName, timeoutMs: number): Promise<void> {
    if (MAY_NAVIGATE.indexOf(op) === -1) return;
    await host.settleAfterAction(timeoutMs);
  }

  /** A step's own `timeout_ms` wins over the Blueprint's, exactly as `wait_for` does in Python. */
  private stepTimeout(step: StepModel, render: Renderer): number {
    const raw = step["timeout_ms"];
    if (raw === undefined || raw === null) return this.timeoutMs;
    const value = Number(render(raw));
    return Number.isFinite(value) && value > 0 ? value : this.timeoutMs;
  }
}

function sessionConfig(ctx: RunContext): SessionConfig {
  const options = ctx.blueprint.options ?? {};
  const session = options.session;
  const stealth = options.stealth;
  return {
    persist: session?.persist === true,
    debug: options.debug === true,
    // The only piece of stealth inside the phase's scope (decision 8): a portal often serves a
    // different DOM to a mobile user agent, and a Blueprint must be able to decide.
    userAgent: typeof stealth === "object" && stealth !== null && "user_agent" in stealth
      ? String((stealth as Record<string, unknown>)["user_agent"])
      : undefined,
  };
}

/**
 * The selectors an op was working on, as a suffix for a failure message (empty when there are none).
 *
 * `extract` carries its selectors inside `outputs`, one per named value; every other op carries a
 * single `selector`. A silence that names neither leaves the author with a deadline and no lead.
 */
function describeTargets(action: string, params: Record<string, unknown>): string {
  const selectors: string[] = [];
  if (action === "extract") {
    const outputs = params["outputs"];
    if (isRecord(outputs)) {
      for (const spec of Object.values(outputs)) {
        if (!isRecord(spec)) continue;
        const one = spec["selector"] ?? spec["each"];
        if (typeof one === "string" && one !== "" && selectors.indexOf(one) === -1) {
          selectors.push(one);
        }
      }
    }
  } else if (typeof params["selector"] === "string" && params["selector"] !== "") {
    selectors.push(params["selector"] as string);
  }
  if (selectors.length === 0) return "";
  return ` on ${selectors.map((selector) => JSON.stringify(selector)).join(", ")}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
