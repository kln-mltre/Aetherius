/**
 * Tokeniser for the expression language.
 *
 * Hand-written rather than generated: the token set is small and fixed, and a generator would need
 * either a build step or dynamic code — the one thing this engine cannot have (Hermes refuses
 * `eval` and `new Function`, see docs/phase-3/README.md, decision 4).
 */

import { TemplateError } from "../errors.js";

export type TokenType = "name" | "number" | "string" | "operator" | "punct" | "eof";

export interface Token {
  readonly type: TokenType;
  /** Operators and punctuation carry their own text; names carry the identifier. */
  readonly value: string;
  /** Literal value for `number` and `string` tokens. */
  readonly literal?: string | number;
  readonly pos: number;
}

/**
 * Multi-character operators first: the scanner takes the longest match, so `<=` never lexes as
 * `<` followed by `=`. `//` (floor division) shares its prefix with `/`, same rule.
 */
const OPERATORS = [
  "==",
  "!=",
  "<=",
  ">=",
  "//",
  "<",
  ">",
  "+",
  "-",
  "*",
  "/",
  "%",
  "|",
  "~",
] as const;

const PUNCT = ["(", ")", "[", "]", "{", "}", ",", ":", "."] as const;

const NAME_START = /[A-Za-z_]/;
const NAME_PART = /[A-Za-z0-9_]/;
const DIGIT = /[0-9]/;

export function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;

  while (i < source.length) {
    const char = source[i] as string;

    if (/\s/.test(char)) {
      i += 1;
      continue;
    }

    if (char === '"' || char === "'") {
      const [value, next] = readString(source, i);
      tokens.push({ type: "string", value, literal: value, pos: i });
      i = next;
      continue;
    }

    if (DIGIT.test(char)) {
      const [value, next] = readNumber(source, i);
      tokens.push({ type: "number", value: String(value), literal: value, pos: i });
      i = next;
      continue;
    }

    if (NAME_START.test(char)) {
      let end = i + 1;
      while (end < source.length && NAME_PART.test(source[end] as string)) end += 1;
      tokens.push({ type: "name", value: source.slice(i, end), pos: i });
      i = end;
      continue;
    }

    const operator = OPERATORS.find((candidate) => source.startsWith(candidate, i));
    if (operator !== undefined) {
      tokens.push({ type: "operator", value: operator, pos: i });
      i += operator.length;
      continue;
    }

    const punct = PUNCT.find((candidate) => source.startsWith(candidate, i));
    if (punct !== undefined) {
      tokens.push({ type: "punct", value: punct, pos: i });
      i += punct.length;
      continue;
    }

    throw new TemplateError(
      `Unexpected character ${JSON.stringify(char)} at position ${i} in expression.`,
    );
  }

  tokens.push({ type: "eof", value: "", pos: source.length });
  return tokens;
}

function readString(source: string, start: number): [string, number] {
  const quote = source[start] as string;
  let out = "";
  let i = start + 1;

  while (i < source.length) {
    const char = source[i] as string;
    if (char === "\\") {
      const next = source[i + 1];
      if (next === undefined) break;
      out += unescape(next);
      i += 2;
      continue;
    }
    if (char === quote) return [out, i + 1];
    out += char;
    i += 1;
  }

  throw new TemplateError(`Unterminated string literal at position ${start} in expression.`);
}

function unescape(char: string): string {
  switch (char) {
    case "n":
      return "\n";
    case "t":
      return "\t";
    case "r":
      return "\r";
    default:
      // Covers \\ and \' and \" — anything else stands for itself, as in Python.
      return char;
  }
}

function readNumber(source: string, start: number): [number, number] {
  let i = start;
  while (i < source.length && DIGIT.test(source[i] as string)) i += 1;
  // A dot only continues the number when a digit follows, so `1.foo` stays an attribute access.
  if (source[i] === "." && DIGIT.test(source[i + 1] ?? "")) {
    i += 1;
    while (i < source.length && DIGIT.test(source[i] as string)) i += 1;
  }
  return [Number(source.slice(start, i)), i];
}
