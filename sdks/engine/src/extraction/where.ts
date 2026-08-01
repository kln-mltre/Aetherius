/**
 * The `where` predicate: Blueprint-supplied code, evaluated per item.
 *
 * Python runs it through `eval` behind an AST allowlist, with dunder access explicitly denied
 * (`core/extraction/json_extractor.py`). The embedded interpreter has **nothing** to offer an
 * attacker — no host functions, no prototype walk, no globals — so safety is not what the
 * restriction below is for. It is there for **parity**: Python's allowlist rejects filters, calls,
 * subscripts and list literals, so a predicate refused there must be refused here too, or the two
 * engines would disagree about which Blueprints are valid.
 *
 * One semantic worth stating because it looks like a bug: a comparison against an **absent** field
 * raises. Python wraps the item in a `SimpleNamespace`, so `item.missing` is an `AttributeError`,
 * caught and re-raised as `ExtractionError`. It does not quietly filter the item out.
 */

import { ExtractionError, TemplateError } from "../errors.js";
import { evaluate, parseExpression, pyTruth, walk, type ExprNode } from "../expr/index.js";

/** Node kinds Python's `_ALLOWED_NODES` has an equivalent for. */
const ALLOWED_KINDS: ReadonlySet<ExprNode["kind"]> = new Set([
  "literal",
  "name",
  "attribute",
  "compare",
  "boolop",
  "unary",
]);

const REJECTION: Readonly<Record<string, string>> = {
  call: "function calls",
  filter: "filters",
  index: "subscripting",
  test: "tests",
  conditional: "inline conditionals",
  list: "list literals",
  dict: "dict literals",
  binary: "arithmetic and concatenation",
};

/** Parse and check *source*; raises `ExtractionError` unless it is a plain boolean predicate. */
export function parseWhere(source: string): ExprNode {
  let node: ExprNode;
  try {
    node = parseExpression(source);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new ExtractionError(`Invalid where expression '${source}': ${reason}`);
  }

  walk(node, (child) => {
    if (!ALLOWED_KINDS.has(child.kind)) {
      const what = REJECTION[child.kind] ?? child.kind;
      throw new ExtractionError(
        `Disallowed construct (${what}) in where expression '${source}'. ` +
          "Only comparisons and boolean logic are permitted.",
      );
    }
    if (child.kind === "unary" && child.op !== "not") {
      throw new ExtractionError(
        `Disallowed construct (unary '${child.op}') in where expression '${source}'. ` +
          "Only comparisons and boolean logic are permitted.",
      );
    }
    // The doorway to the Python object graph (`item.__class__.__globals__`). Denied on both
    // engines, so a predicate written against one is refused by the other for the same reason.
    if (child.kind === "attribute" && child.attr.startsWith("__")) {
      throw new ExtractionError(
        `Disallowed dunder attribute '${child.attr}' in where expression '${source}'.`,
      );
    }
    if (child.kind === "name" && child.name.startsWith("__")) {
      throw new ExtractionError(
        `Disallowed dunder name '${child.name}' in where expression '${source}'.`,
      );
    }
  });

  return node;
}

/** Evaluate a checked predicate against one item. `item` is the only name in scope. */
export function evaluateWhere(node: ExprNode, source: string, item: unknown): boolean {
  try {
    return pyTruth(evaluate(node, { item }));
  } catch (error) {
    if (error instanceof ExtractionError) throw error;
    const reason = error instanceof TemplateError ? error.message : String(error);
    throw new ExtractionError(`Error evaluating where expression '${source}': ${reason}`);
  }
}
