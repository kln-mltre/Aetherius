/**
 * Flux d'evenements, miroir de `src/aetherius/core/events/`.
 *
 * Le contrat de fil est `contracts/events.schema.json` : le moteur embarque emet exactement les
 * memes types que le moteur Python, pour qu'une meme UI puisse consommer les deux. Les types lies
 * aux couches hors perimetre restent declares (le contrat les definit) mais ne sont jamais emis.
 *
 * Squelette Phase 3 : l'implementation du bus et des sinks arrive au jalon 3-A
 * (docs/phase-3/3-a-socle-ts.md).
 */

export type RunEventType =
  | "progress"
  | "step_started"
  | "step_finished"
  | "step_skipped"
  | "debug"
  | "artifact"
  | "error"
  | "done"
  | "input_requested"
  | "input_provided";

export type EventLevel = "debug" | "info" | "warning" | "error";

export interface RunEvent {
  readonly run_id: string;
  /** ISO-8601 UTC. */
  readonly ts: string;
  readonly type: RunEventType;
  readonly step_id?: string;
  readonly level?: EventLevel;
  readonly message?: string;
  readonly data?: Readonly<Record<string, unknown>>;
}

export type RunEventHandler = (event: RunEvent) => void;

/**
 * Un sink consomme le flux. Comme cote Python, une exception levee par un sink est journalisee et
 * avalee : un consommateur defaillant ne casse jamais un run.
 */
export interface Sink {
  onEvent(event: RunEvent): void;
}

/** Diffuse un evenement a tous les sinks enregistres. Implementation : jalon 3-A. */
export interface EventBus {
  emit(event: RunEvent): void;
  register(sink: Sink): void;
}
