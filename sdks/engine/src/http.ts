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

export interface AbortSignalLike {
  readonly aborted: boolean;
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
