/**
 * Typed access to `contracts/actions.json` — the action vocabulary, generated from the Python
 * registry (`src/aetherius/core/actions/`) and inlined into this package at build time.
 *
 * This engine does not redeclare which actions exist, what each act supports, or how a flow step
 * nests: it reads them. That is the whole point of the generated contract — two engines, one
 * source. What it *does* declare on its own is the narrower set it can honour on a device, in
 * `capabilities.ts`.
 */

import { ACTIONS_CONTRACT } from "../generated/actions-contract.js";
import type { ActName } from "./types.js";

export interface ParamSpec {
  readonly name: string;
  readonly kind: "string" | "number" | "integer" | "boolean" | "object" | "array";
  readonly required: boolean;
  readonly default: unknown;
  readonly help: string;
  readonly placeholder: string;
}

export interface ActionSpec {
  readonly summary: string;
  readonly params: readonly ParamSpec[];
}

export interface ActionsContract {
  readonly version: string;
  readonly description: string;
  readonly actions: Readonly<Record<string, ActionSpec>>;
  /**
   * Act name to the actions it supports. Key order is the **escalation order** (vector, continuum,
   * oracle, phantom): `introducingAct` reads it to tell an author which act they are missing.
   */
  readonly act_capabilities: Readonly<Record<string, readonly string[]>>;
  readonly flow_actions: readonly string[];
  /** Flow action to the step fields holding nested step lists (`if` -> then/else, ...). */
  readonly flow_nested_fields: Readonly<Record<string, readonly string[]>>;
}

export const contract: ActionsContract = ACTIONS_CONTRACT;

/** The actions *act* supports according to the shared contract, whatever this engine can run. */
export function contractCapabilities(act: string): ReadonlySet<string> {
  return new Set(contract.act_capabilities[act] ?? []);
}

/** Every act the shared contract knows about, in escalation order. */
export function contractActs(): readonly ActName[] {
  return Object.keys(contract.act_capabilities) as ActName[];
}

/**
 * The first act introducing *action*, or undefined when no act supports it at all.
 *
 * Mirrors `_CAPABILITY_ORIGIN` in core/blueprint/validator.py, derived rather than duplicated: the
 * capability table already encodes the escalation chain, so restating it would be one more thing
 * to keep in step.
 */
export function introducingAct(action: string): ActName | undefined {
  return contractActs().find((act) => contract.act_capabilities[act]?.includes(action));
}

/** The step fields carrying nested steps for *action* (empty when it is not a flow action). */
export function nestedStepFields(action: string): readonly string[] {
  return contract.flow_nested_fields[action] ?? [];
}
