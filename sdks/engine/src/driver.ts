/**
 * Interface de driver et contexte de run, miroir de `src/aetherius/core/driver.py` et
 * `src/aetherius/core/runtime/context.py`.
 *
 * Seule divergence structurelle assumee avec le moteur Python : tout est asynchrone. Le moteur
 * Python est synchrone de bout en bout (Playwright API sync, `time.sleep`, `confirm` bloquant) ;
 * sur appareil, rien ne peut bloquer la boucle JS. La semantique observable — ordre des steps,
 * evenements emis, forme du `Result` — reste identique.
 *
 * Squelette Phase 3 : le moteur (`RunEngine`, executeur de steps, flux) arrive au jalon 3-C
 * (docs/phase-3/3-c-vector.md), le driver WebView au jalon 3-D.
 */

import type { ActName, Blueprint, StepModel } from "./blueprint/types.js";
import type { EventBus } from "./events/index.js";

/** Applique le rendu d'expressions a une valeur (chaine, tableau ou objet). Jalon 3-B. */
export type Renderer = (value: unknown) => unknown;

/**
 * Etat partage d'un run. Les secrets y vivent resolus : ils ne doivent jamais franchir la frontiere
 * des evenements ni des journaux (cf. l'hygiene reproduite au jalon 3-E).
 */
export interface RunContext {
  readonly runId: string;
  readonly blueprint: Blueprint;
  readonly inputs: Readonly<Record<string, unknown>>;
  readonly secrets: Readonly<Record<string, string>>;
  readonly vars: Readonly<Record<string, unknown>>;
  /** Sorties indexees par identifiant de step, lues par `{{ steps.<id>.<champ> }}`. */
  readonly stepOutputs: Record<string, Record<string, unknown>>;
}

/**
 * Un Act est un driver interchangeable derriere cette interface — meme contrat que cote Python,
 * `Promise` en plus. `setup` charge la dependance lourde de l'Act (la WebView pour Continuum) ;
 * elle n'est jamais importee au niveau module, pour qu'un import du moteur reste leger.
 */
export interface ActDriver {
  readonly act: ActName;

  setup(ctx: RunContext): Promise<void>;
  teardown(ctx: RunContext): Promise<void>;
  runStep(
    step: StepModel,
    ctx: RunContext,
    bus: EventBus,
    render: Renderer,
  ): Promise<Record<string, unknown>>;
}
