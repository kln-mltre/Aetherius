/**
 * Parameter-level portability checks.
 *
 * `capabilities.ts` answers "can this engine run this *action*". This module answers the narrower
 * question that only shows up once expressions and extraction exist: can it run this action **as
 * configured**. Today there is exactly one such case, and it earns its place:
 *
 *   `selector_type: "xpath"` in an `http.request` extraction. Outside a browser, XPath needs an
 *   engine of its own — `books-restock-notify` uses `normalize-space(//p[contains(@class, …)])`,
 *   a full XPath 1.0 expression with functions. Reproducing lxml is out of proportion with the
 *   use; declaring the limit is the honest answer.
 *
 * It is refused **at validation**, not at extraction time, for the same reason `upload` is: a
 * Blueprint that cannot run must say so before the run starts, never in the middle of one. The
 * check is safe to make static because `selector_type` is a schema enum — there is no expression to
 * render, so no risk of refusing a Blueprint that would in fact have worked. A JSONPath outside the
 * supported subset gets the opposite treatment (a typed error at extraction time): a parser
 * stricter than `jsonpath-ng` would reject correct Blueprints, and a false refusal is worse than a
 * clean failure. Both limits are written up in docs/embedded.md.
 */

import { BlueprintValidationError } from "../errors.js";
import type { StepModel } from "./types.js";

/** Throw unless every parameter of *step* is honourable on this engine. */
export function checkPortableParams(step: StepModel, label: string, path: string): void {
  const extract = step["extract"];
  if (extract === null || typeof extract !== "object" || Array.isArray(extract)) return;

  for (const [name, raw] of Object.entries(extract as Record<string, unknown>)) {
    if (raw === null || typeof raw !== "object") continue;
    const spec = raw as Record<string, unknown>;
    if (spec["selector_type"] !== "xpath") continue;
    throw new BlueprintValidationError(
      `Step ${label}: extraction '${name}' uses selector_type='xpath', which the embedded engine ` +
        "does not support (no XPath engine without a DOM): use a CSS selector, or run this " +
        `Blueprint on the Python engine (at ${path}).`,
    );
  }
}
