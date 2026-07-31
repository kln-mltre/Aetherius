/**
 * Resultat d'un run, miroir de `src/aetherius/core/runtime/result.py`.
 *
 * Le vocabulaire de statut est celui du moteur (`success`/`failed`/`partial`/`skipped`), pas celui
 * du daemon (`queued`/`running`/`succeeded`/`failed`) : le SDK `@aetherius/client` parle au daemon,
 * ce moteur-ci execute en direct.
 */

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
  /** ISO-8601 UTC. */
  readonly started_at: string;
  /** ISO-8601 UTC. */
  readonly finished_at: string;
}
