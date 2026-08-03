/**
 * Le bail sur l'unique WebView.
 *
 * Il y a **une** vue montee, donc **un** run Act II a la fois. Deux runs `continuum` concurrents
 * appelleraient chacun `configure()` sur le meme hote — le second remontant la vue sous le premier —
 * et le premier `teardown()` detruirait la vue que le second pilote encore. La panne est
 * silencieuse, et elle ressemble a un portail capricieux plutot qu'a une erreur de programmation :
 * d'ou un refus **bruyant**, avant que le second run demarre.
 *
 * L'Act I n'est pas concerne : deux runs `vector` ne partagent rien et restent concurrents.
 *
 * Module a part plutot que dans `registry.ts`, pour eviter un cycle d'import : le registre construit
 * le driver, le driver prend le bail.
 */

import { DependencyError } from "@aetherius/engine";

let holder: string | undefined;

/**
 * Reserve la vue pour *runId*.
 *
 * @throws {DependencyError} un autre run la detient.
 */
export function acquireWebViewHost(runId: string): void {
  if (holder !== undefined && holder !== runId) {
    throw new DependencyError(
      `Act II (Continuum) is already running for run '${holder}': a device has a single WebView, ` +
        "so 'continuum' Blueprints run one at a time. Await the first run, or cancel it " +
        "(RunOptions.signal), before starting another. Act I ('vector') runs stay concurrent.",
    );
  }
  holder = runId;
}

/** Rend la vue. Idempotent, et ne libere jamais le bail d'un autre run. */
export function releaseWebViewHost(runId: string): void {
  if (holder === runId) holder = undefined;
}

/** Le run qui detient la vue, s'il y en a un. */
export function webViewLease(): string | undefined {
  return holder;
}
