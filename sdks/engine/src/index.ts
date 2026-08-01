/**
 * `@aetherius/engine` — le moteur Aetherius embarque.
 *
 * Neutre plateforme : ce paquet ne connait ni React Native, ni Node. Il porte le coeur (modele de
 * Blueprint, runtime, extraction, evenements, erreurs) et l'Act I (Vector) sur `fetch`. L'Act II
 * (Continuum), qui a besoin d'une WebView, vit dans `@aetherius/react-native`.
 *
 * Etat (jalon 3-B) : on charge, valide et refuse un Blueprint, et les deux mini-langages sont la —
 * rendu d'expressions et extraction. Aucun step ne s'execute encore ; le runtime et l'Act I
 * arrivent au jalon 3-C. Voir docs/embedded.md.
 */

export * from "./blueprint/types.js";
export * from "./blueprint/capabilities.js";
export * from "./blueprint/contract.js";
export * from "./blueprint/loader.js";
export * from "./blueprint/portability.js";
export * from "./blueprint/schema.js";
export * from "./blueprint/validator.js";
export * from "./driver.js";
export * from "./errors.js";
export * from "./events/index.js";
export * from "./expr/index.js";
export * from "./extraction/index.js";
export * from "./result.js";
export * from "./template.js";
