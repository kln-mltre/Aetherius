/**
 * Interface de driver et contexte de run, miroir de `src/aetherius/core/driver.py` et
 * `src/aetherius/core/runtime/context.py`.
 *
 * Seule divergence structurelle assumee avec le moteur Python : tout est asynchrone. Le moteur
 * Python est synchrone de bout en bout (Playwright API sync, `time.sleep`, `confirm` bloquant) ;
 * sur appareil, rien ne peut bloquer la boucle JS. La semantique observable — ordre des steps,
 * evenements emis, forme du `Result` — reste identique.
 *
 * Le moteur (`RunEngine`, executeur de steps, flux) vit dans `runtime/` depuis le jalon 3-C ; le
 * driver WebView arrive au jalon 3-D, dans `@aetherius/react-native`.
 */

import type { ActName, Blueprint, StepModel } from "./blueprint/types.js";
import type { EventBus } from "./events/index.js";
import type { FetchLike } from "./http.js";

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
  /**
   * Table exposee par `{{ env.X }}`. Cote Python c'est `os.environ` ; un appareil n'en a pas, donc
   * elle est vide sauf si l'application en fournit une (docs/embedded.md).
   */
  readonly env: Readonly<Record<string, string>>;
  /** Variables de boucle injectees par `for_each`, le temps d'une iteration. */
  readonly scope: Record<string, unknown>;
}

/**
 * Ce que l'hote prete au moteur. Un seul service pour l'instant : `fetch`. Il est passe plutot que
 * capture au niveau module, parce que c'est ce qui rend l'Act I testable sans reseau — et parce
 * qu'une application peut vouloir le sien (interception, telemetrie, epinglage de certificat).
 */
export interface HostServices {
  readonly fetch?: FetchLike;
}

/** Fabrique un driver pour un act. Le registre vit dans `runtime/drivers.ts`. */
export type DriverFactory = (host: HostServices) => ActDriver;

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
