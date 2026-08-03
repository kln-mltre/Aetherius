/**
 * Traduire une erreur du moteur en decision d'interface.
 *
 * Le reflexe repandu, dans les couches de service mobiles, est de tout rattraper et de rendre une
 * valeur vide. Le resultat est qu'**une source en panne et une reponse legitimement vide deviennent
 * indiscernables** : un ecran qui affiche « aucun resultat » peut masquer un service indisponible.
 * Le moteur, lui, leve des erreurs **typees** et ne decide pas a la place de l'application ; ce
 * module est le motif recommande pour les traduire, et il est livre plutot que decrit.
 *
 * Le pendant, qui est la moitie du sujet : **une reponse vide n'est pas une erreur**. Un run
 * `status: "success"` dont les `outputs` portent une liste vide a reellement trouve une liste vide,
 * et `describeFailure` rend `undefined` — il n'y a rien a traduire.
 *
 * La classification part de la hierarchie d'erreurs (`errors.ts`), jamais d'un message : le texte
 * d'une erreur est fait pour un humain, l'analyser serait construire un contrat sur de la prose.
 */

import {
  ActionError,
  AetheriusError,
  BlueprintError,
  DependencyError,
  ExtractionError,
  NetworkError,
  RunCancelledError,
  StatusAssertionError,
  StepTimeoutError,
  TemplateError,
} from "./errors.js";
import type { Result } from "./result.js";

/**
 * Ce qu'une application fait de l'echec. Chaque `kind` correspond a un ecran different — c'est le
 * critere qui a decide de la liste : deux erreurs qui appellent la meme reaction partagent un kind.
 */
export type FailureKind =
  /** Le Blueprint est faux, ou non portable sur cet appareil. Corriger et livrer ; ne pas reessayer. */
  | "blueprint"
  /** La source est injoignable : reseau, delai depasse, reprises epuisees. Reessayer a du sens. */
  | "unavailable"
  /** La source a repondu, mais pas comme le Blueprint l'exigeait (`expect`). */
  | "rejected"
  /** Un echec **nomme** par le Blueprint (`on_timeout: "fail:CODE"`) : `code` porte le nom. */
  | "blocked"
  /**
   * La page ou la reponse n'est pas celle que le Blueprint decrit : selecteur qui ne resout plus,
   * extraction vide, attente non nommee qui expire. Un Blueprint a corriger et a relivrer
   * (jalon 3-F) — pas un bug a remonter.
   */
  | "data"
  /**
   * Une expression n'a pas pu etre rendue : une variable absente (secret non fourni, entree
   * manquante) ou un filtre inconnu.
   *
   * Famille a part, et la sonde sur appareil a montre pourquoi : un secret que le trousseau ne
   * contient pas s'affichait « la page a change ». La page allait tres bien — c'est l'appelant qui
   * n'avait rien fourni, et les deux appellent des ecrans opposes (l'un dit « on s'en occupe »,
   * l'autre « saisis tes identifiants »).
   */
  | "config"
  /** L'appelant a annule. Il n'y a rien a afficher. */
  | "cancelled"
  /** Une piece de plateforme manque (aucune WebView montee, pas de `fetch`). */
  | "unsupported"
  /** Un bug : action non dispatchable, erreur inattendue. A remonter, pas a masquer. */
  | "engine";

export interface Failure {
  readonly kind: FailureKind;
  /** Le message du moteur. Destine a un journal ou a un rapport, pas a un ecran tel quel. */
  readonly message: string;
  /** Le nom de la classe d'erreur, pour un rapport de bug lisible. */
  readonly error: string;
  /** Le code nomme d'un `fail:CODE` (`LOGIN_FAILED`, …), quand il y en a un. */
  readonly code?: string;
  /** Rejouer le meme run a-t-il une chance d'aboutir ? */
  readonly retryable: boolean;
}

/**
 * Classe un echec, ou rend `undefined` quand il n'y en a pas.
 *
 * Accepte les deux canaux du moteur, parce qu'une application ne veut pas savoir lequel a parle :
 * un `Result` (echec propre, trace dans le run) ou une erreur levee (Blueprint refuse avant le
 * demarrage, dependance absente, bug enveloppe dans une `RunError`).
 */
export function describeFailure(subject: Result | unknown): Failure | undefined {
  const result = asResult(subject);
  if (result !== undefined) {
    if (result.status !== "failed") return undefined;
    if (result.cause !== undefined) return fromError(result.cause);
    // Un run echoue sans `cause` ne devrait pas exister ; le dire vaut mieux que rendre `undefined`
    // et faire croire a un succes.
    return {
      kind: "engine",
      message: result.error ?? "the run failed without naming a cause",
      error: "Error",
      retryable: false,
    };
  }
  if (subject instanceof Error) return fromError(subject);
  return undefined;
}

function fromError(error: Error): Failure {
  const base = { message: error.message, error: error.name };

  if (error instanceof RunCancelledError) return { ...base, kind: "cancelled", retryable: false };
  if (error instanceof BlueprintError) return { ...base, kind: "blueprint", retryable: false };
  if (error instanceof DependencyError) return { ...base, kind: "unsupported", retryable: false };
  if (error instanceof StepTimeoutError) {
    // Le code partage la famille en deux, et c'est la distinction utile a l'ecran : un Blueprint
    // qui a **nomme** son echec (`fail:LOGIN_FAILED`) sait ce qui s'est passe et l'application peut
    // l'afficher tel quel ; une attente qui expire sans nom veut seulement dire que la page n'est
    // pas celle qu'on decrivait — le meme diagnostic qu'une extraction qui ne trouve rien.
    return error.code !== undefined
      ? { ...base, kind: "blocked", code: error.code, retryable: false }
      : { ...base, kind: "data", retryable: false };
  }
  // Avant `NetworkError` : `TimeoutError` et `RetryExhaustedError` en heritent, et les trois disent
  // la meme chose a une application — la source n'a pas repondu.
  if (error instanceof NetworkError) return { ...base, kind: "unavailable", retryable: true };
  if (error instanceof StatusAssertionError) return { ...base, kind: "rejected", retryable: true };
  if (error instanceof ExtractionError) return { ...base, kind: "data", retryable: false };
  // Separee de `data` : une expression qui ne rend pas ne dit rien sur la source. Le cas dominant
  // est `StrictUndefined` — un secret ou une entree que personne n'a fournie.
  if (error instanceof TemplateError) return { ...base, kind: "config", retryable: false };
  if (error instanceof ActionError) return { ...base, kind: "engine", retryable: false };
  if (error instanceof AetheriusError) return { ...base, kind: "engine", retryable: false };
  return { ...base, kind: "engine", retryable: false };
}

function asResult(subject: unknown): Result | undefined {
  if (subject === null || typeof subject !== "object" || subject instanceof Error) return undefined;
  const candidate = subject as Partial<Result>;
  return typeof candidate.run_id === "string" && typeof candidate.status === "string"
    ? (subject as Result)
    : undefined;
}
