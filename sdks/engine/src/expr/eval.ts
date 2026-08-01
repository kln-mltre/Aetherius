/**
 * AST interpreter.
 *
 * Two truths coexist here and must not be confused:
 *
 *   - **inside** an expression, `and` / `or` / `not` / the inline conditional use *Python's* native
 *     truthiness (empty string, empty list, `0`, `None` are false) — that is what Jinja evaluates;
 *   - **around** an expression, `when` and `assert` apply Aetherius' own rule (`isTruthy`, see
 *     truthy.ts) to the rendered result. Mixing the two would change what a guard means.
 *
 * The interpreter has no access to host functions, prototypes or globals: the only values it can
 * reach are those the caller put in the context. That is why the `where` predicate — code supplied
 * by the Blueprint — needs no sandbox allowlist to be safe here, only a grammar restriction to stay
 * in step with the Python side (see extraction/where.ts).
 */

import { TemplateError } from "../errors.js";
import type { ExprNode } from "./ast.js";
import { UNDEFINED_TOLERANT, applyFilter } from "./filters.js";
import { binary, compare, pyTruth } from "./operators.js";
import { pythonStr } from "./truthy.js";
import { failUndefined, isUndefined, undefinedValue } from "./undefined.js";

export type Context = Readonly<Record<string, unknown>>;

// `is none` / `is None` never reach runTest: the parser turns an identity check against a keyword
// literal into a comparison, so the Python-flavoured `where` dialect and Jinja's `none` test agree.
const TESTS = new Set(["defined", "undefined"]);

export function evaluate(node: ExprNode, ctx: Context): unknown {
  switch (node.kind) {
    case "literal":
      return node.value;

    case "name":
      return Object.prototype.hasOwnProperty.call(ctx, node.name)
        ? ctx[node.name]
        : undefinedValue(`'${describe(node)}'`);

    case "attribute":
      return member(use(evaluate(node.target, ctx)), node.attr, node);

    case "index": {
      const key = use(evaluate(node.index, ctx));
      return member(use(evaluate(node.target, ctx)), key, node);
    }

    case "call":
      // Nothing in the vocabulary is callable; filters carry their arguments themselves.
      throw new TemplateError(
        `Function calls are not supported in expressions (${describe(node.target)}).`,
      );

    case "filter": {
      const target = evaluate(node.target, ctx);
      const value = UNDEFINED_TOLERANT.has(node.name) ? target : use(target);
      const args = node.args.map((arg) => use(evaluate(arg, ctx)));
      return applyFilter(node.name, value, args);
    }

    case "test":
      return runTest(node.name, evaluate(node.target, ctx), node.negated);

    case "unary":
      return unary(node.op, evaluate(node.operand, ctx));

    case "binary":
      return binary(
        node.op,
        use(evaluate(node.left, ctx)),
        use(evaluate(node.right, ctx)),
      );

    case "compare":
      return compare(
        node.op,
        use(evaluate(node.left, ctx)),
        use(evaluate(node.right, ctx)),
      );

    case "boolop": {
      const left = use(evaluate(node.left, ctx));
      // Python's operators return an operand, not a boolean.
      if (node.op === "and") return pyTruth(left) ? evaluate(node.right, ctx) : left;
      return pyTruth(left) ? left : evaluate(node.right, ctx);
    }

    case "conditional": {
      // Lazy: only the taken branch is evaluated, which is what makes
      // `{{ steps.x.y if steps.x is defined else None }}` work at all.
      if (pyTruth(use(evaluate(node.condition, ctx)))) {
        return evaluate(node.body, ctx);
      }
      if (node.orElse === undefined) {
        return undefinedValue("the inline if-expression evaluated to false with no else branch");
      }
      return evaluate(node.orElse, ctx);
    }

    case "list":
      return node.items.map((item) => use(evaluate(item, ctx)));

    case "dict": {
      const out: Record<string, unknown> = {};
      for (const [key, value] of node.entries) {
        out[pythonStr(use(evaluate(key, ctx)))] = use(evaluate(value, ctx));
      }
      return out;
    }
  }
}

/** Reject an undefined operand at the point of *use* — the whole point of StrictUndefined. */
function use(value: unknown): unknown {
  if (isUndefined(value)) failUndefined(value);
  return value;
}

/**
 * Attribute or subscript access, in Jinja's order: attribute first, then item, then undefined.
 * Prototype properties are never reachable — a Blueprint must not be able to walk to `constructor`.
 */
function member(target: unknown, key: unknown, node: ExprNode): unknown {
  const missing = undefinedValue(`'${describe(node)}'`);
  const name = typeof key === "number" ? key : pythonStr(key);

  if (Array.isArray(target) || typeof target === "string") {
    if (typeof name !== "number") return missing;
    const items = typeof target === "string" ? Array.from(target) : target;
    const index = name < 0 ? items.length + name : name;
    return index >= 0 && index < items.length ? items[index] : missing;
  }

  if (target !== null && typeof target === "object") {
    const property = String(name);
    return Object.prototype.hasOwnProperty.call(target, property)
      ? (target as Record<string, unknown>)[property]
      : missing;
  }

  return missing;
}

function runTest(name: string, value: unknown, negated: boolean): boolean {
  if (!TESTS.has(name)) {
    throw new TemplateError(
      `Unknown test '${name}'. The embedded engine supports: ${[...TESTS].sort().join(", ")}.`,
    );
  }
  const result = name === "defined" ? !isUndefined(value) : isUndefined(value);
  return negated ? !result : result;
}

function unary(op: "not" | "-" | "+", value: unknown): unknown {
  if (op === "not") return !pyTruth(use(value));
  const operand = use(value);
  if (typeof operand !== "number") {
    throw new TemplateError(`Unary '${op}' expects a number, got ${pythonStr(operand)}.`);
  }
  return op === "-" ? -operand : operand;
}

/** A readable path for error messages: `steps.fetch.missing` rather than "an expression". */
function describe(node: ExprNode): string {
  switch (node.kind) {
    case "name":
      return node.name;
    case "attribute":
      return `${describe(node.target)}.${node.attr}`;
    case "index":
      return node.index.kind === "literal"
        ? `${describe(node.target)}[${JSON.stringify(node.index.value)}]`
        : `${describe(node.target)}[…]`;
    default:
      return "expression";
  }
}
