/**
 * The filter table — closed on purpose.
 *
 * Jinja2 ships dozens of filters; a Blueprint uses a handful. Implementing the handful faithfully
 * and refusing the rest **by name** beats implementing many of them approximately: an unknown
 * filter is a loud `TemplateError` here, where a half-right `groupby` would be a silent divergence
 * discovered in production. The three date filters are Aetherius' own
 * (`core/blueprint/template.py`); the others reproduce Jinja's, quirks included.
 */

import { TemplateError } from "../errors.js";
import { parseIsoDate, shiftDays, strftime, toIsoDate } from "./dates.js";
import { pyTruth } from "./operators.js";
import { pythonStr } from "./truthy.js";
import { isUndefined, undefinedValue, type UndefinedValue } from "./undefined.js";

export type FilterFn = (value: unknown, args: readonly unknown[]) => unknown;

function requireInt(args: readonly unknown[], filter: string): number {
  const raw = args[0];
  const n = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(n)) {
    throw new TemplateError(`${filter}: expected a number of days, got ${pythonStr(raw)}.`);
  }
  return Math.trunc(n);
}

function sequenceOf(value: unknown, filter: string): readonly unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") return Array.from(value);
  if (value !== null && typeof value === "object") return Object.keys(value);
  throw new TemplateError(`${filter}: expected a sequence, got ${pythonStr(value)}.`);
}

/** Jinja's `int`/`float` swallow a bad conversion and return their default; so do these. */
function toNumber(value: unknown, fallback: number, truncate: boolean): number {
  if (typeof value === "boolean") return value ? 1 : 0;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  if (!Number.isFinite(n)) return fallback;
  return truncate ? Math.trunc(n) : n;
}

export const FILTERS: Readonly<Record<string, FilterFn>> = {
  // ── Aetherius' own (core/blueprint/template.py) ──────────────────────────
  add_days: (value, args) =>
    toIsoDate(shiftDays(parseIsoDate(value, "add_days"), requireInt(args, "add_days"))),
  sub_days: (value, args) =>
    toIsoDate(shiftDays(parseIsoDate(value, "sub_days"), -requireInt(args, "sub_days"))),
  format_date: (value, args) => {
    const format = args[0];
    if (typeof format !== "string") {
      throw new TemplateError(`format_date: expected a format string, got ${pythonStr(format)}.`);
    }
    return strftime(parseIsoDate(value, "format_date"), format, "format_date");
  },

  // ── Jinja built-ins ──────────────────────────────────────────────────────
  first: (value): unknown => {
    const seq = sequenceOf(value, "first");
    // Jinja returns Undefined on an empty sequence, not None: using the result then raises.
    return seq.length === 0 ? undefinedValue("no first item, sequence was empty") : seq[0];
  },
  last: (value): unknown => {
    const seq = sequenceOf(value, "last");
    return seq.length === 0
      ? undefinedValue("no last item, sequence was empty")
      : seq[seq.length - 1];
  },
  length: (value): number => {
    if (typeof value === "string") return Array.from(value).length;
    if (Array.isArray(value)) return value.length;
    if (value !== null && typeof value === "object") return Object.keys(value).length;
    throw new TemplateError(`length: object of type ${typeof value} has no length.`);
  },
  int: (value, args) => toNumber(value, args.length > 0 ? Number(args[0]) : 0, true),
  float: (value, args) => toNumber(value, args.length > 0 ? Number(args[0]) : 0, false),
  string: (value) => pythonStr(value),
  lower: (value) => pythonStr(value).toLowerCase(),
  upper: (value) => pythonStr(value).toUpperCase(),
  trim: (value, args) => {
    const chars = args[0];
    if (chars === undefined) return pythonStr(value).trim();
    const set = new Set(Array.from(pythonStr(chars)));
    const text = Array.from(pythonStr(value));
    let start = 0;
    let end = text.length;
    while (start < end && set.has(text[start] as string)) start += 1;
    while (end > start && set.has(text[end - 1] as string)) end -= 1;
    return text.slice(start, end).join("");
  },
  join: (value, args) => {
    const separator = args.length > 0 ? pythonStr(args[0]) : "";
    return sequenceOf(value, "join").map(pythonStr).join(separator);
  },
  /**
   * `default(fallback, boolean=False)`, Jinja's signature.
   *
   * The second argument is not a detail: with it, *any* falsy value takes the fallback, not only an
   * undefined one. A Blueprint reading a nullable field writes `| default('', true)` to turn a
   * `null` into an empty string — and without this branch the embedded engine kept the `null`,
   * which is a different value with the same run status. Found by the reference port of milestone
   * 3-G, on a closing time that is `null` while a place is shut.
   */
  default: (value, args) => {
    const fallback = args.length > 0 ? args[0] : "";
    if (isUndefined(value)) return fallback;
    return args.length > 1 && pyTruth(args[1]) && !pyTruth(value) ? fallback : value;
  },
};

/** `default` must see the marker; every other filter gets a defined value. */
export const UNDEFINED_TOLERANT: ReadonlySet<string> = new Set(["default"]);

export const FILTER_NAMES: readonly string[] = Object.keys(FILTERS).sort();

export function applyFilter(
  name: string,
  value: unknown | UndefinedValue,
  args: readonly unknown[],
): unknown {
  const filter = FILTERS[name];
  if (filter === undefined) {
    throw new TemplateError(
      `Unknown filter '${name}'. The embedded engine supports: ${FILTER_NAMES.join(", ")}.`,
    );
  }
  return filter(value, args);
}
