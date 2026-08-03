/**
 * `@aetherius/engine` — le moteur Aetherius embarque.
 *
 * Neutre plateforme : ce paquet ne connait ni React Native, ni Node. Il porte le coeur (modele de
 * Blueprint, runtime, extraction, evenements, erreurs) et l'Act I (Vector) sur `fetch`. L'Act II
 * (Continuum), qui a besoin d'une WebView, vit dans `@aetherius/react-native`.
 *
 * Etat (jalon 3-E) : un Blueprint `act: "vector"` s'execute reellement (jalon 3-C), l'Act II vit
 * dans `@aetherius/react-native` (jalon 3-D), et ce paquet porte desormais les coutures de la
 * surface applicative : rendez-vous d'approbation pour `confirm`, annulation d'un run, et le modele
 * d'erreur (`describeFailure`). La facade elle-meme est dans `@aetherius/react-native`, parce que
 * ses deux implementations par defaut — le trousseau et le modal — sont des faits de plateforme.
 * Voir docs/embedded.md.
 */

export * from "./acts/confirm.js";
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
export * from "./failure.js";
export * from "./http.js";
export * from "./result.js";
export * from "./runtime/approvals.js";
export * from "./runtime/cancel.js";
export * from "./runtime/context.js";
export * from "./runtime/drivers.js";
export * from "./runtime/engine.js";
export * from "./runtime/flow.js";
export * from "./runtime/steps.js";
export * from "./template.js";
