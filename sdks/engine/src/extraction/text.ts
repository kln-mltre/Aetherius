/**
 * Text extraction, mirror of `core/extraction/text_extractor.py`.
 *
 * The third dialect, and the one with nothing to configure: it renders the whole decoded body. A
 * response that is neither JSON nor HTML — iCalendar, CSV, `text/plain` — is data too, and reading
 * it is the application's job. There is deliberately no `regex` sibling: a second regular-expression
 * grammar across Python and JavaScript is a divergence waiting to happen.
 *
 * The body arrives twice over: as the string the client already decoded, and — when the caller read
 * the response as bytes — as those bytes plus the `Content-Type`. Only the second form can honour a
 * charset the header declares, which is why the driver asks for bytes as soon as a `from: "text"`
 * spec is present (see `acts/vector/driver.ts`).
 */

import { decodeBody } from "./charset.js";

export interface TextExtractSpec {
  readonly from: "text";
}

/** Where the body came from: the decoded string, and the bytes when the caller kept them. */
export interface BodySource {
  readonly bytes?: Uint8Array | undefined;
  readonly contentType?: string | undefined;
}

/**
 * Give every named spec the whole decoded body.
 *
 * An empty body yields an empty string, not `null`: a response with nothing in it is a result.
 */
export function extractText(
  body: string,
  specs: Readonly<Record<string, TextExtractSpec>>,
  source: BodySource = {},
): Record<string, unknown> {
  const { bytes } = source;
  // Without bytes there is nothing to re-decode: the string is already the UTF-8 reading, which is
  // what an absent or unknown charset would have produced anyway.
  const text = bytes === undefined ? body : decodeBody(bytes, source.contentType);

  const result: Record<string, unknown> = {};
  for (const name of Object.keys(specs)) result[name] = text;
  return result;
}
