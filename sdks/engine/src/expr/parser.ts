/**
 * Precedence parser for the expression language.
 *
 * The precedence ladder is Jinja2's, deliberately — see `jinja2/parser.py`. The one that bites:
 * filters and the `is` test sit at the **postfix** level, tighter than everything else. So
 * `not x | first` is `not (x | first)` and `x | length > 0` is `(x | length) > 0`. Both forms
 * appear in shipped Blueprints; getting the ladder wrong would silently change what they mean.
 *
 * Chained comparisons (`0 < x < 10`) are desugared into `and`, as Python evaluates them. The
 * language has no side effects, so evaluating the middle operand twice is unobservable.
 */

import type { CompareOp, ExprNode } from "./ast.js";
import { TokenCursor } from "./cursor.js";
import { tokenize } from "./lexer.js";

const COMPARE_OPERATORS = new Set(["==", "!=", "<", "<=", ">", ">="]);

/** Jinja accepts both the lowercase spellings and Python's capitalised ones. */
const KEYWORD_LITERALS: Readonly<Record<string, boolean | null>> = {
  true: true,
  True: true,
  false: false,
  False: false,
  none: null,
  None: null,
};

export function parse(source: string): ExprNode {
  const parser = new Parser(tokenize(source), source);
  const node = parser.parseExpression();
  parser.expectEnd();
  return node;
}

class Parser extends TokenCursor {
  // ── Grammar, loosest binding first ────────────────────────────────────────

  /** `body if condition [else orElse]` — the inline conditional. */
  parseExpression(): ExprNode {
    const body = this.parseOr();
    if (!this.at("name", "if")) return body;
    this.advance();
    const condition = this.parseOr();
    let orElse: ExprNode | undefined;
    if (this.accept("name", "else")) orElse = this.parseExpression();
    return { kind: "conditional", body, condition, orElse };
  }

  private parseOr(): ExprNode {
    let left = this.parseAnd();
    while (this.accept("name", "or")) {
      left = { kind: "boolop", op: "or", left, right: this.parseAnd() };
    }
    return left;
  }

  private parseAnd(): ExprNode {
    let left = this.parseNot();
    while (this.accept("name", "and")) {
      left = { kind: "boolop", op: "and", left, right: this.parseNot() };
    }
    return left;
  }

  private parseNot(): ExprNode {
    // A `not` in operand position is the unary operator; the `not` of `a not in b` is reached from
    // parseCompare, after its left operand, so the two never collide here.
    if (this.at("name", "not")) {
      this.advance();
      return { kind: "unary", op: "not", operand: this.parseNot() };
    }
    return this.parseCompare();
  }

  private parseCompare(): ExprNode {
    const first = this.parseMath1();
    const links: { op: CompareOp; node: ExprNode }[] = [];

    for (;;) {
      const op = this.nextCompareOperator();
      if (op === undefined) break;
      links.push({ op, node: this.parseMath1() });
    }

    if (links.length === 0) return first;

    let left = first;
    let result: ExprNode | undefined;
    for (const link of links) {
      const comparison: ExprNode = { kind: "compare", op: link.op, left, right: link.node };
      result =
        result === undefined
          ? comparison
          : { kind: "boolop", op: "and", left: result, right: comparison };
      left = link.node;
    }
    return result as ExprNode;
  }

  private nextCompareOperator(): CompareOp | undefined {
    if (this.current.type === "operator" && COMPARE_OPERATORS.has(this.current.value)) {
      return this.advance().value as CompareOp;
    }
    if (this.at("name", "in")) {
      this.advance();
      return "in";
    }
    if (this.at("name", "not") && this.peek().type === "name" && this.peek().value === "in") {
      this.advance();
      this.advance();
      return "not in";
    }
    return undefined;
  }

  private parseMath1(): ExprNode {
    let left = this.parseConcat();
    while (this.at("operator", "+") || this.at("operator", "-")) {
      const op = this.advance().value as "+" | "-";
      left = { kind: "binary", op, left, right: this.parseConcat() };
    }
    return left;
  }

  private parseConcat(): ExprNode {
    let left = this.parseMath2();
    while (this.accept("operator", "~")) {
      left = { kind: "binary", op: "~", left, right: this.parseMath2() };
    }
    return left;
  }

  private parseMath2(): ExprNode {
    let left = this.parseUnary();
    while (
      this.at("operator", "*") ||
      this.at("operator", "/") ||
      this.at("operator", "//") ||
      this.at("operator", "%")
    ) {
      const op = this.advance().value as "*" | "/" | "//" | "%";
      left = { kind: "binary", op, left, right: this.parseUnary() };
    }
    return left;
  }

  private parseUnary(): ExprNode {
    let node: ExprNode;
    if (this.at("operator", "-") || this.at("operator", "+")) {
      const op = this.advance().value as "-" | "+";
      node = { kind: "unary", op, operand: this.parseUnary() };
    } else {
      node = this.parsePrimary();
    }
    node = this.parsePostfix(node);
    return this.parseFilterExpression(node);
  }

  /** Attribute access, subscripting and calls — tighter than any operator. */
  private parsePostfix(node: ExprNode): ExprNode {
    for (;;) {
      if (this.accept("punct", ".")) {
        const name = this.expect("name");
        node = { kind: "attribute", target: node, attr: name.value };
        continue;
      }
      if (this.accept("punct", "[")) {
        const index = this.parseExpression();
        this.expect("punct", "]");
        node = { kind: "index", target: node, index };
        continue;
      }
      if (this.at("punct", "(")) {
        node = { kind: "call", target: node, args: this.parseArguments() };
        continue;
      }
      return node;
    }
  }

  /** `| filter[(args)]` and `is [not] test` — same level, left to right. */
  private parseFilterExpression(node: ExprNode): ExprNode {
    for (;;) {
      if (this.accept("operator", "|")) {
        const name = this.expect("name").value;
        const args = this.at("punct", "(") ? this.parseArguments() : [];
        node = { kind: "filter", target: node, name, args };
        continue;
      }
      if (this.at("name", "is")) {
        this.advance();
        const negated = this.accept("name", "not");
        const name = this.expect("name").value;
        if (name in KEYWORD_LITERALS) {
          // `x is None` is an identity comparison in the `where` dialect (Python), and Jinja's
          // `is none` test answers the same question. One node kind serves both.
          const right: ExprNode = { kind: "literal", value: KEYWORD_LITERALS[name] as boolean | null };
          node = { kind: "compare", op: negated ? "is not" : "is", left: node, right };
          continue;
        }
        node = { kind: "test", target: node, name, negated };
        continue;
      }
      return node;
    }
  }

  private parseArguments(): ExprNode[] {
    this.expect("punct", "(");
    const args: ExprNode[] = [];
    if (!this.at("punct", ")")) {
      do {
        args.push(this.parseExpression());
      } while (this.accept("punct", ","));
    }
    this.expect("punct", ")");
    return args;
  }

  private parsePrimary(): ExprNode {
    const token = this.current;

    if (token.type === "string" || token.type === "number") {
      this.advance();
      return { kind: "literal", value: token.literal as string | number };
    }

    if (token.type === "name") {
      if (token.value in KEYWORD_LITERALS) {
        this.advance();
        return { kind: "literal", value: KEYWORD_LITERALS[token.value] as boolean | null };
      }
      this.advance();
      return { kind: "name", name: token.value };
    }

    if (this.accept("punct", "(")) {
      const node = this.parseExpression();
      if (this.at("punct", ",")) {
        // Tuples exist in Jinja but nothing in the Blueprint vocabulary produces one; refusing is
        // better than half-supporting a value the rest of the engine could not render.
        throw this.error("tuples are not supported by the embedded engine");
      }
      this.expect("punct", ")");
      return node;
    }

    if (this.accept("punct", "[")) {
      const items: ExprNode[] = [];
      if (!this.at("punct", "]")) {
        do {
          items.push(this.parseExpression());
        } while (this.accept("punct", ","));
      }
      this.expect("punct", "]");
      return { kind: "list", items };
    }

    if (this.accept("punct", "{")) {
      const entries: (readonly [ExprNode, ExprNode])[] = [];
      if (!this.at("punct", "}")) {
        do {
          const key = this.parseExpression();
          this.expect("punct", ":");
          entries.push([key, this.parseExpression()] as const);
        } while (this.accept("punct", ","));
      }
      this.expect("punct", "}");
      return { kind: "dict", entries };
    }

    throw this.error(`unexpected ${this.describe(token)}`);
  }
}
