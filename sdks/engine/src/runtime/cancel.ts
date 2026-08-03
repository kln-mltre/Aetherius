/**
 * Annulation d'un run — sans jumeau cote Python, et c'est assume.
 *
 * Le moteur Python tourne sur une machine : un run va au bout. Sur un telephone, un utilisateur qui
 * quitte un ecran ou une application mise en arriere-plan sont des evenements ordinaires, et un run
 * qui les ignore laisse vivre une WebView cachee que plus personne ne regarde. L'annulation est donc
 * un besoin de la plateforme, pas un raffinement.
 *
 * Le contrat est court : un run annule prend le chemin d'echec **propre** du moteur
 * (`RunCancelledError` herite d'`AetheriusError`), donc les drivers sont demontes et le `Result` est
 * rendu. On n'invente pas de statut : un run annule est un run `failed` dont la `cause` dit pourquoi
 * — `describeFailure` la traduit en `kind: "cancelled"`, ce qu'une UI traite comme « ne rien
 * afficher », pas comme une panne.
 *
 * Trois grains d'observation, et il en faut trois : entre deux steps (l'executeur), pendant une
 * attente (`wait`, le recul des reprises), et pendant une operation en vol (une requete, un appel a
 * la WebView). N'en tenir qu'un ferait attendre l'annulation jusqu'a trente secondes.
 */

import { RunCancelledError } from "../errors.js";
import type { AbortSignalLike } from "../http.js";

/** @throws {RunCancelledError} le signal est declenche. */
export function throwIfCancelled(signal: AbortSignalLike | undefined): void {
  if (signal?.aborted === true) throw new RunCancelledError("Run cancelled by the caller.");
}

/**
 * Attend *ms*, sauf annulation — qui leve immediatement.
 *
 * `wait` et le recul des reprises passent par la : un `wait` de trente secondes ne doit pas etre le
 * temps qu'il faut pour quitter un ecran.
 */
export function cancellableSleep(ms: number, signal?: AbortSignalLike): Promise<void> {
  throwIfCancelled(signal);
  if (ms <= 0) return Promise.resolve();

  return new Promise<void>((resolve, reject) => {
    const done = (): void => {
      clearTimeout(timer);
      signal?.removeEventListener?.("abort", onAbort);
    };
    const onAbort = (): void => {
      done();
      reject(new RunCancelledError("Run cancelled by the caller."));
    };
    const timer = setTimeout(() => {
      done();
      resolve();
    }, ms);
    signal?.addEventListener?.("abort", onAbort);
  });
}

/**
 * Rend le premier de *promise* ou de l'annulation.
 *
 * L'operation en vol n'est pas interrompue — une WebView ne sait pas rappeler un appel envoye — mais
 * son resultat est **abandonne**, et le demontage qui suit libere la vue. Attendre poliment
 * l'echeance de l'operation ferait durer une annulation aussi longtemps que le step qu'elle annule.
 */
export function raceCancel<T>(promise: Promise<T>, signal: AbortSignalLike | undefined): Promise<T> {
  if (signal === undefined || signal.addEventListener === undefined) return promise;
  throwIfCancelled(signal);

  return new Promise<T>((resolve, reject) => {
    const onAbort = (): void => {
      reject(new RunCancelledError("Run cancelled by the caller."));
    };
    signal.addEventListener?.("abort", onAbort);
    promise.then(resolve, reject).finally(() => {
      signal.removeEventListener?.("abort", onAbort);
    });
  });
}
