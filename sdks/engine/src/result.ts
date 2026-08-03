/**
 * Resultat d'un run, miroir de `src/aetherius/core/runtime/result.py`.
 *
 * Le vocabulaire de statut est celui du moteur (`success`/`failed`/`partial`/`skipped`), pas celui
 * du daemon (`queued`/`running`/`succeeded`/`failed`) : le SDK `@aetherius/client` parle au daemon,
 * ce moteur-ci execute en direct.
 */

import type { AetheriusError } from "./errors.js";

export type RunStatus = "success" | "failed" | "partial" | "skipped";

export interface StepResult {
  readonly step_id: string | null;
  readonly action: string;
  readonly status: RunStatus;
  readonly outputs: Readonly<Record<string, unknown>>;
  readonly error?: string;
  readonly duration_ms: number;
}

export interface Result {
  readonly run_id: string;
  readonly blueprint_name: string;
  readonly status: RunStatus;
  readonly outputs: Readonly<Record<string, unknown>>;
  readonly step_results: readonly StepResult[];
  readonly error?: string;
  /**
   * L'erreur typee derriere `error`. Seul ajout de ce moteur a la forme du `Result`.
   *
   * `error` est une chaine des deux cotes, et une chaine oblige une application a analyser de la
   * prose pour savoir si la source est en panne ou si le Blueprint est faux. Sur mobile c'est cette
   * distinction qui decide de l'ecran affiche, d'ou l'objet — lu par `describeFailure` (failure.ts).
   * Il ne survit pas a une serialisation JSON : c'est une valeur de processus, pas un champ de fil.
   */
  readonly cause?: AetheriusError;
  /** ISO-8601 UTC. */
  readonly started_at: string;
  /** ISO-8601 UTC. */
  readonly finished_at: string;
}
