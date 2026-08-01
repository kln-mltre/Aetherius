/**
 * `@aetherius/engine` — le moteur Aetherius embarque.
 *
 * Neutre plateforme : ce paquet ne connait ni React Native, ni Node. Il porte le coeur (modele de
 * Blueprint, runtime, extraction, evenements, erreurs) et l'Act I (Vector) sur `fetch`. L'Act II
 * (Continuum), qui a besoin d'une WebView, vit dans `@aetherius/react-native`.
 *
 * Etat (jalon 3-C) : un Blueprint `act: "vector"` s'execute reellement — runtime asynchrone, flux,
 * garde `when`, utilitaires partages et requetes HTTP sur `fetch`. L'Act II arrive au jalon 3-D et
 * la facade applicative au jalon 3-E. Voir docs/embedded.md.
 */

export * from "./acts/shared.js";
export * from "./acts/vector/auth.js";
export * from "./acts/vector/client.js";
export * from "./acts/vector/cookies.js";
export * from "./acts/vector/driver.js";
export * from "./acts/vector/encode.js";
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
export * from "./http.js";
export * from "./result.js";
export * from "./runtime/context.js";
export * from "./runtime/drivers.js";
export * from "./runtime/engine.js";
export * from "./runtime/flow.js";
export * from "./runtime/steps.js";
export * from "./template.js";
