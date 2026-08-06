/**
 * Runtime interpolation of the `{{ }}` syntax, mirror of `core/blueprint/template.py`.
 *
 * The **bare expression rule** is the trap of this milestone. When a string is *exactly* one
 * expression (`"{{ steps.week.events }}"`), the raw value is returned — a list stays a list. As
 * soon as there is text around it, the result is a string. Losing that distinction would not fail
 * loudly: every `outputs` entry that returns a collection would keep succeeding, with a string
 * where the data used to be.
 *
 * Interpolated values are stringified the way Python's `str()` does (see `expr/truthy.ts`), so a
 * boolean dropped in a form body is `True` on both engines.
 */

import { TemplateError } from "./errors.js";
import { evaluateExpression, isUndefined, pythonStr, type Context } from "./expr/index.js";

/**
 * A string that is exactly one `{{ … }}` expression, whitespace aside.
 *
 * The body may not contain `}}`. A lazy `[\s\S]*?` backtracks past the first closer, so
 * `"{{ vars.api }}/{{ inputs.id }}"` — the most ordinary way to build a URL — matched as a single
 * expression whose source was `vars.api }}/{{ inputs.id`, and raised instead of interpolating.
 * Both engines had the same defect, so the corpus saw agreement rather than a bug.
 */
const BARE_EXPRESSION = /^\s*\{\{((?:(?!\}\})[\s\S])*)\}\}\s*$/;

/** Every `{{ … }}` occurrence, for the mixed-text path. */
const EXPRESSION = /\{\{([\s\S]*?)\}\}/g;

/**
 * Recursively render `{{ }}` expressions in *value* against *ctx*.
 *
 * Strings are rendered, arrays and objects recursively, non-string scalars pass through unchanged.
 *
 * @throws {TemplateError} undefined variable, unknown filter, or syntax error.
 */
export function renderValue(value: unknown, ctx: Context): unknown {
  if (typeof value === "string") return renderString(value, ctx);
  if (Array.isArray(value)) return value.map((item) => renderValue(item, ctx));
  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[key] = renderValue(item, ctx);
    }
    return out;
  }
  return value;
}

function renderString(value: string, ctx: Context): unknown {
  const bare = BARE_EXPRESSION.exec(value);
  if (bare !== null) {
    const source = (bare[1] as string).trim();
    const result = evaluateExpression(source, ctx);
    if (isUndefined(result)) {
      // Python raises here too: an expression that resolves to StrictUndefined is a Blueprint
      // error, not an empty value to carry forward.
      throw new TemplateError(`Undefined variable in expression: '${source}'`);
    }
    return result;
  }

  if (!value.includes("{{")) return value;

  let out = "";
  let last = 0;
  for (const match of value.matchAll(EXPRESSION)) {
    out += value.slice(last, match.index);
    const source = (match[1] as string).trim();
    const result = evaluateExpression(source, ctx);
    if (isUndefined(result)) {
      throw new TemplateError(`Undefined variable in expression: '${source}'`);
    }
    out += pythonStr(result);
    last = match.index + match[0].length;
  }
  return out + value.slice(last);
}
