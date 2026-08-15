/**
 * Semantic validation: is every step runnable by its effective act, on this engine?
 *
 * Mirror of `src/aetherius/core/blueprint/validator.py`, with the same walk — a step may override
 * the Blueprint act (`step.act`, multi-act composition), nested flow steps inherit the enclosing
 * step's effective act, and the recursion reports a readable path (`steps[3].then[0]`) so a
 * rejection buried in a branch is still actionable.
 *
 * The one thing this engine adds is the second rejection motif: an action the shared contract
 * grants to the act, that has no honest equivalent on a device. Telling that apart from "wrong
 * act" matters — confusing the two sends the author editing an `act` that was correct all along.
 */

import { BlueprintValidationError } from "../errors.js";
import {
  EMBEDDED_ACTS,
  NOT_PORTABLE,
  embeddedCapabilities,
  isEmbeddedAct,
} from "./capabilities.js";
import { contractCapabilities, introducingAct, nestedStepFields } from "./contract.js";
import { checkPortableParams } from "./portability.js";
import type { Blueprint, StepModel } from "./types.js";

const EMBEDDED_ACT_LIST = EMBEDDED_ACTS.join(", ");

/**
 * Throw unless every step of *blueprint* is runnable by its effective act on this engine.
 *
 * @throws {BlueprintValidationError}
 */
export function validateForAct(blueprint: Blueprint): void {
  requireEmbeddedAct(blueprint.act, "the Blueprint");

  const steps = blueprint.steps ?? [];
  if (steps.length === 0) {
    // A goal-only Blueprint is the Phantom contract, and Phantom is not embeddable at all.
    throw new BlueprintValidationError(
      "A goal-only Blueprint (no 'steps') requires act='phantom', which stays on the Python " +
        "engine: the embedded engine runs scripted Blueprints only.",
    );
  }

  steps.forEach((step, index) => validateStep(step, blueprint.act, `steps[${index}]`));
}

function requireEmbeddedAct(act: string, subject: string): void {
  if (isEmbeddedAct(act)) return;
  throw new BlueprintValidationError(
    `Act '${act}' is not supported by the embedded engine (${subject} declares it): ` +
      `Acts III/IV stay on the Python engine. Embedded acts: ${EMBEDDED_ACT_LIST}.`,
  );
}

function validateStep(step: StepModel, inheritedAct: string, path: string): void {
  const act = step.act ?? inheritedAct;
  if (act !== inheritedAct) requireEmbeddedAct(act, `step ${stepLabel(step)}`);

  if (!embeddedCapabilities(act).has(step.action)) {
    throw rejection(step, act, path);
  }

  checkExtractDialects(step, stepLabel(step), path);
  checkPortableParams(step, stepLabel(step), path);

  for (const field of nestedStepFields(step.action)) {
    const nested = step[field];
    if (nested === undefined || nested === null) continue;
    if (!Array.isArray(nested)) {
      // The schema already enforces this shape; keep the check so a caller that skipped the
      // loader still gets a typed error rather than a crash mid-walk.
      throw new BlueprintValidationError(
        `Step ${stepLabel(step)}: '${field}' must be a list of steps (at ${path}.${field}).`,
      );
    }
    nested.forEach((child, index) =>
      // Nested steps inherit the enclosing step's effective act.
      validateStep(child as StepModel, act, `${path}.${field}[${index}]`),
    );
  }
}

/**
 * Keys of the JSON and HTML dialects. `from: "text"` renders the whole decoded body, so none of them
 * can do anything — and a spec carrying one believes it filters when it does not. Mirror of
 * `core/blueprint/validator.py`: this rule is the contract's, not this engine's.
 */
const TEXT_FOREIGN_KEYS = [
  "path",
  "where",
  "fields",
  "selector",
  "selector_type",
  "attr",
  "multiple",
] as const;

/** Throw unless every extraction spec of *step* agrees with the dialect it declares. */
function checkExtractDialects(step: StepModel, label: string, path: string): void {
  const extract = step["extract"];
  if (extract === null || typeof extract !== "object" || Array.isArray(extract)) return;

  for (const [name, raw] of Object.entries(extract as Record<string, unknown>)) {
    if (raw === null || typeof raw !== "object") continue;
    const spec = raw as Record<string, unknown>;
    if (spec["from"] !== "text") continue;

    const foreign = TEXT_FOREIGN_KEYS.filter((key) => key in spec);
    if (foreign.length === 0) continue;
    throw new BlueprintValidationError(
      `Step ${label}: extraction '${name}' declares from='text' with ` +
        `${foreign.map((key) => `'${key}'`).join(", ")}: a text extraction returns the whole ` +
        `decoded body, so there is nothing to select or filter (at ${path}.extract.${name}).`,
    );
  }
}

/** Pick the message that names the actual problem: unknown action, wrong act, or not portable. */
function rejection(step: StepModel, act: string, path: string): BlueprintValidationError {
  const { action } = step;
  const subject = `Step ${stepLabel(step)}: action '${action}'`;

  if (contractCapabilities(act).has(action)) {
    const reason = NOT_PORTABLE[action];
    return new BlueprintValidationError(
      `${subject} is supported by act='${act}' but not by the embedded engine` +
        (reason ? ` (${reason})` : "") +
        `: run this Blueprint on the Python engine (at ${path}).`,
    );
  }

  const origin = introducingAct(action);
  if (origin === undefined) {
    return new BlueprintValidationError(`${subject} is not a known action (at ${path}).`);
  }
  if (!isEmbeddedAct(origin)) {
    return new BlueprintValidationError(
      `${subject} requires act='${origin}', which stays on the Python engine (at ${path}).`,
    );
  }
  return new BlueprintValidationError(
    `${subject} is not supported by act='${act}' ` +
      `(requires act='${origin}' or higher — set it on the blueprint or on this step) (at ${path}).`,
  );
}

function stepLabel(step: StepModel): string {
  return step.id === undefined ? "<unnamed>" : `'${step.id}'`;
}
