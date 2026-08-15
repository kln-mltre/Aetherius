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
import { decodeUtf8 } from "../../extraction/charset.js";
import {
  hostAbortController,
  hostFetch,
  headersToObject,
  type AbortSignalLike,
  type FetchLike,
  type FetchRequestInit,
  type FetchResponse,
} from "../../http.js";
import { cancellableSleep, throwIfCancelled } from "../../runtime/cancel.js";
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
  /**
   * The run's cancellation signal. It joins the timeout controller so a request in flight is
   * dropped when the caller cancels, instead of being waited out — thirty seconds is a long time to
   * hold a WebView, or a screen, that nobody is looking at any more.
   */
  readonly signal?: AbortSignalLike | undefined;
}

export interface VectorRequest {
  readonly method?: string | undefined;
  readonly url: string;
  readonly headers?: Readonly<Record<string, string>> | undefined;
  readonly json?: unknown;
  readonly form?: unknown;
  readonly params?: Readonly<Record<string, unknown>> | undefined;
  readonly expectedStatus?: number | undefined;
  /**
   * Read the body as bytes instead of text. Asked for only when the step extracts `from: "text"`,
   * the one dialect that decodes per the declared charset: a body can be read once, so the choice
   * has to be made before the response arrives. Every other request keeps the path it always had —
   * and on a device, does not pay React Native's base64 bridge.
   */
  readonly readBytes?: boolean | undefined;
}

export interface VectorResponse {
  readonly status: number;
  readonly headers: Record<string, string>;
  /** Always the UTF-8 reading, so `expect`, JSON and HTML behave the same either way. */
  readonly body: string;
  /** The raw body, present only when `readBytes` was asked for. */
  readonly bytes?: Uint8Array | undefined;
  /** Final URL after redirects, when the host reports one; the requested URL otherwise. */
  readonly url: string;
}

export class VectorClient {
  readonly jar = new CookieJar();

  private readonly fetch: FetchLike;
  private readonly timeoutMs: number;
  private readonly retries: RetriesOptions;
  private readonly auth: AuthStrategy;
  private readonly signal: AbortSignalLike | undefined;

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
    this.signal = options.signal;
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
    const response = await this.send(spec, request.readBytes === true);

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

  private async send(spec: RequestSpec, readBytes: boolean): Promise<VectorResponse> {
    const attempts = this.retries.max > 0 ? this.retries.max + 1 : 1;
    for (let attempt = 1; ; attempt += 1) {
      try {
        return await this.attempt(spec, readBytes);
      } catch (error) {
        // A status is an answer, not a transport failure: only NetworkError (and its TimeoutError
        // subclass) is worth trying again.
        if (attempt >= attempts || !(error instanceof NetworkError)) throw error;
        await cancellableSleep(backoffMs(this.retries.backoff, attempt), this.signal);
      }
    }
  }

  private async attempt(spec: RequestSpec, readBytes: boolean): Promise<VectorResponse> {
    throwIfCancelled(this.signal);

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

    // The run's cancellation aborts the same controller: one place decides the request is over,
    // whichever reason came first.
    const onCancel = (): void => controller?.abort();
    if (controller !== undefined) this.signal?.addEventListener?.("abort", onCancel);

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
      const bytes = readBytes ? await readAsBytes(response) : undefined;
      // `body` stays the UTF-8 reading in both modes: it is what `expect`, JSON and HTML see, and
      // only the text dialect re-reads the bytes through the declared charset.
      const body = bytes === undefined ? await response.text() : decodeUtf8(bytes);
      return {
        status: response.status,
        headers: headersToObject(response.headers),
        body,
        ...(bytes !== undefined ? { bytes } : {}),
        url: response.url ?? spec.url,
      };
    } catch (cause) {
      // Cancellation first: an aborted fetch looks exactly like a transport failure, and reporting
      // it as one would put "the source is down" on screen when the user simply left.
      throwIfCancelled(this.signal);
      // A host that cannot hand over the bytes is a limit of the host, not a network failure:
      // dressing it as one would send someone debugging their connection.
      if (cause instanceof ActionError) throw cause;
      if (timedOut) {
        throw new TimeoutError(`Request timed out: ${spec.method} ${spec.url}`);
      }
      throw new NetworkError(`Transport error: ${reason(cause)}`);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
      this.signal?.removeEventListener?.("abort", onCancel);
    }
  }
}

/** The response body as bytes, or a typed error naming the host surface that is missing. */
async function readAsBytes(response: FetchResponse): Promise<Uint8Array> {
  if (typeof response.arrayBuffer !== "function") {
    throw new ActionError(
      "This host's fetch response has no arrayBuffer(): an extraction with from: \"text\" needs " +
        "the raw body to decode it per the response charset.",
    );
  }
  return new Uint8Array(await response.arrayBuffer());
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
