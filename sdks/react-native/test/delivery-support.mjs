/**
 * Scaffolding for the delivery tests: a CDN that answers from a table, and Blueprint documents.
 *
 * The `fetch` is a double, not a server, for one reason that matters to what these tests prove: a
 * delivery is decided by *bytes and digests*, never by a transport. Injecting the fetch keeps every
 * case deterministic — a truncated body is a truncated body, not a flaky socket. The one case that
 * does need a real socket (the exfiltration probe) starts its own server, because there the point
 * is precisely that nothing arrives on it.
 */

import { createHash } from "node:crypto";

export const digest = (text) => createHash("sha256").update(text, "utf8").digest("hex");

export const MANIFEST_URL = "https://cdn.example.test/aetherius/manifest.json";

/** A minimal vector Blueprint, the shape a delivered fix has. */
export function document(name, { marker = "bundled", secrets, act = "vector", steps } = {}) {
  return {
    aetherius: "1.0",
    name,
    act,
    ...(secrets === undefined ? {} : { secrets }),
    steps: steps ?? [{ id: "one", action: "set", value: marker }],
    outputs: { marker: "{{ steps.one.value }}" },
  };
}

export const text = (doc) => JSON.stringify(doc, null, 2);

/**
 * A `fetch` serving *routes* (url -> string body, or `{ status, body }`), counting its calls.
 *
 * A missing route answers 404 rather than throwing: that is what a CDN does with a stale manifest
 * URL, and the registry has to survive it like any other unusable answer.
 *
 * Routes are matched on the URL **without its query**, because the client appends a cache-busting
 * parameter — a static host ignores it, and so does this double. `calls` therefore holds clean URLs
 * (readable assertions) while `raw` holds what really went out, which is what proves the bypass.
 */
export function cdn(routes = {}) {
  const calls = [];
  const raw = [];
  const table = { ...routes };

  const fetcher = async (url, init) => {
    const clean = url.split("?")[0];
    calls.push(clean);
    raw.push({ url, init });
    const route = table[clean];
    if (route === undefined) return response(404, "not found");
    if (typeof route === "function") return route(clean);
    return typeof route === "string" ? response(200, route) : response(route.status ?? 200, route.body ?? "");
  };

  return {
    fetch: fetcher,
    calls,
    raw,
    /** Publish (or replace) a file. This is what a fix being pushed to the CDN looks like. */
    put(url, body) {
      table[url] = body;
    },
    remove(url) {
      delete table[url];
    },
  };
}

/** Build a manifest document for *entries*, keyed by Blueprint name. */
export function manifest(entries, { disabled = false, format = "1" } = {}) {
  const blueprints = {};
  for (const [name, entry] of Object.entries(entries)) {
    const { body, version, url, sha256, ...rest } = entry;
    blueprints[name] = {
      version,
      url,
      sha256: sha256 ?? digest(body),
      ...rest,
    };
  }
  return JSON.stringify({ manifest: format, generated_at: "2026-08-04T00:00:00Z", disabled, blueprints });
}

function response(status, body) {
  return {
    status,
    url: "",
    headers: {
      get: (name) => (name.toLowerCase() === "content-length" ? String(body.length) : null),
      forEach: () => {},
    },
    text: async () => body,
  };
}
