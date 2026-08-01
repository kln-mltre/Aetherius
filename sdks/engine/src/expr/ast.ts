/**
 * Nodes of the expression AST.
 *
 * The grammar is the subset of Jinja2 a Blueprint actually uses (see docs/embedded.md), plus what
 * the `where` predicate needs — one tree shape for the three consumers (rendering, `isTruthy`,
 * `where`), because three grammars would be three chances to diverge.
 *
 * The node set is also the unit the `where` allowlist works on: mirroring Python's `_ALLOWED_NODES`
 * means naming node kinds, so they are named here rather than inferred from the parser's shape.
 */

export type BinaryOp = "+" | "-" | "*" | "/" | "//" | "%" | "~";

export type CompareOp = "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not in" | "is" | "is not";

export type ExprNode =
  | LiteralNode
  | NameNode
  | AttributeNode
  | IndexNode
  | CallNode
  | FilterNode
  | TestNode
  | UnaryNode
  | BinaryNode
  | CompareNode
  | BoolOpNode
  | ConditionalNode
  | ListNode
  | DictNode;

export interface LiteralNode {
  readonly kind: "literal";
  readonly value: string | number | boolean | null;
}

export interface NameNode {
  readonly kind: "name";
  readonly name: string;
}

export interface AttributeNode {
  readonly kind: "attribute";
  readonly target: ExprNode;
  readonly attr: string;
}

export interface IndexNode {
  readonly kind: "index";
  readonly target: ExprNode;
  readonly index: ExprNode;
}

/** A call, only ever applied to a filter argument list (`add_days(7)`); bare calls are rejected. */
export interface CallNode {
  readonly kind: "call";
  readonly target: ExprNode;
  readonly args: readonly ExprNode[];
}

export interface FilterNode {
  readonly kind: "filter";
  readonly target: ExprNode;
  readonly name: string;
  readonly args: readonly ExprNode[];
}

/** `x is defined` / `x is not defined`. Jinja calls these tests; only `defined` is supported. */
export interface TestNode {
  readonly kind: "test";
  readonly target: ExprNode;
  readonly name: string;
  readonly negated: boolean;
}

export interface UnaryNode {
  readonly kind: "unary";
  readonly op: "not" | "-" | "+";
  readonly operand: ExprNode;
}

export interface BinaryNode {
  readonly kind: "binary";
  readonly op: BinaryOp;
  readonly left: ExprNode;
  readonly right: ExprNode;
}

export interface CompareNode {
  readonly kind: "compare";
  readonly op: CompareOp;
  readonly left: ExprNode;
  readonly right: ExprNode;
}

export interface BoolOpNode {
  readonly kind: "boolop";
  readonly op: "and" | "or";
  readonly left: ExprNode;
  readonly right: ExprNode;
}

/** `a if cond else b`. Evaluated lazily, as in Jinja — see eval.ts. */
export interface ConditionalNode {
  readonly kind: "conditional";
  readonly body: ExprNode;
  readonly condition: ExprNode;
  readonly orElse: ExprNode | undefined;
}

export interface ListNode {
  readonly kind: "list";
  readonly items: readonly ExprNode[];
}

export interface DictNode {
  readonly kind: "dict";
  readonly entries: readonly (readonly [ExprNode, ExprNode])[];
}

/** Walk every node of *root*, parents before children. Used by the `where` allowlist. */
export function walk(root: ExprNode, visit: (node: ExprNode) => void): void {
  visit(root);
  for (const child of children(root)) walk(child, visit);
}

function children(node: ExprNode): readonly ExprNode[] {
  switch (node.kind) {
    case "literal":
    case "name":
      return [];
    case "attribute":
      return [node.target];
    case "index":
      return [node.target, node.index];
    case "call":
      return [node.target, ...node.args];
    case "filter":
      return [node.target, ...node.args];
    case "test":
      return [node.target];
    case "unary":
      return [node.operand];
    case "binary":
    case "compare":
    case "boolop":
      return [node.left, node.right];
    case "conditional":
      return node.orElse === undefined
        ? [node.body, node.condition]
        : [node.body, node.condition, node.orElse];
    case "list":
      return node.items;
    case "dict":
      return node.entries.flatMap(([key, value]) => [key, value]);
  }
}
