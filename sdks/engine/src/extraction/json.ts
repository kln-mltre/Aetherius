/**
 * JSON extraction, mirror of `core/extraction/json_extractor.py`.
 *
 * The shape of the result is part of the contract and easy to get wrong: an extraction always
 * yields a **list** of matches, even when the path matches exactly one value. That is why shipped
 * Blueprints write `{{ steps.fetch.title | first }}` rather than `{{ steps.fetch.title }}`.
 */

import { ExtractionError } from "../errors.js";
import { jsonPathFind } from "./jsonpath.js";
import { evaluateWhere, parseWhere } from "./where.js";

export interface JsonExtractSpec {
  readonly from: "json";
  /** JSONPath expression, e.g. `$[*]`. */
  readonly path: string;
  /** Per-item predicate, e.g. `item.eventCategory != 'Vacances'`. */
  readonly where?: string | undefined;
  /** Output name to a JSONPath relative to each matched item. */
  readonly fields?: Readonly<Record<string, string>> | undefined;
}

/** Run every spec against a JSON *body* and collect the results under their output names. */
export function extractJson(
  body: string,
  specs: Readonly<Record<string, JsonExtractSpec>>,
): Record<string, unknown> {
  let data: unknown;
  try {
    data = JSON.parse(body);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new ExtractionError(`Cannot parse JSON response body: ${reason}`);
  }

  const result: Record<string, unknown> = {};
  for (const [name, spec] of Object.entries(specs)) {
    result[name] = runSpec(spec, data);
  }
  return result;
}

function runSpec(spec: JsonExtractSpec, data: unknown): unknown[] {
  let items = jsonPathFind(spec.path, data);

  if (spec.where !== undefined && spec.where !== null && spec.where !== "") {
    const predicate = parseWhere(spec.where);
    items = items.filter((item) => evaluateWhere(predicate, spec.where as string, item));
  }

  const fields = spec.fields;
  if (fields !== undefined && Object.keys(fields).length > 0) {
    // A non-object match has no fields to read; Python maps it to an empty dict, so every field
    // comes out null rather than the extraction blowing up mid-list.
    return items.map((item) => extractFields(isRecord(item) ? item : {}, fields));
  }
  return items;
}

function extractFields(
  item: Record<string, unknown>,
  fields: Readonly<Record<string, string>>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [name, path] of Object.entries(fields)) {
    const matches = jsonPathFind(path, item);
    out[name] = matches.length === 0 ? null : matches.length === 1 ? matches[0] : matches;
  }
  return out;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
