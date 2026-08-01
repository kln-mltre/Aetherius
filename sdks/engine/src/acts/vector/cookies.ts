/**
 * The opportunistic cookie jar — the answer to the hardest constraint of milestone 3-C.
 *
 * `fetch` is not `httpx`. Three facts decide this file, and they are platform facts, not choices:
 *
 *   1. **`Set-Cookie` is usually unreadable from JavaScript.** A browser forbids it outright; a
 *      React Native runtime does not promise it either. Node's `fetch` does expose it, through
 *      `Headers.getSetCookie()`.
 *   2. **The cookie store belongs to the platform.** On a device the OS keeps cookies for the
 *      whole process and attaches them itself, so a session survives without the engine's help —
 *      and cannot be isolated per run.
 *   3. **Node has no store at all.** Nothing attaches anything.
 *
 * Hence: capture what the host lets us read, send back only what we captured ourselves. On a
 * device the jar stays empty and the platform does the work, so no cookie is ever sent twice; on
 * Node the jar *is* the session, which is what makes a form login testable in CI rather than only
 * on someone's phone.
 *
 * Known limit, written down in docs/embedded.md: the jar does not scope by domain, path or expiry.
 * It holds a run's cookies for that run. A Blueprint talking to two unrelated hosts in one run
 * would send the first host's cookies to the second — acceptable while Act I means "one API", and
 * a real reason not to promote this into a general-purpose cookie store.
 */

import type { FetchHeaders } from "../../http.js";

export class CookieJar {
  private readonly cookies = new Map<string, string>();

  get size(): number {
    return this.cookies.size;
  }

  set(name: string, value: string): void {
    this.cookies.set(name, value);
  }

  /** Read `Set-Cookie` when the host exposes it; do nothing when it does not. */
  capture(headers: FetchHeaders): void {
    // Only the structured accessor is used. `headers.get("set-cookie")` returns several cookies
    // joined by commas, and an `Expires` attribute contains a comma too: splitting it is guesswork,
    // and guessing wrong here means sending someone else's session.
    const raw = headers.getSetCookie?.();
    if (raw === undefined) return;
    for (const cookie of raw) this.absorb(cookie);
  }

  private absorb(cookie: string): void {
    const pair = (cookie.split(";")[0] ?? "").trim();
    const equals = pair.indexOf("=");
    if (equals <= 0) return;
    const name = pair.slice(0, equals).trim();
    const value = pair.slice(equals + 1).trim();
    // An empty value is how a server clears a cookie; keeping it would replay a dead session.
    if (value === "") this.cookies.delete(name);
    else this.cookies.set(name, value);
  }

  /** The `Cookie` request header, or `undefined` when the jar holds nothing to say. */
  header(): string | undefined {
    if (this.cookies.size === 0) return undefined;
    return [...this.cookies].map(([name, value]) => `${name}=${value}`).join("; ");
  }
}
