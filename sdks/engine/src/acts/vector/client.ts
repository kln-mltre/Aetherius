/**
 * The Act I HTTP client, mirror of `src/aetherius/acts/vector/client.py`.
 *
 * Same pipeline as the Python one — guard, auth, retries, status assertion — over `fetch` instead
 * of `httpx`. Three behaviours are worth knowing before someone "fixes" them:
 *
 *   - **Retries are a policy, not a habit.** `max: 0` disables them entirely; otherwise the client
 *     makes `max + 1` attempts and waits `none` = 0s, `linear` = 1s, `exponential` = 2^(n-1)s
 *     clamped to [1, 30] — tenacity's formula, **without jitter**. Adding jitter "because it is
 *     better" would make the same Blueprint retry on a different schedule on each engine.
 *   - **Only transport failures are retried**, never a status code. A 500 is an answer; the
 *     Blueprint decides what to make of it through `expect`.
 *   - **Exhausted retries raise the last error**, a `TimeoutError` or a `NetworkError` — not a
 *     `RetryExhaustedError`. That is what Python does too (`reraise=True` hands back the last
 *     exception), and the caller's `catch` should not have to know how many attempts happened.
 *
 * `fetch` has no timeout of its own, so one is built from `AbortController`; the window covers
 * reading the body, as httpx's does.
 */

import type { RetriesOptions } from "../../blueprint/types.js";
import { NetworkError, StatusAssertionError, TimeoutError, ActionError } from "../../errors.js";
import {
  hostAbortController,
  hostFetch,
  headersToObject,
  type FetchLike,
  type FetchRequestInit,
} from "../../http.js";
import { sleep } from "../../runtime/clock.js";
import { NoAuth, type AuthStrategy, type RequestSpec } from "./auth.js";
import { CookieJar } from "./cookies.js";
import { encodeJson, urlEncode, urlWithParams } from "./encode.js";

const DEFAULT_TIMEOUT_MS = 30_000;

export interface VectorClientOptions {
  /** The host's `fetch` by default; injected in tests, and by an application that wraps its own. */
  readonly fetch?: FetchLike | undefined;
  readonly timeoutMs?: number | undefined;
  readonly retries?: RetriesOptions | undefined;
  readonly auth?: AuthStrategy | undefined;
}

export interface VectorRequest {
  readonly method?: string | undefined;
  readonly url: string;
  readonly headers?: Readonly<Record<string, string>> | undefined;
  readonly json?: unknown;
  readonly form?: unknown;
  readonly params?: Readonly<Record<string, unknown>> | undefined;
  readonly expectedStatus?: number | undefined;
}

export interface VectorResponse {
  readonly status: number;
  readonly headers: Record<string, string>;
  readonly body: string;
  /** Final URL after redirects, when the host reports one; the requested URL otherwise. */
  readonly url: string;
}

export class VectorClient {
  readonly jar = new CookieJar();

  private readonly fetch: FetchLike;
  private readonly timeoutMs: number;
  private readonly retries: RetriesOptions;
  private readonly auth: AuthStrategy;

  constructor(options: VectorClientOptions = {}) {
    const fetchImpl = options.fetch ?? hostFetch();
    if (fetchImpl === undefined) {
      throw new NetworkError(
        "This runtime provides no global fetch: pass one to the engine (RunOptions.fetch).",
      );
    }
    this.fetch = fetchImpl;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.retries = options.retries ?? { max: 0, backoff: "none" };
    this.auth = options.auth ?? new NoAuth();
  }

  /** Run the strategy's one-time preparation (a login flow, seeding the jar). */
  async setup(): Promise<void> {
    await this.auth.prepare(this);
  }

  /**
   * Send a request, with retries and an optional status assertion.
   *
   * @throws {ActionError} both `json` and `form` were given.
   * @throws {TimeoutError} the request exceeded the run's timeout.
   * @throws {NetworkError} the transport failed.
   * @throws {StatusAssertionError} `expectedStatus` was set and the response did not match.
   */
  async request(request: VectorRequest): Promise<VectorResponse> {
    const spec = this.prepareRequest(request);
    const response = await this.send(spec);

    const { expectedStatus } = request;
    if (expectedStatus !== undefined && response.status !== expectedStatus) {
      throw new StatusAssertionError(
        `Expected HTTP ${expectedStatus}, got ${response.status} — ${request.url}` +
          (response.body === "" ? "" : `\n${response.body.slice(0, 200)}`),
      );
    }
    return response;
  }

  private prepareRequest(request: VectorRequest): RequestSpec {
    const { json, form } = request;
    if (json !== undefined && json !== null && form !== undefined && form !== null) {
      throw new ActionError("Cannot set both 'json' and 'form' on the same http.request step.");
    }

    const headers: Record<string, string> = { ...(request.headers ?? {}) };
    let body: string | undefined;

    if (json !== undefined && json !== null) {
      body = encodeJson(json);
      setDefaultHeader(headers, "Content-Type", "application/json");
    } else if (form !== undefined && form !== null) {
      if (typeof form !== "object" || Array.isArray(form)) {
        throw new ActionError(`'form' must be an object, got ${JSON.stringify(form)}.`);
      }
      body = urlEncode(form as Record<string, unknown>);
      setDefaultHeader(headers, "Content-Type", "application/x-www-form-urlencoded");
    }

    // Only cookies this jar captured itself: on a device the platform attaches its own, and
    // sending both would duplicate them (see cookies.ts).
    const cookies = this.jar.header();
    if (cookies !== undefined) setDefaultHeader(headers, "Cookie", cookies);

    const spec: RequestSpec = {
      method: (request.method ?? "GET").toUpperCase(),
      url: urlWithParams(request.url, request.params ?? undefined),
      headers,
      ...(body !== undefined ? { body } : {}),
    };
    return this.auth.apply(spec);
  }

  private async send(spec: RequestSpec): Promise<VectorResponse> {
    const attempts = this.retries.max > 0 ? this.retries.max + 1 : 1;
    for (let attempt = 1; ; attempt += 1) {
      try {
        return await this.attempt(spec);
      } catch (error) {
        // A status is an answer, not a transport failure: only NetworkError (and its TimeoutError
        // subclass) is worth trying again.
        if (attempt >= attempts || !(error instanceof NetworkError)) throw error;
        await sleep(backoffMs(this.retries.backoff, attempt));
      }
    }
  }

  private async attempt(spec: RequestSpec): Promise<VectorResponse> {
    const Controller = hostAbortController();
    const controller = Controller === undefined ? undefined : new Controller();
    let timedOut = false;
    // A host without AbortController gets no timeout rather than a fake one; it is reported in
    // docs/embedded.md instead of being silently absent.
    const timer =
      controller === undefined
        ? undefined
        : setTimeout(() => {
            timedOut = true;
            controller.abort();
          }, this.timeoutMs);

    const init: FetchRequestInit = {
      method: spec.method,
      headers: { ...spec.headers },
      redirect: "follow",
      credentials: "include",
      ...(spec.body !== undefined ? { body: spec.body } : {}),
      ...(controller !== undefined ? { signal: controller.signal } : {}),
    };

    try {
      const response = await this.fetch(spec.url, init);
      this.jar.capture(response.headers);
      const body = await response.text();
      return {
        status: response.status,
        headers: headersToObject(response.headers),
        body,
        url: response.url ?? spec.url,
      };
    } catch (cause) {
      if (timedOut) {
        throw new TimeoutError(`Request timed out: ${spec.method} ${spec.url}`);
      }
      throw new NetworkError(`Transport error: ${reason(cause)}`);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
}

/** tenacity's `wait_exponential(multiplier=1, min=1, max=30)`, `wait_fixed(1)`, `wait_fixed(0)`. */
function backoffMs(backoff: RetriesOptions["backoff"], attempt: number): number {
  if (backoff === "exponential") {
    return Math.max(1, Math.min(2 ** (attempt - 1), 30)) * 1000;
  }
  return backoff === "linear" ? 1000 : 0;
}

/** httpx merges its computed headers with `setdefault`: the Blueprint's own always win. */
function setDefaultHeader(headers: Record<string, string>, name: string, value: string): void {
  const wanted = name.toLowerCase();
  if (Object.keys(headers).some((key) => key.toLowerCase() === wanted)) return;
  headers[name] = value;
}

function reason(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
