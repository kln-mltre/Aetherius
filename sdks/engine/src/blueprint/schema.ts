/**
 * Structural validation against `contracts/blueprint.schema.json`.
 *
 * The validator is **precompiled** (see scripts/compile-schema.mjs): what ships is ordinary
 * JavaScript, because the mobile JS engine refuses `eval` and `new Function`. This module is the
 * typed seam over that generated artifact — nothing else in the engine imports it directly.
 */

import validateBlueprintSchema from "../generated/blueprint-validator.js";
import { SCHEMA_SHA256 } from "../generated/schema-meta.js";

export { SCHEMA_SHA256 };

/** One structural violation, in the shape Ajv reports it. */
export interface SchemaViolation {
  /** JSON Pointer to the offending value, e.g. `/steps/2/action`. Empty for the document itself. */
  readonly instancePath: string;
  readonly message: string;
}

interface CompiledValidator {
  (data: unknown): boolean;
  errors?: readonly { instancePath?: string; message?: string }[] | null;
}

const validate = validateBlueprintSchema as unknown as CompiledValidator;

/** Return every schema violation in *data*; an empty array means the document is structurally valid. */
export function schemaViolations(data: unknown): SchemaViolation[] {
  if (validate(data)) return [];
  return (validate.errors ?? []).map((error) => ({
    instancePath: error.instancePath ?? "",
    message: error.message ?? "is invalid",
  }));
}

/** Render violations the way the Python loader renders jsonschema's: one readable line. */
export function formatViolations(violations: readonly SchemaViolation[]): string {
  return violations
    .map(({ instancePath, message }) => (instancePath ? `${instancePath} ${message}` : message))
    .join("; ");
}
