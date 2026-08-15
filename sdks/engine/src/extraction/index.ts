/**
 * Declarative extraction: the `extract` map of an `http.request` step.
 *
 * `dispatchExtract` is the twin of `dispatch_extract` in `core/extraction/dispatch.py` — same
 * defaults, same split between the two dialects, so the milestone that wires Act I (3-C) has
 * nothing left to decide.
 *
 * The two dialects look alike and must not be merged. Vector reads a response with
 * `{from, path, where, fields}` (JSON) or `{from, selector, selector_type, attr, multiple}` (HTML);
 * Continuum reads a live DOM with `outputs: {name: {selector, as, …}}` — a different vocabulary,
 * arriving with the WebView driver at milestone 3-D.
 */

import { pyTruth } from "../expr/index.js";
import { extractHtml, type HtmlExtractSpec } from "./html.js";
import { extractJson, type JsonExtractSpec } from "./json.js";
import { extractText, type BodySource, type TextExtractSpec } from "./text.js";

export type { HtmlExtractSpec } from "./html.js";
export type { JsonExtractSpec } from "./json.js";
export type { BodySource, TextExtractSpec } from "./text.js";
export { decodeBody, decodeUtf8, resolveCharset } from "./charset.js";
export { extractHtml } from "./html.js";
export { extractJson } from "./json.js";
export { extractText } from "./text.js";
export { jsonPathFind, parseJsonPath } from "./jsonpath.js";
export { evaluateWhere, parseWhere } from "./where.js";

/**
 * Build the three spec maps from a step's raw `extract` block and run them against *body*.
 *
 * Defaults mirror `core/extraction/dispatch.py` exactly: `from` defaults to `json`, `path` to `$`,
 * `selector_type` to `css`, `multiple` to `true`. Specs are taken verbatim — neither engine renders
 * `{{ }}` inside a selector or a path, and only changing both at once could.
 *
 * *source* carries the raw bytes and the `Content-Type` when the caller kept them; only the text
 * dialect reads it, and only it can decode per the declared charset.
 */
export function dispatchExtract(
  body: string,
  rawSpecs: Readonly<Record<string, unknown>>,
  source: BodySource = {},
): Record<string, unknown> {
  const jsonSpecs: Record<string, JsonExtractSpec> = {};
  const htmlSpecs: Record<string, HtmlExtractSpec> = {};
  const textSpecs: Record<string, TextExtractSpec> = {};

  for (const [name, raw] of Object.entries(rawSpecs)) {
    const spec = (raw ?? {}) as Record<string, unknown>;
    const from = spec["from"] ?? "json";
    if (from === "json") {
      jsonSpecs[name] = {
        from: "json",
        path: asString(spec["path"], "$"),
        where: optionalString(spec["where"]),
        fields: asFields(spec["fields"]),
      };
    } else if (from === "text") {
      textSpecs[name] = { from: "text" };
    } else {
      // Anything unknown stays HTML, as on the Python side: tightening it here would reject
      // Blueprints that run today, for a typo the validator is better placed to catch.
      htmlSpecs[name] = {
        from: "html",
        selector: asString(spec["selector"], ""),
        selector_type: asString(spec["selector_type"], "css"),
        attr: optionalString(spec["attr"]),
        // Python tests `multiple` for truthiness, so `0` and `""` mean "single" there too; `!== false`
        // would silently return a list where the other engine returns one value.
        multiple: spec["multiple"] === undefined ? true : pyTruth(spec["multiple"]),
      };
    }
  }

  return {
    ...(Object.keys(jsonSpecs).length > 0 ? extractJson(body, jsonSpecs) : {}),
    ...(Object.keys(htmlSpecs).length > 0 ? extractHtml(body, htmlSpecs) : {}),
    ...(Object.keys(textSpecs).length > 0 ? extractText(body, textSpecs, source) : {}),
  };
}

function asString(value: unknown, fallback: string): string {
  return typeof value === "string" ? value : fallback;
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asFields(value: unknown): Record<string, string> {
  if (value === null || typeof value !== "object") return {};
  const out: Record<string, string> = {};
  for (const [name, path] of Object.entries(value as Record<string, unknown>)) {
    if (typeof path === "string") out[name] = path;
  }
  return out;
}
