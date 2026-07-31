/**
 * `@aetherius/engine` — le moteur Aetherius embarque.
 *
 * Neutre plateforme : ce paquet ne connait ni React Native, ni Node. Il porte le coeur (modele de
 * Blueprint, runtime, extraction, evenements, erreurs) et l'Act I (Vector) sur `fetch`. L'Act II
 * (Continuum), qui a besoin d'une WebView, vit dans `@aetherius/react-native`.
 *
 * Squelette Phase 3 : seules les interfaces sont posees. Voir docs/phase-3/README.md.
 */

export * from "./blueprint/types.js";
export * from "./driver.js";
export * from "./errors.js";
export * from "./events.js";
export * from "./result.js";
