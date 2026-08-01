/**
 * Authentication strategies for Act I, mirror of `src/aetherius/acts/vector/auth.py`.
 *
 * Same surface as the Python engine, including the fact that it is a **programmatic** one: no
 * Blueprint field selects a strategy on either side. A caller builds a `VectorClient` with the
 * strategy it wants; `docs/acts/vector.md` says as much.
 *
 * Two of them are affected by the platform (docs/embedded.md):
 *
 *   - `CookieAuth` cannot write the OS cookie store, so it seeds the engine's own jar and the
 *     cookies travel in an explicit `Cookie` header;
 *   - `CasFormLogin` works **blind**. `fetch` follows redirects on its own and hides the
 *     intermediate responses, so the ticket dance happens without the engine seeing it: what is
 *     observable is the final outcome, not the chain. That is enough for the flow to work, and not
 *     enough to debug it from here — hence the explicit failure below rather than a silent one.
 */

import { StatusAssertionError } from "../../errors.js";
import { extractHtml } from "../../extraction/html.js";
import { base64Utf8 } from "./base64.js";
import type { VectorClient } from "./client.js";

/** A request about to be sent, as the strategies see it. */
export interface RequestSpec {
  readonly method: string;
  readonly url: string;
  readonly headers: Readonly<Record<string, string>>;
  readonly body?: string;
}

export interface AuthStrategy {
  /** Called once before the first request (a login flow happens here). */
  prepare(client: VectorClient): Promise<void>;
  /** Called per request, to inject headers. */
  apply(request: RequestSpec): RequestSpec;
}

export class NoAuth implements AuthStrategy {
  async prepare(): Promise<void> {
    /* nothing to do */
  }

  apply(request: RequestSpec): RequestSpec {
    return request;
  }
}

export class BearerAuth implements AuthStrategy {
  constructor(private readonly token: string) {}

  async prepare(): Promise<void> {
    /* nothing to do */
  }

  apply(request: RequestSpec): RequestSpec {
    return withHeader(request, "Authorization", `Bearer ${this.token}`);
  }
}

export class BasicAuth implements AuthStrategy {
  private readonly credentials: string;

  constructor(username: string, password: string) {
    this.credentials = base64Utf8(`${username}:${password}`);
  }

  async prepare(): Promise<void> {
    /* nothing to do */
  }

  apply(request: RequestSpec): RequestSpec {
    return withHeader(request, "Authorization", `Basic ${this.credentials}`);
  }
}

export class CookieAuth implements AuthStrategy {
  constructor(private readonly cookies: Readonly<Record<string, string>>) {}

  async prepare(client: VectorClient): Promise<void> {
    for (const [name, value] of Object.entries(this.cookies)) client.jar.set(name, value);
  }

  apply(request: RequestSpec): RequestSpec {
    return request;
  }
}

/** CAS-style form login: GET the page, carry its hidden fields back with the credentials. */
export class CasFormLogin implements AuthStrategy {
  constructor(
    private readonly loginUrl: string,
    private readonly username: string,
    private readonly password: string,
    private readonly usernameField = "username",
    private readonly passwordField = "password",
  ) {}

  async prepare(client: VectorClient): Promise<void> {
    const page = await client.request({ method: "GET", url: this.loginUrl });
    requireSuccess(page.status, this.loginUrl, page.body);

    const form: Record<string, unknown> = hiddenFields(page.body);
    form[this.usernameField] = this.username;
    form[this.passwordField] = this.password;

    const login = await client.request({ method: "POST", url: this.loginUrl, form });
    requireSuccess(login.status, this.loginUrl, login.body);
  }

  apply(request: RequestSpec): RequestSpec {
    // Nothing to inject: the session lives in the cookie jar — ours on a host that exposes
    // `Set-Cookie`, the platform's on a device.
    return request;
  }
}

/**
 * Every hidden input of the document, in order.
 *
 * Reuses the extraction stack rather than adding a parser: two specs over the same selector line
 * up element for element, because both walk the same match list.
 */
function hiddenFields(html: string): Record<string, string> {
  const selector = "form input[type=hidden]";
  const found = extractHtml(html, {
    names: { from: "html", selector, attr: "name", multiple: true },
    values: { from: "html", selector, attr: "value", multiple: true },
  });
  const names = found["names"] as string[];
  const values = found["values"] as string[];

  const fields: Record<string, string> = {};
  names.forEach((name, index) => {
    if (name !== "") fields[name] = values[index] ?? "";
  });
  return fields;
}

/**
 * Python calls `raise_for_status()` here, which raises an httpx error the engine wraps in a
 * `RunError`. This engine raises its own typed error instead — same failure, one that names the
 * step's problem instead of the library's.
 */
function requireSuccess(status: number, url: string, body: string): void {
  if (status < 400) return;
  throw new StatusAssertionError(
    `Login request failed with HTTP ${status} — ${url}` + (body === "" ? "" : `\n${body.slice(0, 200)}`),
  );
}

function withHeader(request: RequestSpec, name: string, value: string): RequestSpec {
  return { ...request, headers: { ...request.headers, [name]: value } };
}
