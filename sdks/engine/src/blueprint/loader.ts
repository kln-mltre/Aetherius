/**
 * Load a Blueprint: parse, then validate against the JSON Schema. Mirror of
 * `src/aetherius/core/blueprint/loader.py`.
 *
 * Two steps, two errors, as on the Python side: `BlueprintLoadError` says the bytes are not a
 * Blueprint document at all, `BlueprintSchemaError` says the document is structurally wrong. The
 * third step — is this Blueprint coherent for its act, and runnable *here* — lives in
 * `validator.ts` and raises `BlueprintValidationError`.
 *
 * Two deliberate divergences from Python, both consequences of running on a device:
 *   - no file path overload: the engine has no filesystem convention of its own. Blueprint
 *     delivery (bundled asset, remote fetch, cache) is the application's business, and gets its
 *     own milestone (3-F). Callers hand over text or a parsed object.
 *   - JSON only, no YAML: shipping a YAML parser to a phone to read files the tooling always
 *     writes as JSON would be a poor trade.
 */

import { BlueprintLoadError, BlueprintSchemaError } from "../errors.js";
import { formatViolations, schemaViolations } from "./schema.js";
import type { Blueprint } from "./types.js";

/**
 * Constraints the pydantic models enforce that the JSON Schema cannot.
 *
 * `contracts/blueprint.schema.json` requires `steps` **or** `goal` through `anyOf`, which an empty
 * `steps: []` satisfies — the key is there. Python catches it in `Blueprint._require_steps_or_goal`
 * and reports a schema-level error, so this engine has to as well, or the same document would be
 * accepted here and rejected there. Kept explicit and enumerated rather than folded into the
 * semantic validator: it is a model rule, and its error type says so.
 */
function modelViolations(data: Record<string, unknown>): string[] {
  const steps = data["steps"];
  const hasSteps = Array.isArray(steps) && steps.length > 0;
  const hasGoal = typeof data["goal"] === "string" && data["goal"].length > 0;
  return hasSteps || hasGoal ? [] : ["A Blueprint must declare either 'steps' or 'goal'."];
}

/**
 * Validate an in-memory Blueprint document and return it typed.
 *
 * *source* only labels error messages, exactly like the Python counterpart.
 *
 * @throws {BlueprintSchemaError} the document violates the schema or a model rule.
 */
export function validateBlueprintData(data: unknown, source = "<data>"): Blueprint {
  const violations = schemaViolations(data);
  if (violations.length > 0) {
    throw new BlueprintSchemaError(
      `Blueprint schema violation in ${source}: ${formatViolations(violations)}`,
    );
  }

  const model = modelViolations(data as Record<string, unknown>);
  if (model.length > 0) {
    throw new BlueprintSchemaError(
      `Blueprint model validation failed in ${source}: ${model.join("; ")}`,
    );
  }

  return data as Blueprint;
}

/**
 * Parse Blueprint JSON text and validate it.
 *
 * @throws {BlueprintLoadError} the text is not parseable JSON.
 * @throws {BlueprintSchemaError} the document violates the schema or a model rule.
 */
export function parseBlueprint(text: string, source = "<text>"): Blueprint {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch (cause) {
    const reason = cause instanceof Error ? cause.message : String(cause);
    throw new BlueprintLoadError(`Cannot parse Blueprint: ${source} — ${reason}`);
  }
  return validateBlueprintData(data, source);
}
