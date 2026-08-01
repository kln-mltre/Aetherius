/**
 * Token cursor: the plumbing the grammar sits on.
 *
 * Split out of parser.ts so that file reads as the precedence ladder and nothing else — the two
 * concerns (where am I in the token stream, what does the grammar allow next) are easy to tangle,
 * and the ladder is the part someone will come back to read.
 */

import { TemplateError } from "../errors.js";
import type { Token, TokenType } from "./lexer.js";

export class TokenCursor {
  private index = 0;

  constructor(
    private readonly tokens: readonly Token[],
    private readonly source: string,
  ) {}

  protected get current(): Token {
    return this.tokens[this.index] as Token;
  }

  protected peek(offset = 1): Token {
    return this.tokens[this.index + offset] ?? (this.tokens[this.tokens.length - 1] as Token);
  }

  protected advance(): Token {
    const token = this.current;
    if (token.type !== "eof") this.index += 1;
    return token;
  }

  protected at(type: TokenType, value?: string): boolean {
    return this.current.type === type && (value === undefined || this.current.value === value);
  }

  protected accept(type: TokenType, value?: string): boolean {
    if (!this.at(type, value)) return false;
    this.advance();
    return true;
  }

  protected expect(type: TokenType, value?: string): Token {
    if (!this.at(type, value)) {
      throw this.error(`expected ${value ?? type}, got ${this.describe(this.current)}`);
    }
    return this.advance();
  }

  expectEnd(): void {
    if (!this.at("eof")) throw this.error(`unexpected ${this.describe(this.current)}`);
  }

  protected describe(token: Token): string {
    return token.type === "eof" ? "end of expression" : JSON.stringify(token.value);
  }

  /** Every syntax error quotes the offending expression: the Blueprint author needs to find it. */
  protected error(detail: string): TemplateError {
    return new TemplateError(`Invalid expression ${JSON.stringify(this.source.trim())}: ${detail}.`);
  }
}
