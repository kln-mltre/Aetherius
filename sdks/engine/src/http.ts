/**
 * The host's HTTP surface, described structurally.
 *
 * The engine targets three runtimes with three sets of ambient types — a React Native app, Node,
 * and whatever a test harness injects. Reaching for `lib: ["DOM"]` or `@types/node` would tie a
 * platform-neutral package to one of them, so the shapes it actually uses are declared here
 * instead. Two consequences worth keeping: the client takes its `fetch` as a parameter (which is
 * what makes it testable without a network), and nothing here is a dependency.
 *
 * The declarations are deliberately narrower than the WHATWG spec: only what Act I sends and
 * reads. Widening them is a decision, not an accident.
 */

/** Response headers. `getSetCookie` is optional because most hosts do not expose it (see cookies.ts). */
export interface FetchHeaders {
  get(name: string): string | null;
  forEach(callback: (value: string, name: string) => void): void;
  getSetCookie?: () => string[];
}

export interface FetchResponse {
  readonly status: number;
  readonly headers: FetchHeaders;
  /** Final URL after redirects, when the host reports it. */
  readonly url?: string;
  text(): Promise<string>;
  /**
   * The raw body, read only when an extraction declares `from: "text"` — the one dialect that
   * decodes per the response's charset. Optional because a host may wrap `fetch` with a narrower
   * response; the client then fails with a message naming what is missing, rather than silently
   * decoding as UTF-8. React Native's own `fetch` has it (blob response, `readAsArrayBuffer`).
   */
  arrayBuffer?: () => Promise<ArrayBuffer>;
}

export interface FetchRequestInit {
  method?: string;
  headers?: Record<string, string>;
  body?: string;
  /**
   * Always `follow`: `manual` is unsupported in a React Native fetch, and pretending otherwise
   * would make the two hosts of this engine behave differently. See docs/embedded.md.
   */
  redirect?: "follow";
  /** Asks the host to attach its own cookie store, where it has one. */
  credentials?: "include";
  signal?: AbortSignalLike;
}

export type FetchLike = (url: string, init?: FetchRequestInit) => Promise<FetchResponse>;

/**
 * Un signal d'annulation, decrit structurellement — comme `fetch` lui-meme.
 *
 * Les deux ecouteurs sont **optionnels** : le controleur du delai d'une requete n'est lu qu'a
 * travers `aborted` et son `signal` part directement dans `fetch`, tandis que l'annulation d'un run
 * (jalon 3-E) a besoin d'etre notifiee pour liberer une attente en cours. Les declarer optionnels
 * evite d'exiger un `AbortSignal` complet la ou un booleen suffit.
 */
export interface AbortSignalLike {
  readonly aborted: boolean;
  addEventListener?: (type: "abort", listener: () => void) => void;
  removeEventListener?: (type: "abort", listener: () => void) => void;
}

export interface AbortControllerLike {
  readonly signal: AbortSignalLike;
  abort(): void;
}

type AbortControllerCtor = new () => AbortControllerLike;

/**
 * The host's `fetch`, or `undefined` when it has none.
 *
 * Read through `globalThis` rather than referenced directly: a module-level reference would make
 * the package fail to load on a host without `fetch`, instead of failing at the one step that
 * needs it, with a message that says so.
 */
export function hostFetch(): FetchLike | undefined {
  return (globalThis as { fetch?: FetchLike }).fetch;
}

export function hostAbortController(): AbortControllerCtor | undefined {
  return (globalThis as { AbortController?: AbortControllerCtor }).AbortController;
}

/** Response headers as a plain object, the shape `http.request` publishes as `headers`. */
export function headersToObject(headers: FetchHeaders): Record<string, string> {
  const out: Record<string, string> = {};
  headers.forEach((value, name) => {
    out[name] = value;
  });
  return out;
}
