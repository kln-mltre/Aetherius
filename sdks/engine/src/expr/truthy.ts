/**
 * The truthiness rule and Python's `str()`, reproduced to the letter.
 *
 * Both look like details worth "cleaning up" in a JavaScript port. They are not:
 *
 *   - `isTruthy` mirrors `core/runtime/flow.py`: the value is stringified, lowercased, and
 *     compared to `true` / `1` / `yes`. Python's `True` becomes the string `"True"`, which is
 *     truthy. Using JavaScript's native truthiness instead would make `when` guards disagree
 *     between the two engines on real Blueprints — `when: "{{ steps.x.count }}"` with a count of
 *     `2` is *false* here, and native truthiness would make it true.
 *   - `pythonStr` mirrors `str()` because Jinja renders interpolated values with it. A boolean
 *     dropped into a form body must serialise as `True` on both engines, not `true` on one of
 *     them: that divergence would be invisible until a remote server rejected the request.
 */

const TRUTHY = new Set(["true", "1", "yes"]);

/** The single truthiness rule shared by `when` guards and `assert` conditions. */
export function isTruthy(value: unknown): boolean {
  return TRUTHY.has(pythonStr(value).trim().toLowerCase());
}

/**
 * Render *value* the way Python's `str()` would.
 *
 * Known limit, documented in docs/embedded.md: JSON does not distinguish `1` from `1.0`, so a
 * number Python holds as a float renders as `1.0` there and `1` here. Nothing in the engine can
 * recover the distinction — it is lost at `JSON.parse`.
 */
export function pythonStr(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return numberStr(value);
  if (Array.isArray(value)) return `[${value.map(pythonRepr).join(", ")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return `{${entries.map(([key, item]) => `${pythonRepr(key)}: ${pythonRepr(item)}`).join(", ")}}`;
  }
  return String(value);
}

/** `repr()`: what `str()` uses for the *members* of a container. Strings gain their quotes. */
export function pythonRepr(value: unknown): string {
  if (typeof value !== "string") return pythonStr(value);
  return value.includes("'") && !value.includes('"')
    ? `"${value}"`
    : `'${value.replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'`;
}

function numberStr(value: number): string {
  if (Number.isNaN(value)) return "nan";
  if (value === Infinity) return "inf";
  if (value === -Infinity) return "-inf";
  return String(value);
}
