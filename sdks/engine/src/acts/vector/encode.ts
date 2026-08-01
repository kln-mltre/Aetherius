/**
 * Request encoding, byte-for-byte identical to httpx.
 *
 * This is the quiet divergence risk of Act I. A form body or a query string that differs by one
 * character between the two engines raises nothing: the request goes out, the remote server
 * answers something else, and the Blueprint appears to work everywhere except where it matters.
 * So the encoders here reproduce httpx's rules rather than reach for the platform's:
 *
 *   - **`URLSearchParams` is not used.** Its serialiser percent-encodes `~` and leaves `*` alone,
 *     where Python's `quote_plus` does the opposite. Fifteen lines of encoder buy exact parity.
 *   - **Primitives follow `httpx._utils.primitive_value_to_str`**: `true`/`false` for booleans and
 *     the empty string for `None` — *not* Python's `str()`, which the template engine uses. The
 *     two rules coexist in the Python engine and must coexist here.
 *   - **`params` replaces the URL's query**, it does not merge with it. Counter-intuitive, and it
 *     is what httpx does; the fragment survives.
 *   - **JSON bodies** use compact separators and no ASCII escaping, which is exactly
 *     `JSON.stringify`.
 */

import { pythonStr } from "../../expr/index.js";

/** `httpx._utils.primitive_value_to_str`: JSON-flavoured booleans, empty string for null. */
export function primitiveValueToStr(value: unknown): string {
  if (value === true) return "true";
  if (value === false) return "false";
  if (value === null || value === undefined) return "";
  return pythonStr(value);
}

/**
 * `urllib.parse.quote_plus`: unreserved characters plus `~` survive, space becomes `+`.
 *
 * `encodeURIComponent` already leaves the right set alone except for `!*'()`, which Python escapes.
 */
export function quotePlus(value: string): string {
  return encodeURIComponent(value)
    .replace(/[!'()*]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`)
    .replace(/%20/g, "+");
}

/**
 * `urlencode(..., doseq=True)` over httpx's flattening: a list value repeats its key.
 *
 * @throws {never} — a non-object is the caller's to reject, with the field name it knows.
 */
export function urlEncode(data: Readonly<Record<string, unknown>>): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(data)) {
    const items = Array.isArray(value) ? value : [value];
    for (const item of items) {
      parts.push(`${quotePlus(key)}=${quotePlus(primitiveValueToStr(item))}`);
    }
  }
  return parts.join("&");
}

/**
 * *url* with its query replaced by *params* — httpx's behaviour, fragment preserved.
 *
 * `undefined` params leave the URL untouched; an empty object strips the query, `?` included.
 */
export function urlWithParams(url: string, params: Readonly<Record<string, unknown>> | undefined): string {
  if (params === undefined) return url;

  const hash = url.indexOf("#");
  const fragment = hash === -1 ? "" : url.slice(hash);
  const withoutFragment = hash === -1 ? url : url.slice(0, hash);
  const question = withoutFragment.indexOf("?");
  const base = question === -1 ? withoutFragment : withoutFragment.slice(0, question);

  const query = urlEncode(params);
  return query === "" ? `${base}${fragment}` : `${base}?${query}${fragment}`;
}

/** `httpx._content.encode_json`: compact separators, no ASCII escaping. */
export function encodeJson(value: unknown): string {
  return JSON.stringify(value) ?? "null";
}
