/**
 * Body decoding, mirror of `core/extraction/text_extractor.py`.
 *
 * This module exists because the platform cannot be trusted to decode identically: `TextDecoder` is
 * **absent from React Native** and ICU-complete under Node, so leaning on it would make the
 * conformance corpus agree in CI and the phone disagree on a device — the exact failure mode the
 * corpus is there to catch. The decoders are therefore written here, and the label table is the
 * same bounded one the Python engine carries:
 *
 *     iso-8859-1 / latin-1 …  ->  strict Latin-1 (the Python codec, *not* the WHATWG alias to cp1252)
 *     windows-1252 / cp1252   ->  cp1252
 *     anything else, or none  ->  UTF-8
 *
 * Two decisions worth knowing before someone "fixes" them:
 *
 *   - **a BOM is not stripped.** `Response.text()` and the WHATWG decoder strip it; the Python codec
 *     does not, and Python is the reference here;
 *   - **invalid bytes are replaced, never thrown.** The UTF-8 decoder follows the WHATWG algorithm,
 *     which emits one U+FFFD per *maximal subpart* — byte-for-byte what CPython's
 *     `errors="replace"` does. A test pins the degenerate sequences on both engines.
 */

/** cp1252's 0x80–0x9F window; 0xFFFD marks the five bytes the Python codec leaves undefined. */
const CP1252_HIGH = [
  0x20ac, 0xfffd, 0x201a, 0x0192, 0x201e, 0x2026, 0x2020, 0x2021, 0x02c6, 0x2030, 0x0160, 0x2039,
  0x0152, 0xfffd, 0x017d, 0xfffd, 0xfffd, 0x2018, 0x2019, 0x201c, 0x201d, 0x2022, 0x2013, 0x2014,
  0x02dc, 0x2122, 0x0161, 0x203a, 0x0153, 0xfffd, 0x017e, 0x0178,
];

const CODECS: Readonly<Record<string, string>> = {
  "iso-8859-1": "iso-8859-1",
  "iso8859-1": "iso-8859-1",
  "iso_8859-1": "iso-8859-1",
  "latin-1": "iso-8859-1",
  latin1: "iso-8859-1",
  l1: "iso-8859-1",
  "windows-1252": "cp1252",
  cp1252: "cp1252",
  "win-1252": "cp1252",
};

const DEFAULT_CODEC = "utf-8";

/** Strings are built in chunks: `fromCharCode` over a whole 500 kB body would blow the stack. */
const CHUNK = 4096;

/** The codec to decode a body served with *contentType*, UTF-8 when it says nothing usable. */
export function resolveCharset(contentType: string | undefined | null): string {
  if (contentType === undefined || contentType === null || contentType === "") return DEFAULT_CODEC;

  for (const parameter of contentType.split(";").slice(1)) {
    const equals = parameter.indexOf("=");
    if (equals === -1) continue;
    if (parameter.slice(0, equals).trim().toLowerCase() !== "charset") continue;
    const label = parameter
      .slice(equals + 1)
      .trim()
      .replace(/^["']|["']$/g, "")
      .toLowerCase();
    return CODECS[label] ?? DEFAULT_CODEC;
  }
  return DEFAULT_CODEC;
}

/** Decode *bytes* per the charset declared by *contentType*. */
export function decodeBody(bytes: Uint8Array, contentType: string | undefined | null): string {
  const codec = resolveCharset(contentType);
  if (codec === "iso-8859-1") return decodeSingleByte(bytes, undefined);
  if (codec === "cp1252") return decodeSingleByte(bytes, CP1252_HIGH);
  return decodeUtf8(bytes);
}

/**
 * The WHATWG UTF-8 decoder, in replacement mode.
 *
 * Written out rather than approximated: the number of U+FFFD a truncated sequence produces is
 * observable, and "close enough" here means two engines rendering a different string for the same
 * broken response.
 */
export function decodeUtf8(bytes: Uint8Array): string {
  const out: string[] = [];
  const chunk: number[] = [];

  let codepoint = 0;
  let needed = 0;
  let seen = 0;
  let lower = 0x80;
  let upper = 0xbf;

  const emit = (value: number): void => {
    chunk.push(value);
    if (chunk.length >= CHUNK) {
      out.push(String.fromCodePoint(...chunk));
      chunk.length = 0;
    }
  };

  for (let index = 0; index < bytes.length; index += 1) {
    const byte = bytes[index] as number;

    if (needed === 0) {
      if (byte <= 0x7f) {
        emit(byte);
      } else if (byte >= 0xc2 && byte <= 0xdf) {
        needed = 1;
        codepoint = byte & 0x1f;
      } else if (byte >= 0xe0 && byte <= 0xef) {
        if (byte === 0xe0) lower = 0xa0;
        if (byte === 0xed) upper = 0x9f;
        needed = 2;
        codepoint = byte & 0x0f;
      } else if (byte >= 0xf0 && byte <= 0xf4) {
        if (byte === 0xf0) lower = 0x90;
        if (byte === 0xf4) upper = 0x8f;
        needed = 3;
        codepoint = byte & 0x07;
      } else {
        // Includes 0xC0/0xC1 (overlong leads) and every stray continuation byte.
        emit(0xfffd);
      }
      continue;
    }

    if (byte < lower || byte > upper) {
      // The offending byte is *reprocessed* as a fresh sequence start, which is what makes
      // `\xed\xa0\x80` three replacements rather than one.
      codepoint = 0;
      needed = 0;
      seen = 0;
      lower = 0x80;
      upper = 0xbf;
      index -= 1;
      emit(0xfffd);
      continue;
    }

    lower = 0x80;
    upper = 0xbf;
    codepoint = (codepoint << 6) | (byte & 0x3f);
    seen += 1;
    if (seen === needed) {
      emit(codepoint);
      codepoint = 0;
      needed = 0;
      seen = 0;
    }
  }

  if (needed !== 0) emit(0xfffd);
  if (chunk.length > 0) out.push(String.fromCodePoint(...chunk));
  return out.join("");
}

/** A single-byte codec: identity for Latin-1, plus a window for cp1252's 0x80–0x9F. */
function decodeSingleByte(bytes: Uint8Array, high: readonly number[] | undefined): string {
  const out: string[] = [];
  const chunk: number[] = [];

  for (let index = 0; index < bytes.length; index += 1) {
    const byte = bytes[index] as number;
    const mapped = high !== undefined && byte >= 0x80 && byte <= 0x9f;
    chunk.push(mapped ? (high[byte - 0x80] as number) : byte);
    if (chunk.length >= CHUNK) {
      out.push(String.fromCodePoint(...chunk));
      chunk.length = 0;
    }
  }

  if (chunk.length > 0) out.push(String.fromCodePoint(...chunk));
  return out.join("");
}
