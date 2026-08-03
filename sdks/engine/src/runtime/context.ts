/**
 * Per-run state, mirror of `src/aetherius/core/runtime/context.py`.
 *
 * One divergence, and it is a platform fact rather than a choice: `env`. The Python engine exposes
 * `os.environ`, which a device does not have. The table is therefore whatever the host handed over
 * — empty by default — so a Blueprint reading `{{ env.X }}` fails with the usual `StrictUndefined`
 * error instead of silently reading someone else's process.
 */

import type { Blueprint, InputSpec } from "../blueprint/types.js";
import type { RunContext } from "../driver.js";
import { BlueprintValidationError } from "../errors.js";
import type { Context } from "../expr/index.js";
import type { AbortSignalLike } from "../http.js";
import type { ApprovalGateway } from "./approvals.js";

export interface ContextInit {
  readonly runId: string;
  readonly blueprint: Blueprint;
  readonly inputs: Record<string, unknown>;
  readonly secrets: Record<string, string>;
  readonly env?: Record<string, string>;
  readonly approvals?: ApprovalGateway;
  readonly signal?: AbortSignalLike;
}

export function createContext(init: ContextInit): RunContext {
  return {
    runId: init.runId,
    blueprint: init.blueprint,
    inputs: init.inputs,
    secrets: init.secrets,
    vars: init.blueprint.vars ?? {},
    stepOutputs: {},
    env: init.env ?? {},
    scope: {},
    ...(init.approvals !== undefined ? { approvals: init.approvals } : {}),
    ...(init.signal !== undefined ? { signal: init.signal } : {}),
  };
}

/**
 * The rendering context for `{{ }}`.
 *
 * Rebuilt on every render rather than cached: `scope` and `stepOutputs` change as the run
 * progresses, and a stale context is the kind of bug that shows up as a wrong value, not a crash.
 * Loop variables are merged last; the executor refuses ones that would shadow a reserved name.
 */
export function templateContext(ctx: RunContext): Context {
  return {
    inputs: ctx.inputs,
    secrets: ctx.secrets,
    vars: ctx.vars,
    env: ctx.env,
    steps: ctx.stepOutputs,
    ...ctx.scope,
  };
}

/**
 * Validate and resolve caller inputs against the Blueprint's declared specs.
 *
 * @throws {BlueprintValidationError} a required input is missing.
 */
export function resolveInputs(
  blueprint: Blueprint,
  raw: Readonly<Record<string, unknown>> | undefined,
): Record<string, unknown> {
  const provided = { ...(raw ?? {}) };
  const resolved: Record<string, unknown> = {};

  for (const [name, spec] of Object.entries(blueprint.inputs ?? {})) {
    if (Object.prototype.hasOwnProperty.call(provided, name)) {
      resolved[name] = provided[name];
    } else if (hasDefault(spec)) {
      resolved[name] = spec.default;
    } else if (spec.required === true) {
      throw new BlueprintValidationError(
        `Missing required input '${name}' for Blueprint '${blueprint.name}'.`,
      );
    }
  }

  // Extra caller inputs pass through: a Blueprint need not declare every runtime variable.
  for (const [name, value] of Object.entries(provided)) {
    if (!Object.prototype.hasOwnProperty.call(resolved, name)) resolved[name] = value;
  }

  return resolved;
}

/**
 * The values behind a Blueprint's declared secret names.
 *
 * Caller-supplied only, by design: there is no environment and no `.env` on a device. Reading the
 * OS keychain is the *facade's* job (`@aetherius/react-native`, milestone 3-E) — it walks the
 * declared names through a `SecretResolver` and hands the result down here, exactly as Python's
 * `resolve_secrets` runs before the engine rather than inside it. An unresolved secret is
 * *omitted*: the template engine surfaces the error, at the step that actually reads it.
 */
export function resolveSecrets(
  _declared: readonly string[] | undefined,
  provided: Readonly<Record<string, string>> | undefined,
): Record<string, string> {
  // The declared list is taken but unused: it keeps this signature honest about what a caller must
  // have consulted, and lets the engine stay the one place that decides what lands in the context.
  return { ...(provided ?? {}) };
}

/** Python treats `default: null` as "no default"; the same rule decides here. */
function hasDefault(spec: InputSpec): boolean {
  return spec.default !== undefined && spec.default !== null;
}
