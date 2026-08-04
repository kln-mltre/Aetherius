/**
 * La version du moteur, exposee en valeur.
 *
 * Elle est **generee** depuis `package.json` au build (`scripts/compile-schema.mjs`), pour la meme
 * raison que les contrats inlines : un telephone n'a pas de checkout, et importer un JSON demanderait
 * une assertion de module que Hermes ne promet pas.
 *
 * Son seul consommateur est la livraison des Blueprints (jalon 3-F) : le manifeste porte une
 * contrainte `min_engine`, et une entree ecrite pour un moteur plus recent que celui installe est
 * **ignoree** au profit de l'embarque — les vieilles versions d'une application vivent longtemps.
 */

export { ENGINE_VERSION } from "./generated/schema-meta.js";
