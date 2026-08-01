/**
 * The expression evaluator — one brick, three consumers.
 *
 * Rendering (`template.ts`), the `when` / `assert` guards, and the extraction `where` predicate all
 * go through this parser and this interpreter. Giving each its own would guarantee they drift, and
 * the milestone exists precisely to keep two engines from drifting.
 *
 * No dynamic code anywhere: the mobile JS engine refuses `eval` and `new Function`
 * (docs/phase-3/README.md, decision 4). A lexer plus a precedence parser cover the subset a
 * Blueprint uses in a comparable volume, with no dependency and no execution surface.
 */

import { parse } from "./parser.js";
import type { ExprNode } from "./ast.js";
import { evaluate, type Context } from "./eval.js";

export type { Context } from "./eval.js";
export type { ExprNode } from "./ast.js";
export { walk } from "./ast.js";
export { evaluate } from "./eval.js";
export { FILTER_NAMES } from "./filters.js";
export { pyEquals, pyTruth } from "./operators.js";
export { isTruthy, pythonRepr, pythonStr } from "./truthy.js";
export { UndefinedValue, isUndefined } from "./undefined.js";

/**
 * Parsed expressions are cached by source text.
 *
 * A Blueprint renders the same handful of expressions once per step, per loop iteration, per
 * schedule tick, and parsing is pure — so the cache is free correctness-wise. It is capped because
 * an application is long-lived and, from milestone 3-F, will load Blueprints it downloads: an
 * unbounded map keyed by arbitrary text would be a slow leak on someone's phone.
 */
const CACHE_LIMIT = 500;
const CACHE = new Map<string, ExprNode>();

export function parseExpression(source: string): ExprNode {
  const cached = CACHE.get(source);
  if (cached !== undefined) return cached;
  const node = parse(source);
  // Wholesale clear rather than an LRU: the expressions of one Blueprint are used together, so
  // evicting them together costs one re-parse each and keeps the bookkeeping at zero.
  if (CACHE.size >= CACHE_LIMIT) CACHE.clear();
  CACHE.set(source, node);
  return node;
}

/** Parse and evaluate *source* against *ctx*. Raises `TemplateError` on syntax or undefined use. */
export function evaluateExpression(source: string, ctx: Context): unknown {
  return evaluate(parseExpression(source), ctx);
}
