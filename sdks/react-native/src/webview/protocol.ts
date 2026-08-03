/**
 * The wire contract between the driver and the injected agent.
 *
 * This file is the real deliverable of milestone 3-D. What replaces a hand-written hidden WebView
 * is not "JavaScript we inject" but a *protocol*: a closed vocabulary of operations, parameters
 * encoded as JSON, answers correlated by id, deadlines owned by the caller.
 *
 * Two rules hold the whole thing up, and neither is negotiable:
 *
 *   1. **No parameter is ever interpolated into the source of a script.** Parameters cross as JSON,
 *      parsed by the agent. This is what makes impossible-by-construction the commonest bug of
 *      hand-written WebViews — a password containing an apostrophe that breaks the script, or
 *      worse. `evaluate` is the single, documented exception: its `script` *is* code by contract
 *      (its `arg` still crosses as JSON).
 *   2. **Every answer carries the generation of the document it came from.** A navigation destroys
 *      the page context; an answer that arrives afterwards belongs to nobody and must be dropped,
 *      never handed to the call that happens to be waiting. Deriving that from a load event alone
 *      produces races nobody can reproduce.
 *
 * Shared by both sides on purpose: the agent is bundled from these very sources (build-agent.mjs),
 * so a change to the envelope cannot reach one side without the other.
 */

/** Envelope version. Bumped only if the shape below stops being backward compatible. */
export const PROTOCOL_VERSION = 1;

/** The global the agent installs in the page. Its presence is what "agent present" means. */
export const AGENT_GLOBAL = "__aetherius";

/**
 * The global carrying the generation the host assigned to this document.
 *
 * A fresh document remembers nothing, so the agent cannot count generations by itself. The host
 * can: it sees every load. The number is therefore written into the install source — and it is the
 * only value ever interpolated there, an integer the host generates. No Blueprint data goes near
 * it, which is what keeps rule 1 of this file intact.
 */
export const AGENT_GEN_GLOBAL = "__aetheriusGen";

/**
 * Above this many characters a serialised answer is split into parts.
 *
 * The bridge between the page and the application is not built to carry a whole document: a wide
 * extraction has to be segmented by the protocol rather than left to chance. 64 KiB is comfortably
 * under what both platforms handle in one message, and small enough that a truncation would show
 * up in tests rather than on someone's phone.
 */
export const MAX_MESSAGE_CHARS = 65536;

/**
 * The closed vocabulary. A driver may not invent an operation; the agent rejects what it lacks.
 *
 * Navigation is deliberately absent: `navigate`, `back`, `forward` and `reload` are driven by the
 * *host*, which owns the view. Letting the agent set `window.location` — the way hand-written
 * WebViews do it — puts two authorities on the same state, and the loser is whichever one is
 * reading when the document is swapped underneath it.
 */
export const OPS = [
  "click",
  "fill",
  "type",
  "press",
  "select",
  "hover",
  "scroll",
  "wait_for",
  "extract",
] as const;

export type OpName = (typeof OPS)[number];

/**
 * Operations that may kick off a navigation, and after which the caller gives the page a short,
 * bounded window to *start* loading before it treats the document as settled.
 *
 * A click on a link or a submit returns long before the new document exists. Without this the next
 * operation would race the swap and fail against a page that is already dead.
 */
export const MAY_NAVIGATE: readonly OpName[] = ["click", "press", "select"];

/** An order sent to the agent. `params` is data, always — never source. */
export interface AgentRequest {
  readonly aeth: typeof PROTOCOL_VERSION;
  readonly id: string;
  readonly op: OpName;
  readonly params: Readonly<Record<string, unknown>>;
  /** Milliseconds the agent may spend before giving up. The caller owns the deadline too. */
  readonly timeoutMs: number;
}

/** The agent announcing itself on a fresh document. */
export interface AgentReady {
  readonly aeth: typeof PROTOCOL_VERSION;
  readonly gen: number;
  readonly ready: true;
  readonly url: string;
}

/** A whole answer, when it fits in one message. */
export interface AgentResult {
  readonly aeth: typeof PROTOCOL_VERSION;
  readonly gen: number;
  readonly id: string;
  readonly ok: boolean;
  /** Present when `ok`; JSON-serialisable. */
  readonly value?: unknown;
  /** Present when not `ok`. `code` carries a Blueprint's `fail:CODE`. */
  readonly error?: { readonly name: string; readonly message: string; readonly code?: string };
}

/** One slice of an answer too large for a single message. */
export interface AgentChunk {
  readonly aeth: typeof PROTOCOL_VERSION;
  readonly gen: number;
  readonly id: string;
  readonly seq: number;
  readonly total: number;
  readonly part: string;
}

export type AgentMessage = AgentReady | AgentResult | AgentChunk;

export function isAgentMessage(value: unknown): value is AgentMessage {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { aeth?: unknown }).aeth === PROTOCOL_VERSION
  );
}

export function isReady(message: AgentMessage): message is AgentReady {
  return (message as AgentReady).ready === true;
}

export function isChunk(message: AgentMessage): message is AgentChunk {
  return typeof (message as AgentChunk).seq === "number";
}

/**
 * The source that hands one order to an already-installed agent.
 *
 * The order is `JSON.stringify`d whole, so the only thing interpolated is a JSON literal — a string
 * the page parses as data. Rule 1 of this file, expressed in the one line that could break it.
 *
 * The trailing `true;` is not decoration: on iOS, `injectJavaScript` evaluates the source and a
 * last expression it cannot serialise surfaces as an error.
 */
export function dispatchSource(request: AgentRequest): string {
  return `window.${AGENT_GLOBAL}.handle(${JSON.stringify(JSON.stringify(request))});\ntrue;`;
}

/** The source that installs the agent on a document, stamped with the generation the host owns. */
export function installSource(agent: string, generation: number): string {
  return `window.${AGENT_GEN_GLOBAL} = ${Math.trunc(generation)};\n${agent}\ntrue;`;
}
