/**
 * The JSONPath subset the embedded engine honours.
 *
 * The Python engine leans on `jsonpath-ng[ext]`, a very complete implementation; reproducing it
 * would be a project of its own. The rule here is the one the milestone sets: **aim at the useful
 * subset, not at the specification**, and make everything outside it **fail loudly** — a partial
 * result would be worse than an error, because nobody checks a value that arrived.
 *
 * Supported: `$`, `.name`, `.'quoted name'` / `."quoted name"` / `['name']`, `.*` / `[*]`, `[n]`
 * (negative indices included), slices `[a:b:c]`, and recursive descent by name `..name`.
 * Everything else — filters `[?…]`, unions, `len`, arithmetic, `@` — raises.
 *
 * `..*` is deliberately **not** supported. It is the one construct where `jsonpath-ng` and a
 * straightforward reading disagree: it does not descend into list *elements*, so
 * `$..*` over `{"c": [2, 3]}` yields the list but not its items. Rather than reproduce that shape
 * from guesswork for a construct no Blueprint uses, the engine refuses it by name.
 */

import { ExtractionError } from "../errors.js";
import { pyTruth } from "../expr/index.js";

type Segment =
  | { readonly kind: "field"; readonly name: string }
  // `.*` is a *field* access; `[*]` is a full slice. However alike they read, jsonpath-ng treats
  // them as different operators, and so must this — see `step` below.
  | { readonly kind: "fieldWildcard" }
  | { readonly kind: "index"; readonly index: number }
  | {
      readonly kind: "slice";
      readonly start: number | undefined;
      readonly end: number | undefined;
      readonly step: number;
    }
  | { readonly kind: "descend"; readonly name: string };

const NAME = /[A-Za-z0-9_\-@$]/;

/** Parse *path* into segments, or raise naming the construct that put it out of subset. */
export function parseJsonPath(path: string): Segment[] {
  const source = path.trim();
  const segments: Segment[] = [];
  let i = 0;

  if (source.length === 0) throw unsupported(path, "the expression is empty");
  // A relative path (`id`, used inside `fields`) is rooted implicitly, as jsonpath-ng does.
  if (source[i] === "$") i += 1;

  while (i < source.length) {
    const char = source[i] as string;

    if (char === ".") {
      if (source[i + 1] === ".") {
        i += 2;
        if (source[i] === "*") {
          throw unsupported(
            path,
            "recursive descent onto '*' ('..*') is not supported by the embedded engine; " +
              "name the field ('..field')",
          );
        }
        const [name, next] = readName(source, i, path);
        segments.push({ kind: "descend", name });
        i = next;
        continue;
      }
      i += 1;
      if (source[i] === "*") {
        segments.push({ kind: "fieldWildcard" });
        i += 1;
        continue;
      }
      if (source[i] === "'" || source[i] === '"') {
        const [name, next] = readQuoted(source, i, path);
        segments.push({ kind: "field", name });
        i = next;
        continue;
      }
      const [name, next] = readName(source, i, path);
      segments.push({ kind: "field", name });
      i = next;
      continue;
    }

    if (char === "[") {
      const close = source.indexOf("]", i);
      if (close === -1) throw unsupported(path, "unbalanced '['");
      const inner = source.slice(i + 1, close).trim();
      segments.push(bracket(inner, path));
      i = close + 1;
      continue;
    }

    if (segments.length === 0 && NAME.test(char)) {
      const [name, next] = readName(source, i, path);
      segments.push({ kind: "field", name });
      i = next;
      continue;
    }

    throw unsupported(path, `unexpected character '${char}' at position ${i}`);
  }

  return segments;
}

function bracket(inner: string, path: string): Segment {
  // `[*]` is a slice over everything — that is literally how jsonpath-ng parses it, and it is why
  // `[*]` and `.*` answer differently on the same document.
  if (inner === "*") return { kind: "slice", start: undefined, end: undefined, step: 1 };

  if (inner.startsWith("?")) {
    throw unsupported(path, "filter expressions ([?…]) are not supported by the embedded engine");
  }
  if (inner.includes(",")) {
    throw unsupported(path, "unions ([a,b]) are not supported by the embedded engine");
  }

  if (inner.startsWith("'") || inner.startsWith('"')) {
    const [name, next] = readQuoted(inner, 0, path);
    if (next !== inner.length) throw unsupported(path, `unexpected text after ${inner}`);
    return { kind: "field", name };
  }

  if (inner.includes(":")) {
    const parts = inner.split(":");
    if (parts.length > 3) throw unsupported(path, `malformed slice '${inner}'`);
    const [start, end, step] = parts.map((part) => sliceBound(part, inner, path));
    return { kind: "slice", start, end, step: step ?? 1 };
  }

  const index = Number(inner);
  if (!Number.isInteger(index)) {
    throw unsupported(path, `'[${inner}]' is not an index, a slice, a name or '*'`);
  }
  return { kind: "index", index };
}

function sliceBound(part: string, inner: string, path: string): number | undefined {
  const text = part.trim();
  if (text.length === 0) return undefined;
  const value = Number(text);
  if (!Number.isInteger(value)) throw unsupported(path, `malformed slice '${inner}'`);
  return value;
}

function readName(source: string, start: number, path: string): [string, number] {
  let end = start;
  while (end < source.length && NAME.test(source[end] as string)) end += 1;
  if (end === start) throw unsupported(path, `expected a field name at position ${start}`);
  return [source.slice(start, end), end];
}

function readQuoted(source: string, start: number, path: string): [string, number] {
  const quote = source[start] as string;
  const close = source.indexOf(quote, start + 1);
  if (close === -1) throw unsupported(path, "unterminated quoted field name");
  return [source.slice(start + 1, close), close + 1];
}

function unsupported(path: string, detail: string): ExtractionError {
  return new ExtractionError(`Invalid JSONPath '${path}': ${detail}.`);
}

/** Every value *path* matches in *data*, in document order. An empty array means no match. */
export function jsonPathFind(path: string, data: unknown): unknown[] {
  let current: unknown[] = [data];
  for (const segment of parseJsonPath(path)) {
    const next: unknown[] = [];
    for (const value of current) step(segment, value, next);
    current = next;
  }
  return current;
}

function step(segment: Segment, value: unknown, out: unknown[]): void {
  switch (segment.kind) {
    case "field": {
      if (isRecord(value) && Object.prototype.hasOwnProperty.call(value, segment.name)) {
        out.push(value[segment.name]);
      }
      return;
    }
    // `.*` is a field access: it only means anything on an object.
    case "fieldWildcard": {
      if (isRecord(value)) out.push(...Object.values(value));
      return;
    }
    // A slice — and therefore `[*]` — treats a non-list as a one-element list, so `$[*]` over an
    // object yields the object itself. Surprising, but it is what a Blueprint would meet on the
    // other engine. Only `null` drops out entirely.
    case "slice": {
      if (value === null || value === undefined) return;
      const items = Array.isArray(value) ? value : [value];
      out.push(...slice(items, segment.start, segment.end, segment.step));
      return;
    }
    case "index":
      indexed(segment.index, value, out);
      return;
    case "descend":
      descend(value, segment.name, out);
      return;
  }
}

/**
 * `[n]`, reproducing `jsonpath_ng.Index.find` — `if datum.value and len(datum.value) > index`.
 *
 * Which gives, for a subscript that makes no sense on the value at hand: nothing at all for a falsy
 * container, a raised error for a truthy one that cannot be indexed by number (an object, a
 * number), and a raised error for a negative index past the start. Odd, but reproduced rather than
 * tidied: the two engines must refuse and accept the same documents, including the silly ones.
 */
function indexed(index: number, value: unknown, out: unknown[]): void {
  if (!pyTruth(value)) return;

  if (Array.isArray(value) || typeof value === "string") {
    const items: readonly unknown[] = typeof value === "string" ? Array.from(value) : value;
    if (items.length <= index) return;
    const at = index < 0 ? items.length + index : index;
    if (at < 0) throw new ExtractionError(`Invalid JSONPath '[${index}]': index out of range.`);
    out.push(items[at]);
    return;
  }

  // The `len(...) > index` test runs before the subscript, so an object with too few keys yields
  // nothing at all, while one with enough keys gets as far as failing on a numeric key.
  if (isRecord(value) && Object.keys(value).length <= index) return;

  throw new ExtractionError(
    `Invalid JSONPath '[${index}]': cannot take element ${index} of ${typeof value}.`,
  );
}

/**
 * Python's slice semantics, bounds included — this is `slice.indices()` from CPython.
 *
 * Worth reproducing rather than approximating: with a negative step the defaults flip (start
 * becomes the *last* index, stop becomes "before the beginning"), so an intuitive port answers `[]`
 * where Python answers three values.
 */
function slice(
  items: readonly unknown[],
  start: number | undefined,
  end: number | undefined,
  stepBy: number,
): unknown[] {
  if (stepBy === 0) return [];
  const length = items.length;
  const down = stepBy < 0;
  const lower = down ? -1 : 0;
  const upper = down ? length - 1 : length;

  const bound = (value: number | undefined, fallback: number): number => {
    if (value === undefined) return fallback;
    return value < 0 ? Math.max(value + length, lower) : Math.min(value, upper);
  };

  const from = bound(start, down ? upper : lower);
  const to = bound(end, down ? lower : upper);

  const out: unknown[] = [];
  for (let i = from; down ? i > to : i < to; i += stepBy) out.push(items[i]);
  return out;
}

/** Depth-first descent, parents before children — the order `jsonpath-ng` reports matches in. */
function descend(value: unknown, name: string, out: unknown[]): void {
  if (isRecord(value) && Object.prototype.hasOwnProperty.call(value, name)) {
    out.push(value[name]);
  }
  if (Array.isArray(value)) {
    for (const item of value) descend(item, name, out);
    return;
  }
  if (isRecord(value)) {
    for (const item of Object.values(value)) descend(item, name, out);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
