/**
 * `Aetherius` — la facade applicative du moteur embarque.
 *
 * Elle se lit **exactement** comme le SDK daemon (`@aetherius/client`) : `client.run(blueprint,
 * { inputs, secrets, onEvent })`. Le choix d'architecture — embarquer un moteur ou piloter un
 * daemon — ne doit pas se voir dans le code appelant, sans quoi passer de l'un a l'autre voudrait
 * dire reecrire l'application.
 *
 * Ce qu'elle ajoute au `RunEngine`, et qui est precisement le sujet du jalon 3-E :
 *
 *   - **la resolution des secrets** : seuls les noms **declares** par le Blueprint sont demandes au
 *     resolver (le trousseau de l'OS par defaut), et une valeur passee a l'appel gagne — le meme
 *     ordre de priorite que `docs/secrets.md` cote Python ;
 *   - **l'hygiene** : les valeurs resolues sont masquees sur le chemin de sortie (evenements,
 *     message d'echec), parce qu'un `assert` rend son message et qu'une URL peut porter un secret ;
 *   - **le rendez-vous d'approbation** : `confirm` trouve une surface (le modal) au lieu de
 *     retomber sur son `on_timeout` ;
 *   - **l'annulation** : un controleur par run, plus `cancel(runId)` pour l'ecran qui n'a pas garde
 *     le sien.
 *
 * Deux canaux de sortie, comme `@aetherius/client` : un `Result` (echec de run trace dedans, avec sa
 * `cause` typee) et une exception (Blueprint refuse avant le demarrage, dependance absente, bug du
 * moteur). `describeFailure` accepte les deux, justement pour qu'une application n'ait pas a savoir
 * lequel a parle.
 */

import {
  RunEngine,
  hostAbortController,
  parseBlueprint,
  validateBlueprintData,
  type AbortControllerLike,
  type AbortSignalLike,
  type Blueprint,
  type FetchLike,
  type Result,
  type RunEventHandler,
  type Sink,
} from "@aetherius/engine";

import { defaultConfirmGateway, type ConfirmGateway } from "./confirm/gateway.js";
import { redactText, redactingSink, usable, type SecretResolver } from "./secrets/index.js";

/** Un Blueprint deja charge, son texte JSON, ou le document brut d'un `import`. */
export type BlueprintSource = Blueprint | string | Record<string, unknown>;

export interface AetheriusConfig {
  /** D'ou viennent les secrets. Sans resolver, seuls ceux passes a `run` sont disponibles. */
  readonly secrets?: SecretResolver;
  /** La surface de decision des `confirm`. Celle du modal par defaut. */
  readonly approvals?: ConfirmGateway;
  /** La table derriere `{{ env.X }}`. Un appareil n'a pas d'environnement : l'application decide. */
  readonly env?: Readonly<Record<string, string>>;
  /** Remplace le `fetch` de l'hote (interception, telemetrie, epinglage de certificat). */
  readonly fetch?: FetchLike;
  /**
   * Masquer les valeurs de secrets dans les evenements et les messages d'echec. Actif par defaut.
   *
   * Le desactiver n'a de sens qu'au debogage du moteur lui-meme, et se paie : un journal
   * d'application finit souvent ailleurs que sur l'appareil.
   */
  readonly redact?: boolean;
}

export interface RunOptions {
  readonly inputs?: Readonly<Record<string, unknown>>;
  /** Secrets fournis a l'appel. Ils **gagnent** sur ce que rend le resolver. */
  readonly secrets?: Readonly<Record<string, string>>;
  /** Appele pour chaque evenement, dans l'ordre. Le flux **est** l'interface de progression. */
  readonly onEvent?: RunEventHandler;
  /** Annule le run. `cancel(runId)` fait la meme chose depuis l'exterieur. */
  readonly signal?: AbortSignalLike;
  /** Impose l'identifiant du run — celui qu'un ecran a deja affiche, par exemple. */
  readonly runId?: string;
}

export class Aetherius {
  private readonly engine = new RunEngine();
  private readonly running = new Map<string, AbortControllerLike>();

  constructor(private readonly config: AetheriusConfig = {}) {}

  /**
   * Joue un Blueprint et rend son `Result`.
   *
   * @throws {BlueprintError} le document n'est pas un Blueprint valide, ou pas jouable ici.
   * @throws {DependencyError} une piece de plateforme manque (aucune WebView montee, une deja prise).
   * @throws {RunCancelledError} l'appelant avait deja annule avant le demarrage.
   * @throws {RunError} un bug du moteur — il ne se deguise jamais en run qui « n'a pas marche ».
   */
  async run(source: BlueprintSource, options: RunOptions = {}): Promise<Result> {
    const blueprint = toBlueprint(source);
    const secrets = await this.resolveSecrets(blueprint, options.secrets);
    const masked = this.config.redact === false ? [] : usable(Object.values(secrets));

    const runId = options.runId ?? newRunId();
    // Le signal de l'appelant et celui de la facade sont un seul evenement : `cancel(runId)` et un
    // ecran demonte doivent avoir le meme effet.
    const { signal, release } = this.track(runId, options.signal);

    try {
      const result = await this.engine.run(blueprint, {
        runId,
        inputs: options.inputs ?? {},
        secrets,
        sinks: this.sinks(options.onEvent, masked),
        approvals: this.config.approvals ?? defaultConfirmGateway,
        ...(signal !== undefined ? { signal } : {}),
        ...(this.config.env !== undefined ? { env: this.config.env } : {}),
        ...(this.config.fetch !== undefined ? { fetch: this.config.fetch } : {}),
      });
      return scrub(result, masked);
    } catch (error) {
      // Une exception aussi peut citer un secret : une URL interpolee dans un message de refus, par
      // exemple. Le rideau vaut pour les deux canaux ou il ne vaut rien.
      throw scrubError(error, masked);
    } finally {
      this.running.delete(runId);
      release();
    }
  }

  /**
   * Annule un run en cours. Rend `false` s'il est deja fini — ou si l'hote n'a pas d'`AbortController`.
   *
   * Un run annule est un run `failed` dont la `cause` est une `RunCancelledError` : pas de nouveau
   * statut. Ses drivers sont demontes, donc la WebView est liberee — sans quoi une vue cachee
   * survivrait a l'ecran qui l'a demandee.
   */
  cancel(runId: string): boolean {
    const controller = this.running.get(runId);
    if (controller === undefined) return false;
    controller.abort();
    return true;
  }

  /** Les runs en cours, dans leur ordre de demarrage. */
  active(): readonly string[] {
    return [...this.running.keys()];
  }

  /** Annule tout run en cours. Le pendant du `close()` du SDK daemon. */
  async close(): Promise<void> {
    for (const controller of [...this.running.values()]) controller.abort();
  }

  /**
   * Un signal pour ce run, relayant celui de l'appelant.
   *
   * Un hote sans `AbortController` n'a **pas** d'annulation plutot qu'une annulation qui ne
   * declenche rien — meme posture que le delai des requetes (`engine/src/acts/vector/client.ts`).
   */
  private track(
    runId: string,
    caller: AbortSignalLike | undefined,
  ): { signal: AbortSignalLike | undefined; release: () => void } {
    const Controller = hostAbortController();
    if (Controller === undefined) return { signal: caller, release: () => {} };

    const controller = new Controller();
    this.running.set(runId, controller);
    if (caller === undefined) return { signal: controller.signal, release: () => {} };

    if (caller.aborted) controller.abort();
    const forward = (): void => controller.abort();
    caller.addEventListener?.("abort", forward);
    // Le desabonnement compte : un appelant qui reutilise le meme signal pour plusieurs runs
    // accumulerait sinon un ecouteur — et le controleur d'un run fini — a chaque appel.
    return {
      signal: controller.signal,
      release: () => caller.removeEventListener?.("abort", forward),
    };
  }

  /**
   * Les valeurs des secrets **declares** par le Blueprint.
   *
   * Declares seulement : un Blueprint ne peut pas se servir dans le trousseau de l'application. Un
   * secret introuvable est *omis* — c'est le rendu qui signalera l'erreur, au step qui le lit
   * reellement, exactement comme cote Python.
   */
  private async resolveSecrets(
    blueprint: Blueprint,
    supplied: Readonly<Record<string, string>> | undefined,
  ): Promise<Record<string, string>> {
    const resolved: Record<string, string> = { ...(supplied ?? {}) };
    const resolver = this.config.secrets;
    if (resolver === undefined) return resolved;

    for (const name of blueprint.secrets ?? []) {
      if (Object.prototype.hasOwnProperty.call(resolved, name)) continue;
      const value = await resolver.resolve(name);
      if (value !== undefined) resolved[name] = value;
    }
    return resolved;
  }

  private sinks(handler: RunEventHandler | undefined, masked: readonly string[]): readonly Sink[] {
    if (handler === undefined) return [];
    const sink: Sink = { onEvent: handler };
    return [masked.length === 0 ? sink : redactingSink(sink, masked)];
  }
}

/**
 * Un document quelconque devient un Blueprint valide.
 *
 * Un objet deja valide repasse par la validation, et ce n'est pas un oubli : elle coute des
 * microsecondes (le schema est precompile) et supprime toute une classe de bugs ou l'on *croyait*
 * avoir valide. Une application importe le plus souvent un JSON, qui n'a jamais rien traverse.
 */
function toBlueprint(source: BlueprintSource): Blueprint {
  return typeof source === "string"
    ? parseBlueprint(source, "blueprint.json")
    : validateBlueprintData(source, "blueprint.json");
}

function scrub(result: Result, masked: readonly string[]): Result {
  if (masked.length === 0 || result.error === undefined) return result;
  // Le message de la `cause` est reecrit sur place : c'est notre objet, et une application qui le
  // journalise ne doit pas y trouver ce que le `Result` masque.
  if (result.cause !== undefined) result.cause.message = redactText(result.cause.message, masked);
  return { ...result, error: redactText(result.error, masked) };
}

function scrubError(error: unknown, masked: readonly string[]): unknown {
  if (masked.length === 0 || !(error instanceof Error)) return error;
  error.message = redactText(error.message, masked);
  return error;
}

/** Meme forme que celui du moteur : 32 caracteres hexadecimaux, avec un repli explicite. */
function newRunId(): string {
  const uuid = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto?.randomUUID?.();
  if (uuid !== undefined) return uuid.replace(/-/g, "");
  let out = "";
  for (let i = 0; i < 32; i += 1) out += Math.floor(Math.random() * 16).toString(16);
  return out;
}
