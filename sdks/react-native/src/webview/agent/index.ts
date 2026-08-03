/**
 * The injected agent's entry point: install, announce, obey.
 *
 * Assembled by `scripts/build-agent.mjs` into one IIFE and injected on every document. Three things
 * happen here and nowhere else:
 *
 *   - **installation is idempotent.** A load event can fire more than once per navigation (iframes,
 *     SPA loads, redirects), and the host re-injects on fragment navigations. Re-running the bundle
 *     for a generation already installed must not clobber the observers of an operation in flight —
 *     it re-announces readiness and stops there. The hand-written WebViews solve this with a
 *     `posted` latch inside every script; solving it once, here, is the point of having an agent.
 *   - **every answer carries its generation**, so the driver can drop what a dead document
 *     produced instead of handing it to the call that happens to be waiting.
 *   - **a large answer is split.** The bridge is not built to carry a whole document, and a wide
 *     extraction must be segmented by the protocol rather than truncated by chance.
 */

import {
  AGENT_GEN_GLOBAL,
  AGENT_GLOBAL,
  MAX_MESSAGE_CHARS,
  PROTOCOL_VERSION,
  type AgentRequest,
} from "../protocol.js";
import { describeError, OpError } from "./errors.js";
import { OPERATIONS } from "./ops.js";

interface Installed {
  readonly gen: number;
  handle(raw: string): void;
  announce(): void;
  /** Public so `evaluate`'s wrapper — the one script the driver builds itself — can answer. */
  reply(id: string, payload: Record<string, unknown>): void;
}

type Bridged = typeof globalThis & {
  ReactNativeWebView?: { postMessage(payload: string): void };
  [AGENT_GLOBAL]?: Installed;
  [AGENT_GEN_GLOBAL]?: number;
};

const scope = globalThis as Bridged;

function post(payload: unknown): void {
  const bridge = scope.ReactNativeWebView;
  // No bridge means nobody is listening — a page opened by hand in a browser, for instance. Doing
  // nothing is correct; throwing would break the page the agent is a guest on.
  if (bridge === undefined) return;
  bridge.postMessage(JSON.stringify(payload));
}

function install(): void {
  const gen = typeof scope[AGENT_GEN_GLOBAL] === "number" ? (scope[AGENT_GEN_GLOBAL] as number) : 0;
  const existing = scope[AGENT_GLOBAL];
  if (existing !== undefined && existing.gen === gen) {
    // Already ours, same document: say so again (the host may have missed the first `ready`) and
    // leave every in-flight observer alone.
    existing.announce();
    return;
  }

  const announce = (): void => {
    post({ aeth: PROTOCOL_VERSION, gen, ready: true, url: String(location.href) });
  };

  const reply = (id: string, payload: Record<string, unknown>): void => {
    const message = { aeth: PROTOCOL_VERSION, gen, id, ...payload };
    const serialised = JSON.stringify(message);
    if (serialised.length <= MAX_MESSAGE_CHARS) {
      post(message);
      return;
    }
    // Split the *answer*, not the envelope: each part is a slice of the serialised message the
    // driver reassembles and parses. Slicing a JSON document would need a streaming parser on the
    // other side for no gain.
    const total = Math.ceil(serialised.length / MAX_MESSAGE_CHARS);
    for (let seq = 0; seq < total; seq += 1) {
      post({
        aeth: PROTOCOL_VERSION,
        gen,
        id,
        seq,
        total,
        part: serialised.slice(seq * MAX_MESSAGE_CHARS, (seq + 1) * MAX_MESSAGE_CHARS),
      });
    }
  };

  const handle = (raw: string): void => {
    let request: AgentRequest;
    try {
      request = JSON.parse(raw) as AgentRequest;
    } catch {
      return; // not an order we can answer, and we have no id to answer it with
    }

    const operation = OPERATIONS[request.op];
    if (operation === undefined) {
      reply(request.id, {
        ok: false,
        error: describeError(new OpError(`unknown operation ${JSON.stringify(request.op)}`)),
      });
      return;
    }

    const params = (request.params ?? {}) as Record<string, unknown>;
    Promise.resolve()
      .then(() => operation(params, request.timeoutMs))
      .then((value) => {
        reply(request.id, { ok: true, value });
      })
      .catch((error: unknown) => {
        reply(request.id, { ok: false, error: describeError(error) });
      });
  };

  scope[AGENT_GLOBAL] = { gen, handle, announce, reply };
  announce();
}

install();
