/**
 * La livraison des Blueprints (jalon 3-F) : socle embarque, surcouche distante, cache,
 * interrupteur d'arret. Et, depuis le jalon 3-H, le prefixe reserve sous lequel un manifeste a le
 * droit d'*ajouter* (`allowNew`). Voir `registry.ts`.
 */

export { CACHE_KEY, memoryCache } from "./cache.js";
export {
  MANIFEST_FORMAT,
  ManifestError,
  compareVersions,
  parseManifest,
  resolveUrl,
} from "./manifest.js";
export { BlueprintRegistry } from "./registry.js";
export { sha256Hex } from "./sha256.js";
export type {
  AllowNew,
  BlueprintCacheStore,
  BlueprintOrigin,
  BlueprintStatus,
  BundledBlueprint,
  CachedBlueprint,
  Manifest,
  ManifestEntry,
  RefreshEntry,
  RefreshOutcome,
  RefreshReport,
  RegistryConfig,
  ResolvedBlueprint,
} from "./types.js";
