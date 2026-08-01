/**
 * Operator semantics — Python's, not JavaScript's.
 *
 * Split out of eval.ts so that file is the tree walk and this one is the arithmetic: every function
 * here answers "what would Python do", and the differences are the whole point. `-7 % 3` is `2`
 * here and `-1` in JavaScript; `[1, 2] == [1, 2]` is true here and false with `===`; `True == 1` is
 * true; comparing a string to a number raises instead of coercing.
 */

import { TemplateError } from "../errors.js";
import { pythonStr } from "./truthy.js";
import { failUndefined, isUndefined } from "./undefined.js";

export function binary(op: string, left: unknown, right: unknown): unknown {
  if (op === "~") return pythonStr(left) + pythonStr(right);

  if (op === "+") {
    if (typeof left === "string" && typeof right === "string") return left + right;
    if (Array.isArray(left) && Array.isArray(right)) return [...left, ...right];
  }

  const a = numeric(left, op);
  const b = numeric(right, op);
  switch (op) {
    case "+":
      return a + b;
    case "-":
      return a - b;
    case "*":
      return a * b;
    case "/":
      return divide(a, b);
    case "//":
      return Math.floor(divide(a, b));
    default:
      // Python's modulo follows the sign of the divisor; JavaScript's follows the dividend.
      return ((a % nonZero(b)) + b) % b;
  }
}

export function compare(op: string, left: unknown, right: unknown): boolean {
  switch (op) {
    case "==":
      return pyEquals(left, right);
    case "!=":
      return !pyEquals(left, right);
    case "in":
      return contains(right, left);
    case "not in":
      return !contains(right, left);
    case "is":
      return left === right;
    case "is not":
      return left !== right;
    default:
      return ordered(op, left, right);
  }
}

/** Python equality: structural for containers, and `True == 1`. */
export function pyEquals(left: unknown, right: unknown): boolean {
  if (left === right) return true;

  if (typeof left === "boolean" || typeof right === "boolean") {
    const a = typeof left === "boolean" ? Number(left) : left;
    const b = typeof right === "boolean" ? Number(right) : right;
    if (typeof a === "number" && typeof b === "number") return a === b;
  }

  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((item, i) => pyEquals(item, right[i]));
  }

  if (isRecord(left) && isRecord(right)) {
    const keys = Object.keys(left);
    return (
      keys.length === Object.keys(right).length && keys.every((key) => pyEquals(left[key], right[key]))
    );
  }

  return false;
}

/** Python's own truthiness, used *inside* expressions — not `isTruthy`, see eval.ts. */
export function pyTruth(value: unknown): boolean {
  if (isUndefined(value)) failUndefined(value);
  if (value === null || value === undefined) return false;
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return value.length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function ordered(op: string, left: unknown, right: unknown): boolean {
  const numbers =
    (typeof left === "number" || typeof left === "boolean") &&
    (typeof right === "number" || typeof right === "boolean");
  if (!numbers && !(typeof left === "string" && typeof right === "string")) {
    // Python refuses to order a string against a number rather than coercing one of them.
    throw new TemplateError(`Cannot compare ${pythonStr(left)} and ${pythonStr(right)} with '${op}'.`);
  }
  const a = typeof left === "boolean" ? Number(left) : left;
  const b = typeof right === "boolean" ? Number(right) : right;
  switch (op) {
    case "<":
      return a < b;
    case "<=":
      return a <= b;
    case ">":
      return a > b;
    default:
      return a >= b;
  }
}

function contains(haystack: unknown, needle: unknown): boolean {
  if (typeof haystack === "string") return haystack.includes(pythonStr(needle));
  if (Array.isArray(haystack)) return haystack.some((item) => pyEquals(item, needle));
  if (isRecord(haystack)) {
    return Object.prototype.hasOwnProperty.call(haystack, pythonStr(needle));
  }
  throw new TemplateError(`'in' expects a string, list or object, got ${pythonStr(haystack)}.`);
}

function numeric(value: unknown, op: string): number {
  if (typeof value === "number") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  throw new TemplateError(`Operator '${op}' expects numbers, got ${pythonStr(value)}.`);
}

function divide(a: number, b: number): number {
  return a / nonZero(b);
}

function nonZero(value: number): number {
  if (value === 0) throw new TemplateError("Division by zero in expression.");
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
