/**
 * L'action `confirm`, miroir de `SharedActionsMixin._confirm` (`src/aetherius/acts/_shared.py`).
 *
 * Elle gare le run jusqu'a une decision humaine, puis le reprend. Deux chemins, comme cote Python :
 *
 *   - **non surveille** (aucune passerelle sur le contexte) : la politique `on_timeout` s'applique
 *     tout de suite, sans jamais garer. C'est ce que fait une bibliotheque sans surface, et c'est le
 *     comportement que le corpus de conformance fige depuis le jalon 3-C ;
 *   - **surveille** : le run se gare sur un rendez-vous (`runtime/approvals.ts`), une surface decide,
 *     et le run repart. Le statut ne change pas — un run gare est un run `running`.
 *
 * Le defaut est **le refus**, et ce n'est pas de la prudence decorative : une application mise en
 * arriere-plan ne repondra jamais, donc le comportement sur doit etre celui qui arrive tout seul.
 *
 * Fichier a part plutot que dans `shared.ts` : c'est la seule action partagee qui a un cycle de vie
 * (ouvrir, attendre, fermer) et deux evenements a elle.
 */

import type { StepModel } from "../blueprint/types.js";
import type { Renderer, RunContext } from "../driver.js";
import { ActionError, StepTimeoutError } from "../errors.js";
import type { EventBus } from "../events/index.js";
import { createApprovalRequest, type ApprovalRequest, type Decision } from "../runtime/approvals.js";
import { throwIfCancelled } from "../runtime/cancel.js";
import { nowIso } from "../runtime/clock.js";

/**
 * Borne haute obligatoire d'un `confirm` gare (5 min), comme cote Python : un Blueprint peut la
 * raccourcir par `timeout_ms`, mais un run ne se gare jamais indefiniment.
 */
export const DEFAULT_CONFIRM_TIMEOUT_MS = 300_000;

export async function actionConfirm(
  step: StepModel,
  ctx: RunContext,
  bus: EventBus,
  render: Renderer,
): Promise<Record<string, unknown>> {
  const message = String(render(step["message"] ?? "") || "");
  const rawTitle = render(step["title"] ?? null);
  const title = rawTitle === null || rawTitle === "" ? undefined : String(rawTitle);
  const onTimeout = String(render(step["on_timeout"] ?? "reject") || "reject");
  const timeoutMs = milliseconds(
    render(step["timeout_ms"] ?? DEFAULT_CONFIRM_TIMEOUT_MS),
    "confirm: 'timeout_ms'",
  );

  // `channel`/`target`/`config`/`level` sont lus par le schema mais sans effet ici : le moteur
  // embarque n'a pas de couche de notification (meme raison que le refus de `notify` — l'application
  // possede deja les siennes, et sur un telephone la surface de decision est le modal, pas une
  // alerte qui pointerait vers lui).

  const gateway = ctx.approvals;
  if (gateway === undefined) return applyTimeout(onTimeout, message);

  const request = createApprovalRequest(ctx.runId, message, {
    ...(step.id !== undefined ? { stepId: step.id } : {}),
    ...(title !== undefined ? { title } : {}),
    timeoutMs,
  });

  let decision: Decision | null;
  const rendezvous = gateway.open(request);
  try {
    emit(bus, ctx, step, "input_requested", message, "warning", {
      token: request.token,
      title: title ?? null,
      timeout_ms: timeoutMs,
    });
    decision = await rendezvous.wait(ctx.signal);
  } finally {
    // Toujours, y compris a l'annulation : une demande laissee ouverte ferait croire a une surface
    // qu'un run l'attend encore.
    gateway.close(request);
  }

  // Une annulation libere l'attente sans decider : la traiter comme une expiration ferait passer le
  // run pour un refus reussi, alors que plus personne ne le regarde.
  throwIfCancelled(ctx.signal);

  if (decision === null) {
    emitProvided(bus, ctx, step, request, false, "timeout");
    return applyTimeout(onTimeout, message);
  }

  emitProvided(bus, ctx, step, request, decision.approved, decision.decidedBy);
  return {
    approved: decision.approved,
    decision: decision.approved ? "approved" : "rejected",
    value: decision.value ?? null,
    decided_by: decision.decidedBy ?? null,
  };
}

/**
 * Traduit la politique `on_timeout` en issue de step (refus par defaut).
 *
 * `fail:CODE` leve avec le code nomme (meme convention que `wait_for`) ; `approve` laisse passer ;
 * tout le reste — dont le defaut `reject` — refuse **sans faire echouer le run**, de sorte que le
 * step sensible garde par son `when` est simplement saute.
 */
function applyTimeout(onTimeout: string, message: string): Record<string, unknown> {
  if (onTimeout.startsWith("fail:")) {
    const code = onTimeout.slice("fail:".length);
    throw new StepTimeoutError(
      `confirm timed out awaiting a decision: ${JSON.stringify(message)}`,
      code === "" ? undefined : code,
    );
  }
  const approved = onTimeout === "approve";
  return {
    approved,
    decision: approved ? "approved" : "rejected",
    value: null,
    decided_by: "timeout",
  };
}

function emitProvided(
  bus: EventBus,
  ctx: RunContext,
  step: StepModel,
  request: ApprovalRequest,
  approved: boolean,
  decidedBy: string | undefined,
): void {
  const verb = approved ? "approved" : "rejected";
  emit(bus, ctx, step, "input_provided", `confirm: ${verb} by ${decidedBy ?? "unknown"}`, "info", {
    token: request.token,
    approved,
    decided_by: decidedBy ?? null,
  });
}

function emit(
  bus: EventBus,
  ctx: RunContext,
  step: StepModel,
  type: "input_requested" | "input_provided",
  message: string,
  level: "info" | "warning",
  data: Record<string, unknown>,
): void {
  bus.emit({
    run_id: ctx.runId,
    ts: nowIso(),
    type,
    ...(step.id !== undefined ? { step_id: step.id } : {}),
    level,
    message,
    data,
  });
}

function milliseconds(value: unknown, field: string): number {
  const ms = Number(value);
  if (!Number.isFinite(ms)) {
    throw new ActionError(`${field} must be a number, got ${JSON.stringify(value)}.`);
  }
  return ms;
}
