/**
 * The `StrictUndefined` marker.
 *
 * Jinja2's `StrictUndefined` is a choice, not a detail: a missing variable must raise, not render
 * an empty string. That is what turns a typo in a Blueprint into an immediate error instead of a
 * hole in the data at the far end of the pipeline.
 *
 * The marker is *lazy* — producing it is silent, using it raises — because `is defined` and the
 * `else` branch of an inline conditional both need to observe a missing value without failing:
 * `{{ steps.publish.post_id if steps.publish is defined else None }}` is a shipped Blueprint.
 */

import { TemplateError } from "../errors.js";

export class UndefinedValue {
  constructor(readonly what: string) {}
}

export function undefinedValue(what: string): UndefinedValue {
  return new UndefinedValue(what);
}

export function isUndefined(value: unknown): value is UndefinedValue {
  return value instanceof UndefinedValue;
}

/** Raise on any *use* of an undefined value. Never called by `is defined` or by `default`. */
export function failUndefined(value: UndefinedValue): never {
  // Same wording as the Python engine, which reports `Undefined variable in expression: 'name'`.
  throw new TemplateError(`Undefined variable in expression: ${value.what}`);
}
