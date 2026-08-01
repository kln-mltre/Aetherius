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

export type { HtmlExtractSpec } from "./html.js";
export type { JsonExtractSpec } from "./json.js";
export { extractHtml } from "./html.js";
export { extractJson } from "./json.js";
export { jsonPathFind, parseJsonPath } from "./jsonpath.js";
export { evaluateWhere, parseWhere } from "./where.js";

/**
 * Build the two spec maps from a step's raw `extract` block and run them against *body*.
 *
 * Defaults mirror `core/extraction/dispatch.py` exactly: `from` defaults to `json`, `path` to `$`,
 * `selector_type` to `css`, `multiple` to `true`. Specs are taken verbatim — neither engine renders
 * `{{ }}` inside a selector or a path, and only changing both at once could.
 */
export function dispatchExtract(
  body: string,
  rawSpecs: Readonly<Record<string, unknown>>,
): Record<string, unknown> {
  const jsonSpecs: Record<string, JsonExtractSpec> = {};
  const htmlSpecs: Record<string, HtmlExtractSpec> = {};

  for (const [name, raw] of Object.entries(rawSpecs)) {
    const spec = (raw ?? {}) as Record<string, unknown>;
    if ((spec["from"] ?? "json") === "json") {
      jsonSpecs[name] = {
        from: "json",
        path: asString(spec["path"], "$"),
        where: optionalString(spec["where"]),
        fields: asFields(spec["fields"]),
      };
    } else {
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
